"""Manda su Google Drive le miniature, e gli originali dei soli problematici.

    uv run python scripts/sincronizza_drive.py              # dice cosa farebbe
    uv run python scripts/sincronizza_drive.py --esegui     # lo fa
    uv run python scripts/sincronizza_drive.py --esegui --solo-miniature

## Cosa sale, e perche' non tutto

    miniature/<sha>.jpg      TUTTI gli scontrini elaborati      ~7 MB
    originali/<sha>.jpg      SOLO quelli non chiusi             ~19 MB

Uno scontrino CHIUSO quadra col totale e ha tutti i nomi: il dato e' gia'
estratto e verificato, e l'originale a piena risoluzione non serve piu' a
nessuno se non come prova d'origine — per quella basta la miniatura, che resta
leggibile a occhio. Uno NON chiuso invece dovra' essere riletto, da un umano o
da una tecnica futura, e allora servono tutti i pixel.

Mandare i 41 MB interi sarebbe piu' semplice da scrivere e piu' caro da tenere,
per un beneficio che non c'e': e' la stessa ragione per cui il vaglio ricomprime
i chiusi e lascia intatti gli altri.

## E' ripetibile

Salta cio' che e' gia' su Drive con lo stesso nome, quindi si puo' rilanciare
dopo ogni ingestione senza ricaricare tutto. Uno scontrino che da' chiuso in una
passata successiva NON viene ripulito qui: cancellare e' irreversibile e questo
programma non lo fa da solo. Lo dice, con --pulibili, e la decisione resta a te.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.etl.chiusura import esamina  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STRUTTURATI = ROOT / "data" / "strutturati_geometrici"
MINIATURE = ROOT / "data" / "miniature"
RITAGLI = ROOT / "data" / "ritagli"


def stato_per_sha() -> dict[str, str]:
    """sha -> "chiuso" | "da_ripassare", per ogni scontrino strutturato."""
    stati = {}
    for percorso in STRUTTURATI.glob("*.json"):
        try:
            dati = json.loads(percorso.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sha = dati.get("sha256") or percorso.stem
        stati[sha] = esamina(dati)[0]
    return stati


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--esegui", action="store_true",
                   help="carica davvero; senza, dice solo cosa farebbe")
    p.add_argument("--radice", default="ticket-tracer")
    p.add_argument("--solo-miniature", action="store_true",
                   help="non caricare gli originali dei non chiusi")
    p.add_argument("--pulibili", action="store_true",
                   help="elenca gli originali su Drive ormai superflui")
    args = p.parse_args(argv)

    stati = stato_per_sha()
    if not stati:
        raise SystemExit(f"nessuno scontrino in {STRUTTURATI}/")

    # Le miniature sono la verita' su "cosa e' stato elaborato": la tabella
    # esiste solo per cio' che e' passato dalla pipeline.
    miniature = sorted(MINIATURE.glob("*.jpg"))
    non_chiusi = [s for s, stato in stati.items() if stato != "chiuso"]

    da_caricare: list[tuple[str, Path]] = []
    for percorso in miniature:
        da_caricare.append((f"miniature/{percorso.name}", percorso))
    if not args.solo_miniature:
        for sha in sorted(non_chiusi):
            originale = RITAGLI / f"{sha}.jpg"
            if originale.is_file():
                da_caricare.append((f"originali/{sha}.jpg", originale))

    peso = sum(f.stat().st_size for _, f in da_caricare)
    print(f"{len(stati)} scontrini: {len(stati) - len(non_chiusi)} chiusi, "
          f"{len(non_chiusi)} da ripassare\n")
    print(f"  miniature (tutte)          {len(miniature):>4}")
    if not args.solo_miniature:
        originali = sum(1 for k, _ in da_caricare if k.startswith("originali/"))
        print(f"  originali (non chiusi)     {originali:>4}")
    print(f"  in totale                  {len(da_caricare):>4}  "
          f"{peso / 1e6:.1f} MB\n")

    if not args.esegui and not args.pulibili:
        print("Prova soltanto. Con --esegui carica davvero.")
        return 0

    from app.storage.drive import ArchivioDrive
    archivio = ArchivioDrive(radice=args.radice)

    if args.pulibili:
        # Originali caricati quando lo scontrino era aperto, e che ora e'
        # chiuso: non servono piu'. Si ELENCANO, non si cancellano.
        superflui = [k for k in archivio.elenca("originali/")
                     if stati.get(Path(k).stem) == "chiuso"]
        print(f"  {len(superflui)} originali su Drive ora superflui "
              f"(lo scontrino e' chiuso)")
        for chiave in superflui[:20]:
            print(f"    {chiave}")
        if superflui:
            print("\n  Non li cancello da solo: cancellare e' irreversibile.")
        return 0

    # Si chiede a Drive UNA volta cosa c'e' gia', invece di un esiste() per
    # file: con centinaia di file sarebbero centinaia di viaggi di rete.
    presenti = set(archivio.elenca("miniature/"))
    if not args.solo_miniature:
        presenti |= set(archivio.elenca("originali/"))
    print(f"  gia' su Drive: {len(presenti)}\n")

    caricati = saltati = falliti = 0
    for chiave, percorso in da_caricare:
        if chiave in presenti:
            saltati += 1
            continue
        try:
            archivio.scrivi(chiave, percorso.read_bytes())
            caricati += 1
        except Exception as errore:            # una foto non deve fermare tutto
            falliti += 1
            print(f"    FALLITO {chiave}: {errore}")
        if caricati and caricati % 25 == 0:
            print(f"    ...{caricati} caricati")

    print(f"\n  caricati {caricati}, gia' presenti {saltati}, falliti {falliti}")
    if falliti:
        print("  Rilancia: i falliti si riprovano, i riusciti si saltano.")

    # Si lascia la nota per la pagina di elaborazione, cosi' puo' dire quanto
    # c'e' lassu' senza chiederlo a Drive a ogni caricamento.
    # Si RICHIEDE a Drive cosa c'e' davvero, invece di sommare i previsti: con
    # dei falliti la somma sarebbe gonfiata, e la pagina direbbe che le immagini
    # sono al sicuro quando non lo sono. Una chiamata sola, a lavoro finito.
    from app.revisione.riassunto import annota_drive
    annota_drive(ROOT / "data",
                 miniature=len(list(archivio.elenca("miniature/"))),
                 originali=len(list(archivio.elenca("originali/"))))
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
