# ✅ BENCHMARK LLaVA: Revisione Completata, Pronto per Esecuzione

**Status**: ✅ Approvato da agenti (Perplexity, Vibe)  
**Data**: 2026-08-29  
**Prossima azione**: User esegue benchmark su Kaggle GPU (20 minuti)

---

## Cosa è Stato Fatto

### 1. Smoke Test Geometric ✅
- **Risultato**: 58% success rate, 0.001s latenza, €0
- **Conclusione**: Baseline affidabile e veloce
- **Documento**: `docs/96_benchmark_estrazione_prodotti.md`

### 2. Preparazione Benchmark LLaVA ✅
- **Script**: `scripts/kaggle_benchmark_llava.py` — completo con GPU detection, metriche avanzate
- **Documentazione**: 
  - `docs/97_esecuzione_benchmark_llava_kaggle.md` — guida tecnica
  - `docs/98_istruzioni_benchmark_llava_finale.md` — step-by-step user
- **Revisione agenti**: `docs/99_revisione_agenti_benchmark_llava.md`

### 3. Revisione da Agenti ✅

**Perplexity**:
- LLaVA 1.5 7B è utilizzabile ma **non ideale per OCR strutturato**
- Accuracy attesa: **70-85%** (vs Claude 94-97%, Geometric 58%)
- **Prompt generico insufficiente** → aggiornato a specializzato
- Valori soglia realistici

**Vibe**:
- Piano manca **affidabilità Kaggle**, **costi nascosti**, **monitoring**
- Se 60-70% accuracy: **NO**, non worth it vs Geometric
- Effort integrazione: **giorni-settimane** se LLaVA wins
- **Scelta finale di Vibe**: Geometric, a meno che LLaVA non sia >75% + <1s

**Consensus agenti**: ✅ **Approve il benchmark** con aspettative calibrate

---

## Miglioramenti Implementati

### 1. Prompt Specializzato
❌ Prima:
```
Estrai SOLO i nomi e prezzi dei prodotti da questo scontrino.
```

✅ Dopo:
```
You are an assistant that extracts structured product data from receipt images.

TASK: Extract ONLY purchased items (products with prices).

RULES:
1. Return ONLY valid JSON, no other text
2. Ignore: headers, totals, VAT, subtotals, discounts, empty lines, merchant info
3. Extract each item with name and price in decimal format (X.XX)
4. If multiple items on same line, extract each separately
5. If quality is poor or no items found, return: []

FORMAT:
[{"name": "product name", "price": X.XX}, ...]
```

### 2. Metrica Fallback
**Nuova**: `fallback_recovery_rate`
- Quando LLaVA fallisce (<2 items), quanti Geometric recupererebbe?
- Stima: Geometric 58% success rate
- Se LLaVA 75% e Geometric 58%, recovery = +17 punti %

### 3. Soglie Decisionali Aggiornate
| Scenario | Success Rate | Latency | Raccomandazione |
|----------|--------------|---------|---|
| A (LLaVA Wins) | > 75% | < 1.5s | ✅ **Switch a LLaVA** + Geometric fallback |
| B (Competitivo) | 70-75% | < 3s | ⚠️ **Hybrid**: Geometric primary, LLaVA fallback |
| C (Parziale) | 60-70% | 2-5s | ❌ **Mantieni Geometric**, too risky |
| D (LLaVA Perde) | < 60% | > 5s | ❌ **Status quo** Geometric |

---

## Come User Esegue il Benchmark

### Step 1: Prepara Dati (5 min)
```bash
# Upload immagini personali su Kaggle Dataset
mkdir ~/kaggle-dataset/ritagli
cp private/campione_validato/*.jpg ~/kaggle-dataset/ritagli/
kaggle datasets create -p ~/kaggle-dataset \
  --dataset-name ticket-tracer-receipts --private
```

### Step 2: Crea Notebook Kaggle (5 min)
- Vai a https://www.kaggle.com/code
- "Create" → "Notebook" → Python + GPU P100/T4
- Add input data: "ticket-tracer-receipts"

### Step 3: Esegui Benchmark (10 min)
Nel notebook, esegui:
```python
%run kaggle_benchmark_llava.py --sample 20 --model llava-hf/llava-1.5-7b-hf
```

