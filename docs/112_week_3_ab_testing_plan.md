# Week 3: A/B Testing + Gradual Rollout Plan

**Timeline**: 3-5 giorni (full 1 week available if needed)  
**Goal**: Validate HYBRID pipeline on real production traffic before full rollout  
**Success Criteria**: Metrics support >5% accuracy improvement with <3% hallucination rate

---

## Day 1-2: A/B Test Setup (10% HYBRID, 90% Geometric)

### Task 3.1: Deploy Feature Flag

```python
# app/config/feature_flags.py
HYBRID_EXTRACTION_RATIO = 0.10  # 10% of receipts → HYBRID

def should_use_hybrid(receipt_id: int) -> bool:
    """Deterministic: same receipt always gets same treatment."""
    return (receipt_id % 100) < HYBRID_EXTRACTION_RATIO * 100
```

### Task 3.2: Instrument Metrics Collection

Before extraction:
```python
if should_use_hybrid(receipt_id):
    result = hybrid_pipeline.extract(...)  # NEW (HYBRID)
    metrics.record("hybrid", result)
else:
    result = geometric_pipeline.extract(...)  # OLD (control)
    metrics.record("geometric", result)
```

Metrics to collect:
- **Accuracy**: extracted items match ground truth
- **Hallucination**: items in extraction not in receipt
- **Latency**: P50, P90, P99
- **Manual review rate**: % flagged for human review
- **User impact**: customer complaints, manual corrections

### Task 3.3: Manual Review Workflow

```
LLaVA output with flags['requires_review'] → Queue
  ↓
Human review (15 sec/scontrino, expert pool ~3 people)
  ↓
Decision: Approve / Correct / Reject
  ↓
DB update: verified_by_human=true, verification_notes
  ↓
Feedback loop: log corrections for model improvement
```

**SLA**: Review within 24h

---

## Day 3-4: Gradual Rollout (IF metrics good)

### Day 3 Morning: Analyze Day 1-2 data

**Decision Gate**:
```
IF accuracy_hybrid > accuracy_geometric + 10%
   AND hallucination_rate < 3%
   AND manual_review_rate < 10%
THEN proceed to 50%
ELSE investigate / pause
```

### Day 3 Afternoon: 50% HYBRID rollout

```python
HYBRID_EXTRACTION_RATIO = 0.50
```

Monitor for 24h:
- Alert on hallucination > 5% (pause if triggered)
- Alert on latency P99 > 3s (rate limit LLaVA if triggered)
- Alert on manual review queue > 200 (scale up review team if needed)

### Day 4: 100% HYBRID rollout (if metrics stable)

```python
HYBRID_EXTRACTION_RATIO = 1.00
```

Full rollout with continuous monitoring.

---

## Rollback Plan (if metrics bad)

**Automatic rollback triggers**:
- Hallucination rate > 5% → revert to HYBRID_EXTRACTION_RATIO=0
- Latency P99 > 5s → revert to HYBRID_EXTRACTION_RATIO=0
- Manual review queue > 500 → throttle LLaVA (reduce RATIO to 0.5)

**Manual rollback**:
```bash
# 1. Set feature flag to 0
HYBRID_EXTRACTION_RATIO = 0.00

# 2. All new extractions → Geometric only
# 3. Keep LLaVA disabled for 24h (investigation)
# 4. Investigate root cause from logs
# 5. Fix + re-test before re-enabling
```

**Estimated rollback time**: < 1 hour

---

## Daily Monitoring (Week 3 + post-deploy)

### Metrics Dashboard (update every 15 min)

| Metric | Target | Warning | Error |
|--------|--------|---------|-------|
| **Accuracy (HYBRID)** | ≥74% | <72% | <70% |
| **Accuracy (Geometric)** | ≥58% | <56% | <54% |
| **Hallucination Rate** | <2% | >3% | >5% |
| **Latency P50** | <100ms | - | >200ms |
| **Latency P99** | <2000ms | >2500ms | >3000ms |
| **Manual Review Queue** | <50 | >100 | >200 |
| **Review Completion Rate** | >90% | <80% | <70% |
| **GPU Utilization** | <70% | >80% | >95% |

### Daily Standup (9:00 AM)

- 10-min briefing on overnight metrics
- Any alert? Investigate root cause
- Proceed or pause rollout?

### Acceptance Criteria (Week 3 end)

**Minimum (to complete)**: 
- ✅ Rollout reached 100%
- ✅ No critical errors (data corruption, crashes)
- ✅ Manual review queue manageable (<50 pending)

**Target (post-deploy success)**:
- ✅ Accuracy improvement ≥10% (74% vs 58%)
- ✅ Hallucination rate <3% (measured real data)
- ✅ Manual review rate <5%
- ✅ Latency P99 <2s

---

## A/B Test Statistical Significance

**Sample size**: ~100 receipts per treatment (200 total) sufficient for:
- **Significance level**: 95% (α=0.05)
- **Detectable effect**: 10% improvement (58% → 64%)
- **Power**: 80% (β=0.20)

**Hypothesis test**:
```
H0: Accuracy_hybrid = Accuracy_geometric (null)
H1: Accuracy_hybrid > Accuracy_geometric (alternative)

Test statistic: (mean_hybrid - mean_geometric) / SE
Decision: If p-value < 0.05, reject H0 (statistically significant)
```

---

## Post-Deploy (Weeks 4+)

### Week 4: Stabilization

- Monitor metrics daily
- Tune confidence threshold if needed
- Increase manual review capacity if queue backs up

### Weeks 5-8: Optimization

- Analyze hallucinations (retrain LLaVA if patterns emerge)
- A/B test confidence thresholds (40%, 50%, 60%)
- Implement smart prioritization (complex receipts → LLaVA first)
- Reduce manual review to <2%

### Ongoing

- Monitor hallucination rate (weekly report)
- Track GPU costs vs accuracy gains
- Plan for LLaVA model updates (better versions as available)

---

## Risk Mitigation Summary

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Hallucination explosion | LOW | HIGH | Validators + manual review gate |
| GPU failures | LOW | HIGH | Geometric fallback (always works) |
| Review queue backs up | MEDIUM | MEDIUM | On-call review team, auto-escalate |
| Latency SLA breach | LOW | MEDIUM | Rate limiting, async queuing |
| Data corruption | VERY LOW | CRITICAL | Transaction integrity, DB backups |

**Overall risk**: **BASSO** (failsafes in place at every level)

---

## Deliverables by Week 3 End

- ✅ A/B test results (Day 2)
- ✅ Gradual rollout completed (Day 4)
- ✅ Manual review workflow operational
- ✅ Monitoring dashboard live
- ✅ Post-deploy monitoring report

---

## Next Iteration (Future)

Once HYBRID is stable in production:
1. **LLaVA fine-tuning**: Retrain on customer receipts for domain-specific improvement
2. **Confidence calibration**: Dynamic threshold based on receipt complexity
3. **Model ensemble**: Combine Geometric + LLaVA scores before fallback decision
4. **Multilingual support**: Extend to Spanish, French receipts
5. **Category classification**: Use LLaVA for product categorization (not just extraction)

---

**Status**: Ready for Week 3 start  
**Owner**: Extraction Team  
**Approval**: ✅ (based on Week 1-2 results)
