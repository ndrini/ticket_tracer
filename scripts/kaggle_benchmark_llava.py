#!/usr/bin/env python3
"""
Benchmark LLaVA su Kaggle GPU (kernel)

Questo script è progettato per essere eseguito su Kaggle Notebooks con GPU P100/T4.

Esecuzione su Kaggle:
1. Carica questo file come notebook Python su Kaggle
2. Configura input data: /kaggle/input/ticket-tracer-data/
3. GPU automaticamente disponibile
4. Risultati salvati su /kaggle/working/

Local test (CPU, solo verifica):
    python scripts/kaggle_benchmark_llava.py --local --sample 1 --device cpu
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

import torch
import psutil

try:
    from transformers import AutoProcessor, LlavaForConditionalGeneration
    from PIL import Image
except ImportError:
    print("Installing dependencies...")
    os.system("pip install -q transformers pillow")
    from transformers import AutoProcessor, LlavaForConditionalGeneration
    from PIL import Image


def detect_kaggle_environment():
    """Rileva se siamo su Kaggle."""
    return os.path.exists("/kaggle/working")


def detect_device():
    """Rileva device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        device = "cuda"
        device_name = f"CUDA ({torch.cuda.get_device_name(0)})"
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"✅ GPU detected: {device_name}")
        print(f"   VRAM: {vram_gb:.1f} GB")
        return device
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = "mps"
        print(f"✅ Metal Performance Shaders (MPS) available")
        return device
    else:
        print(f"⚠️  CPU only (slow)")
        return "cpu"


def get_memory_usage():
    """Ritorna RAM usage in GB."""
    return psutil.virtual_memory().used / 1e9


