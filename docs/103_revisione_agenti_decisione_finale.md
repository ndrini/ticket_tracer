# Revisione Agenti: Decisione Finale HYBRID APPROACH

**Data**: 2026-08-29  
**Agenti**: Perplexity, Vibe  
**Verdict**: ✅ **APPROVAZIONE CONDIZIONATA** (con miglioramenti)

---

## Feedback Perplexity

### Validazione su 8 Scontrini: Sufficiente?

**Verdict**: ❌ **NO per produzione, ⚠️ OK per rollout controllato**

- **Margin of Error**: ±16.5% → accuracy reale potrebbe essere tra 58%-91%
- **Insufficiente per decisione finale**, ma OK per approvazione condizionata con A/B test

**Raccomandazione**: Approvare HYBRID per rollout sperimentale (A/B su 50+ scontrini), non per "final e production-ready"

---

### Accuracy 74.6% Borderline

**Verdict**: ✅ **Accettabile come FALLBACK**

- Come fallback (non primary), 74.6% è buono
- Improvement +16.6% vs Geometric è reale
- Funziona se confinato a porzione limitata dei casi

**Raccomandazione**: Accettabile, ma non per switch totale

---

### Hallucination 4.2%

**Verdict**: ⚠️ **Gestibile solo a basso volume**

| Volume | Hallucination Rate | Gestibilità |
|--------|-------------------|------------|
| 100 scontrini/mese | 4.2 errori | ✅ Facile |
| 1,000 scontrini/mese | 42 errori | ✅ Possibile |
| 10,000 scontrini/mese | 420 errori | ❌ Non scalabile |

**Raccomandazione**: Mitiga con:
1. `verified_llava` flag (non trust senza verifica)
2. Human review obbligatorio
3. Heuristics automatiche per filtrare hallucinations grossolane

---

### Risk Mitigation

**Verdict**: ❌ **Insufficiente così com'è**

Manca:
- ❌ Definizione chiara di quando scatta fallback umano
- ❌ Confidence score per decidere fiducia
- ❌ Canary/slow rollout plan

**Raccomandazione**: Aggiungi:
1. Regole di coerenza (sum prodotti ≈ total, IVA coerente)
2. Confidence score (proxy: lunghezza input, format non visto)
3. Slow rollout: 10-20% dei scontrini per settimana

---

## Feedback Vibe

### Validazione Metodologica: Sufficiente?

**Verdict**: ❌ **8 scontrini troppo pochi, minimo 50-100**

Statistiche:
- **8 scontrini**: MoE ±16.5% → intervallo 58%-91% (inutile)
- **50 scontrini**: MoE ±13.9% → intervallo 60.7%-88.5%
- **100 scontrini**: MoE ±9.8% → intervallo 64.8%-84.4% (accettabile)

**Raccomandazione**: Test su minimo 50, ideale 100 scontrini prima del deploy

---

### Decisione: HYBRID vs Totale vs Geometric

**Verdict**: ✅ **HYBRID è la scelta giusta**

Confronto:
- **Geometric solo**: 58% accuracy (bassa)
- **Switch totale a LLaVA**: 74% accuracy, ma 4.2% hallucination + 0.5s latency
- **HYBRID**: 74% accuracy (quando usato) + fallback deterministico Geometric

**Raccomandazione**: HYBRID massimizza accuracy minimizzando rischio

---

### Timeline 3 Settimane

**Verdict**: ⚠️ **Stretta, ma fattibile con buffer**

| Settimana | Attività | Effort |
|-----------|----------|--------|
| **W1** | Test su 50-100 scontrini | 40h |
| **W2** | Implementazione fallback logic + automated validation | 40h |
| **W3** | A/B test + monitoring setup | 30h |
| **Buffer** | Imprevisti GPU, troubleshooting | 10h |

**Tempo totale**: ~3.5 settimane (realistico)

**Raccomandazione**: Aggiungi buffer per imprevisti GPU

---

### KPIs da Monitorare

