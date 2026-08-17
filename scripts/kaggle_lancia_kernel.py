"""Spinge su Kaggle il kernel di estrazione e lo esegue su GPU.

    uv run python scripts/kaggle_lancia_kernel.py            # prova a vuoto
    uv run python scripts/kaggle_lancia_kernel.py --esegui   # spinge e avvia
    uv run python scripts/kaggle_lancia_kernel.py --stato    # a che punto e'
    uv run python scripts/kaggle_lancia_kernel.py --scarica  # prende l'output

Esegue `notebooks/kaggle_estrai_gpu.py` dove una GPU esiste: qui il prefill di
uno scontrino costa ~29 s (misurato, nessuna GPU sulla macchina), su T4 e' sotto
il secondo.

## Privato, come il dataset

`is_private: true`. Un kernel pubblica il codice **e l'output**, e qui l'output
contiene negozi, date e importi degli acquisti dell'utente. Lo script rifiuta di
spingere se il flag e' diverso.

## Script, non notebook

`kernel_type: script` gira dall'inizio alla fine e termina, che e' cio' che serve
a un lavoro batch. I marcatori `# %%` restano leggibili nell'editor di Kaggle, ma
niente dipende dalle magie di IPython: l'installazione usa `subprocess`.
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
SORGENTE = ROOT / "notebooks" / "kaggle_estrai_gpu.py"
STAGING = ROOT / "data" / "kaggle_kernel"
USCITA = ROOT / "data" / "kaggle_output"

# ⚠️ Lo slug DEVE corrispondere al titolo, altrimenti Kaggle ne genera uno suo
# diverso dall'id richiesto, e da li' in poi `--stato` e `--scarica` cercano un
# kernel che non esiste. Titolo con parole semplici, slug identico in kebab-case.
SLUG = "ticket-tracer-estrazione-gpu"
TITOLO = "ticket tracer estrazione gpu"

# ⛔️ La T4 va chiesta ESPLICITAMENTE. Lasciando scegliere a Kaggle arriva una
# P100 (capability CUDA sm_60), mentre il PyTorch preinstallato parte da sm_70:
# il modello si carica, scarica i pesi, e muore alla prima inferenza con
# "CUDA error: no kernel image is available for execution on the device".
# L'avviso e' nel log ma NON ferma l'esecuzione: sembra innocuo ed e' la causa.
# ⚠️ Maiuscola iniziale: `nvidiaTeslaT4` viene accettato senza errore e IGNORATO
# — la CLI non valida il valore e arriva comunque la P100.
ACCELERATORE = "NvidiaTeslaT4"
DATASET = "ticket-tracer-ocr"


def utente() -> str:
    """Lo username, dedotto dai propri dataset. Vuoto se non deducibile.

    Col token nuovo `KGAT_` lo username non e' nel file delle credenziali.
    Si usa `csv` e non `split(",")`: un titolo con una virgola produrrebbe uno
    username sbagliato, cioe' un kernel creato nel posto sbagliato.
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


def prepara(nome_utente: str, dataset: str) -> Path:
    """Cartella con il codice e il `kernel-metadata.json`."""
    if not SORGENTE.exists():
        raise SystemExit(f"⛔️ kernel non trovato: {SORGENTE}")
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)
    shutil.copy(SORGENTE, STAGING / SORGENTE.name)

    metadata = {
        "id": f"{nome_utente}/{SLUG}",
        "title": TITOLO,
        "code_file": SORGENTE.name,
        "language": "python",
        "kernel_type": "script",
        # ⛔️ Il kernel contiene il codice E l'output: negozi, date e importi
        # degli acquisti dell'utente. Privato, come il dataset.
        "is_private": True,
        "enable_gpu": True,
        # Ridondante con --accelerator, ma il metadata e' cio' che resta se un
        # domani il kernel si rilancia dall'interfaccia invece che da qui.
        "machine_shape": ACCELERATORE,
        "enable_tpu": False,
        # Serve a scaricare i pesi del modello da Hugging Face.
        "enable_internet": True,
        "dataset_sources": [f"{nome_utente}/{dataset}"],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (STAGING / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2))
    return STAGING


