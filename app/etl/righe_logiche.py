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
import re

import cv2
import numpy as np

from app.etl.geometria import (
    INIZIO_RIEPILOGO,
    SOLO_IMPORTO,
    altezza_riga,
    colonna_dei_prezzi,
    confine_riepilogo,
)

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


# Un frammento che porta un nome: almeno tre lettere di fila. Un codice
# ("22195") o una quantita' non bastano a fare un prodotto.
HA_NOME = re.compile(r"[A-Za-zÀ-ÿ]{3}")

# Un importo ovunque nella riga, non necessariamente da solo.
PORTA_IMPORTO = re.compile(r"-?\d{1,4}[.,]\d{2}")


def _ricuci_righe_spezzate(gruppi, righe_ocr, altezza):
    """
    Riunisce il nome di un prodotto all'importo stampato su un'altra riga.

    IL DIFETTO CHE RISOLVE. Molti negozi stampano un prodotto su piu' righe: non
    e' un errore di lettura, e' come stampano.

        Art/ EA 80417311    22195          <- IKEA, tre righe per articolo
        OVERMATT N campana alim j3 silic
                            4,00   0

        Pastanaga Granel                   <- Cal Fruitos, merce a peso
           1,204      1,78     2,14

    Il consumatore a valle (`_e_riga_prodotto` in `estrattore.py`) pretende nome
    e importo sulla STESSA riga, e cosi' le scarta entrambe: zero prodotti
    estratti, esito PRODOTTI_ASSENTI. Misurato sui 218 scontrini, questo layout
    domina il 28% dei PRODOTTI_ASSENTI contro il 5% dei VALIDO — quasi sei volte
    piu' frequente dove l'estrazione fallisce. Su uno scontrino IKEA con 8
    articoli e totale 52,00 ne veniva estratto UNO, scarto -50,50.

    PERCHE' QUI E NON NEL FILTRO. Ricucire dopo, sul testo gia' appiattito,
    sembrava piu' semplice ma non funziona: il modello riceve due righe mutilate
    — una col solo nome, una coi soli numeri — e ne salta una, cosi' la coppia
    da ricucire non arriva mai al filtro. E il testo appiattito ha perso le
    coordinate, cioe' proprio l'informazione che distingue una ricucitura giusta
    da una inventata. Deciso col consenso degli agenti (Vibe, Gemini,
    Perplexity), con Copilot in dissenso.

    LE TRE GUARDIE, e perche' ciascuna serve:

    1. L'importo deve cadere nella COLONNA DEI PREZZI dello scontrino. E' la
       guardia che vale di piu': senza, sui ritagli che contengono due scontrini
       affiancati (18% dei PRODOTTI_ASSENTI) si accoppierebbe il nome di uno col
       prezzo dell'altro, inventando un prodotto che puo' persino far quadrare i
       conti per caso. Meglio un buco dichiarato che un numero inventato.
    2. Le due righe devono essere ADIACENTI, e sopra il confine del riepilogo:
       sotto ci sono IVA, resto e contante, che prodotti non sono.
    3. La riga dell'importo non deve contenere lettere, e quella del nome non
       deve contenere gia' un importo: si ricuce solo cio' che e' davvero
       spezzato, mai due righe gia' complete.

    Non si allarga TOLLERANZA_RIGA: quella strada e' gia' stata misurata e
    fondeva le righe fra loro (a 0.8 il 74% degli scontrini aveva una riga che
    ne inghiottiva cinque). Qui il vincolo e' su DUE assi, non su uno solo.
    """
    colonna = colonna_dei_prezzi(righe_ocr, altezza)
    if colonna is None:
        return gruppi
    x_min, x_max = colonna
    confine = confine_riepilogo(righe_ocr, altezza)

    def _testo(gruppo):
        return " ".join(v[2] for v in sorted(gruppo, key=lambda v: v[1]) if v[2])

    fusi = []
    saltare = False
    for corrente, seguente in zip(gruppi, gruppi[1:] + [None]):
        if saltare:
            saltare = False
            continue
        if seguente is None:
            fusi.append(corrente)
            continue

        nome, importo = _testo(corrente), _testo(seguente)
        # La y GREZZA, non quella corretta dalla pendenza: il confine del
        # riepilogo e' misurato sulle coordinate originali dell'OCR.
        y = max(v[3] for v in corrente)

        # Una riga che porta gia' un importo e' completa: fonderla con la
        # successiva le farebbe inghiottire il prezzo di un altro prodotto.
        # Misurato: senza questa guardia si perdevano 14 righe prodotto gia'
        # buone, per esempio "3 CERVESA ESP LLAUNA 0,34 1,02" fusa con la riga
        # sotto. `SOLO_IMPORTO` non bastava: aggancia solo i frammenti che sono
        # UNICAMENTE un importo, non un nome seguito dal suo prezzo.
        if (HA_NOME.search(nome) and not PORTA_IMPORTO.search(nome)
                and not INIZIO_RIEPILOGO.search(nome)
                and not HA_NOME.search(importo)
                and y < confine
                and any(SOLO_IMPORTO.match(v[2].strip()) and x_min <= v[1] <= x_max
                        for v in seguente)):
            fusi.append(corrente + seguente)
            saltare = True
        else:
            fusi.append(corrente)
    return fusi


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
        voci.append((y - pendenza * x, x, r["testo"].strip(), y))
    voci.sort()

    gruppi, corrente = [], [voci[0]]
    for voce in voci[1:]:
        if voce[0] - corrente[-1][0] > TOLLERANZA_RIGA * altezza:
            gruppi.append(corrente)
            corrente = []
        corrente.append(voce)
    gruppi.append(corrente)

    gruppi = _ricuci_righe_spezzate(gruppi, righe_ocr, altezza)

    return [" ".join(v[2] for v in sorted(g, key=lambda v: v[1]) if v[2])
            for g in gruppi]


def testo_ricomposto(righe_ocr):
    """Lo scontrino come testo, una riga fisica per riga."""
    return "\n".join(r for r in ricomponi(righe_ocr) if r)


def stessa_riga(righe_ocr):
    """Un test `(y, x) -> bool` che dice se un frammento sta su una data riga.

    Serve a chi ragiona per COORDINATE e non per testo — l'estrattore
    geometrico deve sapere quali frammenti stanno accanto a un importo, non
    leggere la riga gia' composta.

    Perche' esiste invece di lasciare che ognuno confronti le y: un confronto
    orizzontale `abs(y1 - y2) < k` assume lo scontrino dritto. MISURATO sul
    materiale: la mediana e' 0 gradi, ma il decimo peggiore sta a 2,1 gradi e il
    massimo a 4,2 — su uno scontrino largo 400 px sono 15-30 px di dislivello,
    quanto un'intera riga di testo. Su quelli il confronto orizzontale aggancia
    la riga sbagliata.

    Restituisce anche l'altezza mediana, che i chiamanti usano come unita' di
    misura al posto di una costante in pixel.
    """
    if not righe_ocr:
        return (lambda ya, xa, yb, xb: False), 1.0

    altezza = float(np.median([_altezza(r["box"]) for r in righe_ocr])) or 1.0
    pendenza = inclinazione(righe_ocr)

    def sono_vicine(ya, xa, yb, xb, tolleranza=0.5):
        """Le due y, raddrizzate, distano meno di `tolleranza` righe."""
        return abs((ya - pendenza * xa) - (yb - pendenza * xb)) < tolleranza * altezza

    return sono_vicine, altezza
