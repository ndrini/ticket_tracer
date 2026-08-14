"""
Ricompone i frammenti OCR nelle righe fisiche dello scontrino.

PaddleOCR restituisce frammenti separati, non righe: il nome di un prodotto e il
suo prezzo arrivano come due voci distinte perche' sulla carta sono lontani. Il
risultato e' testo illeggibile fuori contesto:

    27.93 €
    1.785 €
    18.93

Cosi' nessun modello puo' decidere se "27.93" sia un prodotto, una base
imponibile o un totale: l'informazione e' andata persa PRIMA della domanda.
Raggruppando i frammenti che condividono la stessa altezza si ottiene invece la
riga come e' stampata:

    1 MONGETA PLANA IK CO 1,50
    Total factura: 10,18
    Efectiu 50,20

Effetto misurato: con le righe ricomposte, qwen2.5:3b-instruct ha restituito il
totale corretto (10,18) su uno scontrino dove il parser geometrico sbagliava,
prendendo 50,20 — che e' il contante consegnato, non il totale.

La riga segue la PENDENZA del testo invece di assumerlo orizzontale, perche' su
una foto storta i frammenti a destra scivolano in basso rispetto a quelli a
sinistra. Le inclinazioni di questo materiale vanno da 1,4 a 6,4 gradi: su uno
scontrino largo 400 px, 6 gradi fanno oltre 40 px di dislivello, ben piu'
dell'altezza di una riga.

LA TOLLERANZA E' STATA SCELTA GUARDANDO CIO' CHE ROMPE, e la misura giusta e'
stata trovata al secondo tentativo. Ottimizzando su quanto spesso etichetta e
importo del TOTALE finiscono sulla stessa riga, il punteggio cresce
all'infinito con la tolleranza (73% a 0.8, 80% a 2.5) — ma e' un miraggio: le
righe fisiche vengono fuse fra loro, da 4280 a 618, e l'etichetta finisce
accanto a un numero qualsiasi.

Anche fermarsi a 0.8 era sbagliato, e se ne e' accorto solo l'estrattore: a
quella soglia il 74% degli scontrini aveva una riga che inghiottiva cinque o
piu' prodotti. Il totale non ne soffriva, i prodotti si'. Vedi TOLLERANZA_RIGA.
"""
import cv2
import numpy as np

# Quanto due frammenti possono distare in altezza restando sulla stessa riga,
# in multipli dell'altezza di una riga di testo.
#
# Il valore e' scelto guardando le RIGHE PRODOTTO, non il totale. Tarandolo sul
# totale si finiva a 0.8, che sembrava innocuo perche' etichetta e importo del
# totale restano comunque vicini; ma a quella soglia il 74% degli scontrini
# aveva almeno una riga che inghiottiva cinque o piu' prodotti, mescolando nomi
# e prezzi in un unico blocco:
#
#   1 GUACAMOLE 1 PANET 11 UN 1 PORCIO LIGHT ... 2,50 1,75 2,35 1,14 1,68
#
# Da un testo cosi' nessun modello puo' ricostruire quale prezzo appartenga a
# quale prodotto. Misurato su 120 scontrini, righe che contengono 5+ importi:
#
#   tolleranza   0.2    0.3    0.4    0.5    0.6    0.8
#   righe fuse   0.1%   0.2%   0.3%   0.7%   1.3%   6.6%
#   righe totali 4136   3805   3618   3400   3075   1863
TOLLERANZA_RIGA = 0.3


def _centro(box, asse):
    return sum(p[asse] for p in box) / 4.0


def _altezza(box):
    return max(p[1] for p in box) - min(p[1] for p in box)


def inclinazione(righe_ocr):
    """
    Pendenza del testo, in pixel di dislivello per pixel di larghezza.

    Si legge direttamente dall'orientamento dei riquadri che l'OCR disegna
    attorno a ogni frammento: un riquadro segue il testo che contiene, quindi la
    sua inclinazione E' quella della riga.

    La prima versione stimava la pendenza accoppiando frammenti vicini in altezza
    e distanti in orizzontale, assumendo che appartenessero alla stessa riga.
    Sbagliato: accoppiava anche frammenti di righe diverse e ne ricavava
    pendenze inventate, con uno scarto medio di 3,6 gradi dalla misura sui
    riquadri e casi oltre i 9 gradi. Applicata alla ricomposizione, PEGGIORAVA
    il risultato (66% contro il 72% che si ottiene ignorando l'inclinazione).

    La mediana ignora i frammenti storti isolati, che ci sono sempre.
    """
    if len(righe_ocr) < 4:
        return 0.0

    angoli = []
    for r in righe_ocr:
        punti = np.asarray(r["box"], dtype=np.float32)
        (larghezza, altezza), angolo = cv2.minAreaRect(punti)[1:]
        # OpenCV riporta l'angolo in [-90, 0) e puo' scambiare i due lati. Si
        # riporta l'angolo a quello del lato LUNGO, che e' la direzione del
        # testo, e poi nell'intervallo [-45, 45].
        if larghezza < altezza:
            angolo += 90
        angolo = (angolo + 45) % 90 - 45
        angoli.append(angolo)

    if not angoli:
        return 0.0
    return float(np.tan(np.radians(np.median(angoli))))


def ricomponi(righe_ocr):
    """
    Le righe fisiche dello scontrino, dall'alto in basso.

    Ogni riga e' il testo dei suoi frammenti concatenato da sinistra a destra,
    cioe' nell'ordine in cui si legge.
    """
    if not righe_ocr:
        return []

    altezza = float(np.median([_altezza(r["box"]) for r in righe_ocr])) or 1.0
    pendenza = inclinazione(righe_ocr)

    # Si corregge la y di ogni frammento come se lo scontrino fosse dritto:
    # cosi' i frammenti di una stessa riga tornano alla stessa altezza anche su
    # una foto inclinata, e il raggruppamento non deve indovinare nulla.
    voci = []
    for r in righe_ocr:
        x, y = _centro(r["box"], 0), _centro(r["box"], 1)
        voci.append((y - pendenza * x, x, r["testo"].strip()))
    voci.sort()

    gruppi, corrente = [], [voci[0]]
    for voce in voci[1:]:
        if voce[0] - corrente[-1][0] > TOLLERANZA_RIGA * altezza:
            gruppi.append(corrente)
            corrente = []
        corrente.append(voce)
    gruppi.append(corrente)

    return [" ".join(t for _, _, t in sorted(g, key=lambda v: v[1]) if t)
            for g in gruppi]


def testo_ricomposto(righe_ocr):
    """Lo scontrino come testo, una riga fisica per riga."""
    return "\n".join(r for r in ricomponi(righe_ocr) if r)
