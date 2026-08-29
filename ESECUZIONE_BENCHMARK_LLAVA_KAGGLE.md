# 🚀 ESECUZIONE BENCHMARK LLaVA su Kaggle GPU

**Status**: Pronto, ready to execute  
**Tempo**: 20-30 minuti  
**Risultato**: JSON con decision tree per quale metodo usare  

---

## STEP 1: Vai su Kaggle Notebooks (5 min)

1. Accedi a: https://www.kaggle.com/code
2. Click: **"+ Create"** → **"Notebook"**
3. Scegli:
   - Language: **Python**
   - Accelerator: **GPU** (P100 o T4, gratis)
   - Visibility: **Private** (per sicurezza)
4. Click: **"Create Notebook"**

---

## STEP 2: Copia il Codice Benchmark (2 min)

Copia tutto il codice qui sotto in una cella del notebook Kaggle:

```python
# ==============================================================================
# BENCHMARK LLaVA per Estrazione Prodotti da Scontrini
# Kaggle GPU Benchmark - 2026-08-29
# ==============================================================================

import json, re, time, torch, psutil
from pathlib import Path
from transformers import AutoProcessor, LlavaForConditionalGeneration
from PIL import Image

print("\n" + "=" * 70)
print("BENCHMARK LLaVA SU KAGGLE GPU")
print("=" * 70)

# Detect device
if torch.cuda.is_available():
    device = "cuda"
    print(f"\n✅ GPU: {torch.cuda.get_device_name(0)}")
    print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")
else:
    device = "cpu"
    print(f"\n⚠️  CPU mode (no GPU available)")

# Load model
print(f"\n📥 Loading model: llava-hf/llava-1.5-7b-hf")
print("   (2-3 minutes)...")

model_id = "llava-hf/llava-1.5-7b-hf"
processor = AutoProcessor.from_pretrained(model_id)
model = LlavaForConditionalGeneration.from_pretrained(
    model_id,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    device_map="auto" if device == "cuda" else None
)
if device != "cuda":
    model = model.to(device)

print("   ✅ Model loaded")

# Test function
def extract_llava(image_path):
    try:
        image = Image.open(image_path).convert('RGB')
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    except Exception as e:
        return [], 0, False, f"Image error: {e}"

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
        t0 = time.time()
        inputs = processor(prompt, image, return_tensors='pt').to(device)

        if device == "cuda":
            for k in inputs:
                if hasattr(inputs[k], 'half'):
                    inputs[k] = inputs[k].half()

        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=200, do_sample=False)

        elapsed = time.time() - t0
        text = processor.decode(outputs[0], skip_special_tokens=True)

        # Extract JSON
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        items = json.loads(json_match.group()) if json_match else []
        success = len(items) > 0

        return items, elapsed, success, None
    except Exception as e:
        return [], 0, False, str(e)[:80]

# Find test images
# NOTA: Se non hai dataset su Kaggle, crea 5 immagini dummy per test
# Oppure modifica il percorso qui se hai aggiunto un dataset
test_images = list(Path("/kaggle/input").glob("**/*.jpg"))[:20]

if not test_images:
    print("\n⚠️  No images found in /kaggle/input")
    print("   To test:")
    print("   1. Add a Kaggle Dataset with receipt images")
    print("   2. Or create 5 test JPG files and re-run")
    print("\n   Demo mode: creating synthetic test...")
    test_images = list(Path("/kaggle/working").glob("**/*.jpg"))[:1]

print(f"\n📊 Testing {len(test_images)} images...")
print(f"{'#':<3} {'Image':<20} {'Items':<6} {'Time':<8} {'Status'}")
print("-" * 60)

times, successes, total_items = [], 0, 0
results = []

for idx, img_path in enumerate(test_images, 1):
    items, elapsed, success, error = extract_llava(str(img_path))

    times.append(elapsed)
    if success:
        successes += 1
    total_items += len(items)

    status = f"✅ {len(items)}" if success else f"⚠️  {error[:25] if error else 'no items'}"
    print(f"{idx:<3} {img_path.stem[:20]:<20} {len(items):<6} {elapsed:.3f}s    {status}")

    results.append({
        "image": img_path.name,
        "items": len(items),
        "elapsed": elapsed,
        "success": success,
        "error": error
    })

# Results
print("\n" + "=" * 70)
print("RISULTATI FINALI")
print("=" * 70)

if times:
    avg_time = sum(times) / len(times)
    p50_time = sorted(times)[len(times)//2]
    p95_time = sorted(times)[int(len(times)*0.95)] if len(times) > 1 else avg_time
else:
    avg_time = p50_time = p95_time = 0

success_rate = 100 * successes / len(results) if results else 0

print(f"\n📊 Metriche:")
print(f"   Success rate: {successes}/{len(results)} ({success_rate:.0f}%)")
print(f"   Avg latency: {avg_time:.3f}s per image")
print(f"   P50 (mediana): {p50_time:.3f}s")
print(f"   P95 (worst case): {p95_time:.3f}s")
print(f"   Total items: {total_items}")

print(f"\n📈 Scalabilità per 200 scontrini/day:")
total_200 = 200 * avg_time
print(f"   GPU time: {total_200:.0f}s = {total_200/3600:.2f}h")
print(f"   Kaggle quota: 30h/week = {30/7:.1f}h/day")
if total_200/3600 <= 4.3:
    print(f"   ✅ FEASIBLE")
else:
    print(f"   ❌ Exceeds quota")

print(f"\n📊 Confronto con Geometric (baseline):")
print(f"   Geometric:  58% success, 0.001s/scontrino, €0")
print(f"   LLaVA:      {success_rate:.0f}% success, {avg_time:.3f}s/scontrino, €0")

# Decision
if success_rate > 75 and avg_time < 1.5:
    print(f"\n   ✅✅ LLaVA WINS - Switch to LLaVA")
elif success_rate > 70 and avg_time < 3:
    print(f"\n   ✅ LLaVA COMPETITIVE - Hybrid (Geometric primary)")
elif success_rate > 58:
    print(f"\n   ⚠️  LLaVA PARTIAL - Keep Geometric, LLaVA for edge cases")
else:
    print(f"\n   ❌ GEOMETRIC WINS - Status quo")

# Save results
summary = {
    "timestamp": time.time(),
    "device": device,
    "model": model_id,
    "sample_size": len(results),
    "success_rate": success_rate,
    "avg_latency": avg_time,
    "p50_latency": p50_time,
    "p95_latency": p95_time,
    "total_items": total_items,
    "results": results
}

print(f"\n💾 Saving results...")
with open("/kaggle/working/benchmark_results.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"✅ Saved to /kaggle/working/benchmark_results.json")
```

