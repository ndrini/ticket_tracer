"""
Il formato della risposta del modello, imposto invece che sperato.

PERCHE' ESISTE. Fino a ieri si chiedeva al modello di COPIARE le righe prodotto
e si interpretava la risposta con espressioni regolari. Funzionava finche' il
modello rispondeva come ci si aspettava — e ha smesso di funzionare appena e'
cambiato il motore che lo esegue.

Misurato su una passata GPU di 316 scontrini (vLLM, Qwen2.5-3B float16) contro
la stessa pipeline in locale (Ollama, stesso modello quantizzato Q4):

  - l'84% delle risposte conteneva la lista dei prodotti RIPETUTA due volte,
    preceduta da un commento ("Ho riportato le righe come richiesto:"). La
    somma usciva esattamente doppia: 20,36 su uno scontrino da 10,18;
  - molte risposte RIORGANIZZAVANO invece di copiare, mettendo i nomi in un
    elenco e i prezzi in un altro ("Righe prezzo: 1 0,86 / 2 2,75"). Nessuna
    riga portava nome e prezzo insieme, e il filtro le scartava tutte.

Gli scontrini che quadrano sono crollati dal 28% al 3%, e non per un difetto
del codice: per il formato della risposta. Un'istruzione nel prompt e' una
speranza; uno schema passato al decoder e' un vincolo, e il modello non puo'
produrre token che lo violino.

COSA SEPARA DA COSA. Qui sta solo il CONTRATTO: quali campi, di che tipo, con
quali invarianti. Chi formula la domanda (`estrattore.py`) e chi la esegue
(Ollama in locale, vLLM sul kernel) non si conoscono fra loro e non conoscono
le regex: entrambi dipendono da questo schema. Cambiare motore non deve piu'
cambiare il modo di leggere la risposta.

IL TOTALE PUO' ESSERE `null`, ED E' UNA SCELTA. Quando lo scontrino non lo
dichiara in modo leggibile, il modello deve poter dire "non c'e'" invece di
inventare un numero: 25 totali su 218 erano inventati, e il danno non restava
li' perche' il totale filtra i prezzi impossibili.

⚠️ Un totale STIMATO non va in questo campo. `total` e' il giudice: e' il
numero che lo scontrino dichiara, e serve a verificare che la somma dei
prodotti torni. Riempirlo con una stima ricavata dai prodotti stessi farebbe
confrontare un numero con se' stesso, e il controllo quadrerebbe sempre. Una
stima e' un dato diverso, con un nome diverso e un campo diverso.
"""

import re

# Un importo come lo stampa uno scontrino: due decimali, virgola o punto.
IMPORTO_NEL_TESTO = re.compile(r"-?\d{1,5}[.,]\d{2}")

# Nome del campo che porta il totale dichiarato dallo scontrino. Estratto in
# una costante perche' lo usano lo schema, il kernel e i test.
CAMPO_TOTALE = "total"

