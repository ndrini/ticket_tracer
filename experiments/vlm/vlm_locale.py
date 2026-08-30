"""Legge i ritagli con un VLM locale via Ollama, senza dipendere da Kaggle.

    uv run python scripts/vlm_locale.py                      # llava:7b
    uv run python scripts/vlm_locale.py --modello qwen2.5vl:3b
    uv run python scripts/vlm_locale.py --limite 3           # prova corta

Scrive lo stesso formato che produce il kernel su Kaggle
(`data/kaggle_output/vlm_risultati.json`), cosi' `confronta_vlm_geometrico.py`
legge indifferentemente l'uno o l'altro.

## Perche' esiste

Il kernel su Kaggle e' fallito quattro volte di fila per ragioni tutte esterne
al modello: versioni di transformers, file non serviti, e soprattutto un
percorso di montaggio del dataset che cambia a ogni esecuzione. Qui non c'e'
niente da montare e niente da versionare: se la GPU manca si paga in tempo, ma
il risultato arriva.

## Piu' lento, e quanto lo dice la misura

Senza GPU il prefill di un'immagine costa decine di secondi. Il numero vero si
vede col primo scontrino e viene stampato subito, cosi' si puo' decidere se
aspettare o fermarsi PRIMA di aver avviato tutto il lotto.

## Non decide niente

Produce la lettura del VLM, come il kernel. Il confronto col totale stampato,
la metrica e le metriche di guardia stanno in confronta_vlm_geometrico.py e in
docs/122_metrica_confronto_vlm.md.
"""
from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RITAGLI = ROOT / "data" / "ritagli"
USCITA = ROOT / "data" / "kaggle_output" / "vlm_risultati.json"
OLLAMA = "http://localhost:11434/api/generate"

PROMPT = """You are an assistant that extracts structured product data from receipt images.

TASK: Extract ONLY purchased items (products with prices).

RULES:
1. Return ONLY valid JSON, no other text
2. Ignore: headers, totals, VAT, subtotals, discounts, empty lines, merchant info
3. Extract each item with name and price in decimal format (X.XX)
4. If multiple items on same line, extract each separately
5. If quality is poor or no items found, return: []

FORMAT:
[
  {"name": "product name", "price": X.XX},
  {"name": "another product", "price": Y.YY}
]"""


def campione(db: Path) -> list[tuple[int, str]]:
    """The crops a human judged as correctly cut: same sample as on Kaggle."""
    conn = sqlite3.connect(db)
    righe = conn.execute("""
        SELECT q.receipt_id, r.image_sha256
        FROM manual_review_queue q JOIN receipts r ON r.id = q.receipt_id
        WHERE q.reason LIKE 'taglio:ok%' AND q.completed_at IS NOT NULL
        ORDER BY q.receipt_id""").fetchall()
    conn.close()
    return righe


def estrai_json(testo: str):
    """Pull the JSON array out of the answer; None if there is none.

    A parse failure must not look like "found no products": they are different
    failures and the guard metrics count them separately.
    """
    inizio, fine = testo.find("["), testo.rfind("]")
    if inizio == -1 or fine == -1 or fine < inizio:
        return None
    try:
        return json.loads(testo[inizio:fine + 1])
    except json.JSONDecodeError:
        return None


def interroga(modello: str, immagine: bytes, timeout: int):
    corpo = json.dumps({
        "model": modello,
        "prompt": PROMPT,
        "images": [base64.b64encode(immagine).decode()],
        "stream": False,
        # Deterministic, like do_sample=False in the Kaggle kernel: the two
        # readings must be comparable.
        "options": {"temperature": 0},
    }).encode()
    richiesta = urllib.request.Request(
        OLLAMA, data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
        return json.loads(risposta.read())["response"]


def ollama_attivo() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        return True
    except (urllib.error.URLError, OSError):
        return False


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=ROOT / "data" / "spese.db")
    p.add_argument("--modello", default="llava:7b")
    p.add_argument("--limite", type=int, default=0, help="solo i primi N")
    p.add_argument("--timeout", type=int, default=600, help="secondi per scontrino")
    p.add_argument("--uscita", type=Path, default=USCITA)
    args = p.parse_args(argv)

    if not ollama_attivo():
        print("Ollama non risponde su localhost:11434. Lo avvio...")
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(1)
            if ollama_attivo():
                break
        else:
            raise SystemExit("Ollama non si avvia: prova 'ollama serve' a mano.")

    righe = campione(args.db)
    if args.limite:
        righe = righe[:args.limite]
    if not righe:
        raise SystemExit("nessuno scontrino col taglio:ok. Rivedine qualcuno prima.")

    print(f"{len(righe)} ritagli, modello {args.modello}\n")
    risultati = []
    inizio = time.time()

    for n, (receipt_id, sha) in enumerate(righe, 1):
        percorso = RITAGLI / f"{sha}.jpg"
        esito = {"receipt_id": receipt_id, "sha256": sha}
        if not percorso.is_file():
            esito.update(stato="errore", errore="ritaglio assente", prodotti=None)
            risultati.append(esito)
            continue

        try:
            t0 = time.time()
            risposta = interroga(args.modello, percorso.read_bytes(), args.timeout)
            esito["secondi"] = round(time.time() - t0, 1)
            prodotti = estrai_json(risposta)
            esito["prodotti"] = prodotti
            esito["risposta_grezza"] = risposta
            esito["stato"] = "ok" if prodotti is not None else "json_illeggibile"
        except Exception as e:
            esito.update(stato="errore", errore=str(e), prodotti=None)

        risultati.append(esito)
        print(f"[{n:3}/{len(righe)}] #{receipt_id:<4} {esito['stato']:<16} "
              f"{len(esito.get('prodotti') or []):>3} prodotti  "
              f"{esito.get('secondi', 0)}s")

        # After the first one the real cost is known: say how long the whole
        # batch will take, while there is still time to stop it.
        if n == 1 and len(righe) > 1 and esito.get("secondi"):
            stima = esito["secondi"] * len(righe) / 60
            print(f"      -> a questo ritmo il lotto costa ~{stima:.0f} min\n")

        # Written every time: a run interrupted halfway keeps what it has done.
        args.uscita.parent.mkdir(parents=True, exist_ok=True)
        args.uscita.write_text(
            json.dumps(risultati, ensure_ascii=False, indent=1), encoding="utf-8")

    minuti = (time.time() - inizio) / 60
    ok = sum(1 for r in risultati if r["stato"] == "ok")
    print(f"\n{len(risultati)} letti in {minuti:.1f} min -> {args.uscita}")
    print(f"  ok: {ok}   "
          f"json illeggibile: {sum(1 for r in risultati if r['stato'] == 'json_illeggibile')}   "
          f"errori: {sum(1 for r in risultati if r['stato'] == 'errore')}")
    print("\nOra il confronto:")
    print("  uv run python scripts/confronta_vlm_geometrico.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
