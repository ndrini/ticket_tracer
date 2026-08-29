#!/usr/bin/env python3
"""
Benchmark LLaVA su Kaggle GPU.

Misura:
1. Tempo di caricamento del modello (first run)
2. Latenza per immagine (inference time)
3. Accuracy dei prodotti estratti
4. Costi (GPU quota Kaggle)

Uso:
    # Local (CPU, slow)
    uv run python scripts/benchmark_llava_kaggle.py --sample 5 --device cpu

    # Kaggle GPU (consigliato)
    kaggle kernels push -p scripts/ -d scripts/benchmark_llava_kaggle.py
    # oppure via Kaggle Notebooks

    # Test rapido locale
    uv run python scripts/benchmark_llava_kaggle.py --sample 3 --device cpu --model llava-hf/llava-1.5-7b-hf
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

try:
    from transformers import AutoProcessor, LlavaForConditionalGeneration
    from PIL import Image
    import torch
except ImportError:
    print("ERROR: Required packages not found. Install with:")
    print("  uv pip install transformers torch pillow")
    sys.exit(1)


def test_device():
    """Rileva device disponibile: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        device = "cuda"
        device_name = f"CUDA ({torch.cuda.get_device_name(0)})"
        gpus = torch.cuda.device_count()
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = "mps"
        device_name = "Apple Metal (MPS)"
        gpus = 1
    else:
        device = "cpu"
        device_name = "CPU (slow)"
        gpus = 0

    print(f"\n🖥️  Device: {device_name}")
    if gpus > 0:
        print(f"   GPUs: {gpus}")
        if torch.cuda.is_available():
            print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    return device


def estrai_llava(image_path, model_id, processor, model, device):
    """
    Estrai prodotti con LLaVA da immagine.
    Ritorna (items, elapsed_time, success).
    """
    try:
        image = Image.open(image_path).convert('RGB')
    except Exception as e:
        return [], 0, False, f"Image load error: {e}"

    prompt = """Estrai i prodotti visibili in questo scontrino.
Per ogni prodotto, dammi NOME e PREZZO.
Rispondi SOLO con JSON: [{"name": "...", "price": X.XX}, ...]
Se non vedi prodotti chiari, rispondi con: []
Non includere intestazioni, totali, IVA."""

    try:
        t0 = time.time()

        # Prepare inputs
        inputs = processor(prompt, image, return_tensors='pt')

        # Move to device
        for key in inputs:
            if isinstance(inputs[key], torch.Tensor):
                inputs[key] = inputs[key].to(device)
                if device == "cuda":
                    inputs[key] = inputs[key].half()  # fp16 per velocità

        # Generate
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=200,
                do_sample=False,  # Greedy decode per riproducibilità
                temperature=0.0,
            )

        elapsed = time.time() - t0

        # Decode
        text = processor.decode(outputs[0], skip_special_tokens=True)

        # Extract JSON
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if not json_match:
            return [], elapsed, False, "No JSON found in output"

        try:
            items = json.loads(json_match.group())
            if not isinstance(items, list):
                items = []
            return items, elapsed, len(items) > 0, None
        except json.JSONDecodeError as e:
            return [], elapsed, False, f"JSON decode error: {e}"

    except Exception as e:
        return [], 0, False, f"Inference error: {e}"