def controlla(cartella: Path) -> None:
    """Non si spinge nulla se privacy e GPU non sono affermate esplicitamente."""
    metadata = json.loads((cartella / "kernel-metadata.json").read_text())
    if str(metadata.get("is_private", "")).lower() != "true":
        raise SystemExit(
            f"⛔️ is_private={metadata.get('is_private')!r}: NON spingo nulla. "
            "Il kernel pubblicherebbe codice e risultati sugli acquisti dell'utente."
        )
    if str(metadata.get("enable_gpu", "")).lower() != "true":
        raise SystemExit(
            "⛔️ enable_gpu non e' true: senza GPU questo lavoro costa ~40-75 s per "
            "scontrino, ed e' esattamente cio' da cui stiamo scappando."
        )
    if metadata.get("machine_shape") != "NvidiaTeslaT4":
        raise SystemExit(
            f"⛔️ machine_shape={metadata.get('machine_shape')!r}: serve esattamente "
            "'NvidiaTeslaT4'. Una P100 non e' compatibile col PyTorch preinstallato "
            "e il kernel muore dopo aver scaricato i pesi."
        )


def stato(riferimento: str) -> str:
    esito = subprocess.run(
        ["kaggle", "kernels", "status", riferimento],
        capture_output=True,
        text=True,
        check=False,
    )
    return (esito.stdout or esito.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esegui", action="store_true", help="spinge e avvia davvero")
    parser.add_argument("--stato", action="store_true", help="a che punto e' l'esecuzione")
    parser.add_argument("--scarica", action="store_true", help="scarica l'output prodotto")
    parser.add_argument("--utente", default="")
    parser.add_argument("--dataset", default=DATASET, help="slug del dataset in ingresso")
    args = parser.parse_args()

    nome_utente = args.utente or utente()
    if not nome_utente:
        raise SystemExit("username Kaggle non deducibile: passalo con --utente <nome>")
    riferimento = f"{nome_utente}/{SLUG}"

    if args.stato:
        print(stato(riferimento))
        return 0

    if args.scarica:
        USCITA.mkdir(parents=True, exist_ok=True)
        esito = subprocess.run(
            ["kaggle", "kernels", "output", riferimento, "-p", str(USCITA)],
            capture_output=True,
            text=True,
            check=False,
        )
        print((esito.stdout or esito.stderr).strip())
        prodotti = sorted(USCITA.glob("*.json"))
        if not prodotti:
            print("⚠️ nessun JSON: l'esecuzione potrebbe non essere finita (--stato)")
            return 1
        for percorso in prodotti:
            print(f"  {percorso.name} ({percorso.stat().st_size / 1024:.0f} KB)")
        return 0

    cartella = prepara(nome_utente, args.dataset)
    controlla(cartella)
    print(f"kernel pronto in {cartella}")
    print(f"  id: {riferimento}   privato: si'   GPU: {ACCELERATORE}")
    print(f"  dataset in ingresso: {nome_utente}/{args.dataset}")

    if not args.esegui:
        print("\nPROVA A VUOTO. Con --esegui spingerei e avvierei l'esecuzione su GPU.")
        return 0

    esito = subprocess.run(
        ["kaggle", "kernels", "push", "-p", str(cartella), "--accelerator", ACCELERATORE],
        capture_output=True,
        text=True,
        check=False,
    )
    print((esito.stdout or esito.stderr).strip())
    if esito.returncode != 0:
        return 1

    print(f"\nstato: {stato(riferimento)}")
    print(
        "\nIl push avvia anche l'esecuzione. Poi:\n"
        "  uv run python scripts/kaggle_lancia_kernel.py --stato\n"
        "  uv run python scripts/kaggle_lancia_kernel.py --scarica"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
