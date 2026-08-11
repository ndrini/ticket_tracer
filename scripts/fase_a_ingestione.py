"""
Fase A — ingestione idempotente: dalle foto ai ritagli e al testo OCR.

Produce i livelli 1-2 dell'architettura (vedi docs/20_analisi_e_strategie_sviluppo.md):

    data/estratti/<sha256>.json    un file per scontrino, con testo OCR
    data/ritagli/<sha256>.jpg      il ritaglio corrispondente

Perche' su file e non subito nel database: i dati grezzi vanno corretti e
rifatti piu' volte, e su file basta cancellare e rilanciare, mentre in tabelle
relazionali servirebbero UPDATE incrociati. Il database si popola tardi, quando
i dati sono gia' normalizzati e categorizzati.

Due difese contro il doppio lavoro, a due livelli diversi:

1. SCONTRINO — l'identita' e' l'hash SHA-256 del RITAGLIO, non della foto: una
   foto contiene piu' scontrini, e il ritaglio e' cio' che diventera' una riga
   del database. Un ritaglio gia' presente viene saltato.

   L'hash cambia se cambia la segmentazione (un ritaglio spostato di un pixel
   e' un file diverso). E' voluto: un ritaglio diverso E' uno scontrino
   estratto diversamente, e va rielaborato.

2. FOTOGRAFIA — la stessa foto puo' arrivare da fonti diverse (backup,
   WhatsApp, un altro telefono) ricompressa: i byte cambiano, il contenuto no.
   L'SHA-256 qui non serve a nulla, ed e' stato misurato: una ricompressione
   che sposta i pixel di 2.30 livelli medi su 255 produce un hash
   completamente diverso. Serve un hash PERCETTIVO (dhash), che guarda la
   struttura dell'immagine.

   Misurato: la stessa foto ricompressa o ridimensionata resta a distanza 0-2,
   foto diverse stanno a 23-31. Il registro delle foto viste sta in
   data/foto_viste.json e fa anche da indice foto -> scontrini.

Uso:
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --limite 5
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --rifai
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --ricostruisci-registro
"""
import hashlib
import json
import logging
import os
import sys
import time
import warnings

import cv2

warnings.filterwarnings("ignore")
os.environ.setdefault("GLOG_minloglevel", "3")
sys.path.insert(0, os.getcwd())

from app.etl.etl_engine import ReceiptPipeline  # noqa: E402
from app.etl.segmenter import ReceiptSegmenter  # noqa: E402

logging.basicConfig(level=logging.WARNING)

DIR_ESTRATTI = "data/estratti"
DIR_RITAGLI = "data/ritagli"
REGISTRO_FOTO = "data/foto_viste.json"

# Distanza di Hamming sotto la quale due foto sono considerate la stessa.
# Misurata: la stessa foto ricompressa (q80, q50) o ridimensionata (50%, 25%)
# resta a distanza 0-2, mentre foto diverse stanno a 23-31. La soglia cade in
# mezzo a un margine vuoto e ampio, non e' una taratura delicata.
SOGLIA_DUPLICATO = 8


def dhash(img, size=8):
    """
    Hash percettivo: confronta pixel adiacenti di una miniatura in grigio.

    L'hash SHA-256 non serve a riconoscere la stessa foto arrivata da fonti
    diverse: WhatsApp, un backup o un altro telefono la ricomprimono, e bastano
    2.30 livelli di differenza media su 255 — cioe' un'immagine visivamente
    identica — per cambiare completamente l'hash crittografico.

    Questo invece guarda la STRUTTURA dell'immagine (dove il chiaro passa allo
    scuro), che la ricompressione non altera.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return "".join("%02x" % int("".join("1" if b else "0" for b in bits[i:i + 8]), 2)
                   for i in range(0, len(bits), 8))


def distanza_hash(a, b):
    """Quanti bit differiscono fra due hash percettivi."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def carica_registro():
    """Foto gia' elaborate, con il loro hash percettivo."""
    if os.path.exists(REGISTRO_FOTO):
        with open(REGISTRO_FOTO) as fh:
            return json.load(fh)
    return {}


def gia_vista(registro, phash):
    """Nome della foto gia' elaborata che coincide con questa, se esiste."""
    for nome, voce in registro.items():
        if distanza_hash(voce["phash"], phash) <= SOGLIA_DUPLICATO:
            return nome
    return None