# Lo schema JSON della risposta. E' il formato accettato sia da vLLM
# (`guided_json` / `structured_outputs`) sia da Ollama (parametro `format`),
# quindi i due percorsi possono imporre lo STESSO contratto.
SCHEMA_SCONTRINO = {
    "type": "object",
    "properties": {
        "shop_name": {
            "type": ["string", "null"],
            "description": "Nome del negozio, senza indirizzo ne' partita IVA",
        },
        CAMPO_TOTALE: {
            # `null` e' ammesso apposta: vedi il docstring del modulo.
            "type": ["number", "null"],
            "description": (
                "Il totale STAMPATO sullo scontrino. null se non e' leggibile: "
                "non calcolarlo e non stimarlo"
            ),
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                },
                "required": ["name", "price"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["shop_name", CAMPO_TOTALE, "items"],
    "additionalProperties": False,
}


def prompt_scontrino(testo):
    """
    La domanda unica, ora che la risposta e' vincolata dallo schema.

    Prima le domande erano tre (negozio, totale, prodotti) perche' una sola
    risposta libera con tre informazioni dentro era troppo fragile da
    interpretare. Con lo schema il problema non si pone, e una domanda sola
    costa un solo prefill invece di tre.

    IL TESTO PRIMA DELLA DOMANDA, non dopo: la cache di prefisso riusa il
    lavoro fatto sui token iniziali, e mettere prima la parte che cambia la
    invaliderebbe a ogni scontrino. Misurato in locale: 28,0 s contro 0,8 s
    sulla seconda chiamata.
    """
    return (
        "SCONTRINO:\n"
        f"{testo}\n\n"
        "Estrai i dati di questo scontrino.\n"
        "Copia i nomi dei prodotti ESATTAMENTE come sono scritti.\n"
        # NON si spiega al modello quale importo prendere. Provato: "se una riga
        # ha DUE importi prendi l'ULTIMO" ha peggiorato le cose, perche' il
        # modello ha cominciato a prendere per prezzo i numeri dentro il NOME
        # ("ESTAC.CONSUM 250" -> price 250.00, somma 258,46 su uno scontrino da
        # 10,18). La distinzione fra prezzo unitario e importo di riga e'
        # GEOMETRICA — sta nelle colonne — e si risolve nel codice, non nel
        # prompt: vedi `prezzo_di_riga` sotto.
        "Non includere righe di riepilogo: totale, IVA, resto, contante.\n"
        "Il totale e' quello STAMPATO sullo scontrino: se non lo leggi, "
        "rispondi null. Non calcolarlo sommando i prodotti."
    )


def _compare_nel_testo(prezzo, testo):
    """L'importo e' STAMPATO da qualche parte sullo scontrino?

    Un prezzo che nel testo non compare non e' stato letto: e' stato generato.
    Misurato su una passata GPU di 316 scontrini, il 9% dei prezzi estratti non
    esisteva nel testo — numeri di telefono presi per importi ("TELEFONO VIA
    LAIETANA" -> 651.317.190), grammature ("PA LLESCAT 490GR" -> 490,00),
    cifre inventate di sana pianta. Uno scontrino da 2,53 sommava 651 milioni.
    """
    if prezzo is None or not testo:
        return False
    for trovato in IMPORTO_NEL_TESTO.findall(testo):
        if abs(prezzo - float(trovato.replace(",", "."))) < 0.005:
            return True
    return False


def prezzo_di_riga(nome, prezzo, testo_scontrino):
    """
    Il prezzo che fa somma per questa riga, corretto se il modello ha preso
    quello unitario.

    PERCHE' NEL CODICE E NON NEL PROMPT. Una riga come

        2 4 ESTAC.CONSUM 250 0,86 1,72

    porta due importi: 0,86 e' quanto costa una unita', 1,72 e' quanto si paga
    per la riga. E' il secondo che entra nel totale. Chiederlo al modello e'
    stato provato e ha peggiorato: ha iniziato a scambiare per prezzi i numeri
    contenuti nei nomi ("ESTAC.CONSUM 250" -> 250,00). Qui invece si guarda il
    testo dello scontrino, che e' un dato, non una generazione.

    Si corregge SOLO quando la riga e' identificabile senza ambiguita' e porta
    davvero due importi dopo il nome. Negli altri casi si lascia quello che il
    modello ha detto: meglio un dato dubbio dichiarato che una correzione
    d'ufficio sbagliata.
    """
    if not nome or prezzo is None or not testo_scontrino:
        return prezzo

    ago = nome.strip().casefold()
    candidate = [r for r in testo_scontrino.split("\n") if ago in r.casefold()]
    if len(candidate) != 1:
        # Il nome non individua una riga sola: non si sa quale riga guardare, e
        # una correzione a caso sarebbe peggio del dato dubbio. Resta pero' un
        # controllo che non richiede la riga: un prezzo che nello scontrino non
        # compare AFFATTO non e' stato letto, e' stato generato.
        if not _compare_nel_testo(prezzo, testo_scontrino):
            return None
        return prezzo
    # Gli importi che seguono il nome sulla riga: solo quelli con due decimali,
    # cosi' "250" dentro il nome non conta come prezzo.
    coda = candidate[0].casefold().split(ago, 1)[1]
    importi = re.findall(r"-?\d{1,4}[.,]\d{2}", coda)
    if not importi:
        # La riga non porta nessun importo: il numero viene dal nome (una
        # grammatura, un numero di telefono). Se non e' stampato altrove nello
        # scontrino non e' un prezzo.
        if not _compare_nel_testo(prezzo, testo_scontrino):
            return None
        return prezzo
    valori = [float(v.replace(",", ".")) for v in importi]
    ultimo = valori[-1]
    # Il prezzo di riga e' l'ULTIMO importo. Si sostituisce quando il modello
    # ha preso un altro numero della riga (tipicamente il prezzo unitario) o un
    # numero che sulla riga non e' un importo affatto: "ESTAC.CONSUM 250" gli ha
    # fatto restituire 250,00, che e' parte del NOME. In entrambi i casi
    # l'importo giusto e' misurato dal testo, non generato.
    # Il prezzo deve essere uno degli importi STAMPATI sulla riga. Se non lo e',
    # il modello l'ha preso altrove — tipicamente da un numero dentro il nome:
    # "1 4 ESTAC.CONSUM 250 0,86" gli ha fatto restituire 250,00, e la somma di
    # quello scontrino usciva 285,42 contro un totale di 38,50.
    if not any(abs(prezzo - v) < 0.005 for v in valori):
        # Il numero non e' un importo di questa riga: viene dal nome (una
        # grammatura, un codice). La riga pero' e' individuata con certezza e
        # un importo ce l'ha, quindi quello e' il prezzo — non si scarta il
        # prodotto quando il dato giusto e' li' accanto, misurabile.
        return ultimo
    # Fra due importi vince l'ultimo: il primo e' il prezzo di UNA unita'
    # ("2 4 ESTAC.CONSUM 250 0,86 1,72" sono due pezzi da 0,86 che fanno 1,72).
    if any(abs(prezzo - v) < 0.005 for v in valori[:-1]):
        return ultimo
    return prezzo


def normalizza(risposta, testo_scontrino=None):
    """
    La risposta del modello, ridotta alla forma che la pipeline si aspetta.

    Lo schema garantisce i tipi, non il buon senso: un modello puo' comunque
    ripetere lo stesso prodotto o restituire un prezzo negativo. Qui si tolgono
    solo le cose che sono certamente sbagliate, e si segnala il resto altrove.

    I DUPLICATI SI SCARTANO. La stessa coppia (nome, prezzo) ripetuta e' quasi
    sempre il modello che ricopia la lista due volte, non due unita' dello
    stesso articolo: quelle lo scontrino le stampa con la quantita' ("2 PANET
    1,10 2,20"), non con due righe identiche. Misurato: senza questo scarto la
    somma usciva doppia sull'84% degli scontrini di una passata GPU.
    """
    if not isinstance(risposta, dict):
        return {"shop_name": None, CAMPO_TOTALE: None, "items": []}

    prodotti, viste = [], set()
    for voce in risposta.get("items") or []:
        if not isinstance(voce, dict):
            continue
        nome = (voce.get("name") or "").strip()
        prezzo = voce.get("price")
        if not nome or prezzo is None:
            continue
        prezzo = prezzo_di_riga(nome, float(prezzo), testo_scontrino)
        if prezzo is None:
            # Prezzo inventato: si scarta la riga invece di correggerla a caso.
            # Lo scontrino risultera' SOMMA_IN_DIFETTO, cioe' un buco
            # dichiarato, e non VALIDO per un numero che nessuno ha letto.
            continue
        chiave = (nome.casefold(), round(float(prezzo), 2))
        if chiave in viste:
            continue
        viste.add(chiave)
        prodotti.append({"name": nome[:80], "price": round(float(prezzo), 2)})

    negozio = risposta.get("shop_name")
    totale = risposta.get(CAMPO_TOTALE)
    return {
        "shop_name": negozio.strip()[:80] if isinstance(negozio, str) else None,
        CAMPO_TOTALE: round(float(totale), 2) if isinstance(totale, (int, float)) else None,
        "items": prodotti,
    }
