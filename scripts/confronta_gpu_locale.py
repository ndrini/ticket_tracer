"""Confronta i risultati prodotti su GPU con quelli gia' ottenuti in locale.

    uv run python scripts/confronta_gpu_locale.py

La domanda non e' "la GPU e' piu' veloce" — quello e' ovvio — ma **se produce
gli stessi dati**. Una pipeline piu' veloce che estrae peggio non serve a nulla.

## Le metriche di guardia, dichiarate PRIMA di misurare

Come impone il metodo (sezione 4), il confronto e' deciso in anticipo:

- **scontrini col totale**: non deve calare (il totale si legge per coordinate,
  quindi dovrebbe essere IDENTICO: se cambia, e' un difetto del trasporto)
- **scontrini quadrati** (somma prodotti == totale): non deve calare
- **prodotti estratti**: non deve calare in modo sistematico
- **negozi identificati**: non deve calare

Un peggioramento di una qualunque, anche a fronte di un guadagno di tempo,
conta come fallimento: il tempo non compra qualita'.

Le differenze sui singoli campi vengono ELENCATE, non solo contate: un numero
aggregato uguale puo' nascondere due errori che si compensano.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALI = ROOT / "data" / "strutturati"
GPU = ROOT / "data" / "kaggle_output" / "estratti_gpu.json"
TOLLERANZA = 0.02


def quadra(record) -> bool:
    totale = record.get("total")
    if not totale:
        return False
    somma = sum(i.get("price", 0) for i in record.get("items") or [])
    return abs(somma - totale) < TOLLERANZA


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", type=Path, default=GPU)
    parser.add_argument("--locali", type=Path, default=LOCALI)
    args = parser.parse_args()

    if not args.gpu.exists():
        raise SystemExit(
            f"⛔️ {args.gpu} non c'e'. Scaricalo prima:\n"
            "  uv run python scripts/kaggle_lancia_kernel.py --scarica"
        )

    da_gpu = {r["sha256"]: r for r in json.loads(args.gpu.read_text())}
    da_locale = {}
    for percorso in glob.glob(str(args.locali / "*.json")):
        record = json.loads(Path(percorso).read_text())
        if record.get("sha256") in da_gpu:
            da_locale[record["sha256"]] = record

    comuni = sorted(set(da_gpu) & set(da_locale))
    if not comuni:
        raise SystemExit("⛔️ nessuno scontrino in comune: non c'e' niente da confrontare")

    print(f"{len(comuni)} scontrini confrontabili (su {len(da_gpu)} elaborati su GPU)\n")

    def conta(sorgente, chiave):
        return sum(1 for s in comuni if sorgente[s].get(chiave))

    righe = [
        ("con totale", conta(da_locale, "total"), conta(da_gpu, "total")),
        ("con negozio", conta(da_locale, "shop_name"), conta(da_gpu, "shop_name")),
        ("con data", conta(da_locale, "date"), conta(da_gpu, "date")),
        (
            "quadrati",
            sum(1 for s in comuni if quadra(da_locale[s])),
            sum(1 for s in comuni if quadra(da_gpu[s])),
        ),
        (
            "prodotti totali",
            sum(len(da_locale[s].get("items") or []) for s in comuni),
            sum(len(da_gpu[s].get("items") or []) for s in comuni),
        ),
    ]

    print(f"{'metrica':20} {'locale':>8} {'GPU':>8}   esito")
    peggiorate = []
    for nome, loc, gpu in righe:
        if gpu < loc:
            esito = f"⛔️ PEGGIORA ({gpu - loc})"
            peggiorate.append(nome)
        elif gpu > loc:
            esito = f"migliora (+{gpu - loc})"
        else:
            esito = "uguale"
        print(f"{nome:20} {loc:8} {gpu:8}   {esito}")

    # I totali devono essere IDENTICI: si leggono per coordinate, non col
    # modello. Una differenza qui non e' una variazione del modello ma un
    # difetto nel trasporto dei dati, ed e' piu' grave.
    diversi = [
        s for s in comuni if da_locale[s].get("total") != da_gpu[s].get("total")
    ]
    print(f"\ntotali diversi fra locale e GPU: {len(diversi)}")
    if diversi:
        print("  ⛔️ il totale si legge per COORDINATE, non col modello: dovrebbe")
        print("     essere identico. Una differenza indica un difetto nel trasporto.")
        for s in diversi[:5]:
            print(f"     {s[:12]}  locale={da_locale[s].get('total')}  gpu={da_gpu[s].get('total')}")

    nomi_diversi = [
        s
        for s in comuni
        if (da_locale[s].get("shop_name") or "").strip().lower()
        != (da_gpu[s].get("shop_name") or "").strip().lower()
    ]
    print(f"\nnegozi con nome diverso: {len(nomi_diversi)}")
    for s in nomi_diversi[:8]:
        print(f"  {s[:12]}  locale={da_locale[s].get('shop_name')!r}  gpu={da_gpu[s].get('shop_name')!r}")

    print()
    if peggiorate or diversi:
        print(f"⛔️ ESITO: NON adottare cosi'. Peggiorano: {', '.join(peggiorate) or 'i totali'}")
        return 1
    print("✅ ESITO: nessuna metrica di guardia peggiora.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
