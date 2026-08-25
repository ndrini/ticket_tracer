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
        "Non includere righe di riepilogo: totale, IVA, resto, contante.\n"
        "Il totale e' quello STAMPATO sullo scontrino: se non lo leggi, "
        "rispondi null. Non calcolarlo sommando i prodotti."
    )


def normalizza(risposta):
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
