"""Riduce i ritagli a miniature leggibili e ne registra l'impronta.

    uv run python scripts/miniature.py                    # genera le miniature
    uv run python scripts/miniature.py --larghezza 400    # piu' grandi
    uv run python scripts/miniature.py --verifica         # controlla e basta

## A cosa serve

Quando i dati di uno scontrino sono gia' estratti, l'immagine a piena
risoluzione non serve piu' a leggerla: serve solo a un occhio umano che voglia
controllare, mesi dopo, cosa c'era scritto. Per quello basta molto meno.

MISURATO il 2026-08-30: a 300 px di larghezza e qualita' JPEG 45 uno scontrino
resta leggibile — prodotti, prezzi e totale si distinguono — e pesa 18 KB invece
di 105. Tutti i 325 scontrini stanno in 5,7 MB invece di 34. A 200 px il negozio
si riconosce ancora ma i nomi dei prodotti diventano faticosi: e' sotto la
soglia utile.

## L'impronta sopravvive alla riduzione, l'hash no

L'SHA-256 di una miniatura e' completamente diverso da quello dell'originale:
cambia un byte, cambia tutto. Serve un hash PERCETTIVO, che guarda la struttura
dell'immagine invece dei byte.

VERIFICATO su sei foto ridotte a 600, 400 e 200 px e ricompresse a qualita' 60:
la distanza di Hamming dal dhash originale resta fra 0 e 4, sotto la soglia di 5,
mentre foto diverse stanno a 23-31. Quindi una miniatura resta riconoscibile
come "gia' vista", ed e' cio' che permette di ritrovare uno scontrino gia'
elaborato anche partendo da una copia ridotta.

## Cosa scrive

    data/miniature/<sha256>.jpg     la miniatura, nominata come il ritaglio
    tabella `miniature` in spese.db  sha256, dhash, dimensioni, peso

La tabella e' nel database e non in un file a parte perche' lo sha256 e' gia' la
chiave di receipts: cosi' una query sola lega dato estratto, giudizio umano e
immagine di controllo.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RITAGLI = ROOT / "data" / "ritagli"
MINIATURE = ROOT / "data" / "miniature"

# Misurati, non scelti a occhio: vedi la docstring.
LARGHEZZA = 300
QUALITA = 45

SCHEMA = """
CREATE TABLE IF NOT EXISTS miniature (
    sha256 TEXT PRIMARY KEY,      -- lo stesso di receipts.image_sha256
    dhash TEXT NOT NULL,          -- impronta percettiva, sopravvive alla riduzione
    larghezza INTEGER,
    altezza INTEGER,
    byte INTEGER,
    creata_il TEXT DEFAULT CURRENT_TIMESTAMP
)
"""


def dhash(img, size=8):
    """Impronta percettiva: confronta pixel adiacenti di una miniatura in grigio.

    Stessa funzione usata dall'ingestione per riconoscere le foto duplicate
    (scripts/fase_a_ingestione.py). Ripetuta qui invece di importarla perche'
    quel modulo carica PaddleOCR all'import, che qui non serve.
    """
    grigio = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    piccola = cv2.resize(grigio, (size + 1, size), interpolation=cv2.INTER_AREA)
    bit = piccola[:, 1:] > piccola[:, :-1]
    valore = 0
    for b in bit.flatten():
        valore = (valore << 1) | int(b)
    return f"{valore:0{size * size // 4}x}"


def riduci(img, larghezza):
    """La miniatura. INTER_AREA perche' rimpicciolisce senza aliasing."""
    if img.shape[1] <= larghezza:
        return img
    scala = larghezza / img.shape[1]
    return cv2.resize(img, (larghezza, max(1, int(img.shape[0] * scala))),
                      interpolation=cv2.INTER_AREA)


def genera(conn, larghezza, qualita, rifai=False):
    MINIATURE.mkdir(parents=True, exist_ok=True)
    conn.execute(SCHEMA)

    fatte = saltate = rotte = 0
    peso = 0
    for sorgente in sorted(RITAGLI.glob("*.jpg")):
        sha = sorgente.stem
        destinazione = MINIATURE / f"{sha}.jpg"
        if destinazione.is_file() and not rifai:
            saltate += 1
            peso += destinazione.stat().st_size
            continue

        img = cv2.imread(str(sorgente))
        if img is None:
            rotte += 1
            continue

        piccola = riduci(img, larghezza)
        ok, buf = cv2.imencode(".jpg", piccola, [cv2.IMWRITE_JPEG_QUALITY, qualita])
        if not ok:
            rotte += 1
            continue
        destinazione.write_bytes(buf.tobytes())

        # L'impronta si calcola sulla MINIATURA, non sull'originale: e' quella
        # che verra' confrontata quando ricomparira' una copia ridotta.
        conn.execute(
            "INSERT OR REPLACE INTO miniature "
            "(sha256, dhash, larghezza, altezza, byte) VALUES (?,?,?,?,?)",
            (sha, dhash(piccola), piccola.shape[1], piccola.shape[0], len(buf)))
        fatte += 1
        peso += len(buf)

    conn.commit()
    return fatte, saltate, rotte, peso


def verifica(conn):
    """Le miniature sono ancora riconoscibili come i loro ritagli?"""
    righe = conn.execute("SELECT sha256, dhash FROM miniature").fetchall()
    if not righe:
        print("nessuna miniatura registrata.")
        return

    lontane = mancanti = 0
    for sha, impronta in righe:
        originale = RITAGLI / f"{sha}.jpg"
        if not originale.is_file():
            mancanti += 1
            continue
        img = cv2.imread(str(originale))
        if img is None:
            mancanti += 1
            continue
        distanza = bin(int(dhash(img), 16) ^ int(impronta, 16)).count("1")
        if distanza > 5:
            lontane += 1

    print(f"miniature registrate: {len(righe)}")
    print(f"  riconoscibili dal ritaglio originale: {len(righe) - lontane - mancanti}")
    print(f"  oltre la soglia di 5:                 {lontane}")
    if mancanti:
        print(f"  ritaglio originale assente:           {mancanti}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(ROOT / "data" / "spese.db"))
    p.add_argument("--larghezza", type=int, default=LARGHEZZA)
    p.add_argument("--qualita", type=int, default=QUALITA)
    p.add_argument("--rifai", action="store_true", help="rigenera anche le esistenti")
    p.add_argument("--verifica", action="store_true", help="controlla e basta")
    args = p.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.execute(SCHEMA)

    if args.verifica:
        verifica(conn)
        return 0

    fatte, saltate, rotte, peso = genera(conn, args.larghezza, args.qualita, args.rifai)
    totale = fatte + saltate
    print(f"miniature a {args.larghezza} px, qualita' {args.qualita}\n")
    print(f"  generate:      {fatte}")
    print(f"  gia' presenti: {saltate}")
    if rotte:
        print(f"  illeggibili:   {rotte}")
    if totale:
        print(f"\n  {totale} miniature, {peso / 1e6:.1f} MB "
              f"({peso / totale / 1024:.1f} KB l'una)")
    print(f"  in {MINIATURE.relative_to(ROOT)}/ e nella tabella `miniature`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
