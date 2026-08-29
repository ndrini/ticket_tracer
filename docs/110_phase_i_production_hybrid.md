# Phase I: Produzione - HYBRID Extraction Pipeline

**Timeline**: 3.5 settimane (settimanale: 8-9 agosto, 15-16 agosto, 22-23 agosto)  
**Status**: Ready to Start  
**Team**: 1 Engineer  

---

## Architettura Finale

```
Receipt Image
    ↓
[1] GEOMETRIC (Primary)
    ├─ Success & confidence > 50%? → Output DB (extraction_method='geometric')
    └─ Fail OR confidence ≤ 50%? → [2]
                                      ↓
                        [2] LLaVA (Fallback, GPU async)
                            ├─ Success? → Output DB (method='llava_fallback', verified_flag=false)
                            └─ Fail? → Requires Manual Review (method='none')
```

### Metriche Target

| Metrica | Target | Status |
|---------|--------|--------|
| **Geometric Success Rate** | ≥ 85% | Measured: 58% |
| **LLaVA Success Rate (fallback)** | ≥ 70% | Measured: 74.6% |
| **Overall Accuracy** | ≥ 70% | Estimated: 90% × 58% + 10% × 74% = ~60% |
| **Hallucination Rate** | ≤ 5% | Measured: 4.2% |
| **Latency (P50)** | ≤ 1s | Geometric: 0.001s, LLaVA: 0.5s |
| **Latency (P99)** | ≤ 3s | Target: <3s (LLaVA P99 ~1.5s + queue) |

---

## Week 1: Validazione Estesa + Automated Validation

### Day 1-3: Validazione su 100 Scontrini

**Task 1.1**: Selezionare 100 scontrini RAPPRESENTATIVI
```bash
# Criteri:
# - Da almeno 5 negozi diversi (non clustering locale)
# - Mix: 30% semplici (1-5 items), 50% normali (5-20 items), 20% complessi (20+ items)
# - 3-4 mesi di dati (varianza temporale)

# Script: scripts/select_validation_sample.py
# Output: data/validation_sample_100.json (SHA256, store, item_count)
```

**Task 1.2**: Esegui LLaVA su 100 scontrini (con 3 run per ognuno)
```bash
# Simile a validate_llava_vs_geometric.py ma su 100 scontrini
# Aggiungi: confidence score, per-scontrino accuracy

uv run python scripts/validate_llava_100_samples.py \
  --sample-file data/validation_sample_100.json \
  --output data/validation_100_results.json
```

**Task 1.3**: Calcola statistiche
- Accuracy media ± std
- Hallucination rate
- Margin of Error (MoE)
- Stratificazione: accuracy per store, per complessità scontrino

**Output**: Report con decisione go/no-go per W2

### Day 4-5: Implementa Automated Validation

**Task 1.4**: Definisci validation rules
```python
# app/etl/llava_validators.py

class LLaVAValidator:
    def validate(self, items, receipt_total, receipt_store):
        """Post-process LLaVA output, flag hallucinations"""
        
        errors = []
        
        # Rule 1: Sum check (±5%)
        item_sum = sum(item['price'] for item in items)
        if not (receipt_total * 0.95 <= item_sum <= receipt_total * 1.05):
            errors.append(f"Sum mismatch: {item_sum} vs {receipt_total}")
        
        # Rule 2: Catalog check (product name exists?)
        catalog = load_canonical_products()
        for item in items:
            if not fuzzy_match(item['name'], catalog):
                errors.append(f"Not in catalog: {item['name']}")
        
        # Rule 3: Price sanity (€0.01 - €100)
        for item in items:
            if not (0.01 <= item['price'] <= 100):
                errors.append(f"Price out of range: {item['price']}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "risk_level": "high" if len(errors) > 2 else "medium" if len(errors) > 0 else "low"
        }
```

**Task 1.5**: Test validators su 100 scontrini
- Hallucination filtering rate
- False positive rate (valid items flagged erroneously)
- Adjustment per store/complexity

**Output**: Validators ready for W2 integration

---

## Week 2: Implementazione Fallback Logic

### Day 1-2: Fallback Pipeline

