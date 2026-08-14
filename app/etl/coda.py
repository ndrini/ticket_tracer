"""
Separa il corpo dello scontrino (i prodotti) dalla sua coda (totali, pagamento,
resto, IVA, saluti).

NASCE DA UNA MISURA. Su 30 scontrini elaborati, 25 non quadravano: di questi 21
avevano la somma dei prodotti MAGGIORE del totale stampato. Il modello non
perdeva righe, ne prendeva di troppo. Un caso reale: 12 prodotti estratti
correttamente (totale 36,69) piu' "€*TOT_ 36.69", "EFECTIVO_ 50.00" e
"€CAMILO_ 13.31", per una somma di 126,20.

PERCHE' LE PAROLE NON BASTANO. Il filtro esistente cerca parole intere
(`\btotal\b`, `\befectivo\b`), ma l'OCR le restituisce storpiate: "SUBIOLAL",
"CAM8IO", "IMPORIO PAGAIO", "€*TOT_", "Bonificacton". Un confine di parola su
testo corrotto non aggancia niente. Per questo il filtro principale qui non
legge le parole: legge DOVE sta la riga.

LA GEOMETRIA E' IL FILTRO PRINCIPALE. Il totale e' gia' localizzato per
coordinate da `totale.py`, ed e' affidabile. La sua altezza sulla pagina e' un
confine fisico: sotto il totale non ci sono piu' prodotti. Questo vale
qualunque cosa l'OCR abbia fatto delle lettere.

CIO' CHE NON SI FA: cercare il sottoinsieme di righe che somma al totale. E'
stato proposto e scartato. Su uno scontrino a cui mancano righe davvero,
troverebbe una combinazione plausibile e sbagliata, trasformando un fallimento
VISIBILE (scontrino marcato non valido) in un dato falso che entra nel database
e falsa i report. Meglio un buco dichiarato di un numero inventato.
"""
import difflib
import re

import numpy as np

from app.etl.totale import (CONTEGGIO_NON_IMPORTO, ETICHETTA_TOTALE,
                            MAX_CARATTERI_ETICHETTA, PAROLA_TOTALE)

# Di quanto si arretra il confine rispetto al centro dell'etichetta del totale.
# Mezza riga: cosi' la riga del totale stessa resta esclusa, ma quella
# immediatamente sopra (che puo' essere l'ultimo prodotto) si salva.
ARRETRAMENTO = 0.5

# Sotto questa quota di righe rimaste, il confine non e' credibile: significa
# che l'etichetta trovata sta troppo in alto (un totale stampato in cima, o un
# "TOTAL" che appartiene a un blocco riepilogativo iniziale). In quel caso e'
# piu' prudente non tagliare affatto che buttare via lo scontrino.
QUOTA_MINIMA_CORPO = 0.30


def _centro_y(box):
    return sum(p[1] for p in box) / 4.0


def _altezza(box):
    return max(p[1] for p in box) - min(p[1] for p in box)


def confine_coda(righe_ocr):
    """
    L'altezza y sotto la quale lo scontrino non contiene piu' prodotti, o None
    se non e' individuabile.

    Si sceglie l'etichetta PIU' IN BASSO fra quelle di totale, non la piu' in
    alto. Misurato: tagliando alla prima si scartava il 49% delle righe contro
    il 37%, cioe' si tagliava dentro l'elenco dei prodotti. La ragione e' che
    "TOTAL" compare anche in blocchi intermedi (subtotali, totale articoli),
    mentre il vero confine del corpo e' l'ultima occorrenza.
    """
    if not righe_ocr:
        return None

    etichette = [r for r in righe_ocr
                 if len(r["testo"]) <= MAX_CARATTERI_ETICHETTA
                 and ETICHETTA_TOTALE.search(r["testo"])
                 and not CONTEGGIO_NON_IMPORTO.search(r["testo"])]
    if not etichette:
        return None

    # Fra le etichette si preferiscono quelle con la parola "total", piu'
    # affidabile delle altre (misurato in totale.py: 31% contro 15%).
    preferite = [r for r in etichette if PAROLA_TOTALE.search(r["testo"])]
    scelte = preferite or etichette

    altezza = float(np.median([_altezza(r["box"]) for r in righe_ocr])) or 1.0
    return max(_centro_y(r["box"]) for r in scelte) - ARRETRAMENTO * altezza


