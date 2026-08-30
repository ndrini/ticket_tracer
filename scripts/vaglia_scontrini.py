"""Separa gli scontrini CHIUSI da quelli che vanno ripassati.

    uv run python scripts/vaglia_scontrini.py                 # solo il rapporto
    uv run python scripts/vaglia_scontrini.py --archivia      # sposta i chiusi
    uv run python scripts/vaglia_scontrini.py --archivia --qualita 60

## Il criterio

Uno scontrino e' CHIUSO quando la somma delle sue righe quadra col totale
stampato (entro 2 centesimi) E ogni riga ha un nome. Non "tutti i prodotti che
stanno sulla carta": quelli non sono verificabili senza rileggerli a mano. Se i
conti tornano, cio' che si ha e' coerente e si puo' mettere via.

Gli altri restano DA_RIPASSARE, divisi per motivo, cosi' una tecnica futura
(template per catena, modelli nuovi) puo' attaccare un gruppo per volta invece
di rifare tutto.

## Cosa fa concretamente

    <destinazione>/chiusi/<sha>.jpg          ritaglio compresso, si archivia
    <destinazione>/da_ripassare/<motivo>/    ritaglio a piena qualita'
    <destinazione>/inventario.csv            una riga per scontrino

I chiusi vengono ricompressi perche' sono finiti: servono solo come prova
d'origine di un dato gia' estratto. Quelli da ripassare restano intatti, perche'
qualcuno dovra' rileggerli.

NON tocca il database e NON cancella i ritagli originali: e' un vaglio, non una
migrazione.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.etl.chiusura import esamina, somma_righe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STRUTTURATI = ROOT / "data" / "strutturati_geometrici"
RITAGLI = ROOT / "data" / "ritagli"

def comprimi(sorgente: Path, destinazione: Path, qualita: int) -> bool:
    """Ricomprime il ritaglio. False se manca Pillow o l'immagine e' illeggibile."""
    try:
        from PIL import Image
        with Image.open(sorgente) as im:
            im.convert("RGB").save(destinazione, "JPEG",
                                   quality=qualita, optimize=True)
        return True
    except Exception:
        shutil.copy2(sorgente, destinazione)
        return False


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--destinazione", type=Path,
                   default=Path("/mnt/condivisa/scontrini_processati"))
    p.add_argument("--archivia", action="store_true",
                   help="scrive i file; senza, stampa solo il rapporto")
    p.add_argument("--qualita", type=int, default=70,
                   help="qualita' JPEG per i ritagli chiusi (default 70)")
    args = p.parse_args(argv)

    percorsi = sorted(STRUTTURATI.glob("*.json"))
    if not percorsi:
        raise SystemExit(f"nessuno scontrino in {STRUTTURATI}/")

    conteggi, righe_csv = {}, []
    valore_chiuso = valore_aperto = 0.0

    for percorso in percorsi:
        dati = json.loads(percorso.read_text())
        sha = dati.get("sha256") or percorso.stem
        stato, motivo = esamina(dati)
        items = dati.get("items") or []
        somma = somma_righe(dati)

        chiave = "chiusi" if stato == "chiuso" else f"da_ripassare/{motivo}"
        conteggi[chiave] = conteggi.get(chiave, 0) + 1
        if stato == "chiuso":
            valore_chiuso += dati.get("total") or 0
        else:
            valore_aperto += dati.get("total") or somma

        righe_csv.append({
            "sha256": sha, "stato": stato, "motivo": motivo,
            "negozio": dati.get("shop_name") or "",
            "data": dati.get("date") or "",
            "totale": dati.get("total") if dati.get("total") is not None else "",
            "somma_righe": somma, "n_righe": len(items),
            "righe_senza_nome": sum(1 for i in items
                                    if not (i.get("name") or "").strip()),
        })

        if args.archivia:
            sorgente = RITAGLI / f"{sha}.jpg"
            if not sorgente.is_file():
                continue
            cartella = args.destinazione / chiave
            cartella.mkdir(parents=True, exist_ok=True)
            if stato == "chiuso":
                comprimi(sorgente, cartella / f"{sha}.jpg", args.qualita)
            else:
                shutil.copy2(sorgente, cartella / f"{sha}.jpg")

    n = len(righe_csv)
    chiusi = conteggi.get("chiusi", 0)
    print(f"{n} scontrini esaminati\n")
    print(f"  {'CHIUSI (quadrano, nomi completi)':<38} {chiusi:>4}  "
          f"{chiusi / n * 100:>3.0f}%   {valore_chiuso:>9.2f} EUR")
    for chiave in sorted(k for k in conteggi if k != "chiusi"):
        q = conteggi[chiave]
        print(f"  {chiave:<38} {q:>4}  {q / n * 100:>3.0f}%")
    print(f"  {'valore ancora da chiudere':<38} {'':>4}       "
          f"{valore_aperto:>9.2f} EUR")

    if args.archivia:
        args.destinazione.mkdir(parents=True, exist_ok=True)
        percorso_csv = args.destinazione / "inventario.csv"
        with open(percorso_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(righe_csv[0]))
            w.writeheader()
            w.writerows(sorted(righe_csv, key=lambda r: (r["stato"], r["motivo"])))
        print(f"\n  scritti in {args.destinazione}/")
        print(f"  inventario -> {percorso_csv}")
    else:
        print("\nRapporto soltanto. Con --archivia scrive i file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
