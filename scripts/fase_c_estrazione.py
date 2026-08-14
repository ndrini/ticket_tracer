"""
Fase C — dal testo OCR ai dati strutturati, uno scontrino per volta.

Legge i file prodotti dalla Fase A (`data/estratti/<hash>.json`), interroga il
modello linguistico locale e scrive `data/strutturati/<hash>.json` con negozio,
data, totale e prodotti.

Come la Fase A, e' IDEMPOTENTE: cio' che e' gia' stato elaborato viene saltato,
quindi rilanciare e' sicuro e riprende da dove si era fermato. Serve perche' una
passata completa dura ore.

Ogni scontrino porta con se' il proprio giudizio: la somma dei prodotti viene
confrontata col totale stampato, e i prezzi implausibili vengono segnalati. Un
risultato che non quadra non viene scartato ma marcato, cosi' i report sanno
sempre quanta parte del totale e' affidabile.

Uso:
    uv run python scripts/fase_c_estrazione.py
    uv run python scripts/fase_c_estrazione.py --limite 10
    uv run python scripts/fase_c_estrazione.py --rifai
    uv run python scripts/fase_c_estrazione.py --modello qwen2.5:3b-instruct
"""
import glob
import json
import logging
import os
import sys
import time
import warnings

import numpy as np

warnings.filterwarnings("ignore")
os.environ.setdefault("GLOG_minloglevel", "3")
sys.path.insert(0, os.getcwd())

from app.etl.estrattore import EstrattoreScontrino  # noqa: E402
from app.etl.plausibilita import controlla_scontrino  # noqa: E402
from app.etl.riduci_testo import riga_utile  # noqa: E402
from app.etl.righe_logiche import testo_ricomposto  # noqa: E402
from app.etl.verifica import TOLLERANZA  # noqa: E402

logging.basicConfig(level=logging.WARNING)

DIR_ESTRATTI = "data/estratti"
DIR_STRUTTURATI = "data/strutturati"

# Sotto questa confidenza media l'OCR ha prodotto testo inaffidabile: passarlo
# al modello costerebbe un minuto per ottenere spazzatura strutturata.
CONFIDENZA_MINIMA = 0.60
RIGHE_MINIME = 8


def testo_per_modello(righe_ocr):
    """Righe ricomposte come sulla carta, senza le parti inutili."""
    righe = testo_ricomposto(righe_ocr).split("\n")
    return "\n".join(r for r in righe if riga_utile(r))


def giudica(dati, totale_dichiarato):
    """
    Confronta la somma dei prodotti col totale e segnala i prezzi strani.

    Restituisce l'esito e i dettagli, senza scartare nulla: uno scontrino che
    non quadra resta un dato, marcato per quello che e'.
    """
    prodotti = dati.get("items") or []
    somma = round(sum(p["price"] for p in prodotti), 2) if prodotti else None
    problemi = controlla_scontrino(prodotti, totale_dichiarato)

    if totale_dichiarato is None:
        esito = "TOTALE_ASSENTE"
    elif somma is None:
        esito = "PRODOTTI_ASSENTI"
    elif abs(somma - totale_dichiarato) <= TOLLERANZA:
        esito = "VALIDO"
    else:
        esito = "SCARTO_ECCESSIVO"

    return {
        "esito": esito,
        "somma_prodotti": somma,
        "scarto": round(somma - totale_dichiarato, 2)
        if (somma is not None and totale_dichiarato is not None) else None,
        "prezzi_sospetti": problemi,
    }


def elabora(percorso, estrattore, rifai=False):
    """Un solo scontrino. Restituisce (elaborato, esito)."""
    with open(percorso) as fh:
        record = json.load(fh)

    digest = record["sha256"]
    destinazione = os.path.join(DIR_STRUTTURATI, digest + ".json")
    if os.path.exists(destinazione) and not rifai:
        return False, "gia_presente"

    righe = record.get("righe_ocr") or []
    if len(righe) < RIGHE_MINIME:
        return False, "troppo_corto"
    confidenza = float(np.mean([r["confidenza"] for r in righe]))
    if confidenza < CONFIDENZA_MINIMA:
        return False, "ocr_inaffidabile"

    testo = testo_per_modello(righe)
    dati = estrattore.estrai(testo, righe)
    giudizio = giudica(dati, dati.get("total"))

    with open(destinazione, "w") as fh:
        json.dump({
            "sha256": digest,
            "foto_origine": record.get("foto_origine"),
            "confidenza_ocr": round(confidenza, 3),
            **dati,
            **giudizio,
            "elaborato_il": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, fh, indent=2, ensure_ascii=False)

    return True, giudizio["esito"]


def main(argv):
    rifai = "--rifai" in argv
    limite = int(argv[argv.index("--limite") + 1]) if "--limite" in argv else None
    modello = argv[argv.index("--modello") + 1] if "--modello" in argv else None

    os.makedirs(DIR_STRUTTURATI, exist_ok=True)
    estrattore = EstrattoreScontrino(modello) if modello else EstrattoreScontrino()

    percorsi = sorted(glob.glob(os.path.join(DIR_ESTRATTI, "*.json")))
    if limite:
        percorsi = percorsi[:limite]

    print(f"Fase C — {len(percorsi)} scontrini da {DIR_ESTRATTI}/")
    print(f"  modello  : {estrattore.modello}")
    print(f"  risultati: {DIR_STRUTTURATI}/\n")

    conteggi = {}
    inizio = time.time()
    for i, percorso in enumerate(percorsi, 1):
        t0 = time.time()
        elaborato, esito = elabora(percorso, estrattore, rifai)
        conteggi[esito] = conteggi.get(esito, 0) + 1
        if elaborato:
            print(f"  [{i:3d}/{len(percorsi)}] {esito:<18} {time.time() - t0:5.0f}s")

    durata = time.time() - inizio
    print(f"\nesiti su {len(percorsi)} scontrini:")
    for esito, n in sorted(conteggi.items(), key=lambda z: -z[1]):
        print(f"  {esito:<20} {n:4d}")
    print(f"\nTempo: {durata / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