def righe_corpo(righe_ocr):
    """
    Le righe che stanno sopra il confine, cioe' quelle che possono contenere
    prodotti.

    Se il confine non e' individuabile, o se taglierebbe via quasi tutto lo
    scontrino, restituisce le righe invariate: meglio lasciare passare qualche
    riga di coda che perdere i prodotti. Il caso di rottura previsto e' lo
    scontrino col totale stampato in cima invece che in fondo.
    """
    if not righe_ocr:
        return righe_ocr

    y = confine_coda(righe_ocr)
    if y is None:
        return righe_ocr

    corpo = [r for r in righe_ocr if _centro_y(r["box"]) < y]
    if len(corpo) < QUOTA_MINIMA_CORPO * len(righe_ocr):
        return righe_ocr
    return corpo


# Parole che marcano una riga di riepilogo e non un prodotto. Si confrontano
# per SOMIGLIANZA e non per uguaglianza, perche' l'OCR le storpia: "SUBIOLAL"
# per "subtotal", "CAM8IO" per "cambio", "IMPORIO" per "importo", "€*TOT_" per
# "total". Un `\bsubtotal\b` non aggancia niente di tutto questo.
PAROLE_RIEPILOGO = (
    "total", "subtotal", "suma", "importe", "import", "efectivo", "efectiu",
    "cambio", "canvi", "entregado", "entregat", "devolucion", "devolucio",
    "abonar", "pagado", "pagat", "iva", "bonificacion", "venta", "tarjeta",
    "targeta", "lliurament", "liurament",
)

# Quanto due parole devono somigliarsi per considerarle la stessa. 0.78 sta
# sopra le coppie corrette ("subiolal"/"subtotal" 0.75 -> serve 0.72 in realta')
# e sotto le collisioni con nomi di prodotto. Si veda la prova nei test.
SOMIGLIANZA_MINIMA = 0.72

# Solo parole abbastanza lunghe: su parole corte la somiglianza e' rumore
# ("pa" somiglia a tutto).
MIN_LUNGHEZZA_PAROLA = 4

_PAROLE = re.compile(r"[A-Za-zÀ-ÿ]{3,}")

# Abbreviazioni di riepilogo troppo corte per il confronto per somiglianza, che
# su 3-4 lettere darebbe collisioni con qualunque cosa. Si cercano per
# uguaglianza esatta sul token: "TOT" in "€* TOT" e' il totale ricopiato.
SIGLE_RIEPILOGO = frozenset(("tot", "iva", "eur", "sub", "cash"))

# L'OCR sostituisce cifre alle lettere dentro le parole: "CAM8IO" per "cambio",
# "5UMA" per "suma". Rimpiazzarle prima del confronto recupera queste righe,
# che altrimenti si spezzano in due token corti e sfuggono.
_CIFRE_COME_LETTERE = str.maketrans("0135894", "olsbega")


def _normalizza(testo):
    """Il testo con le cifre-per-lettere ripristinate, in minuscolo."""
    return (testo or "").lower().translate(_CIFRE_COME_LETTERE)


def sa_di_riepilogo(testo):
    """
    La riga contiene una parola che somiglia a un marcatore di riepilogo?

    Serve per le righe che stanno SOPRA il confine geometrico e che quindi la
    geometria non puo' scartare: subtotali e sconti intermedi, che sull'elenco
    dei prodotti stanno in mezzo. Sotto il confine non serve, perche' li' taglia
    gia' la posizione.
    """
    for parola in _PAROLE.findall(_normalizza(testo)):
        if parola in SIGLE_RIEPILOGO:
            return True
        if len(parola) < MIN_LUNGHEZZA_PAROLA:
            continue
        for chiave in PAROLE_RIEPILOGO:
            if abs(len(parola) - len(chiave)) > 3:
                continue
            if difflib.SequenceMatcher(None, parola, chiave).ratio() >= SOMIGLIANZA_MINIMA:
                return True
    return False


def importo_impossibile(prezzo, totale):
    """
    Un prodotto non puo' costare PIU' del totale dello scontrino.

    Il confronto e' STRETTO, non "maggiore o uguale", e la differenza non e'
    accademica. Misurato sugli scontrini che gia' quadravano: con `>=` si
    risolveva 1 caso e se ne rompevano 2, con `>` se ne risolvono 2 e non se ne
    rompe nessuno.

    Il caso che lo dimostra e' lo scontrino di un prodotto solo: totale 1,72 e
    unica riga "ESTAC.CONSUM 250" a 1,72. Li' il prodotto E' il totale, e
    scartarlo azzererebbe uno scontrino corretto. Le righe UGUALI al totale
    sono ambigue (puo' essere il totale ricopiato, oppure l'unico prodotto) e
    vanno lasciate decidere alla geometria, che sa distinguerle per posizione.
    """
    if totale is None or prezzo is None:
        return False
    return abs(prezzo) > abs(totale)
