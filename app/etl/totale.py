"""
Trova il totale stampato su uno scontrino.

Serve alla Fase B: ogni scontrino dichiara il proprio totale, e confrontarlo con
la somma delle righe estratte e' il controllo di qualita' piu' forte
disponibile. Non costa nulla perche' il dato e' gia' sulla carta.

Due scelte, entrambe decise misurando su ~300 scontrini reali e non a intuito:

1. Si cerca l'importo per COORDINATE, sulla stessa altezza dell'etichetta e alla
   sua destra, invece che sulla riga di testo successiva. E' come lo scontrino e'
   davvero stampato — etichetta a sinistra, cifra a destra — e l'OCR le separa in
   frammenti distinti. Misurato: 211 totali trovati per coordinate contro 191
   leggendo la riga dopo.

2. L'etichetta deve essere CORTA. La parola "total" compare anche in frasi di
   cortesia ("...con el fin de lograr un silencio total"), e una riga di prosa
   verrebbe scambiata per un totale. Su 512 righe contenenti la parola, 511 sono
   etichette sotto i 34 caratteri e una sola e' prosa: il limite di lunghezza
   separa i due casi senza ambiguita'.
"""
import re

import numpy as np

# Etichette che precedono il totale, in spagnolo e catalano.
ETICHETTA_TOTALE = re.compile(
    r"\b(total|import\s+per\s+abonar|a\s+pagar|suma)\b", re.IGNORECASE)

# Fra le etichette accettate, quella che indica il totale con piu' affidabilita'.
# Le altre ("import per abonar", "suma") compaiono anche accanto al contante
# consegnato.
PAROLA_TOTALE = re.compile(r"\btotal\b", re.IGNORECASE)

# Un importo: 1234,56 oppure 1234.56, eventualmente negativo.
# Il segno va conservato: i resi esistono e sono dati validi, non errori. Su uno
# scontrino IKEA di reso il totale e' -58,98 EUR, e leggerlo come positivo
# falserebbe le somme al posto di segnalarle.
IMPORTO = re.compile(r"(-?\d{1,4})[.,](\d{2})(?!\d)")

# Oltre questa lunghezza la riga e' prosa, non un'etichetta.
MAX_CARATTERI_ETICHETTA = 34

# Etichette che contengono la parola "totale" ma contano PEZZI, non euro.
# Su uno scontrino IKEA "Total articles: 5" veniva letto come un totale di
# 0,19 euro, perche' e' l'ultima etichetta e vince su "Total" in denaro.
CONTEGGIO_NON_IMPORTO = re.compile(
    r"\b(articles?|articulos?|arti[cg]ol[oi]|unitats?|unidades?|pe[czs]as?|"
    r"linies?|lineas?|items?)\b", re.IGNORECASE)


def _centro_y(box):
    return sum(p[1] for p in box) / 4.0


def _centro_x(box):
    return sum(p[0] for p in box) / 4.0


def _altezza(box):
    return max(p[1] for p in box) - min(p[1] for p in box)


def _importo(testo):
    """L'ultimo importo nel testo, o None. L'ultimo perche' su una riga come
    "2 PANET 1,14 2,28" il valore che conta e' il totale di riga, non l'unitario."""
    trovati = IMPORTO.findall(testo)
    if not trovati:
        return None
    intero, decimali = trovati[-1]
    valore = float(f"{intero.lstrip('-')}.{decimali}")
    return -valore if intero.startswith("-") else valore


