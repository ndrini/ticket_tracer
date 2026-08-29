"""
A/B Test Configuration & Feature Flags

Controls hybrid extraction rollout:
- HYBRID_EXTRACTION_RATIO: 0.10 (10%), 0.50 (50%), 1.00 (100%)
- Deterministic: receipt_id % 100 always yields same treatment
"""

# Feature flag: % of receipts using HYBRID vs GEOMETRIC control
HYBRID_EXTRACTION_RATIO = 0.10  # Start: 10% HYBRID, 90% Geometric control

# Confidence threshold for fallback (tunable)
CONFIDENCE_THRESHOLD_FOR_FALLBACK = 0.50

# Metrics
METRIC_PRIMARY = "accuracy"  # Main metric we're optimizing
METRIC_GUARDRAIL = ["hallucination_rate", "latency_p99", "manual_review_rate"]

# Decision thresholds
ACCURACY_IMPROVEMENT_TARGET = 0.10  # ≥ 10% improvement to scale
HALLUCINATION_RATE_MAX = 0.03  # < 3%
MANUAL_REVIEW_RATE_MAX = 0.05  # < 5%
LATENCY_P99_MAX = 2000  # < 2000 ms


def should_use_hybrid(receipt_id: int) -> bool:
    """
    Deterministic assignment: same receipt always gets same treatment.

    Args:
        receipt_id: Database receipt ID

    Returns:
        True if receipt should use HYBRID pipeline
        False if receipt should use GEOMETRIC control
    """
    return (receipt_id % 100) < int(HYBRID_EXTRACTION_RATIO * 100)


def get_ab_group(receipt_id: int) -> str:
    """Get A/B group assignment."""
    return "hybrid" if should_use_hybrid(receipt_id) else "geometric"


def get_rollout_stats() -> dict:
    """Get current rollout statistics."""
    return {
        "hybrid_ratio": HYBRID_EXTRACTION_RATIO,
        "geometric_ratio": 1.0 - HYBRID_EXTRACTION_RATIO,
        "hybrid_percentage": int(HYBRID_EXTRACTION_RATIO * 100),
        "confidence_threshold": CONFIDENCE_THRESHOLD_FOR_FALLBACK,
        "status": _get_rollout_status()
    }


def _get_rollout_status() -> str:
    """Describe current rollout stage."""
    if HYBRID_EXTRACTION_RATIO == 0.0:
        return "paused"
    elif HYBRID_EXTRACTION_RATIO < 0.2:
        return "canary"
    elif HYBRID_EXTRACTION_RATIO < 0.8:
        return "scaling"
    else:
        return "full"
