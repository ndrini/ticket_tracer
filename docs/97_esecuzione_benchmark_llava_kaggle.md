# Esecuzione Benchmark LLaVA su Kaggle GPU

**Scopo**: Misurare efficienza di LLaVA per estrazione prodotti su GPU gratuita Kaggle.

**Tempo stimato**: 15-20 minuti (caricamento modello 2-3 min + inference su 20 scontrini 10-15 min)

## Setup: Preparare i dati su Kaggle

### Passo 1: Creare un Kaggle Dataset privato con i dati

```bash
# Local: Prepara i dati per upload su Kaggle
mkdir -p /tmp/ticket-tracer-data
cp -r data/ritagli/ /tmp/ticket-tracer-data/  # Copia immagini scontrini (JPG)
# Opzionale: cp -r data/estratti/ /tmp/ticket-tracer-data/  # OCR JSON

# Zip per upload
cd /tmp
tar -czf ticket-tracer-data.tar.gz ticket-tracer-data/
```

### Passo 2: Upload dataset su Kaggle

1. Accedi a Kaggle: https://www.kaggle.com
2. Vai a "Datasets" → "Create new dataset"
3. Upload manuale oppure via CLI:

```bash
# Via Kaggle CLI
kaggle datasets create -p /tmp/ticket-tracer-data \
  --dataset-name ticket-tracer-data \
  --public  # o --private

# Conferma il dataset ID (es: `username/ticket-tracer-data`)
```

**Risultato**: Dataset disponibile come `/kaggle/input/ticket-tracer-data/ritagli/`

## Setup: Creare il Kaggle Notebook

### Passo 1: Upload dello script

**Opzione A: Kaggle Notebooks UI** (consigliato)

1. Vai a https://www.kaggle.com/code
2. "Create" → "Notebook"
3. Scegli: Python, GPU (P100/T4 disponibili gratis)
4. Nuovo notebook vuoto

### Passo 2: Configura input data

Nel notebook, in alto a destra: "Add input data"
- Seleziona il dataset creato sopra: `username/ticket-tracer-data`
- Sarà disponibile come `/kaggle/input/ticket-tracer-data/`

### Passo 3: Carica lo script

Nel notebook, aggiungi una cella code:

```python
# Scarica lo script dal repo
import urllib.request
url = "https://raw.githubusercontent.com/[your-repo]/main/scripts/kaggle_benchmark_llava.py"
urllib.request.urlretrieve(url, "benchmark_llava.py")
```

Oppure copia-incolla direttamente il contenuto di `scripts/kaggle_benchmark_llava.py` in una cella.

### Passo 4: Esegui il benchmark

```python
# Cella Python nel notebook Kaggle
%run benchmark_llava.py --sample 20 --model llava-hf/llava-1.5-7b-hf
```

Oppure da riga di comando:

```bash
python benchmark_llava.py --sample 20 --model llava-hf/llava-1.5-7b-hf
```

## Parametri dello Script

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `--sample N` | 20 | Numero di scontrini da testare (10-50 consigliato) |
| `--model ID` | `llava-hf/llava-1.5-7b-hf` | Model ID da HuggingFace |
| `--device cuda` | cuda | Device: cuda (GPU), cpu, mps |
| `--local` | False | Esegui locale (CPU test, lentissimo) |

### Esempi

```bash
# Benchmark completo: 50 scontrini su GPU
python benchmark_llava.py --sample 50

# Quick test: 10 scontrini
python benchmark_llava.py --sample 10

# Modello diverso
python benchmark_llava.py --sample 20 --model llava-hf/llava-1.5-13b-hf
```

## Output Atteso

### A: Output nel notebook

```
============================================================
BENCHMARK LLaVA SU KAGGLE GPU
============================================================

🖥️  Environment: Kaggle Kernel
🖥️  GPU detected: CUDA (Tesla P100-PCIE-16GB)
   VRAM: 16.0 GB

📥 Caricamento modello: llava-hf/llava-1.5-7b-hf
   (primo caricamento: 2-5 minuti su GPU)...
   ✅ Caricato in 120.5s, RAM +5.2 GB

📊 Campione: 20 scontrini

#    Immagine             Items  Time      Status
--------------------------------------------
1    002fe2495663e261     8      2.341s    ✅ 8 items
2    012eb9e829c1d5a     12      2.156s    ✅ 12 items
...

============================================================
RISULTATI FINALI
============================================================

📊 Metriche Performance:
   Success rate: 18/20 (90%)
   Items: 234 totali, 11.7 per immagine

⏱️  Latenza:
   Media: 2.234s per immagine
   P50 (mediana): 2.156s
   P95 (95-esimo): 2.891s
   Totale: 44.7s per 20 immagini

💾 Caricamento modello: 120.5s (una volta)

📈 Scalabilità per 200 scontrini/giorno:
   Tempo GPU richiesto: 446.8s = 0.12h
   Quota Kaggle: 4.3h/day (30h/week)
   ✅ FEASIBLE: 0.12h < 4.3h

📊 Confronto metodi estrazione:
   Geometric:  58% success, 0.001s/scontrino, €0
   LLaVA:      90% success, 2.234s/scontrino, €0
   ✅ LLaVA VINCE: migliore accuracy + latenza accettabile

💾 Risultati: /kaggle/working/benchmark_llava_results.json
   (45.2 KB)
```