**Task 2.1**: Crea hybrid extraction pipeline
```python
# scripts/pipeline_estrazione_hybrid.py

class HybridExtractionPipeline:
    def __init__(self):
        self.geometric = GeometricExtractor()
        self.llava = LLaVAExtractor(async=True)  # GPU async
        self.validator = LLaVAValidator()
    
    def extract(self, receipt_image, receipt_id):
        """Primary: Geometric, Fallback: LLaVA"""
        
        # Step 1: Geometric (fast, reliable)
        geo_result = self.geometric.extract(receipt_image)
        if geo_result.success and geo_result.confidence > 0.50:
            return {
                "method": "geometric",
                "items": geo_result.items,
                "confidence": geo_result.confidence,
                "flags": []
            }
        
        # Step 2: LLaVA fallback (slower, higher accuracy)
        try:
            llava_result = self.llava.extract(receipt_image, async=True)
            
            # Validate LLaVA output
            validation = self.validator.validate(
                llava_result.items,
                receipt_total=geo_result.total or None,
                receipt_store=geo_result.store or None
            )
            
            if validation['valid'] or validation['risk_level'] == 'low':
                return {
                    "method": "llava_fallback",
                    "items": llava_result.items,
                    "confidence": llava_result.confidence,
                    "flags": ["verified_llava_low_risk"] if validation['valid'] else ["requires_review"]
                }
            else:
                # High risk hallucination
                return {
                    "method": "none",
                    "items": [],
                    "confidence": 0,
                    "flags": ["requires_manual_review", f"validation_errors: {validation['errors']}"]
                }
        
        except Exception as e:
            # LLaVA timeout/error → fallback to Geometric anyway
            logger.warning(f"LLaVA failed: {e}, using Geometric")
            return {
                "method": "geometric_fallback_after_llava_error",
                "items": geo_result.items,
                "confidence": geo_result.confidence,
                "flags": ["llava_error"]
            }
    
    def db_insert(self, receipt_id, result):
        """Insert extraction result to DB"""
        # app/db/db_manager.py
        # INSERT INTO receipt_lines (receipt_id, product_id, extraction_method, flags)
        # + UPDATE receipts (extraction_method, extraction_flags)
```

**Task 2.2**: Setup async GPU inference
```python
# Celery task per LLaVA async
# app/tasks/extraction_tasks.py

from celery import shared_task

@shared_task
def extract_llava_async(receipt_id, image_path):
    """Async LLaVA extraction, queued"""
    model = LLaVAExtractor()
    result = model.extract(image_path)
    
    # Save to DB when done
    db_insert_extraction(receipt_id, result)
    return result
```

**Task 2.3**: Database schema update
```sql
-- Add flags column to receipts
ALTER TABLE receipts ADD COLUMN extraction_flags TEXT DEFAULT NULL;

-- Track which extractions were manual
ALTER TABLE receipt_lines ADD COLUMN verified_by_human BOOLEAN DEFAULT FALSE;
ALTER TABLE receipt_lines ADD COLUMN verification_timestamp TIMESTAMP DEFAULT NULL;
```

### Day 3-4: Monitoring + Alerting

**Task 2.4**: Setup Grafana dashboard
```
Metrics to track:
- Geometric success rate (%)
- LLaVA success rate (%)
- Fallback rate (%)
- Hallucination rate (%)
- Latency P50, P90, P99
- Manual review queue size
- GPU utilization (%)
- API errors (rate)
```

**Task 2.5**: Setup alerts
```python
# Alert conditions
- Hallucination rate > 5% → Slack alert
- Latency P99 > 3s → Slack alert
- LLaVA error rate > 1% → Slack alert
- GPU utilization > 80% → Slack warning
- Manual review queue > 100 → Slack alert
```

### Day 5: Integration Testing

**Task 2.6**: E2E test (50 scontrini synthetic)
- Geometric success
- LLaVA fallback success
- Validators catch hallucinations
- DB inserts are correct

**Output**: Hybrid pipeline ready for W3 A/B test

---

## Week 3: A/B Testing + Slow Rollout

### Day 1-2: A/B Test Setup (10% HYBRID, 90% Geometric)

**Task 3.1**: Deploy HYBRID to 10% traffic
```python
# app/config/feature_flags.py
HYBRID_EXTRACTION_RATIO = 0.10  # 10% → HYBRID, 90% → Geometric

# Before extraction:
if random.random() < HYBRID_EXTRACTION_RATIO:
    result = hybrid_pipeline.extract(image)  # New
else:
    result = geometric_pipeline.extract(image)  # Old (control)
```

