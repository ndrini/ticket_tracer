"""Dice cosa c'e' di NUOVO in una cartella di foto, senza elaborare niente.

    uv run python scripts/ispeziona_cartella.py /percorso/di/una/cartella
    uv run python scripts/ispeziona_cartella.py ~/Foto --elenca
    uv run python scripts/ispeziona_cartella.py ~/Foto --copia-nuove data/lotto3

Le copie degli scontrini finiscono un po' dappertutto — backup, WhatsApp, un
altro telefono. Prima di lanciare un'ingestione che costa due minuti a foto,
questo dice quante di quelle foto sono gia' state elaborate.

## Riconosce anche le copie RIDOTTE

Il confronto NON usa l'SHA-256, che cambia completamente se cambia un byte:
usa un'impronta percettiva (dhash), che guarda la struttura dell'immagine.

MISURATO: la stessa foto ridotta a 600, 400 o 200 px e ricompressa a qualita' 60
resta a distanza 0-4 dall'originale, mentre foto diverse stanno a 23-31. Quindi
una copia ridimensionata o ricompressa viene riconosciuta come gia' vista.

Confronta contro DUE registri:
  - data/foto_viste.json, le fotografie gia' ingerite
  - la tabella `miniature`, cioe' i singoli scontrini gia' estratti

Il secondo serve al caso in cui ricompaia il ritaglio di uno scontrino, non la
foto intera.

## Non elabora e non sposta niente

Stampa un rapporto. Con --copia-nuove copia altrove le sole foto mai viste,
pronte per l'ingestione, lasciando intatta la cartella d'origine.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
REGISTRO = ROOT / "data" / "foto_viste.json"
ESTENSIONI = (".jpg", ".jpeg", ".png", ".webp")

# Stessa soglia dell'ingestione: 0-4 per la stessa foto ricompressa, 23-31 per
# foto diverse. Il varco fra i due gruppi e' largo, la soglia cade in mezzo.
SOGLIA = 5


def dhash(img, size=8):
    grigio = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    piccola = cv2.resize(grigio, (size + 1, size), interpolation=cv2.INTER_AREA)
    valore = 0
    for b in (piccola[:, 1:] > piccola[:, :-1]).flatten():
        valore = (valore << 1) | int(b)
    return f"{valore:0{size * size // 4}x}"


def distanza(a, b):
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (TypeError, ValueError):
        return 99


def impronte_note(db: Path):
    """(impronta, etichetta) di tutto cio' che e' gia' stato elaborato."""
    note = []
    if REGISTRO.is_file():
        registro = json.loads(REGISTRO.read_text(encoding="utf-8"))
        for nome, voce in registro.items():
            if voce.get("phash"):
                note.append((voce["phash"], f"foto gia' vista: {nome}"))

    if db.is_file():
        conn = sqlite3.connect(db)
        try:
            for sha, impronta in conn.execute(
                    "SELECT sha256, dhash FROM miniature"):
                note.append((impronta, f"scontrino gia' estratto: {sha[:12]}"))
        except sqlite3.OperationalError:
            pass  # la tabella non esiste ancora: si confronta solo col registro
        conn.close()
    return note


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cartella", type=Path)
    p.add_argument("--db", type=Path, default=ROOT / "data" / "spese.db")
    p.add_argument("--elenca", action="store_true", help="elenca le foto nuove")
    p.add_argument("--copia-nuove", type=Path, metavar="DEST",
                   help="copia le sole foto mai viste in questa cartella")
    args = p.parse_args(argv)

    if not args.cartella.is_dir():
        raise SystemExit(f"non e' una cartella: {args.cartella}")

    note = impronte_note(args.db)
    print(f"registro: {len(note)} impronte gia' note\n")

    foto = sorted(f for f in args.cartella.rglob("*")
                  if f.is_file() and f.suffix.lower() in ESTENSIONI)
    if not foto:
        raise SystemExit(f"nessuna immagine in {args.cartella}")

    nuove, viste, illeggibili = [], [], []
    for percorso in foto:
        img = cv2.imread(str(percorso))
        if img is None:
            illeggibili.append(percorso)
            continue
        impronta = dhash(img)
        somiglianti = [(distanza(impronta, n), e) for n, e in note]
        vicina = min(somiglianti) if somiglianti else (99, "")
        if vicina[0] <= SOGLIA:
            viste.append((percorso, vicina))
        else:
            nuove.append(percorso)

    n = len(foto)
    print(f"{n} immagini in {args.cartella}")
    print(f"  GIA' ELABORATE: {len(viste):>4}  ({len(viste) / n * 100:.0f}%)")
    print(f"  mai viste:      {len(nuove):>4}  ({len(nuove) / n * 100:.0f}%)")
    if illeggibili:
        print(f"  illeggibili:    {len(illeggibili):>4}")

    if viste[:3]:
        print("\n  esempi di riconosciute:")
        for percorso, (d, etichetta) in viste[:3]:
            print(f"    {percorso.name[:34]:<36} distanza {d}  {etichetta}")

    if args.elenca and nuove:
        print(f"\n  le {len(nuove)} mai viste:")
        for percorso in nuove:
            print(f"    {percorso}")

    if args.copia_nuove:
        args.copia_nuove.mkdir(parents=True, exist_ok=True)
        for percorso in nuove:
            shutil.copy2(percorso, args.copia_nuove / percorso.name)
        print(f"\n  copiate {len(nuove)} foto nuove in {args.copia_nuove}/")
        print(f"  ora: uv run python scripts/fase_a_ingestione.py "
              f"{args.copia_nuove.name}")
    elif nuove:
        print(f"\n  Con --copia-nuove <cartella> le copia pronte per l'ingestione.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
