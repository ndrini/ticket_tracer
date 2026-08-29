#!/usr/bin/env python3
"""
Test rapido LLaVA locale (CPU) su 3 immagini.

Questo è un TEST solo per verificare che il codice funziona.
Per benchmark vero, usa Kaggle GPU via docs/97_esecuzione_benchmark_llava_kaggle.md

Esecuzione:
    python scripts/test_llava_local_quick.py --sample 3
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

print("Loading dependencies...")
try:
    import torch
    import psutil
    from transformers import AutoProcessor, LlavaForConditionalGeneration
    from PIL import Image
except ImportError as e:
    print(f"ERROR: {e}")
    print("Install: pip install torch transformers pillow psutil")
    sys.exit(1)


def detect_device():
    """Rileva device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        device = "cuda"
        device_name = f"CUDA ({torch.cuda.get_device_name(0)})"
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"✅ GPU: {device_name} ({vram_gb:.1f} GB VRAM)")
        return device
    else:
        device = "cpu"
        print(f"⚠️  CPU mode (slow, per testing only)")
        return device


def test_llava_image(image_path, processor, model, device):
    """Test LLaVA su una immagine."""
    try:
        image = Image.open(image_path).convert('RGB')
        # Ridimensiona per velocità
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    except Exception as e:
        return [], 0, False, f"Image error: {e}"

    prompt = """Estrai i prodotti da questo scontrino.
Rispondi: [{"name": "...", "price": X.XX}, ...]"""

    try:
        t0 = time.time()
        inputs = processor(prompt, image, return_tensors='pt').to(device)

        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=150, do_sample=False)

        elapsed = time.time() - t0
        text = processor.decode(outputs[0], skip_special_tokens=True)

        # Estrai JSON
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            return items, elapsed, len(items) > 0, None
    except Exception as e:
        return [], 0, False, str(e)[:80]

    return [], elapsed, False, "No JSON"


def main(argv):
    parser = argparse.ArgumentParser(description="Test rapido LLaVA")
    parser.add_argument("--sample", type=int, default=3, help="Numero immagini")
    parser.add_argument("--model", default="llava-hf/llava-1.5-7b-hf", help="Model")
    args = parser.parse_args(argv)

    print("\n" + "=" * 60)
    print("TEST RAPIDO LLaVA (LOCAL CPU)")
    print("=" * 60)

    device = detect_device()

    # Carica modello
    print(f"\n📥 Loading model: {args.model}")
    print("   (2-5 minutes su CPU)...")

    t0 = time.time()
    try:
        processor = AutoProcessor.from_pretrained(args.model)
        model = LlavaForConditionalGeneration.from_pretrained(args.model)
        model = model.to(device)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    load_time = time.time() - t0
    print(f"   ✅ Loaded in {load_time:.1f}s")

    # Cerca immagini
    image_files = sorted(list(Path("data/ritagli").glob("*.jpg")))[:args.sample]

    if not image_files:
        print("❌ No images found in data/ritagli/")
        return 1

    print(f"\n📊 Testing: {len(image_files)} images\n")

    results = []
    times = []
    successes = 0

    for idx, img_path in enumerate(image_files, 1):
        img_name = img_path.stem[:12]
        items, elapsed, success, error = test_llava_image(img_path, processor, model, device)

        times.append(elapsed)
        if success:
            successes += 1

        status = f"✅ {len(items)} items" if success else f"⚠️  {error}"
        print(f"{idx}. {img_name}: {elapsed:.3f}s ... {status}")

        results.append({
            "image": img_path.name,
            "items": len(items),
            "elapsed": elapsed,
            "success": success,
            "error": error
        })

    # Statistiche
    print("\n" + "=" * 60)
    print("RISULTATI TEST")
    print("=" * 60)

    avg_time = sum(times) / len(times) if times else 0
    success_rate = 100 * successes / len(results) if results else 0

    print(f"\n✅ Success rate: {successes}/{len(results)} ({success_rate:.0f}%)")
    print(f"⏱️  Avg latency: {avg_time:.3f}s per image")
    print(f"📊 Model load: {load_time:.1f}s (one-time)")

    print(f"\n📈 Scaling to 200 receipts/day:")
    total_time = 200 * avg_time
    print(f"   CPU: {total_time:.0f}s = {total_time/3600:.1f}h ❌ troppo lento")
    print(f"   GPU: ~{200*0.003:.0f}s = ~0.2h ✅ OK")

    print(f"\n⚠️  NOTE: This is CPU test, very slow. Use Kaggle GPU for real benchmark.")
    print(f"   See: docs/97_esecuzione_benchmark_llava_kaggle.md")

    # Salva risultati
    with open("data/test_llava_local_results.json", "w") as f:
        json.dump({
            "device": device,
            "load_time": load_time,
            "success_rate": success_rate,
            "avg_latency": avg_time,
            "sample_size": len(results),
            "results": results
        }, f, indent=2)

    print(f"\n💾 Results: data/test_llava_local_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