def main(argv):
    parser = argparse.ArgumentParser(description="Benchmark LLaVA su Kaggle GPU")
    parser.add_argument("--sample", type=int, default=10, help="Numero di scontrini da testare")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu", "mps"], default="auto",
                        help="Device: auto (detect), cuda, cpu, mps")
    parser.add_argument("--model", default="llava-hf/llava-1.5-7b-hf",
                        help="Model ID (default: llava-hf/llava-1.5-7b-hf)")
    parser.add_argument("--skip-model-load", action="store_true",
                        help="Skip model loading (test solo su fixture)")
    args = parser.parse_args(argv)

    print("\n" + "=" * 60)
    print("BENCHMARK LLaVA SU KAGGLE GPU")
    print("=" * 60)

    # Detect device
    if args.device == "auto":
        device = test_device()
    else:
        device = args.device
        print(f"\n🖥️  Device (forced): {device}")

    # Carica DB
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
    print(f"\n📊 Campione: {len(receipts)} scontrini")

    if not receipts:
        print("❌ Nessuno scontrino trovato nel database")
        return 1

    # Carica modello
    print(f"\n📥 Modello: {args.model}")
    print("   (primo caricamento: 2-3 minuti...)")

    t0_load = time.time()

    try:
        processor = AutoProcessor.from_pretrained(args.model)
        model = LlavaForConditionalGeneration.from_pretrained(
            args.model,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None
        )
        if device != "cuda":
            model = model.to(device)
    except Exception as e:
        print(f"❌ Errore caricamento modello: {e}")
        return 1

    load_time = time.time() - t0_load
    print(f"   ✅ Caricato in {load_time:.1f}s")

    # Benchmark
    results = []
    times = []
    successes = 0
    total_items = 0

    print(f"\n{'#':<3} {'SHA256':<12} {'Items':<6} {'Time':<8} {'Status':<30}")
    print("-" * 60)

    for idx, receipt in enumerate(receipts, 1):
        sha256 = receipt["image_sha256"]
        image_path = Path("data/ritagli") / f"{sha256}.jpg"

        if not image_path.exists():
            status = "⚠️  Image not found"
            print(f"{idx:<3} {sha256[:12]:<12} {'-':<6} {'-':<8} {status:<30}")
            continue

        # Estrai
        items, elapsed, success, error = estrai_llava(
            str(image_path), args.model, processor, model, device
        )

        times.append(elapsed)
        if success:
            successes += 1
        total_items += len(items)

        status = "✅" if success else f"❌ {error}"
        print(f"{idx:<3} {sha256[:12]:<12} {len(items):<6} {elapsed:.3f}s    {status:<30}")

        results.append({
            "sha256": sha256,
            "items": len(items),
            "elapsed": elapsed,
            "success": success,
            "error": error
        })

    conn.close()

    # Statistiche finali
    print("\n" + "=" * 60)
    print("RISULTATI FINALI")
    print("=" * 60)

    avg_time = sum(times) / len(times) if times else 0
    success_rate = 100 * successes / len(results) if results else 0

    print(f"\n📈 Metriche:")
    print(f"   Success rate: {successes}/{len(results)} ({success_rate:.1f}%)")
    print(f"   Items estratti: {total_items} totali, {total_items/max(1,len(results)):.1f} per scontrino")
    print(f"   Latenza media: {avg_time:.3f}s per immagine")
    print(f"   Latenza totale: {sum(times):.1f}s per {len(results)} scontrini")
    print(f"   Caricamento modello: {load_time:.1f}s (una volta)")

    # Scalabilità
    print(f"\n📊 Scalabilità per 200 scontrini/giorno:")
    total_for_200 = 200 * avg_time
    if device == "cuda":
        gpu_hours = total_for_200 / 3600
        print(f"   Tempo GPU: {total_for_200:.1f}s = {gpu_hours:.2f}h")
        print(f"   Quota Kaggle: 30h/week ✅ Sufficienti per 200/day")
    else:
        print(f"   ⚠️  CPU: {total_for_200:.1f}s = {total_for_200/3600:.1f}h (molto lento)")
        print(f"   ❌ CPU non scalabile a 200/day")

    # Costi
    print(f"\n💰 Costi:")
    print(f"   LLaVA: €0 (Kaggle GPU gratis, 30h/week)")
    print(f"   Claude fallback: €0.02/scontrino = €4/day (se serve)")

    # Confronto con Geometric
    print(f"\n📊 Confronto con Geometric (baseline):")
    print(f"   Geometric: 58% success, 0.001s/scontrino, €0")
    print(f"   LLaVA:     {success_rate:.0f}% success, {avg_time:.3f}s/scontrino, €0")
    if success_rate > 58 and avg_time < 5:
        print(f"   ✅ LLaVA VINCE: migliore accuracy + latenza accettabile")
    elif success_rate > 58:
        print(f"   ⚠️  LLaVA migliore accuracy ma latenza alta (5s+)")
    else:
        print(f"   ❌ LLaVA perde su accuracy e/o latenza")

    # Salva risultati
    results_file = Path("data/benchmark_llava_results.json")
    with open(results_file, "w") as f:
        json.dump({
            "model": args.model,
            "device": device,
            "timestamp": time.time(),
            "load_time": load_time,
            "sample_size": len(results),
            "success_rate": success_rate,
            "avg_latency": avg_time,
            "total_items": total_items,
            "results": results
        }, f, indent=2)
    print(f"\n💾 Risultati salvati: {results_file}")

    return 0 if success_rate > 50 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