### B: File di output

**File**: `/kaggle/working/benchmark_llava_results.json`

```json
{
  "timestamp": 1693123456.789,
  "environment": "kaggle",
  "device": "cuda",
  "model": "llava-hf/llava-1.5-7b-hf",
  "sample_size": 20,
  "load_time": 120.5,
  "success_rate": 90.0,
  "avg_latency": 2.234,
  "p50_latency": 2.156,
  "p95_latency": 2.891,
  "total_items": 234,
  "total_time": 44.7,
  "results": [
    {
      "image": "002fe2495663e261d29157ba1445c6e539bb6aa1039f66e8fe36275f57c0c2d2.jpg",
      "items": 8,
      "elapsed": 2.341,
      "success": true,
      "error": null
    },
    ...
  ]
}
```

## Interpretazione dei Risultati

### Success Rate

- **> 75%**: LLaVA è accurato, considera come primary method
- **50-75%**: Comparabile a Geometric, ma con migliore accuracy
- **< 50%**: Geometric è più affidabile

### Latenza

- **< 2s per immagine**: Scalabile a 200/day ✅
- **2-5s per immagine**: Accettabile (0.5-1h al giorno)
- **> 5s per immagine**: Problematico per 200/day ⚠️

### Quota Kaggle

**Disponibile**: 30h GPU/week gratis (Tier 2+ membership)

**Calcolo**:
- Media latenza: 2.234s/immagine
- 200 immagini/giorno: 200 × 2.234s = 446.8s = 0.12h
- Quota giornaliera: 30/7 = 4.3h
- Utilizzo: 0.12h / 4.3h = 2.8% della quota ✅

## Decisione Basata su Risultati

### Scenario 1: LLaVA migliore (success_rate > 80%, latenza < 3s)

```
Raccomandazione: Usa LLaVA come extraction method principale
✅ Primary: LLaVA
⚠️  Fallback: Geometric (per 5-10% dei casi anomali)
Costi: €0 (Kaggle quota sufficiente)
Implementazione: 2-3h (setup pipeline Kaggle + local fallback)
```

### Scenario 2: LLaVA comparabile (success_rate ≈ 58%, latenza 2-4s)

```
Raccomandazione: Mantieni Geometric come primary
✅ Primary: Geometric (locale, istantaneo, affidabile)
⚠️  Fallback: LLaVA per edge cases (layout anomali)
Costi: €0
Implementazione: 1h (integrate LLaVA come optional)
```

### Scenario 3: LLaVA peggiore (success_rate < 50%)

```
Raccomandazione: Geometric è la scelta vincente
✅ Primary: Geometric
❌ Skip: LLaVA
Costi: €0
Implementazione: mantieni status quo
```

## Download dei Risultati

Dopo l'esecuzione su Kaggle, scarica i risultati:

```bash
# Dalla pagina del notebook Kaggle: "Output" → Download JSON

# Oppure via CLI
kaggle kernels output username/notebook-name -p /tmp/output
```

Poi confronta con il benchmark Geometric:

```bash
# Local
python -c "
import json
with open('data/benchmark_llava_results.json') as f:
    llava = json.load(f)
print(f'LLaVA success: {llava[\"success_rate\"]:.1f}%')
print(f'LLaVA latency: {llava[\"avg_latency\"]:.3f}s')
"
```

## Troubleshooting

### GPU non disponibile su Kaggle

**Problema**: "CUDA not available" oppure CPU mode

**Soluzione**:
1. Vai a Notebook settings (in alto a destra)
2. Accelerator: cambia da "None" a "GPU"
3. Salva e riavvia il kernel

### Timeout durante inference

**Problema**: "CUDA out of memory" oppure inference timeout

**Soluzione**:
```python
# Nei parametri dello script, riduci dimensione immagini
# (già implementato con image_size_limit=1024)

# Oppure usa modello più piccolo
python benchmark_llava.py --sample 10 --model llava-hf/llava-1.5-7b-hf
```

### Dataset non trovato

**Problema**: "Directory not found: /kaggle/input/ticket-tracer-data"

**Soluzione**:
```bash
# Nel notebook Kaggle, verifica la struttura
import os
os.listdir('/kaggle/input')  # Vedi i dataset disponibili
os.listdir('/kaggle/input/ticket-tracer-data/')  # Vedi i file
```

### Import Error per transformers

**Problema**: "No module named transformers"

**Soluzione**: Già gestito nello script con fallback install automatico, ma se persiste:

```python
# Nel notebook, cella Python
!pip install -q transformers pillow torch
```

## Prossimi Step

1. **Esegui il benchmark**: segui questa guida su Kaggle
2. **Scarica i risultati**: salva il JSON con i numeri
3. **Confronta**: LLaVA vs Geometric
4. **Decidi**: quale metodo per produzione
5. **Implementa**: integra il metodo vincente nella pipeline

---

**Documento correlato**: [docs/96_benchmark_estrazione_prodotti.md](96_benchmark_estrazione_prodotti.md) — risultati Geometric baseline
