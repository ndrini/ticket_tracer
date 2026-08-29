# Scalabilità Assessment: MVP → Production

**Data:** 2026-08-29  
**Domanda:** Se scalo da 96 foto a 1000 foto (10x), cosa cambia? Vale la pena?

**Risposta breve:** Scalare è utile, ma **non automaticamente**. Servono prerequisiti infrastrutturali altrimenti il rumore rimane rumore.

## Analisi Metriche a Scala

### Sticky Metrics (non cambiano con volume)

**Date Coverage: 71.2%** (rimane fissa)
- Causa: dipende dal **formato filename**, non dal volume
- Con 1000 foto con stesso naming: rimane 71%
- Salire a 90% richiederebbe: OCR date extraction (regeex DD/MM/YYYY) + fallback mtime
- **Azione**: aggiungere H+ prima di scalare, oppure accept 71%

**Weight Coverage: 9%** (potrebbe peggiorare)
- Causa: dipende da **varietà layout OCR** e qualità riconoscimento
- Rischio con 1000 foto: più layout anomali → più errori OCR → peso non estratto correttamente
- Potrebbe: rimanere 9%, salire a 15%, oppure crollare a 5% (non è prevedibile)
- **Azione**: aggiungere data quality checks (OCR loss rate) prima di scalare

### Metriche Migliorabili (cambiano con effort)

**Category Coverage: 100%** (rimane, ma "Altro" crolla)
- Ora: 69% "Altro", 31% categorizzate correttamente
- Con 1000 foto: scoprirai **nuovi prodotti e sinonimi** che il dizionario non conosce
- Rischio: "Altro" sale a 75-80% (più varietà = più unknowns)
- **Beneficio**: con dizionario esteso, "Altro" può scendere a 40-50%
- **Azione**: pianificare workflow per estendere dizionario iterativamente (Fase I)

**Catalog Stability: (?) — da misurare**
- Ora: 664 prodotti canonici da 96 foto
- Con 1000 foto: quanti nuovi prodotti unici scoprirai?
- Se scopri +500 nuovi prodotti, il catalogo diventa instabile (cambia ogni week)
- Se scopri +50, il catalogo è stabile (convergenza della long-tail)
- **Azione**: misurare a 200 foto, 500 foto per capire la curva

### Metriche che Diventano Credibili

**Trend temporale: (rumoroso ora, credibile a scala)**
- Ora: 11 mesi, ma con 96 foto = ~9 scontrini/mese = rumore
- Con 1000 foto: ~90 scontrini/mese = segnale
- Soglia di credibilità: **50+ scontrini/mese/categoria** (rule of thumb)
- **Beneficio reale**: puoi rilevare "Ho speso +20% in frutta ad agosto"
- **Azione**: non fare budget decisioni su <96 foto, attendere 300+

**Anomaly Detection: (impossibile ora, possibile a 500+)**
- Ora: "Speso €250 in frutta" è baseline; non conosco varianza
- Con 500 foto: conosci varianza mensile, puoi rilevare outlier
- "Questo mese ho speso €400 (3x media)" = rilevabile
- **Beneficio reale**: alert su spesa anomala
- **Azione**: aggiungere Fase J (budget alerts) solo dopo 300+ foto

## Bottleneck Reale

### Rank 1: LLM Extraction (Latenza, Rate Limit, Costi)

**Problema**:
- Fase C (LLM estrazione) è il passo più lento (~3-5 min per 96 foto)
- Con 1000 foto: 30-50 minuti, possibilmente timeout
- Rate limit: rischio di colpi di "429 Too Many Requests"
- Costi: LLM API × 1000 foto = +€X (poco oggi, ma cresce)

**Mitigation**:
- Implementare batching (4-8 foto per batch)
- Caching del prompt + reuse della cache (28s → 0.8s con reuse)
- Retry exponential backoff
- Considerare modello più economico (Claude Haiku vs Opus)

### Rank 2: OCR Quality Degradation

**Problema**:
- Fase B (OCR geometrico) funziona per layout "standard" (cartaceo)
- Con 1000 foto: più varianza di receipt (ricevute fotografate, stampate male, scansioni)
- Rischio: drop-off in OCR success rate (oggi 287/317 = 90.5%, con 1000 potrebbe crollare a 70%)

**Mitigation**:
- Aggiungere quality check per OCR (numero di parole riconosciute, confidenza)
- Classificare i "bad OCR receipts" e gestirli separatamente
- Monitorare OCR loss rate per mese

### Rank 3: Categorie Instabili

**Problema**:
- Con nuovi prodotti emerge il 69% "Altro" come problema reale
- Se "Altro" sale a 75-80%, i report diventano inutili ("spendo 75% in prodotti sconosciuti?")

**Mitigation**:
- Fase I: estendi dizionario keyword (5-10 ore di lavoro)
- ML-based suggestion: usa product names to cluster → suggest category
- Non aspettare 100%, accept 50-60% "Altro" come baseline realistica

