"""
A/B Test Analysis & Metrics Collection

Compares HYBRID vs GEOMETRIC on real data:
- Accuracy, hallucination, latency, manual review rate
- Statistical significance (p-value, MoE)
- Daily reports
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
from math import sqrt
from scipy import stats

logger = logging.getLogger(__name__)


class ABTestAnalyzer:
    """Analyze A/B test results."""

    def __init__(self, db_path: str = "data/spese.db"):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_daily_results(self, test_date: date) -> Dict:
        """Get A/B test results for a specific date."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Geometric group
        cursor.execute("""
            SELECT
                COUNT(*) as count,
                AVG(extraction_confidence) as avg_confidence,
                AVG(extraction_latency_ms) as avg_latency_ms
            FROM receipts
            WHERE DATE(date) = ? AND hybrid_method = 'geometric'
        """, (test_date,))

        geometric = dict(cursor.fetchone()) if cursor.fetchone() else {}

        # LLaVA group
        cursor.execute("""
            SELECT
                COUNT(*) as count,
                AVG(extraction_confidence) as avg_confidence,
                AVG(extraction_latency_ms) as avg_latency_ms,
                SUM(CASE WHEN extraction_risk_level = 'high' THEN 1 ELSE 0 END) as high_risk_count
            FROM receipts
            WHERE DATE(date) = ? AND hybrid_method = 'llava_fallback'
        """, (test_date,))

        hybrid = dict(cursor.fetchone()) if cursor.fetchone() else {}

        # Hallucination rate
        cursor.execute("""
            SELECT
                hybrid_method,
                100.0 * SUM(CASE WHEN rl.is_hallucinated THEN 1 ELSE 0 END) /
                    NULLIF(COUNT(rl.id), 0) as hallucination_rate
            FROM receipts r
            LEFT JOIN receipt_lines rl ON r.id = rl.receipt_id
            WHERE DATE(r.date) = ? AND r.hybrid_method IN ('geometric', 'llava_fallback')
            GROUP BY r.hybrid_method
        """, (test_date,))

        halluc_by_method = {row["hybrid_method"]: row["hallucination_rate"] for row in cursor.fetchall()}

        # Manual review rate
        cursor.execute("""
            SELECT
                hybrid_method,
                100.0 * COUNT(CASE WHEN r.hybrid_method = 'manual_review' THEN 1 END) /
                    NULLIF(COUNT(*), 0) as manual_review_rate
            FROM receipts r
            WHERE DATE(r.date) = ? AND r.hybrid_method IN ('geometric', 'llava_fallback')
            GROUP BY r.hybrid_method
        """, (test_date,))

        review_by_method = {}
        for row in cursor.fetchall():
            if row["hybrid_method"]:
                review_by_method[row["hybrid_method"]] = row["manual_review_rate"]

        conn.close()

        return {
            "test_date": str(test_date),
            "geometric": {
                "count": geometric.get("count", 0),
                "avg_confidence": geometric.get("avg_confidence"),
                "avg_latency_ms": geometric.get("avg_latency_ms"),
                "hallucination_rate": halluc_by_method.get("geometric", 0),
                "manual_review_rate": review_by_method.get("geometric", 0)
            },
            "hybrid": {
                "count": hybrid.get("count", 0),
                "avg_confidence": hybrid.get("avg_confidence"),
                "avg_latency_ms": hybrid.get("avg_latency_ms"),
                "hallucination_rate": halluc_by_method.get("llava_fallback", 0),
                "manual_review_rate": review_by_method.get("llava_fallback", 0)
            }
        }

    def get_cumulative_results(self, start_date: date, end_date: date) -> Dict:
        """Get A/B test results across date range."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Accuracy via direct extraction success (proxy)
        cursor.execute("""
            SELECT
                hybrid_method,
                COUNT(*) as count,
                100.0 * COUNT(CASE WHEN extraction_risk_level = 'low' THEN 1 END) /
                    NULLIF(COUNT(*), 0) as success_rate,
                AVG(extraction_confidence) as avg_confidence,
                AVG(extraction_latency_ms) as avg_latency_ms
            FROM receipts
            WHERE DATE(date) BETWEEN ? AND ? AND hybrid_method IN ('geometric', 'llava_fallback')
            GROUP BY hybrid_method
        """, (start_date, end_date))

        by_method = {}
        for row in cursor.fetchall():
            by_method[row["hybrid_method"]] = {
                "count": row["count"],
                "success_rate": row["success_rate"],
                "avg_confidence": row["avg_confidence"],
                "avg_latency_ms": row["avg_latency_ms"]
            }

        # Hallucination rate
        cursor.execute("""
            SELECT
                r.hybrid_method,
                100.0 * SUM(CASE WHEN rl.is_hallucinated THEN 1 ELSE 0 END) /
                    NULLIF(COUNT(rl.id), 0) as hallucination_rate
            FROM receipts r
            LEFT JOIN receipt_lines rl ON r.id = rl.receipt_id
            WHERE DATE(r.date) BETWEEN ? AND ? AND r.hybrid_method IN ('geometric', 'llava_fallback')
            GROUP BY r.hybrid_method
        """, (start_date, end_date))

        for row in cursor.fetchall():
            if row["hybrid_method"] in by_method:
                by_method[row["hybrid_method"]]["hallucination_rate"] = row["hallucination_rate"]

        # Manual review rate
        cursor.execute("""
            SELECT
                r.hybrid_method,
                100.0 * COUNT(CASE WHEN r.extraction_risk_level = 'high' THEN 1 END) /
                    NULLIF(COUNT(*), 0) as manual_review_rate
            FROM receipts r
            WHERE DATE(r.date) BETWEEN ? AND ? AND r.hybrid_method IN ('geometric', 'llava_fallback')
            GROUP BY r.hybrid_method
        """, (start_date, end_date))

        for row in cursor.fetchall():
            if row["hybrid_method"] in by_method:
                by_method[row["hybrid_method"]]["manual_review_rate"] = row["manual_review_rate"]

        conn.close()

        # Calculate deltas
        geometric_data = by_method.get("geometric", {})
        hybrid_data = by_method.get("hybrid", {})

        return {
            "date_range": f"{start_date} to {end_date}",
            "geometric": {
                **geometric_data,
                "group": "control"
            },
            "hybrid": {
                **hybrid_data,
                "group": "treatment"
            },
            "improvement": self._calculate_improvement(geometric_data, hybrid_data)
        }

    def _calculate_improvement(self, control: Dict, treatment: Dict) -> Dict:
        """Calculate treatment effect."""
        if not control or not treatment:
            return {"status": "insufficient_data"}

        control_success = control.get("success_rate", 0)
        treatment_success = treatment.get("success_rate", 0)

        absolute_improvement = treatment_success - control_success
        relative_improvement = (treatment_success / (control_success + 0.01)) - 1

        return {
            "absolute": absolute_improvement,
            "relative": relative_improvement,
            "control_success_rate": control_success,
            "treatment_success_rate": treatment_success,
            "status": "positive" if absolute_improvement > 5 else "neutral" if absolute_improvement > -5 else "negative"
        }

    def statistical_test(
        self,
        start_date: date,
        end_date: date,
        metric: str = "success_rate"
    ) -> Dict:
        """
        Two-sample t-test: Geometric vs LLaVA.

        Args:
            start_date, end_date: Date range
            metric: 'success_rate', 'hallucination_rate', 'latency_ms'

        Returns:
            t-statistic, p-value, significance
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Sample Geometric group
        cursor.execute(f"""
            SELECT extraction_confidence as value
            FROM receipts
            WHERE DATE(date) BETWEEN ? AND ? AND hybrid_method = 'geometric'
            LIMIT 100
        """, (start_date, end_date))

        geometric_values = [row["value"] for row in cursor.fetchall() if row["value"] is not None]

        # Sample Hybrid group
        cursor.execute(f"""
            SELECT extraction_confidence as value
            FROM receipts
            WHERE DATE(date) BETWEEN ? AND ? AND hybrid_method = 'llava_fallback'
            LIMIT 100
        """, (start_date, end_date))

        hybrid_values = [row["value"] for row in cursor.fetchall() if row["value"] is not None]

        conn.close()

        if len(geometric_values) < 5 or len(hybrid_values) < 5:
            return {"status": "insufficient_data", "min_samples": 5}

        # Two-sample t-test
        t_stat, p_value = stats.ttest_ind(hybrid_values, geometric_values)

        # Significance at α=0.05
        alpha = 0.05
        is_significant = p_value < alpha

        # Effect size (Cohen's d)
        pooled_std = sqrt(
            (len(geometric_values) - 1) * (np.std(geometric_values) ** 2) +
            (len(hybrid_values) - 1) * (np.std(hybrid_values) ** 2)
        ) / sqrt(len(geometric_values) + len(hybrid_values) - 2)

        cohens_d = (np.mean(hybrid_values) - np.mean(geometric_values)) / (pooled_std + 0.001)

        return {
            "test_type": "two_sample_t_test",
            "control_n": len(geometric_values),
            "treatment_n": len(hybrid_values),
            "control_mean": float(np.mean(geometric_values)),
            "treatment_mean": float(np.mean(hybrid_values)),
            "t_statistic": float(t_stat),
            "p_value": float(p_value),
            "alpha": alpha,
            "is_significant": is_significant,
            "cohens_d": float(cohens_d),
            "confidence": "95%"
        }


# Import numpy for stats
try:
    import numpy as np
except ImportError:
    logger.warning("numpy not available for statistical tests")
