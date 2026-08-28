"""
Cosa conta come prodotto: gli ADDENDI del totale.

LA DEFINIZIONE, data dall'utente il 2026-08-25 e adottata come contratto:

    Un prodotto e' cio' che determina un prezzo atomico sullo scontrino, cioe'
    cio' che fa apparire una riga con un importo che entra nella somma.

Un armadio IKEA fatto di viti, pannelli e istruzioni e' UN prodotto da 200 EUR:
le viti e i pannelli non lo sono, lo e' l'insieme, perche' e' l'insieme a
produrre l'addendo. Trecentottantanove grammi di arance sono UN prodotto,
perche' il peso e il prezzo al chilo insieme determinano un importo che si
sommera' agli altri.

PERCHE' CAMBIA L'APPROCCIO. Tutti i tentativi precedenti guardavano il NOME:
parole di riepilogo (`NON_PRODOTTO`), "almeno tre lettere di fila", "piu'
lettere che cifre". Sono tutti falliti, e in modo istruttivo:

  - il vecchio filtro scartava prodotti veri (`TRUITA PATATA`, `BASE
    PROTECTORA`) e NON prendeva i codici (`Art/ EA 39151700`);
  - la regola "piu' cifre che lettere", misurata prima di applicarla, avrebbe
    tolto 8 casi dall'eccesso ma rotto 3 scontrini che quadravano e mandato 7 a
    zero prodotti — bilancio negativo. Scartava `SAMARRETA-0483123 3,49`, che
    e' una maglietta vera col codice nel nome.

Il nome non e' il criterio. **La posizione dell'importo lo e'**: un numero che
cade nella colonna che somma, sopra il riepilogo, e' un addendo qualunque cosa
ci sia scritto accanto; un numero fuori da quella colonna non lo e' nemmeno se
ha un bel nome. E' una proprieta' misurabile sulla carta, non un'euristica sul
testo.

QUESTO MODULO NON SCARTA NIENTE. Dice quali importi sono addendi; chi lo usa
decide cosa farne. La separazione e' la stessa di `geometria.py`: qui la
misura, altrove il giudizio.
"""
from app.etl.geometria import (INIZIO_RIEPILOGO, altezza_riga, centro_x,
                               centro_y, colonna_dei_prezzi, valore)


def confine_somma(righe_ocr, altezza=None):
    """
    La y sotto la quale gli importi non sono piu' addendi.

    Diversa da `geometria.confine_riepilogo`, e per un motivo misurato.
    Quella cerca il primo marcatore SOTTO la meta' dello scontrino, perche' in
    cima compaiono intestazioni ("IMPORT") che non chiudono nulla. Ma su uno
    scontrino con la coda lunga — IKEA stampa mezza pagina di condizioni di
    reso — la meta' cade sotto il totale, e il marcatore vero viene ignorato:
    misurato su 289 scontrini, succede in 24 casi, l'8%.

    Qui si prende il PRIMO marcatore che abbia almeno un importo sopra di se':
    un riepilogo che non chiude nessun prodotto non e' un riepilogo, e'
    un'intestazione. Non dipende da dove cade la meta' del foglio.
    """
    if not righe_ocr:
        return float("inf")
    if altezza is None:
        altezza = altezza_riga(righe_ocr)

    importi_y = sorted(centro_y(r["box"]) for r in righe_ocr
                       if valore(r["testo"]) is not None)
    if not importi_y:
        return float("inf")

    marcatori = sorted(centro_y(r["box"]) for r in righe_ocr
                       if len(r["testo"]) <= 34 and INIZIO_RIEPILOGO.search(r["testo"]))
    for y in marcatori:
        # Il marcatore deve chiudere qualcosa: sopra di lui devono esserci
        # importi, altrimenti e' l'intestazione della colonna ("IMPORT").
        if any(iy < y - 0.5 * altezza for iy in importi_y):
            return y - 0.5 * altezza
    return float("inf")


