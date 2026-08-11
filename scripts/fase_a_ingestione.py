"""
Fase A — ingestione idempotente: dalle foto ai ritagli e al testo OCR.

Produce i livelli 1-2 dell'architettura (vedi docs/20_analisi_e_strategie_sviluppo.md):

    data/estratti/<sha256>.json    un file per scontrino, con testo OCR
    data/ritagli/<sha256>.jpg      il ritaglio corrispondente

Perche' su file e non subito nel database: i dati grezzi vanno corretti e
rifatti piu' volte, e su file basta cancellare e rilanciare, mentre in tabelle
relazionali servirebbero UPDATE incrociati. Il database si popola tardi, quando
i dati sono gia' normalizzati e categorizzati.

L'identita' di uno scontrino e' l'hash SHA-256 del suo RITAGLIO, non della foto:
una foto contiene piu' scontrini, e il ritaglio e' cio' che diventera' una riga
del database. Un ritaglio gia' presente viene saltato, quindi rilanciare lo
script e' sicuro e riprende da dove si era fermato.

Nota: l'hash cambia se cambia la segmentazione (un ritaglio spostato di un
pixel e' un file diverso). E' voluto: un ritaglio diverso E' uno scontrino
estratto diversamente, e va rielaborato.

Uso:
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --limite 5
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --rifai
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


def elabora_foto(path, pipeline, segmenter, rifai=False):
    """Orient, segment, OCR. Returns (nuovi, saltati, scontrini_trovati)."""
    raw = cv2.imread(path)
    if raw is None:
        print(f"  NON LEGGIBILE  {os.path.basename(path)}")
        return 0, 0, 0

    img = pipeline._resize_safe(raw, 2000)
    img = pipeline._orient_whole_image(img, max_orient_dim=800)

    boxes = segmenter.boxes(img)
    nuovi = saltati = 0

    for indice, (x, y, w, h) in enumerate(boxes):
        crop = img[y:y + h, x:x + w]
        if crop.size == 0:
            continue
        digest, buf = sha256_immagine(crop)
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

    return nuovi, saltati, len(boxes)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    sorgente = argv[0]
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

    tot_nuovi = tot_saltati = tot_scontrini = 0
    inizio = time.time()

    for i, nome in enumerate(nomi, 1):
        t0 = time.time()
        nuovi, saltati, trovati = elabora_foto(
            os.path.join(sorgente, nome), pipeline, segmenter, rifai)
        tot_nuovi += nuovi
        tot_saltati += saltati
        tot_scontrini += trovati
        print(f"  [{i:3d}/{len(nomi)}] {nome:<30} "
              f"{trovati} scontrini  ({nuovi} nuovi, {saltati} gia' presenti)"
              f"  {time.time() - t0:.0f}s")

    durata = time.time() - inizio
    print(f"\n{tot_scontrini} scontrini in {len(nomi)} foto "
          f"(media {tot_scontrini / max(1, len(nomi)):.1f} per foto)")
    print(f"{tot_nuovi} nuovi, {tot_saltati} gia' presenti")
    print(f"Tempo: {durata / 60:.1f} min ({durata / max(1, len(nomi)):.0f}s per foto)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