**Priorità Alta**:
- ✅ Accuracy (per scontrino e prodotto)
- ✅ Hallucination rate (%)
- ✅ Fallback rate (%)
- ✅ Latency (P50, P90, P99)

**Priorità Media**:
- Confidence score distribuzione
- GPU utilization
- Error rate

**Raccomandazione**: Setup dashboard Grafana con alert automatici

---

## Consensus Agenti

| Punto | Perplexity | Vibe | Consensus |
|-------|-----------|------|-----------|
| **Approval HYBRID** | ⚠️ Condizionato | ✅ Sì | ✅ **Approvato con condizioni** |
| **8 scontrini sufficienti** | ❌ NO | ❌ NO | ❌ **Minimo 50-100 prima deploy** |
| **Accuracy 74.6% OK** | ✅ Fallback | ✅ Fallback | ✅ **Accettabile per fallback** |
| **Hallucination 4.2%** | ⚠️ Gestibile | ⚠️ Limitato volume | ⚠️ **Richiede automazione** |
| **Risk mitigation** | ❌ Insufficiente | ❌ Insufficiente | ❌ **Serve più struttura** |

---

## Azioni Richieste (Prima Implementazione)

### Immediate (Prima della W1)

1. **Seleziona 100 scontrini RAPPRESENTATIVI** (diversi negozi, tipologie)
2. **Definisci confidence threshold**: Testare 40%, 50%, 60%
3. **Implementa validation rules**: Catalogo prodotti, regex, coerenza sum
4. **Prepara monitoring**: Grafana dashboard template

### W1: Validazione Estesa

1. **Esegui LLaVA su 100 scontrini** (simile a ciò che hai fatto con 8)
2. **Calcola MoE** → accuracy con intervallo di confidenza
3. **Misura hallucination rate** su questo set
4. **Cross-validate** → split 2x50 deve entrambi vincere

### W2: Implementazione

1. **Fallback logic**: Geometric → LLaVA se confidence < threshold
2. **Automated validation**: Post-processing LLaVA
3. **Logging dettagliato**: Ogni fallback case loggato per analisi

### W3: Testing & Deploy

1. **A/B test**: 10% traffico su HYBRID, 90% su Geometric solo
2. **Monitoring**: KPIs in tempo reale, alert su anomalie
3. **Slow rollout**: 25% → 50% → 100% con monitoring

---

## Decision Matrix Finale

### ✅ APPROVAZIONE HYBRID

**Condizioni**:
1. ✅ Test su 50-100 scontrini (non 8)
2. ✅ Automated validation implementata
3. ✅ Monitoring real-time con alert
4. ✅ Confidence threshold testato
5. ✅ Human review workflow per hallucinations

**Timeline**: 3.5 settimane (con buffer per imprevisti)

**Risk**: BASSO (Geometric always available as fallback)

**Go/No-Go**: 🟢 **GO** (con condizioni di cui sopra)

---

## Appendice: Dettagli Tecnici (da Vibe)

### Confidence Threshold: Testare

**Suggestione**: Usare **dynamic threshold** basato su accuracy storica di LLaVA

Pseudocode:
```python
# Empiricamente, testare 40%, 50%, 60%
confidence_thresholds = [0.40, 0.50, 0.60]

for threshold in thresholds:
    fallback_rate = (LLaVA_calls / total_calls)
    accuracy = validate_on_testset()
    hallucination_rate = measure_hallucinations()
    
    # Scegli il threshold che massimizza:
    # accuracy * (1 - hallucination_rate) * (1 - fallback_rate)
```

### Async GPU Inference: Gestire Concurrency

**Rischi**:
- GPU saturation → timeout
- Memory leaks (PyTorch VRAM)
- Cold start latency

**Mitigazione**:
1. **Rate limiting**: Max 10 LLaVA richieste in parallelo
2. **Queue system**: Redis + Celery (o simile)
3. **GPU monitoring**: Alert su >80% utilization

---

**Verdict Finale**: ✅ **APPROVATO** con implementazione delle 5 condizioni sopra.

Non buttiamo Geometric, aggiungiamo LLaVA intelligentemente. ✅
