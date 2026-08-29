# Istruzioni: Benchmark LLaVA su Kaggle GPU

**Obiettivo**: Misurare efficienza LLaVA vs Geometric per estrazione prodotti  
**Tempo**: 15-25 minuti (caricamento modello + inference)  
**Device**: GPU P100/T4 Kaggle gratis (30h/week)

## STEP 1: Preparare i Dati (Locale)

### Opzione A: Upload immagini personali su Kaggle

Se vuoi testare con i tuoi scontrini:

```bash
# Locale: crea cartella dataset
mkdir -p ~/kaggle-dataset/ritagli
cp private/campione_validato/*.jpg ~/kaggle-dataset/ritagli/

# Metadati
cat > ~/kaggle-dataset/dataset-metadata.json <<'JSON'
{
  "title": "Ticket Tracer Receipts",
  "id": "username/ticket-tracer-receipts",
  "licenses": [{"name": "CC0"}],
  "keywords": ["receipts", "llava"],
  "collaborators": [],
  "data": []
}
JSON

# Upload su Kaggle (richiede kaggle.json in ~/.kaggle/)
cd ~/kaggle-dataset
kaggle datasets create -p . --dataset-name ticket-tracer-receipts --private
```

### Opzione B: Usare dati pubblici (più veloce)

Oppure testa direttamente con immagini pubbliche su Kaggle (es. Food101, COCO), modificando il percorso nel script.

## STEP 2: Creare Notebook Kaggle

### 1. Vai a https://www.kaggle.com/code
### 2. Click: "Create" → "Notebook"
### 3. Scegli: Python, GPU P100/T4 (gratis)
### 4. Nuovo notebook

## STEP 3: Configurare Input Data

Nel notebook Kaggle:
1. In alto a destra: "+ Add input data"
2. Cerca il dataset creato: "ticket-tracer-receipts"
3. Seleziona e aggiungi

Sarà disponibile come: `/kaggle/input/ticket-tracer-receipts/ritagli/`

## STEP 4: Eseguire il Benchmark

Nel notebook Kaggle, copia-incolla questo codice:

```python
# Cella 1: Installa dipendenze (se necessario)
!pip install -q transformers torch pillow psutil

# Cella 2: Carica e esegui lo script
import subprocess
import os

# Scarica lo script
script = """
import json, re, time, sys, torch
from pathlib import Path
from transformers import AutoProcessor, LlavaForConditionalGeneration
from PIL import Image

# Detect device
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device}")
if device == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")

# Load model
print("\\nLoading model (2-3 min)...")
model_id = "llava-hf/llava-1.5-7b-hf"
processor = AutoProcessor.from_pretrained(model_id)
model = LlavaForConditionalGeneration.from_pretrained(model_id, torch_dtype=torch.float16 if device == "cuda" else torch.float32, device_map="auto" if device == "cuda" else None)
if device != "cuda":
    model = model.to(device)

# Test su immagini
img_dir = Path("/kaggle/input/ticket-tracer-receipts/ritagli")
images = sorted(list(img_dir.glob("*.jpg")))[:20]  # Prime 20

print(f"\\nTesting {len(images)} images...")
print(f"{'#':<3} {'Image':<15} {'Items':<6} {'Time':<8} {'Status'}")
print("-" * 50)

times, successes, total_items = [], 0, 0

for idx, img_path in enumerate(images, 1):
    try:
        image = Image.open(img_path).convert('RGB')
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        
        prompt = "Estrai i prodotti da questo scontrino. Rispondi: [{\\"name\\": \\"...\\", \\"price\\": X.XX}, ...]"
        
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
        
        # Estrai JSON
        json_match = re.search(r'\\[.*?\\]', text, re.DOTALL)
        items = json.loads(json_match.group()) if json_match else []
        success = len(items) > 0
        
        times.append(elapsed)
        if success:
            successes += 1
        total_items += len(items)
        
        status = f"✅ {len(items)}" if success else "❌ no items"
        print(f"{idx:<3} {img_path.stem[:15]:<15} {len(items):<6} {elapsed:.3f}s    {status}")
    except Exception as e:
        print(f"{idx:<3} {img_path.stem[:15]:<15} {'-':<6} {'-':<8} ⚠️  {str(e)[:30]}")

# Risultati
print("\\n" + "=" * 50)
print(f"Success rate: {successes}/{len(images)} ({100*successes//len(images)}%)")
print(f"Avg latency: {sum(times)/len(times):.3f}s per image")
print(f"Total items: {total_items}")
print(f"Scaling to 200/day: {200*sum(times)/len(times):.0f}s = {200*sum(times)/len(times)/3600:.2f}h")
print(f"Kaggle quota: 30h/week = {30/7:.1f}h/day ✅")
"""

with open("benchmark.py", "w") as f:
    f.write(script)

exec(open("benchmark.py").read())
```

