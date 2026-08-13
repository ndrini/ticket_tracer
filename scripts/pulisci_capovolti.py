"""
Rimuove i ritagli estratti prima della correzione dell'orientamento.

Perche' servono: 13 foto su 96 uscivano capovolte (vedi il commit "catch the
180-degree errors the orientation classifier makes"). Rielaborandole, la Fase A
produce ritagli nuovi con l'orientamento giusto, ma quelli vecchi restano: hanno
un hash diverso, perche' l'hash e' calcolato sul ritaglio e un ritaglio ruotato
e' un'immagine diversa. Vanno tolti a mano, una volta sola.

Come si riconoscono: dalla confidenza media dell'OCR. Un riconoscitore che legge
testo capovolto tira a indovinare, e le due popolazioni non si sovrappongono.
Misurato sulle foto elaborate due volte:

    ritagli corretti    0.90 .. 0.99
    ritagli capovolti   0.30 .. 0.46

La soglia a 0.60 cade in mezzo a un intervallo vuoto.

Prudenze:
  - i ritagli poveri di testo (< 8 righe OCR) sono esclusi dal giudizio: una
    ricevuta di pochi caratteri puo' avere confidenza bassa senza essere
    capovolta;
  - senza --conferma lo script non cancella nulla, mostra soltanto.

Uso:
    uv run python scripts/pulisci_capovolti.py
    uv run python scripts/pulisci_capovolti.py --conferma
"""
import glob
import json
import os
import sys

import numpy as np

SOGLIA_CONFIDENZA = 0.60
MIN_RIGHE = 8

DIR_ESTRATTI = "data/estratti"
DIR_RITAGLI = "data/ritagli"


def confidenza(record):
    righe = record.get("righe_ocr") or []
    if not righe:
        return 0.0
    return float(np.mean([r["confidenza"] for r in righe]))


def main(argv):
    conferma = "--conferma" in argv

    da_togliere, tenuti, esclusi = [], 0, 0
    for percorso in sorted(glob.glob(os.path.join(DIR_ESTRATTI, "*.json"))):
        with open(percorso) as fh:
            record = json.load(fh)

        if record["n_righe_ocr"] < MIN_RIGHE:
            esclusi += 1
            continue

        conf = confidenza(record)
        if conf < SOGLIA_CONFIDENZA:
            da_togliere.append((percorso, record, conf))
        else:
            tenuti += 1

    # Quali foto restano senza alcun ritaglio leggibile una volta ripulite:
    # per quelle la Fase A va rilanciata, altrimenti spariscono dai dati.
    buone_per_foto = {}
    for percorso in sorted(glob.glob(os.path.join(DIR_ESTRATTI, "*.json"))):
        with open(percorso) as fh:
            r = json.load(fh)
        if r["n_righe_ocr"] >= MIN_RIGHE and confidenza(r) >= SOGLIA_CONFIDENZA:
            buone_per_foto[r["foto_origine"]] = True
    orfane = sorted({rec["foto_origine"] for _, rec, _ in da_togliere
                     if rec["foto_origine"] not in buone_per_foto})

    print(f"ritagli analizzati : {len(da_togliere) + tenuti + esclusi}")
    print(f"  leggibili        : {tenuti}")
    print(f"  poveri (<{MIN_RIGHE} righe): {esclusi}  (non giudicati)")
    print(f"  CAPOVOLTI        : {len(da_togliere)}\n")

    if orfane:
        print(f"ATTENZIONE: {len(orfane)} foto non hanno ancora una versione")
        print("corretta. Ripulendole restano senza dati finche' la Fase A non")
        print("viene rilanciata (cancellare e' proprio cio' che la fa rifare):")
        for nome in orfane:
            print(f"  {nome}")
        print()

    for _, record, conf in da_togliere[:12]:
        print(f"  {record['foto_origine'][:34]:<36} conf={conf:.2f} "
              f"righe={record['n_righe_ocr']}")
    if len(da_togliere) > 12:
        print(f"  ... e altri {len(da_togliere) - 12}")

    if not conferma:
        print("\nNessun file cancellato. Rilancia con --conferma per procedere.")
        return 0

    rimossi = 0
    for percorso, record, _ in da_togliere:
        os.remove(percorso)
        ritaglio = os.path.join(DIR_RITAGLI, record["sha256"] + ".jpg")
        if os.path.exists(ritaglio):
            os.remove(ritaglio)
        rimossi += 1
    print(f"\n{rimossi} ritagli capovolti rimossi.")
    print("Rilancia la Fase A per rielaborare le foto che ne erano prive.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
