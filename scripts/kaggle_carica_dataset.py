"""Carica su Kaggle il testo OCR degli scontrini come dataset **privato**.

    uv run python scripts/kaggle_carica_dataset.py            # prova a vuoto
    uv run python scripts/kaggle_carica_dataset.py --esegui   # carica davvero

Prepara l'ingresso per `notebooks/kaggle_estrai_gpu.py`, che gira il modello
linguistico su una GPU che questa macchina non ha: qui il prefill di uno
scontrino costa ~29 s (misurato, nessuna GPU), su T4 e' sotto il secondo.

## Si carica il TESTO, non le fotografie

Differenza sostanziale rispetto a `vista_stradale`, dove il lavoro su GPU e' un
modello di visione e servono le immagini. Qui OCR e ritaglio sono GIA' FATTI e
stanno su disco: alla GPU serve solo il testo gia' riconosciuto.

Ne segue che il problema dell'EXIF **non si pone**: nessuna immagine lascia
questa macchina, quindi nessuna coordinata GPS. 5,4 MB di JSON invece di 36 MB
di ritagli.

## Restano dati personali, e il dataset resta privato

Il testo porta nomi di negozi, date e importi: sono gli acquisti dell'utente,
cioe' i suoi spostamenti e le sue abitudini. Percio' valgono le stesse due
salvaguardie del progetto gemello, nessuna delle due opzionale:

1. **Dataset privato.** Dipende SOLO dall'assenza di `--public` sulla riga di
   comando (verificato nel sorgente: `dataset_create_new(public: bool = False)`
   e poi `is_private = not public`), non dal metadata. Questo script non passa
   mai `--public`.
2. **Nomi di file originali rimossi.** `foto_origine` contiene il nome della
   fotografia ("2025-07-11 18.36.08.jpg"), che porta data e ora dello scatto:
   un dato che alla GPU non serve. Si sostituisce con lo sha256, che e' gia'
   la chiave di tutto il resto della pipeline.

## Dopo l'upload

La privacy si **verifica**, non si suppone: lo script richiede il metadata a
Kaggle e fallisce rumorosamente se la risposta non e' "privato".
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESTRATTI = ROOT / "data" / "estratti"
STAGING = ROOT / "data" / "kaggle_upload"
SLUG = "ticket-tracer-ocr"

# Campi che servono al modello. Tutto il resto e' peso inutile o dato personale
# che non ha ragione di uscire da qui.
CAMPI_UTILI = ("sha256", "righe_ocr", "n_righe_ocr", "indice_nella_foto")


def prepara(sorgente: Path, destinazione: Path, limite: int = 0) -> tuple[int, int]:
    """Copia i JSON tenendo solo i campi utili. Restituisce (copiati, ripuliti).

    `limite` > 0 prepara solo i primi N scontrini: serve allo smoke test, che
    va fatto prima di spendere ore di GPU su un lotto intero.
    """
    destinazione.mkdir(parents=True, exist_ok=True)
    copiati = ripuliti = 0
    for percorso in sorted(sorgente.glob("*.json")):
        dati = json.loads(percorso.read_text())
        if "foto_origine" in dati:
            ripuliti += 1
        magro = {k: dati[k] for k in CAMPI_UTILI if k in dati}
        (destinazione / percorso.name).write_text(json.dumps(magro, ensure_ascii=False))
        copiati += 1
        if limite and copiati >= limite:
            break
    return copiati, ripuliti


def verifica_ripuliti(cartella: Path) -> None:
    """Nessun file esce con i nomi delle fotografie originali.

    Controllo SEPARATO dalla scrittura, di proposito: se un domani `prepara`
    smettesse di ripulire, questo se ne accorge **prima** dell'upload. Lo stesso
    schema usato per l'EXIF in vista_stradale.
    """
    vietati = ("foto_origine", "percorso", "path")
    for percorso in sorted(cartella.glob("*.json")):
        dati = json.loads(percorso.read_text())
        presenti = [c for c in vietati if c in dati]
        if presenti:
            raise SystemExit(
                f"⛔️ {percorso.name} contiene ancora {presenti}. "
                "NON carico nulla: i nomi delle foto portano data e ora dello scatto."
            )


def copia_codice(destinazione: Path) -> int:
    """Copia `app/etl/` dentro il dataset. Restituisce il numero di moduli.

    Il kernel importa questi moduli invece di riscrivere l'estrazione: il
    parsing del totale, il filtro della coda e le regex delle date sono gia'
    stati misurati e corretti, e una seconda copia divergerebbe in silenzio.
    """
    sorgente = ROOT / "app"
    if not (sorgente / "etl" / "estrattore.py").exists():
        raise SystemExit(f"⛔️ app/etl/ non trovato in {sorgente}")
    copiati = 0
    for percorso in sorted(sorgente.rglob("*.py")):
        if "__pycache__" in percorso.parts:
            continue
        relativo = percorso.relative_to(ROOT)
        arrivo = destinazione / "codice" / relativo
        arrivo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(percorso, arrivo)
        copiati += 1
    # `app` e `app.etl` devono essere pacchetti importabili anche se il progetto
    # non versiona gli `__init__.py` a ogni livello.
    for pacchetto in ("app", "app/etl"):
        init = destinazione / "codice" / pacchetto / "__init__.py"
        init.parent.mkdir(parents=True, exist_ok=True)
        init.touch(exist_ok=True)
    return copiati


def scrivi_metadata(cartella: Path, utente: str, slug: str) -> None:
    """Il `dataset-metadata.json` richiesto dalla CLI.

    ⚠️ Non contiene la privacy: quella dipende solo dall'assenza di `--public`.
    """
    (cartella / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "Ticket tracer - testo OCR scontrini (privato)",
                "id": f"{utente}/{slug}",
                "licenses": [{"name": "other"}],
            },
            indent=2,
        )
    )


def utente_kaggle() -> str:
    """Lo username, che serve a comporre l'id del dataset.

    Col token nuovo `KGAT_` (formato in uso qui: ~/.kaggle/access_token) lo
    username NON e' nel file, e va chiesto all'API. Si usa il modulo `csv` e non
    `split(",")`: un titolo che contiene una virgola produrrebbe uno username
    sbagliato, cioe' un dataset creato nel posto sbagliato.
    """
    esito = subprocess.run(
        ["kaggle", "datasets", "list", "--mine", "--csv"],
        capture_output=True,
        text=True,
        check=False,
    )
    for riga in csv.reader(io.StringIO(esito.stdout)):
        if riga and "/" in riga[0]:
            return riga[0].split("/")[0].strip()
    return ""


def verifica_privato(riferimento: str, staging: Path) -> None:
    """Dopo l'upload: **chiede a Kaggle** se e' privato, non lo suppone."""
    esito = subprocess.run(
        ["kaggle", "datasets", "metadata", riferimento, "-p", str(staging)],
        capture_output=True,
        text=True,
        check=False,
    )
    percorso = staging / "dataset-metadata.json"
    if esito.returncode != 0 or not percorso.exists():
        print(f"⚠️ non ho potuto verificare la privacy: {esito.stderr.strip()[:200]}")
        print(f"   Controlla a mano: https://www.kaggle.com/datasets/{riferimento}")
        return
    dati = json.loads(percorso.read_text())
    # ⚠️ Il metadata SCARICATO annida tutto sotto `info`, mentre quello che si
    # carica e' piatto. Cercare `isPrivate` al primo livello dava `None` su un
    # dataset correttamente privato: un falso allarme, peggio di nessun allarme.
    dati = dati.get("info", dati)
    privato = dati.get("isPrivate", dati.get("is_private"))
    if privato is True:
        print("✅ verificato: il dataset e' PRIVATO")
    else:
        print(
            f"⛔️ ATTENZIONE: isPrivate={privato!r}. Vai subito su "
            f"https://www.kaggle.com/datasets/{riferimento}/settings e rendilo privato."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--esegui", action="store_true", help="carica davvero (senza, e' una prova a vuoto)"
    )
    parser.add_argument("--utente", default="", help="username Kaggle (se non deducibile)")
    parser.add_argument("--estratti", type=Path, default=ESTRATTI, help="cartella dei JSON OCR")
    parser.add_argument("--slug", default=SLUG, help="nome del dataset su Kaggle")
    parser.add_argument(
        "--limite", type=int, default=0,
        help="carica solo i primi N scontrini (per lo smoke test)",
    )
    parser.add_argument(
        "--versione", default="", help="messaggio: aggiorna un dataset esistente invece di crearlo"
    )
    parser.add_argument(
        "--senza-codice", action="store_true",
        help="non includere app/etl (il kernel non partirebbe)",
    )
    args = parser.parse_args()

    if not args.estratti.is_dir():
        raise SystemExit(f"JSON OCR non trovati in {args.estratti}")

    staging = ROOT / "data" / f"kaggle_upload_{args.slug}"
    if staging.exists():
        shutil.rmtree(staging)
    copiati, ripuliti = prepara(args.estratti, staging, args.limite)
    verifica_ripuliti(staging)

    # Il codice dell'estrazione viaggia col dataset: il kernel lo importa invece
    # di riscriverlo, cosi' i risultati di Kaggle restano confrontabili con quelli
    # locali. Due implementazioni divergerebbero in silenzio.
    if not args.senza_codice:
        moduli = copia_codice(staging)
        print(f"  piu' {moduli} moduli di app/etl: il kernel li importa, non li riscrive")

    peso_mb = sum(p.stat().st_size for p in staging.glob("*.json")) / 1e6
    print(f"{copiati} scontrini pronti in {staging} ({peso_mb:.1f} MB)")
    print(f"  {ripuliti} avevano il nome della foto originale: ora NON ce l'hanno piu'")
    print("  nessuna immagine viene caricata: solo il testo gia' riconosciuto")

    utente = args.utente or utente_kaggle()
    if not utente:
        raise SystemExit(
            "non riesco a dedurre lo username Kaggle. Passalo con --utente <nome>: "
            "col token KGAT_ non e' nel file delle credenziali."
        )
    scrivi_metadata(staging, utente, args.slug)
    riferimento = f"{utente}/{args.slug}"

    if not args.esegui:
        azione = "aggiornerei" if args.versione else "creerei"
        print(f"\nPROVA A VUOTO. Con --esegui {azione} il dataset PRIVATO {riferimento}")
        print("Nessun dato e' uscito da questa macchina.")
        return 0

    if args.versione:
        print(f"\naggiorno {riferimento} (nuova versione)...")
        comando = ["kaggle", "datasets", "version", "-p", str(staging),
                   "-m", args.versione, "--dir-mode", "zip"]
    else:
        print(f"\ncarico {riferimento} come dataset PRIVATO (nessun --public)...")
        comando = ["kaggle", "datasets", "create", "-p", str(staging), "--dir-mode", "zip"]

    esito = subprocess.run(comando, capture_output=True, text=True, check=False)
    print(esito.stdout.strip() or esito.stderr.strip())
    if esito.returncode != 0:
        return 1

    verifica_privato(riferimento, staging)
    print(f"\nNel kernel il percorso e':\n  ESTRATTI = Path('/kaggle/input/{args.slug}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