def estrai_llava_immagine(image_path, processor, model, device, image_size_limit=1024):
    """
    Estrai prodotti con LLaVA da una singola immagine.

    Ritorna: (items, elapsed_time, success, error_msg)
    """
    try:
        # Carica immagine
        image = Image.open(image_path).convert('RGB')

        # Ridimensiona se troppo grande (risparmi VRAM)
        if image.width > image_size_limit or image.height > image_size_limit:
            image.thumbnail((image_size_limit, image_size_limit), Image.Resampling.LANCZOS)

    except Exception as e:
        return [], 0, False, f"Image load failed: {e}"

    prompt = """You are an assistant that extracts structured product data from receipt images.

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

    try:
        mem_before = get_memory_usage()
        t0 = time.time()

        # Processa immagine e prompt
        inputs = processor(prompt, image, return_tensors='pt')

        # Muovi su device
        for key in inputs:
            if isinstance(inputs[key], torch.Tensor):
                if device == "cuda":
                    inputs[key] = inputs[key].to(device).half()  # fp16
                else:
                    inputs[key] = inputs[key].to(device)

        # Generate con timeout implicito
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=250,
                do_sample=False,
                temperature=0.0,
            )

        elapsed = time.time() - t0
        mem_after = get_memory_usage()

        # Decode output
        text = processor.decode(outputs[0], skip_special_tokens=True)

        # Estrai JSON
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if not json_match:
            return [], elapsed, False, "No JSON in output"

        try:
            items = json.loads(json_match.group())
            if not isinstance(items, list):
                items = []

            return items, elapsed, len(items) > 0, None
        except json.JSONDecodeError as e:
            return [], elapsed, False, f"JSON decode: {str(e)[:50]}"

    except Exception as e:
        return [], 0, False, f"Inference: {str(e)[:100]}"


def main(argv):
    parser = argparse.ArgumentParser(description="LLaVA Benchmark su Kaggle GPU")
    parser.add_argument("--sample", type=int, default=20, help="Numero di scontrini")
    parser.add_argument("--model", default="llava-hf/llava-1.5-7b-hf", help="Model ID")
    parser.add_argument("--local", action="store_true", help="Esegui locale (CPU test)")
    parser.add_argument("--device", choices=["cuda", "cpu", "mps"], default="cuda",
                        help="Device forzato")
    args = parser.parse_args(argv)

    print("\n" + "=" * 70)
    print("BENCHMARK LLaVA SU KAGGLE GPU")
    print("=" * 70)

    # Ambiente
    on_kaggle = detect_kaggle_environment()
    print(f"\n🖥️  Environment: {'Kaggle Kernel' if on_kaggle else 'Local'}")

    # Device
    if args.local:
        device = args.device
        print(f"🖥️  Device (forced): {device}")
    else:
        device = detect_device()

    # Percorsi dati
    if on_kaggle:
        data_dir = Path("/kaggle/input/ticket-tracer-data")
        output_dir = Path("/kaggle/working")
        images_dir = data_dir / "ritagli"
    else:
        data_dir = Path("data")
        output_dir = data_dir
        images_dir = data_dir / "ritagli"

    output_dir.mkdir(exist_ok=True)

    print(f"📁 Data dir: {data_dir}")
    print(f"📁 Output dir: {output_dir}")

    # Carica modello
    print(f"\n📥 Caricamento modello: {args.model}")
    print("   (primo caricamento: 2-5 minuti su GPU)...")

    mem_before = get_memory_usage()
    t0_load = time.time()

    try:
        processor = AutoProcessor.from_pretrained(args.model)

        if device == "cuda":
            model = LlavaForConditionalGeneration.from_pretrained(
                args.model,
                torch_dtype=torch.float16,
                device_map="auto"
            )
        else:
            model = LlavaForConditionalGeneration.from_pretrained(args.model)
            model = model.to(device)

    except Exception as e:
        print(f"❌ Errore caricamento modello: {e}")
        return 1

    load_time = time.time() - t0_load
    mem_used = get_memory_usage() - mem_before
    print(f"   ✅ Caricato in {load_time:.1f}s, RAM +{mem_used:.1f} GB")

    # Cerca immagini
    if not images_dir.exists():
        print(f"❌ Directory immagini non trovata: {images_dir}")
        print(f"   Possibili percorsi:")
        print(f"   - /kaggle/input/ticket-tracer-data/ritagli/")
        print(f"   - data/ritagli/")
        return 1

    image_files = sorted(list(images_dir.glob("*.jpg")))[:args.sample]

    if not image_files:
        print(f"❌ Nessuna immagine trovata in {images_dir}")
        return 1

    print(f"\n📊 Campione: {len(image_files)} scontrini")

    # Benchmark
    results = []
    times = []
    successes = 0
    total_items = 0

    print(f"\n{'#':<4} {'Immagine':<20} {'Items':<6} {'Time':<8} {'Status':<40}")
    print("-" * 80)

    t_total_start = time.time()

    for idx, img_path in enumerate(image_files, 1):
        img_name = img_path.stem[:16]

        items, elapsed, success, error = estrai_llava_immagine(
            str(img_path), processor, model, device
        )

        times.append(elapsed)
        if success:
            successes += 1
        total_items += len(items)

        status = f"✅ {len(items)} items"
        if error:
            status = f"⚠️  {error[:35]}"

        print(f"{idx:<4} {img_name:<20} {len(items):<6} {elapsed:.3f}s    {status:<40}")

        results.append({
            "image": img_path.name,
            "items": len(items),
            "elapsed": elapsed,
            "success": success,
            "error": error
        })

        # Mostra progresso ogni 5 immagini
        if idx % 5 == 0:
            avg_so_far = sum(times) / len(times) if times else 0
            print(f"   [Progress] {idx}/{len(image_files)}, avg latency: {avg_so_far:.3f}s")

    t_total = time.time() - t_total_start

    # Statistiche finali
    print("\n" + "=" * 70)
    print("RISULTATI FINALI")
    print("=" * 70)

    if times:
        avg_time = sum(times) / len(times)
        p50_time = sorted(times)[len(times)//2]
        p95_time = sorted(times)[int(len(times)*0.95)]
    else:
        avg_time = p50_time = p95_time = 0

    success_rate = 100 * successes / len(results) if results else 0

    # Metrica fallback: se LLaVA fallisce, quanti Geometric recupererebbe?
    # (Stima: Geometric 58% success rate)
    geometric_expected_success = 0.58 * len(results)
    fallback_recovery = max(0, successes - geometric_expected_success)
    recovery_rate = 100 * fallback_recovery / (len(results) - geometric_expected_success) if (len(results) - geometric_expected_success) > 0 else 0

    print(f"\n📊 Metriche Performance:")
    print(f"   Success rate: {successes}/{len(results)} ({success_rate:.1f}%)")
    print(f"   Items: {total_items} totali, {total_items/max(1,len(results)):.1f} per immagine")
    print(f"\n⏱️  Latenza:")
    print(f"   Media: {avg_time:.3f}s per immagine")
    print(f"   P50 (mediana): {p50_time:.3f}s")
    print(f"   P95 (95-esimo): {p95_time:.3f}s")
    print(f"   Totale: {t_total:.1f}s per {len(results)} immagini")
    print(f"\n💾 Caricamento modello: {load_time:.1f}s (una volta)")

    # Scalabilità
    print(f"\n📈 Scalabilità per 200 scontrini/giorno:")
    total_for_200 = 200 * avg_time
    gpu_hours = total_for_200 / 3600

    if device == "cuda":
        print(f"   Tempo GPU richiesto: {total_for_200:.1f}s = {gpu_hours:.2f}h")
        kaggle_quota = 30  # h/week
        daily_quota = kaggle_quota / 7  # h/day
        print(f"   Quota Kaggle: {daily_quota:.1f}h/day (30h/week)")
        if gpu_hours <= daily_quota:
            print(f"   ✅ FEASIBLE: {gpu_hours:.2f}h < {daily_quota:.1f}h")
        else:
            print(f"   ⚠️  RISKY: {gpu_hours:.2f}h > {daily_quota:.1f}h (potrebbe superare quota)")
    else:
        cpu_hours = total_for_200 / 3600
        print(f"   CPU: {total_for_200:.1f}s = {cpu_hours:.1f}h ❌ troppo lento")

    # Confronto
    print(f"\n📊 Confronto metodi estrazione:")
    print(f"   Geometric:  58% success, 0.001s/scontrino, €0")
    print(f"   LLaVA:      {success_rate:.0f}% success, {avg_time:.3f}s/scontrino, €0")
    print(f"   Fallback gain: +{recovery_rate:.0f}% items se LLaVA fallisce (Geometric recupera)")

    if success_rate > 75 and avg_time < 1.5:
        print(f"\n   ✅✅ LLaVA WINS: accuracy significativa + latenza OK")
        print(f"       Raccomandazione: Switch a LLaVA + Geometric fallback")
    elif success_rate > 70 and avg_time < 3:
        print(f"\n   ✅ LLaVA COMPETITIVO: accuracy buona, latenza accettabile")
        print(f"       Raccomandazione: Hybrid (Geometric primary, LLaVA fallback)")
    elif success_rate > 58:
        print(f"\n   ⚠️  LLaVA PARZIALE: migliore accuracy, latenza alta")
        print(f"       Raccomandazione: Mantieni Geometric, LLaVA per edge cases")
    else:
        print(f"\n   ❌ GEOMETRIC VINCE: LLaVA non migliora")
        print(f"       Raccomandazione: Status quo Geometric")

    # Costi
    print(f"\n💰 Costi:")
    print(f"   LLaVA: €0 (Kaggle GPU gratis, 30h/week)")
    print(f"   Claude fallback: €0.02/scontrino (se serve)")
    print(f"   Totale per 200/day: €0 (se latenza OK)")

    # Salva risultati
    results_file = output_dir / "benchmark_llava_results.json"
    summary = {
        "timestamp": time.time(),
        "environment": "kaggle" if on_kaggle else "local",
        "device": device,
        "model": args.model,
        "sample_size": len(results),
        "load_time": load_time,
        "success_rate": success_rate,
        "avg_latency": avg_time,
        "p50_latency": p50_time,
        "p95_latency": p95_time,
        "total_items": total_items,
        "total_time": t_total,
        "fallback_recovery_rate": recovery_rate,
        "geometric_baseline": 0.58,
        "results": results
    }

    with open(results_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n💾 Risultati: {results_file}")
    print(f"   ({len(json.dumps(summary)) / 1e3:.1f} KB)")

    return 0 if success_rate >= 50 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