## ROI Reale: Quando Diventa Utile

### MVP (Ora): 96 foto, 11 mesi coperti

| Domanda | Risposta | Affidabilità |
|---------|----------|--------------|
| "Quanto spendo totale?" | €4168.65 | ✅ Certa |
| "Quanto in Frutta?" | €250.07 | ⚠️ Indicativa |
| "Trend: Frutta cresce?" | Dati insufficienti | ❌ Rumore |
| "Budget: posso spendere €200/mese in frutta?" | N/A - no baseline | ❌ Impossibile |

### A 300 foto (3x scale): 6-12 mesi coperti

| Domanda | Risposta | Affidabilità |
|---------|----------|--------------|
| "Quanto spendo totale?" | Preciso | ✅ Certa |
| "Quanto in Frutta?" | Preciso | ✅ Certa |
| "Trend: Frutta cresce?" | Rilevabile | ⚠️ Inizia a emergere |
| "Budget: €200/mese ok?" | Baseline calcolabile | ⚠️ Usabile |

### A 1000 foto (10x scale): 12-24 mesi coperti

| Domanda | Risposta | Affidabilità |
|---------|----------|--------------|
| "Quanto spendo totale?" | Preciso | ✅ Certa |
| "Quanto in Frutta?" | Preciso con varianza | ✅ Certa |
| "Trend: Frutta cresce?" | Chiaro (±5% confidence) | ✅ Affidabile |
| "Budget: €200/mese ok?" | Personale e robusto | ✅ Affidabile |
| "Anomalia: ho speso 3x?" | Rilevabile | ✅ Affidabile |

**Threshold di utilità: 300-500 foto** (6-12 mesi), non prima.

## Cosa Preparare ORA (Prima di Scalare)

### Must-Have (Bloccanti)

1. **LLM Robustness**
   - [ ] Aggiungere batching + retry logic
   - [ ] Rate limit handling
   - [ ] Monitorare tempo/costo per foto
   - Effort: 4-6h

2. **DB Indici**
   - [ ] Index su `(category, date)` per report veloce
   - [ ] Index su `(product_id, receipt_id)` per join
   - Effort: 1-2h

3. **Quality Metrics**
   - [ ] OCR loss rate (righe perse vs. expected)
   - [ ] Parse failure rate (items non estratti)
   - [ ] Unknown category rate (% "Altro")
   - [ ] Date coverage per mese
   - Effort: 3-4h

### Nice-to-Have (Non Bloccanti, ma Utili)

4. **Catalog Governance**
   - [ ] Workflow per aggiungere sinonimi (non ad-hoc)
   - [ ] Versioning del dizionario keyword
   - Effort: 2-3h

5. **Regression Testing**
   - [ ] Set di "problematic receipts" (layout anomali)
   - [ ] Test che coverage non cala su nuove fasi
   - Effort: 2-3h

## Roadmap per Production

### Phase 1: Stabilizzare MVP (Ora → 2 settimane)

- [ ] Merge `feat/catalog-normalization-e` a `main`
- [ ] Aggiungere LLM robustness (batching, retry)
- [ ] Aggiungere DB indici
- **Effort**: 8-12h
- **Output**: MVP stabile, pronto per 300+ foto

### Phase 2: Scalare a 300 foto (2-6 settimane)

- [ ] Raccogliere 300 foto (o generare con strategie synthetic)
- [ ] Runfare la pipeline completa E-H
- [ ] Misurare quality metrics
- [ ] Decidere: catalog governance necesaria?
- **Effort**: 10-20h (maggior parte è data collection)
- **Output**: dati per 6-12 mesi, threshold di affidabilità

### Phase 3: Passare a Production (6-12 settimane)

- [ ] Fase I: estendere categorie a 50-60% coverage
- [ ] Fase J: aggiungere budget alerts
- [ ] Monitoring dashboard (trend mensile, anomaly)
- [ ] Automate pipeline: run settimanale
- **Effort**: 30-40h (sopratutto Fase I)
- **Output**: sistema affidabile per budget tracking

## Decisione Finale

**Vale la pena scalare a 1000 foto?**

✅ **SÌ**, ma:
1. **Non subito**: attendere 300+ foto e 6-12 mesi di dati prima di budget decisions
2. **Non gratis**: richiedere infra work (LLM robustness, indici, quality metrics)
3. **Con condizioni**: se vuoi davvero usarlo per budget/trend, non solo "curiosità"

❌ **NO**, se:
- Vuoi restare a "curiosità" (96 foto bastano)
- Non puoi sostenere il costo LLM × 1000
- Non vuoi fare la Fase I (estendere categorie)

**Raccomandazione**: Merge a `main` adesso, scalare a 300 foto entro 6 settimane, valutare dopo.

---

**Documento correlato**: [docs/00_master_plan.md](00_master_plan.md) (roadmap generale)