---

## STEP 3: Esegui il Notebook (10-15 min)

1. **Seleziona la cella** con il codice sopra
2. Click: **"Run cell"** (▶️)
3. Attendi che finisca (il caricamento del modello impiega 2-3 minuti)

### Output Atteso

```
======================================================================
BENCHMARK LLaVA SU KAGGLE GPU
======================================================================

✅ GPU: Tesla T4
   VRAM: 16.0 GB

📥 Loading model: llava-hf/llava-1.5-7b-hf
   (2-3 minutes)...
   ✅ Model loaded

📊 Testing 20 images...
#   Image                Items  Time      Status
------------------------------------------------------------
1   image_001           8     2.341s    ✅ 8
2   image_002          12     2.156s    ✅ 12
...

======================================================================
RISULTATI FINALI
======================================================================

📊 Metriche:
   Success rate: 18/20 (90%)
   Avg latency: 2.234s per image
   P50 (mediana): 2.156s
   P95 (worst case): 2.891s
   Total items: 234

📈 Scalabilità per 200 scontrini/day:
   GPU time: 446.8s = 0.12h
   Kaggle quota: 4.3h/day
   ✅ FEASIBLE

📊 Confronto con Geometric (baseline):
   Geometric:  58% success, 0.001s/scontrino, €0
   LLaVA:      90% success, 2.234s/scontrino, €0

   ✅✅ LLaVA WINS - Switch to LLaVA
```

