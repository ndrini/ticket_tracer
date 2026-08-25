"""
La geometria dello scontrino: dove cadono i frammenti OCR sulla carta.

PERCHE' ESISTE QUESTO MODULO. Le stesse domande geometriche — dove sta la
colonna dei prezzi, sotto quale altezza comincia il riepilogo, quanto e' alta
una riga — servono a piu' consumatori: `verifica.py` per sommare gli importi
delle righe prodotto, `righe_logiche.py` per ricucire i prodotti stampati su
piu' righe. Erano scritte una volta sola, dentro `verifica.py`, dove pero'
nessun altro poteva usarle senza dipendere dal giudice aritmetico.

Tenerle qui separa la MISURA (dove sono le cose) dal GIUDIZIO (se i conti
tornano) e dalla RICOMPOSIZIONE (come si legge la riga): tre responsabilita'
distinte, tre moduli. Duplicarle avrebbe fatto divergere le due copie alla
prima correzione.

Questo modulo non decide nulla sui prodotti: risponde solo a domande sul dove.
"""
import re

import numpy as np

# Un importo isolato in un frammento OCR: "12,34" oppure "-58.98".
SOLO_IMPORTO = re.compile(r"^-?\d{1,4}[.,]\d{2}$")

# Parole che aprono il riepilogo: sotto di esse non ci sono piu' prodotti.
INIZIO_RIEPILOGO = re.compile(
    r"\b(suma|total|subtotal|descompte|descuento|dto|import|iva|base|"
    r"entregado|entregat|efectiu|efectivo|canvi|cambio|targeta|tarjeta|"
    r"pagament|pago|abonar)\b", re.IGNORECASE)


def centro_x(box):
    """Ascissa del centro di un riquadro OCR."""
    return sum(p[0] for p in box) / 4.0


def centro_y(box):
    """Ordinata del centro di un riquadro OCR."""
    return sum(p[1] for p in box) / 4.0


def altezza_riga(righe_ocr):
    """
    L'altezza tipica di una riga di testo, in pixel.

    E' la SCALA DEL DOCUMENTO: usarla come unita' di misura rende ogni soglia
    indipendente dalla risoluzione della foto e da quanto lo scontrino riempie
    il fotogramma. La mediana ignora i frammenti anomali, che ci sono sempre.
    """
    if not righe_ocr:
        return 1.0
    alte = [max(p[1] for p in r["box"]) - min(p[1] for p in r["box"])
            for r in righe_ocr]
    return float(np.median(alte)) or 1.0


def valore(testo):
    """L'importo di un frammento che contiene SOLO un importo, altrimenti None."""
    testo = testo.strip()
    if not SOLO_IMPORTO.match(testo):
        return None
    return float(testo.replace(",", "."))


def colonne(importi, altezza):
    """
    Raggruppa gli importi in colonne verticali.

    `importi` e' una sequenza di (valore, x, y). Due importi appartengono alla
    stessa colonna se le loro x distano meno di due altezze di riga: e' la
    scala del documento stesso, quindi il criterio non dipende dalla
    risoluzione della foto.

    Uno scontrino ha tipicamente due colonne — prezzo unitario e importo di
    riga — e su un caso reale il raggruppamento le separa a x 216..224 e
    x 296..314.
    """
    if not importi:
        return []
    ordinati = sorted(importi, key=lambda v: v[1])
    gruppi = [[ordinati[0]]]
    for voce in ordinati[1:]:
        if voce[1] - gruppi[-1][-1][1] <= 2 * altezza:
            gruppi[-1].append(voce)
        else:
            gruppi.append([voce])
    return gruppi


def confine_riepilogo(righe_ocr, altezza=None):
    """
    La y sotto la quale non ci sono piu' righe prodotto.

    Il confine arretra di mezza riga rispetto al marcatore, perche' etichetta e
    importo stanno sulla stessa riga fisica ma l'OCR li colloca a y leggermente
    diverse: su uno scontrino Mercadona "TOTAL" cade a y=816 e il suo 27,57 a
    y=813. Senza l'arretramento l'etichetta viene esclusa e la cifra no, e il
    totale finisce sommato ai prodotti.
    """
    marcatori = [centro_y(r["box"]) for r in righe_ocr
                 if len(r["testo"]) <= 34 and INIZIO_RIEPILOGO.search(r["testo"])]
    if not marcatori:
        return float("inf")
    # Il primo marcatore che si trovi sotto la meta' dello scontrino: sopra
    # compaiono intestazioni ("IMPORT") che non chiudono nulla.
    ys = [centro_y(r["box"]) for r in righe_ocr]
    meta = (min(ys) + max(ys)) / 2.0
    sotto = [y for y in marcatori if y > meta]
    if not sotto:
        return float("inf")
    if altezza is None:
        altezza = altezza_riga(righe_ocr)
    return min(sotto) - 0.5 * altezza


def colonna_dei_prezzi(righe_ocr, altezza=None, confine=None):
    """
    L'intervallo di x in cui cadono gli importi di riga, o None.

    E' la colonna PIU' POPOLATA fra quelle sopra il confine del riepilogo (vedi
    sotto perche' non la piu' a destra). Restituisce (x_minima, x_massima) allargato di
    un'altezza di riga per parte, cosi' il confronto tollera l'imprecisione dei
    riquadri OCR senza aprirsi all'intera larghezza dello scontrino.

    Serve a chi deve decidere se un importo isolato sia il prezzo di un
    prodotto: un numero che non cade in questa colonna non lo e'. E' il vincolo
    che impedisce di accoppiare il nome di uno scontrino col prezzo di quello
    fotografato accanto.
    """
    if not righe_ocr:
        return None
    if altezza is None:
        altezza = altezza_riga(righe_ocr)
    if confine is None:
        confine = confine_riepilogo(righe_ocr, altezza)

    importi = []
    for r in righe_ocr:
        v = valore(r["testo"])
        if v is None:
            continue
        y = centro_y(r["box"])
        if y >= confine:
            continue
        importi.append((v, centro_x(r["box"]), y))

    gruppi = colonne(importi, altezza)
    if not gruppi:
        return None

    # La colonna PIU' POPOLATA, non la piu' a destra. `somma_righe` prende la
    # piu' a destra perche' su UNO scontrino le colonne sono prezzo unitario e
    # importo di riga, e conta la seconda. Ma un ritaglio puo' contenere due
    # scontrini affiancati, e allora la piu' a destra e' quella del vicino:
    # misurato su un caso di prova, la colonna scelta cadeva a x 1210..1250,
    # cioe' sull'altro scontrino. La colonna con piu' importi e' quella dei
    # prodotti dello scontrino che si sta leggendo.
    # A parita' di popolazione vince la piu' a destra, che e' il criterio
    # originale: e' il caso normale dello scontrino singolo a due colonne.
    scelta = max(gruppi, key=lambda g: (len(g), g[-1][1]))
    xs = [x for _, x, _ in scelta]
    return (min(xs) - altezza, max(xs) + altezza)