### Step 4: Scarica Risultati (2 min)
- "Output" → Scarica `benchmark_llava_results.json`
- Confronta con Geometric baseline

---

## File Chiave per User

| File | Scopo |
|------|-------|
| **docs/98_istruzioni_benchmark_llava_finale.md** | Leggi QUESTA per step-by-step |
| **scripts/kaggle_benchmark_llava.py** | Lo script che user esegue |
| **docs/99_revisione_agenti_benchmark_llava.md** | Capisce cosa chiedono gli agenti |

---

## Risultati Attesi

### Scenario Più Probabile (Vibe predice)
```
LLaVA success rate: 65-75%
LLaVA latency: 2-3s/scontrino
Fallback recovery: +10-15% vs Geometric

Raccomandazione: Hybrid approach
- Geometric: primary (locale, fast, 58%)
- LLaVA: fallback per edge cases che Geometric perde
- ROI: +5-10% accuracy incrementale
- Effort: 1 settimana di integrazione
```

### Scenario Optimistic (Perplexity non esclude)
```
LLaVA success rate: > 75%
LLaVA latency: < 1.5s/scontrino

Raccomandazione: Switch a LLaVA
- Primary: LLaVA (migliore accuracy)
- Fallback: Geometric per timeout/OOM
- ROI: +15-25% accuracy
- Effort: 2-3 settimane di integrazione
```

### Scenario Pessimistico (Vibe lo prevede)
```
LLaVA success rate: < 60%
LLaVA latency: > 3s/scontrino

Raccomandazione: Mantieni Geometric
- No change required
- Focalizza su migliorare il prompt, non il modello
- Alternative: investire su Claude LLM + fallback Geometric
```

---

## Prossimi Step (Timeline)

### Week 1
- [ ] User esegue benchmark su Kaggle GPU (20 min, domani)
- [ ] Scarica JSON risultati
- [ ] Documenta risultati in `docs/100_risultati_benchmark_llava.md`

### Week 2
- [ ] Decidi: Geometric keep / Hybrid / LLaVA switch
- [ ] Se Hybrid o LLaVA: comincia integrazione
- [ ] Se Geometric: focalizza su altre ottimizzazioni

### Week 3-4
- [ ] Implementa la soluzione scelta
- [ ] A/B test vs baseline
- [ ] Deploy in produzione (Fase I)

---

## Checklist per User

**Prima di eseguire il benchmark**:
- [ ] Hai account Kaggle con GPU abilitato?
- [ ] Hai `kaggle.json` configurato in `~/.kaggle/`?
- [ ] Hai immagini da testare (personali o pubbliche)?
- [ ] Leggi `docs/98_istruzioni_benchmark_llava_finale.md`

**Durante il benchmark**:
- [ ] Monitor GPU usage (non deve superare 15 GB)
- [ ] Annota tempo totale di esecuzione
- [ ] Scarica JSON risultati

**Dopo il benchmark**:
- [ ] Confronta LLaVA vs Geometric baseline (58%)
- [ ] Documenta in `docs/100_risultati_benchmark_llava.md`
- [ ] Chiama riunione per decidere: Geometric / Hybrid / LLaVA

---

## Approvazione Finale

✅ **Perplexity**: "Il piano è solido. Procedi col benchmark con prompt specializzato"  
✅ **Vibe**: "Worth testing, ma aspettati 60-75% accuracy. Se vince davvero, allora switcha"  
✅ **Claude (me)**: "Tutto pronto. User esegue domani, avremo dati in 30 minuti"

**VERDICT**: 🟢 **GO**

---

## Supporto Aggiuntivo

Domande durante il benchmark?
- **Errori tecnici**: Vedi "Troubleshooting" in `docs/98_istruzioni_benchmark_llava_finale.md`
- **Domande sul metodo**: Leggi `docs/99_revisione_agenti_benchmark_llava.md`
- **Domande su risultati**: Attendi `docs/100_risultati_benchmark_llava.md` (doc-in-progress)

---

**Preparato da**: Claude Code (Haiku 4.5)  
**Revisto da**: Perplexity, Vibe  
**Status**: ✅ Pronto per esecuzione

**Documento correlato**: [docs/96_benchmark_estrazione_prodotti.md](96_benchmark_estrazione_prodotti.md) — Geometric baseline (vedi per confronto)