def candidati_totale(righe_ocr):
    """Tutti gli importi stampati accanto a un'etichetta di totale.

    Serve a chi ha un modo INDIPENDENTE di riconoscere quello giusto — per
    esempio la somma delle righe gia' estratte. `trova_totale` sceglie da solo
    con una regola posizionale; questa restituisce le opzioni e lascia scegliere.

    NASCE DA UNA MISURA (2026-08-30): su 144 righe-totale con piu' di un importo,
    "il piu' a destra" e "il maggiore" divergono in 96 casi, e NESSUNA delle due
    regole e' giusta. Sulla riga di riepilogo IVA `TOTAL 31,10 2,03` il piu' a
    destra e' la quota d'imposta; su `Total 7,79 ... 20,00` il maggiore e' il
    contante consegnato. La posizione da sola non basta a distinguerli.
    """
    if not righe_ocr:
        return []

    altezza_riga = float(np.median([_altezza(r["box"]) for r in righe_ocr])) or 1.0
    etichette = [r for r in righe_ocr
                 if len(r["testo"]) <= MAX_CARATTERI_ETICHETTA
                 and ETICHETTA_TOTALE.search(r["testo"])
                 and not CONTEGGIO_NON_IMPORTO.search(r["testo"])]

    valori = []
    for etichetta in etichette:
        proprio = _importo(etichetta["testo"])
        if proprio is not None:
            valori.append(proprio)
            continue
        y, x = _centro_y(etichetta["box"]), _centro_x(etichetta["box"])
        for r in righe_ocr:
            if (abs(_centro_y(r["box"]) - y) < 1.2 * altezza_riga
                    and _centro_x(r["box"]) > x):
                valore = _importo(r["testo"])
                if valore is not None:
                    valori.append(valore)

    # Ordine stabile senza duplicati.
    visti, unici = set(), []
    for v in valori:
        if v not in visti:
            visti.add(v)
            unici.append(v)
    return unici


def trova_totale(righe_ocr):
    """
    Il totale dichiarato sullo scontrino, o None se non e' individuabile.

    `righe_ocr` sono i frammenti prodotti dalla Fase A, ognuno con `testo` e
    `box`. Fra tutte le etichette di totale si tiene quella con l'importo PIU'
    GRANDE, perche' la spesa complessiva supera sempre le sue componenti.

    Prendere l'ultima etichetta in basso e' la regola sbagliata, e la misura lo
    ha mostrato: sotto il totale vero c'e' spesso la tabella IVA, che si chiude
    con la parola "TOTAL" seguita da una quota d'imposta. Su uno scontrino
    Mercadona questo restituiva 0,51 euro (una quota IVA) al posto di 7,79, e la
    firma dell'errore era inequivocabile — la somma delle righe superava il
    totale dichiarato in 179 casi su 202, cioe' quasi mai per rumore casuale.

    Le due regole differiscono sul 24% degli scontrini.
    """
    if not righe_ocr:
        return None

    etichette = [r for r in righe_ocr
                 if len(r["testo"]) <= MAX_CARATTERI_ETICHETTA
                 and ETICHETTA_TOTALE.search(r["testo"])
                 and not CONTEGGIO_NON_IMPORTO.search(r["testo"])]
    if not etichette:
        return None

    altezza_riga = float(np.median([_altezza(r["box"]) for r in righe_ocr])) or 1.0

    candidati = []
    for etichetta in etichette:
        # L'importo puo' stare sull'etichetta stessa ("TOTAL 28,80")...
        valore = _importo(etichetta["testo"])
        if valore is None:
            # ...oppure, molto piu' spesso, in un frammento alla sua destra.
            y = _centro_y(etichetta["box"])
            x = _centro_x(etichetta["box"])
            vicini = [r for r in righe_ocr
                      if abs(_centro_y(r["box"]) - y) < 1.2 * altezza_riga
                      and _centro_x(r["box"]) > x
                      and _importo(r["testo"]) is not None]
            if not vicini:
                continue
            # Il piu' a destra: sulle righe con piu' numeri l'importo finale
            # e' l'ultimo della colonna.
            vicini.sort(key=lambda r: _centro_x(r["box"]))
            valore = _importo(vicini[-1]["testo"])
        candidati.append((etichetta["testo"], valore))

    if not candidati:
        return None

    # A parita' di scelta si preferisce l'etichetta piu' affidabile, non
    # l'importo piu' grande. Misurato confrontando ogni etichetta con la somma
    # dei prodotti: "total" coincide nel 31% dei casi, "import per abonar" e
    # "suma" solo nel 15%. Su uno scontrino Consum "IMPORT PER ABONAR 50,20"
    # era il contante consegnato e vinceva su "Total factura: 10,18", che era
    # il totale vero.
    preferiti = [v for etichetta, v in candidati
                 if PAROLA_TOTALE.search(etichetta)]
    if preferiti:
        return max(preferiti, key=abs)

    # Per valore assoluto, cosi' i resi (totali negativi) restano riconoscibili.
    return max((v for _, v in candidati), key=abs)