---

## STEP 4: Scarica i Risultati (2 min)

1. Nel notebook, cerca il panel **"Output"** (in alto a destra)
2. Clicca su `benchmark_results.json`
3. Click: **"Download"**
4. Il file si scarica sul tuo computer

---

## STEP 5: Interpretazione Risultati

### Success Rate

| Range | Decision |
|-------|----------|
| **> 75%** | ✅ LLaVA is good |
| **70-75%** | ⚠️ Borderline |
| **60-70%** | ❌ Not much better than Geometric |
| **< 60%** | ❌ Geometric is better |

### Latency

| Latency | Scalability |
|---------|------------|
| **< 1.5s** | ✅ Perfect for 200/day |
| **1.5-3s** | ✅ OK, ~15 min GPU/day |
| **3-5s** | ⚠️ Risky, ~28 min GPU/day |
| **> 5s** | ❌ Too slow |

### Decision Matrix

```
Success > 75% + Latency < 1.5s
→ ✅✅ SWITCH TO LLaVA (better accuracy)

Success 70-75% + Latency < 3s
→ ✅ HYBRID (Geometric primary, LLaVA fallback)

Success 60-70% + Latency 2-5s
→ ❌ KEEP GEOMETRIC (not worth the complexity)

Success < 60%
→ ❌ GEOMETRIC WINS (status quo)
```

---

## Possibili Problemi

### 1. "CUDA out of memory"
**Soluzione**: 
- Riduci numero di immagini (`test_images = ... [:10]` invece di `[:20]`)
- Oppure ridimensiona immagini più piccole (`image.thumbnail((512, 512))`)

### 2. "Model not found" su HuggingFace
**Soluzione**:
- Assicurati di avere internet abilitato (check: "Enable internet" nelle notebook settings)
- Primo run scarica ~7 GB di modello, richiede tempo

### 3. Nessuna immagine trovata (`No images found in /kaggle/input`)
**Soluzione A**: Aggiungi un dataset Kaggle
1. Nel notebook, "Add input data"
2. Carica il tuo dataset di scontrini
3. Modifica il path nel codice: `/kaggle/input/your-dataset-name/`

**Soluzione B**: Test con immagini pubbliche
- Modifica: `test_images = list(Path("/kaggle/input/cifar-10").glob("**/*.png"))[:20]`

**Soluzione C**: Crea immagini di test (quick demo)
```python
from PIL import Image
# Crea 3 immagini bianche dummy
for i in range(3):
    img = Image.new('RGB', (600, 800), color='white')
    img.save(f"/kaggle/working/test_{i}.jpg")
```

---

## Timeline Totale

| Step | Time |
|------|------|
| Accedi Kaggle, crea notebook | 5 min |
| Copia e incolla il codice | 2 min |
| Esegui benchmark | 15 min |
| Scarica risultati | 2 min |
| **TOTALE** | **~25 min** |

---

## Prossimi Step Dopo il Benchmark

1. **Scarica** `benchmark_results.json`
2. **Confronta** LLaVA vs Geometric baseline (58%)
3. **Decidi** quale metodo usare (segui la matrice decisionale)
4. **Documenta** in: `docs/100_risultati_benchmark_llava.md`
5. **Implementa** la scelta in Fase I (1-2 settimane)

---

## Support

Domande? Consulta:
- `docs/98_istruzioni_benchmark_llava_finale.md` — step-by-step dettagliato
- `docs/99_revisione_agenti_benchmark_llava.md` — feedback agenti (Perplexity, Vibe)
- `docs/00_NEXT_STEPS_BENCHMARK_LLAVA.md` — riepilogo esecutivo

---

**Prepared by**: Claude Code (Haiku 4.5)  
**Reviewed by**: Perplexity, Vibe  
**Status**: ✅ Ready to execute

**Baseline for comparison**: Geometric 58% success, 0.001s latency, €0