**Task 3.2**: Collect metrics daily
- Accuracy comparison (HYBRID vs Geometric baseline)
- Hallucination rate (actual, not simulated)
- Latency impact (P50, P99)
- Manual review volume

**Task 3.3**: Manual review workflow
```
LLaVA output with flags['requires_review'] → Queue
  ↓
Human review (15 sec per scontrino)
  ↓
Approve / Reject / Correct
  ↓
DB update (verified_by_human=true)
  ↓
Feedback loop: log corrections for model improvement
```

### Day 3-4: Gradual Rollout (10% → 50% → 100%)

**If metrics good**:
- Day 3 (50% HYBRID): Monitor 24h
- Day 4 (100% HYBRID): Full rollout

**If metrics concerning**:
- Pause rollout, investigate
- May need threshold tuning or validator fixes
- Rollback to Geometric-only if needed

### Day 5: Post-Deploy Monitoring

**Task 3.5**: Daily checks first 2 weeks
- Accuracy stability
- Hallucination trend
- GPU resource usage
- Error rate

---

## Deliverables by Week

### Week 1
- ✅ Validation report (100 scontrini, MoE < 10%)
- ✅ Automated validators implemented
- ✅ Decision: go/no-go for W2

### Week 2
- ✅ Hybrid extraction pipeline (Geometric + LLaVA fallback)
- ✅ Async GPU inference (Celery)
- ✅ Database schema updated
- ✅ Monitoring dashboard + alerts
- ✅ E2E integration test passing

### Week 3
- ✅ A/B test results (10% HYBRID vs 90% Geometric)
- ✅ Gradual rollout completed (10% → 50% → 100%)
- ✅ Manual review workflow operational
- ✅ Post-deploy monitoring report

---

## Success Criteria

### Minimum (to launch)
- ✅ Hallucination rate < 5% (measured on 100 samples)
- ✅ Accuracy improvement ≥ 10% vs Geometric alone
- ✅ Latency P99 < 3s (acceptable)
- ✅ Manual review queue < 20% of extractions

### Target (after 2 weeks)
- ✅ Overall accuracy ≥ 70% (hybrid average)
- ✅ Hallucination rate < 3% (after automated validation)
- ✅ Manual review queue < 5% of extractions
- ✅ No critical errors (GPU crashes, data corruption)

### Stretch (after 4 weeks)
- ✅ Optimize confidence threshold (data-driven)
- ✅ Add smart prioritization (complex scontrini → LLaVA first)
- ✅ Reduce manual review to < 2%

---

## Rollback Plan

**If metrics are bad**:
1. Set `HYBRID_EXTRACTION_RATIO = 0`
2. All new extractions → Geometric only
3. Keep LLaVA fallback disabled for 24h
4. Investigate: validator issues? LLaVA degradation? Threshold wrong?
5. Fix + re-test on sample before re-enabling

**Estimated rollback time**: < 1 hour

---

## Team & Resources

| Role | Effort | Duration |
|------|--------|----------|
| **Engineer (you)** | 40h | 3 weeks full-time |
| **Manual review** | 5h/week (estimated) | Ongoing |
| **GPU (Kaggle)** | ~10h/week allocation | Within free quota |

---

## Risk Mitigation Summary

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Hallucination explosion | Low | High | Automated validators + manual review |
| GPU unavailable | Low | High | Fallback to Geometric (always works) |
| Accuracy drops | Medium | Medium | A/B test detects, rollback easy |
| Latency SLA breach | Low | Medium | Async LLaVA, rate limiting |

**Overall risk**: **BASSO** (Geometric always available as fallback)

---

## Next Steps

### Immediate (Today)
- [ ] Create `scripts/select_validation_sample.py` (choose 100 scontrini)
- [ ] Update database schema (add flags column)
- [ ] Create validation rules spec

### This Week
- [ ] Execute W1 tasks (validation on 100 scontrini)
- [ ] Implement automated validators
- [ ] Publish W1 report (decision: go/no-go)

### Next Week
- [ ] Implement hybrid pipeline
- [ ] Setup Celery async
- [ ] Integration testing

### Week After
- [ ] A/B test deployment
- [ ] Gradual rollout
- [ ] Production monitoring

---

**Status**: Ready to start Week 1 immediately.  
**Approval**: ✅ Approved by Perplexity, Vibe (with conditions met)  
**Go date**: As soon as validation sample is ready
