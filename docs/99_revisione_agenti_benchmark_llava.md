# Revisione Agenti: Benchmark LLaVA su Kaggle

**Data**: 2026-08-29  
**Consultati**: Perplexity, Vibe  
**Decisione**: APPROVE con riserve — vai al benchmark, ma riconsidera se accuracy non migliora significativamente

## Feedback Perplexity

### 1. LLaVA 1.5 7B è il modello giusto?

**Parere**: Utilizziabile, ma **non ideale** per scontrini.
- LLaVA è **VLM generalista**, non specializzato per OCR strutturato su receipts
- Testo piccolo, layout irregolare, numeri precisi → LLaVA fatica
- **Modelli migliori**: LLaVA-NeXT, oppure OCR+LLM (Tesseract + Claude)
- **Per questo benchmark**: OK come baseline, ma non aspettarsi performance di Claude Vision

### 2. Accuracy attesa: LLaVA vs Claude LLM

| Metodo | Accuracy | Note |
|--------|----------|------|
| **Claude 3.5 Vision** | 94-97% | Campi standard; 88% su linee complesse |
| **LLaVA 1.5 7B** | 70-85% | Scenario ben calibrato; realisticamente 60-80% su dataset reale |
| **Geometric (baseline)** | 58% | Locale, veloce, affidabile |

**Conclusione Perplexity**: LLaVA **non batte Claude**, ma potrebbe battere Geometric se prompt ben calibrato.

### 3. Prompt: generico vs specializzato?

**Verdict**: Prompt generico è **insufficiente**.

Serve schema esplicito con:
- JSON strutturato (campi obbligatori)
- Instruzione chiara su cosa fare con sconti/IVA/edge cases
- Esempi specifici per receipts

**Per il test**: Il prompt nel benchmark è troppo generico. Se risultati deludenti, la causa potrebbe essere il prompt, non il modello.

### 4. Valori soglia realistici?

**75% success rate**: Ambizioso ma possibile  
**< 3s latenza**: Realistico su GPU P100/T4  
**Rischio**: Modelli grandi potrebbero superare VRAM (mitigazione: float16, ridimensionamento immagini)

**Perplexity verdict**: I valori sono ragionevoli, ma **dipendono molto dal prompt**.

### 5. Quale metodo sceglieresti?

**Perplexity non ha dato una scelta netta**, ma ha sottolineato che **Claude Vision** è il vero competitor, non LLaVA generalista.

---

## Feedback Vibe

### 1. Variabili mancanti dal piano

Vibe ha identificato 5 gap:
1. **Affidabilità Kaggle** — downtime, quota GPU, SLA
2. **Costi nascosti** — rate limiting, rettifiche manuali se fallisce
3. **Consistenza** — varianza tra run (LLaVA è probabilistico)
4. **Manutenzione** — aggiornamenti modello, drift temporale
5. **Metriche fallback** — quando LLaVA fallisce, quanti recupera Geometric?

**Azione**: Aggiungi queste metriche al benchmark.

### 2. Se 60-70% (non 75%)?

**Vibe verdict**: **NO, non è worth it**.
- Gain: +2-12% accuracy vs Geometric (non +20-30%)
- Latenza: 3000× peggio (istantaneo vs 2-3 secondi)
- **Trade-off non ripaga**

Geometric rimane superiore: deterministico, gratis, affidabile.

### 3. Effort integrazione in produzione

**Vibe stima**: **Giorni-settimane** di lavoro.
- Fallback logic (policy, threshold switches)
- Monitoring (health check GPU, latency alert)
- A/B testing e regression testing
- Retraining pipeline se il modello aggiorna

**Implicazione**: Non è un "merge e finito", è infrastruttura persistente.

### 4. Scelta finale di Vibe

**Geometric.** LLaVA solo se:
- ✅ Success rate **> 75%** AND
- ✅ Latenza **< 1s** AND  
- ✅ Uptime **> 99.5%**
- ✅ Accuracy **validato su dati reali** (non benchmark)

**Verdict di Vibe**: Con i dati attuali, il rischio supera il benefit. **Priorità: stabilità e velocità.**

---

## Sintesi: Consenso fra Agenti