## Output Atteso

```
Device: cuda
GPU: Tesla T4, VRAM: 16.0 GB

Loading model (2-3 min)...
✅ Model loaded in 145.2s

Testing 20 images...
#   Image           Items  Time      Status
--------------------------------------------------
1   002fe24956         8     2.341s    ✅ 8
2   012eb9e829        12     2.156s    ✅ 12
3   01ff2296d9         6     2.234s    ✅ 6
...

==================================================
Success rate: 18/20 (90%)
Avg latency: 2.234s per image
Total items: 234
Scaling to 200/day: 446.8s = 0.12h
Kaggle quota: 4.3h/day ✅
```

## Interpretazione Risultati

### Success Rate

| Rate | Interpretazione |
|------|---|
| **> 80%** | LLaVA è accurato ✅ Usa come primary |
| **60-80%** | Comparabile a Geometric |
| **< 60%** | Geometric è migliore ❌ Skip LLaVA |

### Latenza

| Latenza | Scalabilità per 200/day |
|---------|---|
| **< 2s** | ✅ 6.7 minuti totali |
| **2-5s** | ✅ 12-17 minuti (accettabile) |
| **> 5s** | ⚠️ 28+ minuti (rischia quota) |

### Confronto Geometric

```
Geometric (baseline):
  - Success rate: 58%
  - Latency: 0.001s (istantaneo)
  - Costo: €0
  - Scalabilità: ✅✅✅

LLaVA (candidato):
  - Success rate: ?? (misura!)
  - Latency: ?? (misura!)
  - Costo: €0 (Kaggle quota)
  - Scalabilità: ?? (dipende da latency)
```

### Decisione Finale

**Se LLaVA success rate > 75% E latency < 3s:**
```
✅ LLaVA VINCE
Primary: LLaVA (migliore accuracy)
Fallback: Geometric (per anomalie)
Costo: €0
ROI: +20-30% accuracy vs Geometric
```

**Se LLaVA success rate ≈ 58% O latency > 5s:**
```
❌ Geometric VINCE
Primary: Geometric (affidabile, locale, veloce)
Skip: LLaVA (no improvement)
Costo: €0
ROI: mantieni status quo
```

## Download Risultati

Dopo il test, scarica i risultati dal notebook Kaggle:
1. Click "Output" (in alto a destra)
2. Scarica il file JSON/notebook

## Automazione Futura

Una volta deciso il metodo:
1. Implementa nella pipeline di estrazione (Fase I)
2. Aggiungi fallback logic (Geometric fallback se LLaVA timeout)
3. Monitora latency in produzione

## Troubleshooting

### GPU non disponibile
**Problema**: "CUDA not available"  
**Soluzione**: Settings → Accelerator: change to "GPU"

### Out of Memory (OOM)
**Problema**: "CUDA out of memory"  
**Soluzione**: Riduci batch size o usa modello più piccolo (7B invece di 13B)

### Timeout inference
**Problema**: Kernel muore dopo 10 minuti  
**Soluzione**: Riduci sample size (10 immagini invece di 20)

## Prossimi Step

1. ✅ Esegui benchmark su Kaggle GPU
2. ✅ Scarica risultati JSON
3. ✅ Confronta con Geometric baseline
4. ✅ Decidi metodo (LLaVA o Geometric)
5. ⏳ Implementa in produzione

---

**Documenti correlati**:
- [docs/96_benchmark_estrazione_prodotti.md](96_benchmark_estrazione_prodotti.md) — Geometric baseline (58% success)
- [docs/97_esecuzione_benchmark_llava_kaggle.md](97_esecuzione_benchmark_llava_kaggle.md) — Setup dettagliato
- [scripts/kaggle_benchmark_llava.py](../scripts/kaggle_benchmark_llava.py) — Script completo