# Un addendo negativo non e' merce: e' uno sconto, una promozione, un reso.
# Misurato: 19 addendi su 1790 (1,1%), su 16 scontrini.
#
# ⚠️ DEBITO DICHIARATO, con la via d'uscita. Per ora lo sconto entra nella somma
# come una riga a se', e il giudice aritmetico continua a quadrare. Ma non e'
# cio' che dovrebbe finire nel database: uno sconto del 10% e' una riduzione su
# OGNI prodotto, e "DESCOMPTE 10% -4,51" e' solo la somma di quelle riduzioni.
# Trattarlo come un prodotto falsera' la fase F, la categorizzazione: chiedere
# "quanto spendo in frutta" dara' un numero troppo alto, perche' lo sconto sulla
# frutta sta in una riga che frutta non e'.
#
# La ripartizione e' rimandata, non scartata, e non e' una stima: distribuendo
# lo sconto sui prodotti in proporzione, la somma DEVE tornare al totale, quindi
# la correttezza si verifica invece di sperarla. Deciso con l'utente il
# 2026-08-25: prima si chiude la quadratura, poi si ripartisce.
#
# I RESI SONO UN'ALTRA COSA e non vanno confusi con gli sconti: `325c72d0d73c`
# (Decathlon, quantita' -1) e `379ce162b193` (IKEA, tre `Devolucio`) sono
# restituzioni, cioe' scontrini interi col segno rovesciato. Vedi
# docs/46_campione_validato_a_mano.md.


def e_sconto(prezzo):
    """L'addendo e' una riduzione invece che merce?

    Il segno basta: sullo scontrino un importo negativo nella colonna che somma
    e' uno sconto, una promozione o un reso. Chi costruisce il catalogo prodotti
    deve saperlo, per non creare un articolo chiamato "DESCOMPTE 10%".
    """
    return prezzo is not None and prezzo < 0


def addendi(righe_ocr):
    """
    Gli importi che entrano nella somma, dall'alto in basso.

    Restituisce una lista di (valore, y): il valore e' l'addendo, la y serve a
    chi deve associarlo alla riga che lo descrive.

    Due condizioni, entrambe geometriche:

      1. l'importo cade nella COLONNA che somma — quella dei prezzi di riga,
         non quella dei prezzi unitari, che sommati conterebbero due volte;
      2. sta SOPRA il riepilogo — sotto ci sono totale, IVA, contante e resto,
         che addendi non sono.
    """
    if not righe_ocr:
        return []
    altezza = altezza_riga(righe_ocr)
    colonna = colonna_dei_prezzi(righe_ocr, altezza)
    if colonna is None:
        return []
    x_min, x_max = colonna
    confine = confine_somma(righe_ocr, altezza)

    trovati = []
    for r in righe_ocr:
        v = valore(r["testo"])
        if v is None:
            continue
        x, y = centro_x(r["box"]), centro_y(r["box"])
        if x_min <= x <= x_max and y < confine:
            trovati.append((v, x, y))
    trovati.sort(key=lambda t: t[2])
    return _senza_ricapitolazione(_uno_per_riga(trovati, altezza))


# Tolleranza del confronto fra somme, la stessa del giudice aritmetico.
TOLLERANZA_SOMMA = 0.02