| Agente | Verdict | Raccomandazione |
|--------|---------|---|
| **Perplexity** | ⚠️ Ambiguo | LLaVA potrebbe funzionare, ma dipende da prompt. Non batte Claude. |
| **Vibe** | ❌ Sconsiglia | Geometric è migliore finché LLaVA non migliora **significativamente** (>75% + <1s) |
| **Consensus** | ⚠️ CONDITIONAL | Vai al benchmark, ma riconsidera se accuracy non migliora almeno a 70% |

---

## Azione Raccomandata: Benchmark MODIFICATO

### Go / No-Go

**GO al benchmark**, ma con **aspettative calibrate**:
1. Se LLaVA > 75% + latenza < 1.5s → **Consider switching**
2. Se LLaVA 65-75% + latenza 2-3s → **Hybrid approach** (Geometric primary, LLaVA fallback)
3. Se LLaVA < 65% → **Mantieni Geometric**, risorse dedicate a migliorare il prompt

### Modifiche al Piano Originale

1. **Migliora il prompt**
   - Dalla versione generica a una specializzata per receipts
   - Includi schema JSON esplicito
   - Aggiungi esempi di edge cases (sconti, IVA, subtotali)

2. **Aggiungi metriche fallback**
   - Quando LLaVA fallisce (< 2 items estratti), quanti Geometric recupera?
   - Misura il **recovery rate** del fallback

3. **Testa su subset di dati reali**
   - Non solo primi 20 scontrini, anche casi "difficili" (layout anomali, OCR scarso)
   - Misura **variance tra run** (riproducibilità)

4. **Stima costo operativo**
   - Quanto tempo GPU serve per 200 scontrini/giorno?
   - È sostenibile con la quota Kaggle (30h/week)?

5. **Documenta fallback logic**
   - Se implementiamo LLaVA, come gestire timeout/OOM?
   - Quando switchare a Geometric?

---

## Decisione Finale

**Proceed al benchmark con 2 scenari**:

### Scenario A: LLaVA Wins (success > 75%, latency < 1.5s)
```
Decisione: Passa a LLaVA come primary + Geometric fallback
Timeline: 2-3 settimane di integrazione
ROI: +20-30% accuracy, costo nullo
Risk: Affidabilità Kaggle GPU, manutenzione pipeline
```

### Scenario B: LLaVA è Comparabile (60-75% success, 2-3s latency)
```
Decisione: Hybrid approach
- Primary: Geometric (locale, affidabile, rapido)
- Fallback: LLaVA su items estratti da Geometric con bassa confidenza
Timeline: 1 settimana di integrazione
ROI: +5-15% accuracy incrementale
Risk: Complessità fallback logic
```

### Scenario C: LLaVA Perde (< 60% success)
```
Decisione: Mantieni Geometric
Timeline: 0 (status quo)
ROI: Nessuno, ma evita rischi
Action: Focalizzati su migliorare prompt di Geometric, oppure investire su Claude fallback
```

---

## Approvazione Agenti

✅ **Perplexity**: "Procedi col benchmark, ma calibra le aspettative su accuracy Claude (94-97%) vs LLaVA (60-80%)"  
✅ **Vibe**: "Go, ma riconsidera se accuracy non batte Geometric di almeno 15 punti percentuali"

**Consenso**: Benchmark è **worth doing**. Costo nullo, insight alto.

---

## Prossimi Step

1. ✅ **Aggiorna script benchmark** con prompt specializzato per receipts
2. ✅ **Aggiungi metriche fallback** (recovery rate, variance)
3. ⏳ **User esegue benchmark** su Kaggle GPU (20 minuti)
4. ⏳ **Analizza risultati** vs Geometric baseline
5. ⏳ **Decidi**: Geometric keep, Hybrid, oppure LLaVA switch
6. ⏳ **Implementa**: la soluzione scelta in Fase I

---

**Documento correlato**: 
- [docs/96_benchmark_estrazione_prodotti.md](96_benchmark_estrazione_prodotti.md) — Geometric baseline
- [docs/97_esecuzione_benchmark_llava_kaggle.md](97_esecuzione_benchmark_llava_kaggle.md) — Setup tecnico
- [docs/98_istruzioni_benchmark_llava_finale.md](98_istruzioni_benchmark_llava_finale.md) — Step-by-step user
