"""
Database operations for Hybrid Pipeline.

Manages:
- Extraction queue (Celery tasks)
- Manual review queue
- Extraction metrics
- Receipt/line verification tracking
"""

import sqlite3
import json
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, date

logger = logging.getLogger(__name__)


class ExtractionDB:
    """Database manager for extraction operations."""

    def __init__(self, db_path: str = "data/spese.db"):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # === Extraction Queue ===

    def queue_llava_extraction(
        self,
        receipt_id: int,
        task_id: str,
        method: str = "llava_async"
    ) -> int:
        """Queue LLaVA extraction task."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO extraction_queue (receipt_id, task_id, method, status)
            VALUES (?, ?, ?, 'pending')
        """, (receipt_id, task_id, method))

        queue_entry_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Queued LLaVA task {task_id} for receipt {receipt_id}")
        return queue_entry_id

    def update_extraction_task(
        self,
        task_id: str,
        status: str,
        result_json: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update extraction task status."""
        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now()

        cursor.execute("""
            UPDATE extraction_queue
            SET status = ?,
                result_json = ?,
                error_message = ?,
                started_at = CASE WHEN started_at IS NULL AND status = 'processing' THEN ? ELSE started_at END,
                completed_at = CASE WHEN status = 'completed' OR status = 'failed' THEN ? ELSE NULL END
            WHERE task_id = ?
        """, (status, result_json, error_message, now, now, task_id))

        conn.commit()
        conn.close()

        logger.info(f"Updated task {task_id} status: {status}")

    def get_extraction_task(self, task_id: str) -> Optional[Dict]:
        """Get extraction task status."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM extraction_queue WHERE task_id = ?
        """, (task_id,))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    # === Receipt Extraction Metadata ===

    def save_extraction_result(
        self,
        receipt_id: int,
        method: str,
        items: List[Dict],
        confidence: float,
        total: Optional[float],
        risk_level: str,
        flags: List[str],
        latency_ms: int
    ):
        """Save extraction result to receipt."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Update receipt metadata
        cursor.execute("""
            UPDATE receipts
            SET hybrid_method = ?,
                extraction_risk_level = ?,
                extraction_confidence = ?,
                extraction_latency_ms = ?,
                extraction_flags = ?
            WHERE id = ?
        """, (
            method,
            risk_level,
            confidence,
            latency_ms,
            ",".join(flags),
            receipt_id
        ))

        # Insert/update receipt_lines (if extraction succeeded)
        if method != "manual_review" and items:
            # Clear existing lines for this receipt (if re-extracting)
            # Note: In production, you might keep history; here we replace

            cursor.execute("""
                DELETE FROM receipt_lines WHERE receipt_id = ?
            """, (receipt_id,))

            # Insert new lines
            for idx, item in enumerate(items):
                cursor.execute("""
                    INSERT INTO receipt_lines (
                        receipt_id,
                        product_id,
                        name,
                        total_price,
                        extraction_method,
                        is_hallucinated
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    receipt_id,
                    None,  # Will be populated by product matching later
                    item.get("name", ""),
                    float(item.get("price", 0)),
                    method,
                    0  # Will be set by validator if needed
                ))

        conn.commit()
        conn.close()

        logger.info(f"Saved extraction for receipt {receipt_id} (method: {method})")

    # === Manual Review Queue ===

    def flag_for_review(
        self,
        receipt_id: int,
        reason: str,
        extraction_method: Optional[str] = None,
        errors: Optional[List[str]] = None,
        priority: int = 0
    ) -> int:
        """Flag receipt for manual review."""
        conn = self._get_conn()
        cursor = conn.cursor()

        errors_json = json.dumps(errors) if errors else None

        cursor.execute("""
            INSERT INTO manual_review_queue (
                receipt_id,
                reason,
                extraction_method,
                errors,
                priority
            )
            VALUES (?, ?, ?, ?, ?)
        """, (receipt_id, reason, extraction_method, errors_json, priority))

        review_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.warning(f"Receipt {receipt_id} flagged for review: {reason}")
        return review_id

    def get_review_queue(self, pending_only: bool = True) -> List[Dict]:
        """Get manual review queue."""
        conn = self._get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM manual_review_queue"
        if pending_only:
            query += " WHERE completed_at IS NULL"
        query += " ORDER BY priority DESC, created_at ASC"

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def complete_review(
        self,
        review_id: int,
        reviewed_by: str,
        action_taken: str,
        notes: Optional[str] = None
    ):
        """Mark review as completed."""
        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now()

        cursor.execute("""
            UPDATE manual_review_queue
            SET reviewed_by = ?,
                action_taken = ?,
                review_notes = ?,
                completed_at = ?
            WHERE id = ?
        """, (reviewed_by, action_taken, notes, now, review_id))

        conn.commit()
        conn.close()

        logger.info(f"Review {review_id} completed: {action_taken}")

    # === Verification Tracking ===

    def mark_line_verified(
        self,
        line_id: int,
        verified_by: str,
        notes: Optional[str] = None
    ):
        """Mark receipt_line as verified by human."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE receipt_lines
            SET verified_by_human = 1,
                verified_by_user = ?,
                verification_timestamp = ?,
                verification_notes = ?
            WHERE id = ?
        """, (verified_by, datetime.now(), notes, line_id))

        conn.commit()
        conn.close()

    def mark_hallucinated(self, line_id: int):
        """Mark receipt_line as hallucinated."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE receipt_lines
            SET is_hallucinated = 1
            WHERE id = ?
        """, (line_id,))

        conn.commit()
        conn.close()

    # === Metrics ===

    def record_extraction_metric(
        self,
        date: date,
        method: str,
        count: int,
        avg_accuracy: float = 0.0,
        avg_latency_ms: int = 0,
        hallucination_rate: float = 0.0
    ):
        """Record extraction metrics for dashboard."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO extraction_metrics
            (date, method, count, avg_accuracy, avg_latency_ms, hallucination_rate)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, method, count, avg_accuracy, avg_latency_ms, hallucination_rate))

        conn.commit()
        conn.close()

    def get_metrics_summary(self, days: int = 7) -> Dict:
        """Get extraction metrics summary (last N days)."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                method,
                SUM(count) as total_count,
                AVG(avg_accuracy) as avg_accuracy,
                AVG(avg_latency_ms) as avg_latency_ms,
                AVG(hallucination_rate) as avg_hallucination_rate
            FROM extraction_metrics
            WHERE date >= DATE('now', '-' || ? || ' days')
            GROUP BY method
        """, (days,))

        rows = cursor.fetchall()
        conn.close()

        return {row["method"]: dict(row) for row in rows}

    # === Health Checks ===

    def get_queue_status(self) -> Dict[str, Any]:
        """Get extraction queue and review queue status."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Extraction queue
        cursor.execute("""
            SELECT
                status,
                COUNT(*) as count,
                AVG(CAST((julianday('now') - julianday(submitted_at)) * 86400 AS INTEGER)) as avg_age_seconds
            FROM extraction_queue
            WHERE status IN ('pending', 'processing')
            GROUP BY status
        """)

        extraction_status = {row["status"]: {"count": row["count"], "avg_age_sec": row["avg_age_seconds"]} for row in cursor.fetchall()}

        # Review queue
        cursor.execute("""
            SELECT
                COUNT(*) as pending,
                MAX(CAST((julianday('now') - julianday(created_at)) * 86400 AS INTEGER)) as oldest_age_seconds
            FROM manual_review_queue
            WHERE completed_at IS NULL
        """)

        review_row = cursor.fetchone()
        review_status = {
            "pending": review_row["pending"],
            "oldest_age_sec": review_row["oldest_age_seconds"]
        }

        conn.close()

        return {
            "extraction_queue": extraction_status,
            "review_queue": review_status
        }

    def get_hallucination_rate(self, days: int = 7) -> float:
        """Get current hallucination rate (last N days)."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                100.0 * SUM(CASE WHEN rl.is_hallucinated THEN 1 ELSE 0 END) / NULLIF(COUNT(rl.id), 0) as rate
            FROM receipt_lines rl
            JOIN receipts r ON rl.receipt_id = r.id
            WHERE r.date >= DATE('now', '-' || ? || ' days')
        """, (days,))

        row = cursor.fetchone()
        conn.close()

        return row["rate"] if row and row["rate"] else 0.0