def sha256_immagine(img):
    """Hash of the encoded crop: the receipt's identity."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise ValueError("codifica JPEG fallita")
    return hashlib.sha256(buf.tobytes()).hexdigest(), buf


def ocr_righe(pipeline, crop):
    """OCR lines as plain text plus their box, ready to be re-parsed later."""
    righe = []
    for linea in pipeline._run_single_ocr(crop) or []:
        try:
            box, (testo, conf) = linea[0], linea[1]
            righe.append({
                "testo": testo,
                "confidenza": round(float(conf), 4),
                "box": [[int(p[0]), int(p[1])] for p in box],
            })
        except Exception:
            # A malformed line must not lose the whole receipt.
            continue
    return righe


def elabora_foto(path, pipeline, segmenter, registro, rifai=False):
    """Orient, segment, OCR. Returns (nuovi, saltati, scontrini_trovati)."""
    nome = os.path.basename(path)
    raw = cv2.imread(path)
    if raw is None:
        print(f"  NON LEGGIBILE  {nome}")
        return 0, 0, 0

    # La stessa foto puo' arrivare da fonti diverse (backup, WhatsApp, un altro
    # telefono) con una ricompressione che ne cambia i byte ma non il contenuto.
    # L'hash percettivo la riconosce comunque.
    phash = dhash(raw)
    if not rifai:
        originale = gia_vista(registro, phash)
        if originale is not None and originale != nome:
            print(f"  DUPLICATO      {nome:<30} = {originale}")
            return 0, 0, 0

    img = pipeline._resize_safe(raw, 2000)
    img = pipeline._orient_whole_image(img, max_orient_dim=800)

    boxes = segmenter.boxes(img)
    nuovi = saltati = 0
    digests = []

    for indice, (x, y, w, h) in enumerate(boxes):
        crop = img[y:y + h, x:x + w]
        if crop.size == 0:
            continue
        digest, buf = sha256_immagine(crop)
        digests.append(digest)
        path_json = os.path.join(DIR_ESTRATTI, digest + ".json")

        if os.path.exists(path_json) and not rifai:
            saltati += 1
            continue

        righe = ocr_righe(pipeline, crop)
        record = {
            "sha256": digest,
            "foto_origine": os.path.basename(path),
            "indice_nella_foto": indice,
            "box": [x, y, w, h],
            "dimensioni_ritaglio": [w, h],
            "righe_ocr": righe,
            "n_righe_ocr": len(righe),
            "estratto_il": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(path_json, "w") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
        with open(os.path.join(DIR_RITAGLI, digest + ".jpg"), "wb") as fh:
            fh.write(buf.tobytes())
        nuovi += 1

    # Il registro tiene anche la corrispondenza foto -> scontrini, cosi' serve
    # da indice per risalire dal ritaglio alla fotografia di provenienza.
    registro[nome] = {
        "phash": phash,
        "scontrini": digests,
        "elaborata_il": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return nuovi, saltati, len(boxes)


def ricostruisci_registro(sorgente):
    """
    Ricalcola l'hash percettivo delle foto gia' elaborate.

    Serve una volta sola, per le foto passate prima che il registro esistesse:
    senza, quelle foto non sono protette dal controllo duplicati. Costa poco,
    perche' l'hash percettivo non richiede ne' OCR ne' segmentazione.
    """
    registro = carica_registro()
    aggiunte = 0
    for nome in sorted(os.listdir(sorgente)):
        if not nome.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        if nome in registro:
            continue
        img = cv2.imread(os.path.join(sorgente, nome))
        if img is None:
            continue
        registro[nome] = {
            "phash": dhash(img),
            "scontrini": [],  # ignoto: la foto e' stata elaborata prima
            "elaborata_il": None,
        }
        aggiunte += 1
    with open(REGISTRO_FOTO, "w") as fh:
        json.dump(registro, fh, indent=2, ensure_ascii=False)
    print(f"Registro: {aggiunte} foto aggiunte, {len(registro)} in totale.")
    print(f"Scritto in {REGISTRO_FOTO}")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    sorgente = argv[0]

    if "--ricostruisci-registro" in argv:
        return ricostruisci_registro(sorgente)
    rifai = "--rifai" in argv
    limite = None
    if "--limite" in argv:
        limite = int(argv[argv.index("--limite") + 1])

    os.makedirs(DIR_ESTRATTI, exist_ok=True)
    os.makedirs(DIR_RITAGLI, exist_ok=True)

    nomi = sorted(f for f in os.listdir(sorgente)
                  if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if limite:
        nomi = nomi[:limite]

    print(f"Fase A — {len(nomi)} foto da {sorgente}/")
    print(f"  ritagli  -> {DIR_RITAGLI}/")
    print(f"  estratti -> {DIR_ESTRATTI}/\n")

    pipeline = ReceiptPipeline()
    segmenter = ReceiptSegmenter()
    registro = carica_registro()

    tot_nuovi = tot_saltati = tot_scontrini = 0
    prima = len(registro)
    inizio = time.time()

    for i, nome in enumerate(nomi, 1):
        t0 = time.time()
        nuovi, saltati, trovati = elabora_foto(
            os.path.join(sorgente, nome), pipeline, segmenter, registro, rifai)
        tot_nuovi += nuovi
        tot_saltati += saltati
        tot_scontrini += trovati
        if trovati:
            print(f"  [{i:3d}/{len(nomi)}] {nome:<30} "
                  f"{trovati} scontrini  ({nuovi} nuovi, {saltati} gia' presenti)"
                  f"  {time.time() - t0:.0f}s")
        # Salvataggio a ogni foto: un'interruzione a meta' non perde il lavoro.
        with open(REGISTRO_FOTO, "w") as fh:
            json.dump(registro, fh, indent=2, ensure_ascii=False)

    durata = time.time() - inizio
    print(f"\n{tot_scontrini} scontrini in {len(nomi)} foto "
          f"(media {tot_scontrini / max(1, len(nomi)):.1f} per foto)")
    print(f"{tot_nuovi} nuovi, {tot_saltati} gia' presenti")
    print(f"foto nel registro: {len(registro)} (erano {prima})")
    print(f"Tempo: {durata / 60:.1f} min ({durata / max(1, len(nomi)):.0f}s per foto)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
