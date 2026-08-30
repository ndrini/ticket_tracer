"""Manda su Drive il testo estratto: i JSON strutturati e il database.

    uv run python scripts/sincronizza_dati_drive.py            # dice cosa farebbe
    uv run python scripts/sincronizza_dati_drive.py --esegui   # lo fa

Sta accanto a sincronizza_drive.py, che porta su le immagini, e non lo tocca:
insieme mettono nello stesso posto la fonte primaria (la foto) e cio' che ne
abbiamo ricavato (il testo). Sono separati perche' hanno regole diverse.

## Due regole diverse, e non e' un capriccio

    strutturati/<sha>.json   immutabile   si salta se c'e' gia'
    database/spese-AAAA-MM-GG.db  mutevole   nuova copia a ogni passata

Un JSON strutturato descrive UNO scontrino ed e' finito: una volta scritto non
cambia piu', quindi si carica una volta sola e le passate successive lo saltano,
esattamente come le immagini.

Il database invece cambia a ogni fase. Sovrascriverlo sempre allo stesso nome
farebbe sparire la versione precedente, e con essa la possibilita' di accorgersi
che una fase ha peggiorato le cose. Percio' ogni copia porta la data: costano
poche decine di KB l'una e sono l'unica rete di sicurezza che abbiamo.

## Il database di oggi NON e' l'archivio

Al momento data/test_spese.db contiene un solo record, con image_sha256 a NULL:
la fase D non e' mai stata eseguita. Lo si carica lo stesso, perche' e' cio' che
c'e' e averlo su Drive non fa danno, ma il dato vero sta nei JSON. Chi legge fra
sei mesi merita di saperlo senza doverlo scoprire da solo.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
STRUTTURATI = ROOT / "data" / "strutturati_geometrici"
DATABASE = ROOT / "data" / "test_spese.db"


def righe_nel_db(percorso: Path) -> str:
    """Quante ricevute ci sono davvero, per non caricare alla cieca."""
    if not percorso.is_file():
        return "assente"
    try:
        with sqlite3.connect(f"file:{percorso}?mode=ro", uri=True) as conn:
            n = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            con_sha = conn.execute(
                "SELECT COUNT(image_sha256) FROM receipts"
            ).fetchone()[0]
        return f"{n} ricevute, {con_sha} con sha"
    except sqlite3.Error as errore:
        return f"illeggibile: {errore}"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--esegui", action="store_true",
                   help="carica davvero; senza, dice solo cosa farebbe")
    p.add_argument("--radice", default="ticket-tracer")
    p.add_argument("--senza-db", action="store_true",
                   help="carica solo i JSON, non il database")
    args = p.parse_args(argv)

    json_locali = sorted(STRUTTURATI.glob("*.json"))
    if not json_locali:
        raise SystemExit(f"nessuno strutturato in {STRUTTURATI}/")

    peso_json = sum(f.stat().st_size for f in json_locali)
    print(f"  strutturati (json)   {len(json_locali):>4}  "
          f"{peso_json / 1e6:.1f} MB")
    if not args.senza_db:
        print(f"  database             {'1':>4}  "
              f"{DATABASE.stat().st_size / 1e6:.2f} MB  "
              f"({righe_nel_db(DATABASE)})")
    print()

    if not args.esegui:
        print("Prova soltanto. Con --esegui carica davvero.")
        return 0

    from app.storage.drive import ArchivioDrive
    archivio = ArchivioDrive(radice=args.radice)

    # Una sola interrogazione invece di un esiste() per file: con 325 file
    # sarebbero 325 viaggi di rete per sapere una cosa sola.
    presenti = set(archivio.elenca("strutturati/"))
    print(f"  gia' su Drive: {len(presenti)} strutturati\n")

    caricati = saltati = falliti = 0
    for percorso in json_locali:
        chiave = f"strutturati/{percorso.name}"
        if chiave in presenti:
            saltati += 1
            continue
        try:
            archivio.scrivi(chiave, percorso.read_bytes())
            caricati += 1
        except Exception as errore:        # un file non deve fermare gli altri
            falliti += 1
            print(f"    FALLITO {chiave}: {errore}")
        if caricati and caricati % 50 == 0:
            print(f"    ...{caricati} caricati")

    if not args.senza_db and DATABASE.is_file():
        # Datato, mai sovrascritto: vedi il perche' nel docstring.
        chiave = f"database/spese-{date.today().isoformat()}.db"
        try:
            archivio.scrivi(chiave, DATABASE.read_bytes())
            print(f"\n  database -> {chiave}")
            caricati += 1
        except Exception as errore:
            falliti += 1
            print(f"\n    FALLITO {chiave}: {errore}")

    print(f"\n  caricati {caricati}, gia' presenti {saltati}, falliti {falliti}")
    if falliti:
        print("  Rilancia: i falliti si riprovano, i riusciti si saltano.")
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