def _uno_per_riga(trovati, altezza):
    """
    Di piu' importi sulla STESSA riga fisica tiene solo il piu' a destra.

    PERCHE'. Consum e Charter stampano il prezzo unitario e il totale di riga
    accanto: "3 LLET SEN.CONSUM 1L   0.94   2,82", dove 2,82 = 0,94 x 3.
    Le due cifre stanno in colonne diverse ma sulla stessa riga, e
    `colonna_dei_prezzi` — che tollera l'imprecisione dei riquadri allargandosi
    di un'altezza per parte — le contiene entrambe. Sommandole si conta due
    volte: su `83b3fef9222c` la somma usciva 12,17 contro un totale di 11,23,
    ossia esattamente +0,94.

    Che `addendi()` dovesse escludere i prezzi unitari era gia' scritto nel suo
    docstring ("che sommati conterebbero due volte"): mancava il modo di
    distinguerli, perche' la colonna da sola non basta.

    Si tiene il piu' a DESTRA perche' e' li' che i negozi stampano il totale di
    riga. Misurate tre regole — il piu' a destra, il piu' grande, il piu' a
    destra solo se multiplo dell'altro — danno lo STESSO risultato su 218
    scontrini (117 quadrati, 3 regressioni). Fra tre regole equivalenti si
    sceglie quella che guarda solo la geometria e mai i valori: non puo'
    essere ingannata da un prezzo che per caso e' multiplo di un altro.

    Misurato:  quadrano 111 -> 117, regressioni 6 -> 3.
    """
    if not trovati:
        return []
    gruppi = [[trovati[0]]]
    for t in trovati[1:]:
        # Stessa riga fisica: l'OCR colloca a y leggermente diverse i frammenti
        # che sulla carta sono allineati.
        if abs(t[2] - gruppi[-1][-1][2]) < 0.5 * altezza:
            gruppi[-1].append(t)
        else:
            gruppi.append([t])
    scelti = []
    for g in gruppi:
        v, _, y = max(g, key=lambda t: t[1])
        scelti.append((v, y))
    return scelti


def _senza_ricapitolazione(trovati):
    """
    Toglie l'ultimo addendo quando vale la somma di tutti i precedenti.

    PERCHE'. Molti scontrini stampano il totale DUE volte: una in fondo
    all'elenco, prima del riepilogo, e una sotto, accanto alla parola. Il primo
    esemplare cade sopra il confine, entra fra gli addendi, e la somma esce
    ESATTAMENTE DOPPIA: su `8fbdc7a3f4e5` 18,44 contro un totale di 9,22, su
    `a0b224079745` 37,58 contro 18,79. Il doppio esatto e' la firma del difetto.

    Perche' non si guarda il totale. La regola ovvia sarebbe "togli l'ultimo
    addendo se e' uguale al totale", e misurata fa 112 quadrati contro i 111 di
    questa. Un caso in piu', pagato pero' con una CIRCOLARITA': il totale e' il
    giudice della somma, e usarlo per decidere cosa sommare significa
    aggiustare la risposta con la soluzione. Un giudice che sceglie gli imputati
    non assolve nessuno.

    Questa formulazione guarda solo la lista degli addendi: se l'ultimo vale la
    somma dei precedenti e' una ricapitolazione, qualunque cosa dica il totale.
    Vale anche quando il totale manca o e' sbagliato — cioe' proprio nei casi in
    cui serve di piu'.

    Misurato su 218 scontrini:  quadrano 104 -> 111, regressioni 9 -> 6.
    """
    if len(trovati) < 2:
        return trovati
    somma_precedenti = round(sum(v for v, _ in trovati[:-1]), 2)
    if abs(trovati[-1][0] - somma_precedenti) <= TOLLERANZA_SOMMA:
        return trovati[:-1]
    return trovati


def e_addendo(prezzo, righe_ocr, tolleranza=0.005):
    """
    Questo prezzo e' uno degli addendi dello scontrino?

    Serve a chi ha in mano un prodotto estratto dal modello e deve sapere se il
    suo importo sia davvero una riga della somma o un numero raccolto altrove —
    un codice d'articolo, una grammatura, un prezzo unitario.

    Non guarda il nome. Un prodotto puo' chiamarsi `SAMARRETA-0483123`: se il
    suo importo e' un addendo, e' merce.
    """
    if prezzo is None:
        return False
    return any(abs(prezzo - v) <= tolleranza for v, _ in addendi(righe_ocr))
