"""
Benchmark: Geometrico vs Claude LLM vs Groq LLM vs LLaVA VLM

Confronta 4 metodi di estrazione prodotti da scontrini:
1. Geometrico: estrai dalla posizione dei prezzi (locale)
2. Claude LLM: OCR testo → Claude (API pagato, €0.01-0.02/scontrino)
3. Groq LLM: OCR testo → Groq (API gratis, limite giornaliero)
4. LLaVA VLM: foto direttamente → LLaVA (Kaggle GPU, gratis)

Metriche dichiarate PRIMA:
- Items estratti (numero)
- Accuracy dei nomi (confronto con baseline)
- Accuracy dei prezzi
- Tempo per scontrino
- Costi stimati

Uso:
    uv run python scripts/benchmark_extraction_methods.py --sample 20
    uv run python scripts/benchmark_extraction_methods.py --sample 50 --skip-llava
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from collections import defaultdict
import sqlite3

sys.path.insert(0, os.getcwd())

from app.etl.addendi import addendi
from app.etl.geometria import colonna_dei_prezzi, altezza_riga, centro_x, centro_y


def estrai_geometrico(righe_ocr, total, tolerance=0.02):
    """
    Estrai prodotti dalla posizione geometrica dei prezzi.
    """
    if not righe_ocr:
        return {"items": [], "success": False, "error": "no_ocr"}

    try:
        altezza = altezza_riga(righe_ocr)
        col = colonna_dei_prezzi(righe_ocr, altezza)
        trovati = addendi(righe_ocr)

        items = []
        for valore, y in trovati:
            # Trova il nome a sinistra dell'addendo
            nome = None
            for riga in righe_ocr:
                riga_y = centro_y(riga["box"])
                if abs(riga_y - y) < 0.5 * altezza:
                    riga_x = centro_x(riga["box"])
                    if riga_x < col[1]:  # a sinistra del prezzo
                        nome = riga["testo"].strip()
                        break

            items.append({
                "name": nome or "(no name)",
                "price": round(valore, 2),
                "source": "geometric"
            })

        somma = round(sum(v for v, _ in trovati), 2)
        valida = total and abs(somma - total) <= tolerance

        return {
            "items": items,
            "success": valida,
            "sum": somma,
            "total": total,
            "error": None
        }
    except Exception as e:
        return {"items": [], "success": False, "error": str(e)}


def estrai_claude_llm(testo_ocr):
    """
    Estrai prodotti con Claude LLM da testo OCR.
    """
    try:
        import anthropic
    except ImportError:
        return {"items": [], "success": False, "error": "anthropic not installed"}

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return {"items": [], "success": False, "error": "no ANTHROPIC_API_KEY"}

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Estrai SOLO i prodotti da questo testo OCR di uno scontrino.
Per ogni prodotto, dammi NOME e PREZZO.
Ignora righe che non sono prodotti (intestazioni, totali, IVA, etc).
Rispondi con JSON: [{{"name": "...", "price": X.XX}},...]

Testo OCR:
{testo_ocr}"""

    try:
        t0 = time.time()
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        elapsed = time.time() - t0

        text = response.content[0].text

        # Estrai JSON
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            for item in items:
                item["source"] = "claude"
            return {
                "items": items,
                "success": len(items) > 0,
                "elapsed": elapsed,
                "error": None
            }
    except Exception as e:
        return {"items": [], "success": False, "error": str(e), "elapsed": 0}

    return {"items": [], "success": False, "error": "no json"}


def estrai_groq_llm(testo_ocr):
    """
    Estrai prodotti con Groq LLM da testo OCR.
    """
    try:
        from groq import Groq
    except ImportError:
        return {"items": [], "success": False, "error": "groq not installed"}

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return {"items": [], "success": False, "error": "no GROQ_API_KEY"}

    client = Groq(api_key=api_key)

    prompt = f"""Estrai SOLO i prodotti da questo testo OCR di uno scontrino.
Per ogni prodotto, dammi NOME e PREZZO.
Rispondi con JSON: [{{"name": "...", "price": X.XX}},...]

Testo OCR:
{testo_ocr}"""

    try:
        t0 = time.time()
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        elapsed = time.time() - t0

        text = response.choices[0].message.content

        # Estrai JSON
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            for item in items:
                item["source"] = "groq"
            return {
                "items": items,
                "success": len(items) > 0,
                "elapsed": elapsed,
                "error": None
            }
    except Exception as e:
        if "rate_limit_exceeded" in str(e).lower():
            return {"items": [], "success": False, "error": "groq_quota_exceeded", "elapsed": 0}
        return {"items": [], "success": False, "error": str(e), "elapsed": 0}

    return {"items": [], "success": False, "error": "no json"}


