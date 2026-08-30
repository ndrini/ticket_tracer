"""Carica su Kaggle i RITAGLI del campione giudicato, come dataset **privato**.

    uv run python scripts/kaggle_carica_ritagli.py            # prova a vuoto
    uv run python scripts/kaggle_carica_ritagli.py --esegui   # carica davvero

Prepara l'ingresso per il confronto geometrico vs VLM descritto in
docs/122_metrica_confronto_vlm.md.

## Qui escono le IMMAGINI, non solo il testo

Differenza sostanziale rispetto a kaggle_carica_dataset.py, che carica solo il
testo OCR proprio per NON far uscire le fotografie. Un modello di visione ha
bisogno dei pixel: senza immagini non c'e' niente da misurare.

Cosa esce davvero: il ritaglio di uno scontrino, che mostra negozio, data, ora e
la lista della spesa. Su dataset privato, ma su un server altrui. E' una scelta
dell'utente, non un dettaglio tecnico, ed e' il motivo per cui questo script
chiede conferma esplicita con --esegui.

Due salvaguardie, nessuna opzionale:

1. **Dataset privato.** Dipende SOLO dall'assenza di `--public` (verificato nel
   sorgente di kaggle: `dataset_create_new(public: bool = False)`). Questo
   script non passa mai `--public`.
2. **Nessun EXIF.** VERIFICATO il 2026-08-30: i ritagli sono riscritti da
   OpenCV, che non copia i metadati, quindi non portano GPS ne' data di scatto.
   Il controllo e' rifatto qui prima di ogni upload invece di essere dato per
   buono: se un domani la pipeline cambiasse encoder, se ne accorge PRIMA.

Il nome del file e' lo sha256 del ritaglio, che e' gia' la chiave di tutta la
pipeline e non porta con se' data ne' ora.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RITAGLI = ROOT / "data" / "ritagli"
STAGING = ROOT / "data" / "kaggle_ritagli"
SLUG = "ticket-tracer-ritagli"


def campione(db: Path) -> list[tuple[int, str]]:
    """The crops a human judged as correctly cut.

    Only taglio:ok: on a badly cut crop both extractors read the wrong picture,
    so neither can win and the comparison would measure segmentation instead.
    """
    conn = sqlite3.connect(db)
    righe = conn.execute("""
        SELECT q.receipt_id, r.image_sha256
        FROM manual_review_queue q JOIN receipts r ON r.id = q.receipt_id
        WHERE q.reason LIKE 'taglio:ok%' AND q.completed_at IS NOT NULL
        ORDER BY q.receipt_id""").fetchall()
    conn.close()
    return righe


def verifica_niente_exif(cartella: Path) -> None:
    """No crop leaves with metadata. Checked separately from the copying, so a
    future change to the pipeline's encoder is caught BEFORE the upload."""
    from PIL import Image

    for percorso in sorted(cartella.glob("*.jpg")):
        with Image.open(percorso) as im:
            exif = im.getexif()
        if exif and len(exif):
            raise SystemExit(
                f"NON carico nulla: {percorso.name} porta {len(exif)} tag EXIF, "
                "che possono contenere GPS e data dello scatto."
            )


def utente() -> str:
    """Kaggle username. The new token format does not carry it, so it is asked
    of the API; guessing it would create the dataset in the wrong place."""
    fatto = subprocess.run(["kaggle", "datasets", "list", "--mine", "--csv"],
                           capture_output=True, text=True)
    if fatto.returncode != 0:
        raise SystemExit(f"kaggle non risponde:\n{fatto.stderr.strip()}")
    # csv, not split(","): a title containing a comma would yield a wrong name.
    righe = list(csv.reader(io.StringIO(fatto.stdout)))
    for riga in righe[1:]:
        if riga and "/" in riga[0]:
            return riga[0].split("/", 1)[0]
    raise SystemExit("non deduco lo username da Kaggle: dimmelo tu.")


def prepara(righe, destinazione: Path, nome_utente: str) -> int:
    if destinazione.exists():
        shutil.rmtree(destinazione)
    destinazione.mkdir(parents=True)

    indice = []
    for receipt_id, sha in righe:
        sorgente = RITAGLI / f"{sha}.jpg"
        if not sorgente.is_file():
            print(f"  manca il ritaglio di #{receipt_id} ({sha[:12]}), lo salto")
            continue
        shutil.copy2(sorgente, destinazione / f"{sha}.jpg")
        indice.append({"receipt_id": receipt_id, "sha256": sha})

    (destinazione / "indice.json").write_text(
        json.dumps(indice, indent=1), encoding="utf-8")
    (destinazione / "dataset-metadata.json").write_text(json.dumps({
        "title": "ticket tracer ritagli",
        "id": f"{nome_utente}/{SLUG}",
        "licenses": [{"name": "other"}],
    }, indent=1), encoding="utf-8")
    return len(indice)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=ROOT / "data" / "spese.db")
    p.add_argument("--esegui", action="store_true",
                   help="carica davvero (senza, e' una prova a vuoto)")
    args = p.parse_args(argv)

    righe = campione(args.db)
    print(f"Campione: {len(righe)} ritagli giudicati col taglio buono\n")
    if not righe:
        raise SystemExit("nessuno scontrino con taglio:ok. Rivedine qualcuno prima.")

    nome_utente = utente() if args.esegui else "(da chiedere a Kaggle)"
    n = prepara(righe, STAGING, nome_utente)
    verifica_niente_exif(STAGING)
    peso = sum(f.stat().st_size for f in STAGING.glob("*.jpg")) / 1e6
    print(f"  {n} ritagli pronti in {STAGING.relative_to(ROOT)}/  ({peso:.1f} MB)")
    print("  nessun EXIF: verificato")

    if not args.esegui:
        print("\nProva a vuoto. Con --esegui carica su Kaggle come dataset PRIVATO.")
        print("ATTENZIONE: le immagini degli scontrini escono da questa macchina.")
        return 0

    fatto = subprocess.run(
        ["kaggle", "datasets", "create", "-p", str(STAGING), "--dir-mode", "zip"],
        capture_output=True, text=True)
    uscita = (fatto.stdout + fatto.stderr).strip()
    print(uscita)
    if fatto.returncode != 0 and "already exists" in uscita:
        fatto = subprocess.run(
            ["kaggle", "datasets", "version", "-p", str(STAGING),
             "-m", f"campione giudicato: {n} ritagli", "--dir-mode", "zip"],
            capture_output=True, text=True)
        print((fatto.stdout + fatto.stderr).strip())
    if fatto.returncode != 0:
        raise SystemExit("upload fallito")

    # Privacy is verified, not assumed.
    meta = subprocess.run(
        ["kaggle", "datasets", "metadata", f"{nome_utente}/{SLUG}", "-p", str(STAGING)],
        capture_output=True, text=True)
    print(meta.stdout.strip() or meta.stderr.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
