"""
Smista i ritagli gia' elaborati in due mucchi: da ripassare, e no.

    uv run python scripts/smista_processati.py --anno 2026
    uv run python scripts/smista_processati.py --anno 2025
    uv run python scripts/smista_processati.py            # tutti
    uv run python scripts/smista_processati.py --sposta    # invece di copiare

Produce:

    <destinazione>/<anno>/da_ripassare/<sospetto>/<sha256>.jpg
    <destinazione>/<anno>/ok/<sha256>.jpg
    <destinazione>/<anno>/inventario.csv

SMISTA I RITAGLI, NON LE FOTO. Una foto contiene piu' scontrini (fino a 4 nelle
foto del 2026) che possono ricadere in classi opposte: la stessa foto sarebbe
insieme "da ripassare" e "no". Il ritaglio invece e' l'unita' che ha un solo
verdetto, ed e' cio' che diventa una riga del database.

IL CRITERIO NON E' RIDEFINITO QUI: viene da app/revisione/coda.py, lo stesso che
ordina la coda di revisione umana. Duplicarlo significherebbe che un domani i due
diverbono in silenzio, e l'interfaccia mostrerebbe una cosa e le cartelle
un'altra.

L'ANNO VIENE DAL REGISTRO DELLE FOTO, non da receipts.foto_origine: quel campo
e' vuoto per 88 record su 306, mentre data/foto_viste.json mappa tutti e 306 i
ritagli alla foto da cui vengono. Il registro e' scritto durante l'ingestione,
quando l'origine e' ancora nota per costruzione.

COPIA, non sposta, salvo --sposta: data/ritagli/ e' l'archivio da cui rilanciare
le fasi successive, e svuotarlo renderebbe l'operazione non ripetibile.
"""
import argparse
import csv
import json
import os
import shutil
import re
import sqlite3
import sys

sys.path.insert(0, os.getcwd())

from app.revisione.coda import costruisci_coda  # noqa: E402

DIR_RITAGLI = "data/ritagli"
REGISTRO_FOTO = "data/foto_viste.json"
CARTELLE_ANNO = {"2025": "data/2025_scontrini", "2026": "data/2026_scontrini"}


def mappa_anni():
    """sha256 of a crop -> the year of the folder its photo came from.

    Falls back to the date in the file name for photos no longer in either
    folder (leftovers from earlier runs): declared as a guess in the CSV rather
    than silently folded into a year.
    """
    with open(REGISTRO_FOTO, encoding="utf-8") as f:
        registro = json.load(f)

    per_anno = {a: set(os.listdir(d)) for a, d in CARTELLE_ANNO.items()
                if os.path.isdir(d)}

    anni, incerti = {}, {}
    for foto, voce in registro.items():
        anno = next((a for a, nomi in per_anno.items() if foto in nomi), None)
        if anno is None:
            # Not in any source folder: guess from the name, but say so.
            trovato = re.search(r"(20\d{2})", foto)
            anno = trovato.group(1) if trovato else "ignoto"
            for sha in voce.get("scontrini", []):
                incerti[sha] = foto
        for sha in voce.get("scontrini", []):
            anni[sha] = (anno, foto)
    return anni, incerti


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/spese.db")
    p.add_argument("--destinazione", default="/mnt/condivisa/scontrini_processati")
    p.add_argument("--anno", help="tratta solo quest'anno (es. 2026)")
    p.add_argument("--sposta", action="store_true",
                   help="sposta invece di copiare (svuota data/ritagli)")
    args = p.parse_args(argv)

    anni, incerti = mappa_anni()

    conn = sqlite3.connect(args.db)

    # The queue decides what needs another look; everything else in the table
    # is, by definition, the other pile.
    coda = costruisci_coda(conn)
    da_ripassare = {v.sha256: v for v in coda}

    tutti = conn.execute(
        "SELECT image_sha256, COALESCE(validation_status,''), foto_origine "
        "FROM receipts WHERE image_sha256 IS NOT NULL").fetchall()

    trasferisci = shutil.move if args.sposta else shutil.copy2
    verbo = "spostati" if args.sposta else "copiati"

    conteggi = {}
    mancanti = []
    righe_csv = []

    saltati_altro_anno = 0
    for sha, stato, foto in tutti:
        anno, foto_reg = anni.get(sha, ("ignoto", foto or ""))
        if args.anno and anno != args.anno:
            saltati_altro_anno += 1
            continue

        voce = da_ripassare.get(sha)
        if voce is not None:
            sotto = os.path.join("da_ripassare", voce.sospetto.value)
            motivo = voce.motivo
        else:
            sotto = "ok"
            motivo = "valido e completo"

        sorgente = os.path.join(DIR_RITAGLI, f"{sha}.jpg")
        if not os.path.isfile(sorgente):
            mancanti.append(sha)
            continue

        cartella = os.path.join(args.destinazione, anno, sotto)
        os.makedirs(cartella, exist_ok=True)
        trasferisci(sorgente, os.path.join(cartella, f"{sha}.jpg"))

        chiave = os.path.join(anno, sotto)
        conteggi[chiave] = conteggi.get(chiave, 0) + 1
        righe_csv.append({
            "sha256": sha, "anno": anno, "anno_incerto": "si" if sha in incerti else "",
            "destinazione": sotto, "motivo": motivo,
            "stato_validazione": stato, "foto_origine": foto_reg or foto or "",
            "n_righe": voce.n_righe if voce else "",
            "delta": f"{voce.delta:.2f}" if voce and voce.delta is not None else "",
        })

    base_csv = os.path.join(args.destinazione, args.anno) if args.anno else args.destinazione
    os.makedirs(base_csv, exist_ok=True)
    percorso_csv = os.path.join(base_csv, "inventario.csv")
    with open(percorso_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sha256", "anno", "anno_incerto",
                                          "destinazione", "motivo",
                                          "stato_validazione", "foto_origine",
                                          "n_righe", "delta"])
        w.writeheader()
        w.writerows(sorted(righe_csv, key=lambda r: (r["destinazione"], r["sha256"])))

    print(f"Ritagli {verbo} in {args.destinazione}/\n")
    for sotto in sorted(conteggi):
        print(f"  {sotto:<32} {conteggi[sotto]:>4}")
    totale = sum(conteggi.values())
    print(f"  {'TOTALE':<32} {totale:>4}")
    print(f"\n  inventario -> {percorso_csv}")
    if saltati_altro_anno:
        print(f"  ({saltati_altro_anno} ritagli di altri anni non toccati)")

    visti_incerti = [s for s in incerti if any(r["sha256"] == s for r in righe_csv)]
    if visti_incerti:
        print(f"\n  {len(visti_incerti)} ritagli con anno DEDOTTO dal nome file "
              f"(foto non piu' nelle cartelle sorgente); vedi anno_incerto nel CSV")

    # A receipt in the database whose crop is gone is a real inconsistency, not
    # noise: say it out loud instead of silently moving fewer files.
    if mancanti:
        print(f"\n  ATTENZIONE: {len(mancanti)} ritagli nel database ma assenti "
              f"da {DIR_RITAGLI}/")
        for sha in mancanti[:5]:
            print(f"    {sha}")
        if len(mancanti) > 5:
            print(f"    ... e altri {len(mancanti) - 5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