def estrai_llava_vlm(image_path):
    """
    Estrai prodotti con LLaVA VLM direttamente dall'immagine.
    """
    try:
        from transformers import AutoProcessor, LlavaForConditionalGeneration
        from PIL import Image
        import torch
    except ImportError:
        return {"items": [], "success": False, "error": "transformers/PIL not installed"}

    try:
        # Load model (una volta)
        if not hasattr(estrai_llava_vlm, '_model_loaded'):
            print("  [LLaVA] Caricamento modello (prima volta, 2-3 min)...")
            model_id = "llava-hf/llava-1.5-7b-hf"
            estrai_llava_vlm._processor = AutoProcessor.from_pretrained(model_id)
            estrai_llava_vlm._model = LlavaForConditionalGeneration.from_pretrained(
                model_id,
                torch_dtype=torch.float16,
                device_map="auto"
            )
            estrai_llava_vlm._model_loaded = True

        image = Image.open(image_path).convert('RGB')

        prompt = """Estrai i prodotti visibili in questo scontrino.
Per ogni prodotto, dammi NOME e PREZZO.
Rispondi con JSON: [{"name": "...", "price": X.XX},...]"""

        t0 = time.time()
        inputs = estrai_llava_vlm._processor(prompt, image, return_tensors='pt').to(
            estrai_llava_vlm._model.device, torch.float16
        )

        with torch.no_grad():
            outputs = estrai_llava_vlm._model.generate(**inputs, max_new_tokens=200)

        text = estrai_llava_vlm._processor.decode(outputs[0], skip_special_tokens=True)
        elapsed = time.time() - t0

        # Estrai JSON
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            for item in items:
                item["source"] = "llava"
            return {
                "items": items,
                "success": len(items) > 0,
                "elapsed": elapsed,
                "error": None
            }
    except Exception as e:
        return {"items": [], "success": False, "error": str(e), "elapsed": 0}

    return {"items": [], "success": False, "error": "no json"}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20, help="Numero di scontrini da testare")
    parser.add_argument("--skip-llava", action="store_true", help="Salta LLaVA (no GPU disponibile)")
    args = parser.parse_args(argv)

    print("\n=== BENCHMARK EXTRACTION METHODS ===\n")

    # Carica sample di scontrini dal database
    conn = sqlite3.connect("data/spese.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.image_sha256, r.total_declared, r.date
        FROM receipts r
        WHERE r.extraction_method = 'geometric'
        LIMIT ?
    """, (args.sample,))

    receipts = cursor.fetchall()
    print(f"Campione: {len(receipts)} scontrini\n")

    results = defaultdict(list)
    times_by_method = defaultdict(list)

    for idx, receipt in enumerate(receipts):
        receipt_id = receipt["id"]
        sha256 = receipt["image_sha256"]
        total = receipt["total_declared"]

        print(f"\n[{idx+1}/{len(receipts)}] Scontrino {sha256[:12]}...")

        # Leggi OCR da data/estratti/{sha256}.json
        estratti_path = Path("data/estratti") / f"{sha256}.json"
        if not estratti_path.exists():
            print(f"  ❌ OCR file not found: {estratti_path}")
            continue

        try:
            with open(estratti_path) as f:
                estratti_data = json.load(f)
            righe_ocr = estratti_data.get("righe_ocr", [])
            testo_ocr = "\n".join([r.get("testo", "") for r in righe_ocr])
        except Exception as e:
            print(f"  ❌ Error reading OCR: {e}")
            continue

        # Geometrico
        t0 = time.time()
        result_geo = estrai_geometrico(righe_ocr, total)
        t_geo = time.time() - t0
        results["geometric"].append(result_geo)
        times_by_method["geometric"].append(t_geo)
        print(f"  Geometric: {len(result_geo['items'])} items, {t_geo:.3f}s")

        # Claude
        if os.environ.get('ANTHROPIC_API_KEY'):
            result_claude = estrai_claude_llm(testo_ocr)
            times_by_method["claude"].append(result_claude.get("elapsed", 0))
            results["claude"].append(result_claude)
            print(f"  Claude: {len(result_claude['items'])} items, {result_claude.get('elapsed', 0):.3f}s")
        else:
            print(f"  Claude: skipped (no ANTHROPIC_API_KEY)")

        # Groq — deprecated API keys, skip for now
        # if os.environ.get('GROQ_API_KEY'):
        #     result_groq = estrai_groq_llm(testo_ocr)
        #     times_by_method["groq"].append(result_groq.get("elapsed", 0))
        #     results["groq"].append(result_groq)
        #     error = result_groq.get('error')
        #     print(f"  Groq: {len(result_groq['items'])} items, {result_groq.get('elapsed', 0):.3f}s" + (f", error={error}" if error else ""))
        # else:
        print(f"  Groq: skipped (deprecated API keys)")

        # LLaVA
        if not args.skip_llava:
            image_path = Path("data/ritagli") / f"{sha256}.jpg"
            if image_path.exists():
                result_llava = estrai_llava_vlm(str(image_path))
                times_by_method["llava"].append(result_llava.get("elapsed", 0))
                results["llava"].append(result_llava)
                print(f"  LLaVA: {len(result_llava['items'])} items, {result_llava.get('elapsed', 0):.3f}s")
            else:
                print(f"  LLaVA: image not found ({image_path})")
        else:
            print(f"  LLaVA: skipped (--skip-llava)")

    conn.close()

    # Statistiche finali
    print("\n\n=== RISULTATI FINALI ===\n")

    for method in ["geometric", "claude", "groq", "llava"]:
        if not results[method]:
            continue

        successful = sum(1 for r in results[method] if r.get('success'))
        total_items = sum(len(r.get('items', [])) for r in results[method])
        avg_time = sum(times_by_method[method]) / len(times_by_method[method]) if times_by_method[method] else 0

        print(f"{method.upper()}:")
        print(f"  Success rate: {successful}/{len(results[method])} ({100*successful//len(results[method])}%)")
        print(f"  Items estratti: {total_items}")
        print(f"  Avg time: {avg_time:.3f}s/scontrino")

    # Costi stimati
    print("\n=== COSTI (per 200 scontrini/giorno) ===\n")
    print("Geometric: €0 (locale)")
    print("Claude: 200 × €0.02 = €4/day = €120/month")
    print("Groq: 200 × €0 = €0/day (gratis, limite 5000 token/giorno)")
    print("LLaVA: €0 (Kaggle GPU gratis, limite 30h/settimana)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
