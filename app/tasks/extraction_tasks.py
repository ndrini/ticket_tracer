"""
Week 2, Task 2.2: Async LLaVA Extraction via Celery

Queue system for LLaVA inference:
- Celery tasks for async queuing
- Redis backend for task queue
- Max 10 concurrent LLaVA requests (GPU capacity)
- Timeout: 5 seconds per extraction
"""

import logging
from typing import Any, Dict, List, Optional
from celery import shared_task
import time

logger = logging.getLogger(__name__)

# Note: In production, Celery is configured in app/celery_config.py
# For now, define task stubs that can be mocked/replaced


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    time_limit=10,  # Hard limit: kill after 10s
    soft_time_limit=7   # Soft limit: warn after 7s
)
def extract_llava_async(
    self,
    receipt_id: int,
    image_path: str,
    receipt_total: Optional[float] = None,
    receipt_store: Optional[str] = None
) -> Dict[str, Any]:
    """
    Async LLaVA extraction task.

    Args:
        receipt_id: Database receipt ID
        image_path: Path to receipt image
        receipt_total: Known total (for validation)
        receipt_store: Store name (for context)

    Returns:
        Dict with extraction result (will be stored in DB or cache)
    """
    from app.models.llava_extractor import LLaVAExtractor
    from app.db.db_manager import update_receipt_extraction

    logger.info(f"[Task {self.request.id}] LLaVA extraction started for receipt {receipt_id}")

    try:
        start_time = time.time()

        # Load LLaVA model (cached in GPU)
        extractor = LLaVAExtractor()

        # Extract (blocks for ~0.5-1s)
        result = extractor.extract(image_path)

        elapsed = time.time() - start_time
        logger.info(
            f"[Task {self.request.id}] LLaVA completed in {elapsed:.2f}s, "
            f"extracted {len(result.items)} items"
        )

        # Format result
        extraction_data = {
            "receipt_id": receipt_id,
            "method": "llava_async",
            "items": [
                {"name": item.get("name"), "price": float(item.get("price", 0))}
                for item in result.items
            ],
            "confidence": result.confidence,
            "total": result.total,
            "latency_ms": int(elapsed * 1000),
            "timestamp": time.time()
        }

        # Save to DB
        # Note: This is async, so DB insert happens eventually
        # In production, use Celery task chaining or webhooks
        try:
            update_receipt_extraction(receipt_id, extraction_data)
            logger.info(f"[Task {self.request.id}] Saved extraction to DB")
        except Exception as db_error:
            logger.error(f"[Task {self.request.id}] DB save failed: {db_error}")
            # Don't fail task, but log error for monitoring

        return extraction_data

    except SoftTimeLimitExceeded:
        logger.warning(f"[Task {self.request.id}] Soft time limit (7s) exceeded, retrying...")
        raise self.retry(countdown=10, exc=TimeoutError("LLaVA soft timeout"))

    except Exception as e:
        logger.error(f"[Task {self.request.id}] LLaVA extraction failed: {e}")

        # Retry once
        try:
            raise self.retry(countdown=5, max_retries=1, exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"[Task {self.request.id}] Max retries exceeded, giving up")
            return {
                "receipt_id": receipt_id,
                "method": "llava_error",
                "items": [],
                "confidence": 0.0,
                "error": str(e)
            }


@shared_task(bind=True)
def validate_llava_extraction(
    self,
    receipt_id: int,
    extraction_data: Dict[str, Any],
    receipt_total: Optional[float] = None,
    receipt_store: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post-extraction validation task.

    Args:
        receipt_id: Database receipt ID
        extraction_data: Output from extract_llava_async
        receipt_total: Known total
        receipt_store: Store name

    Returns:
        Validation result with flags
    """
    from app.etl.llava_validators import LLaVAValidator
    from app.db.db_manager import flag_receipt_for_review

    logger.info(f"[Task {self.request.id}] Validating extraction for receipt {receipt_id}")

    validator = LLaVAValidator()
    validation = validator.validate(
        items=extraction_data.get("items", []),
        receipt_total=receipt_total,
        receipt_store=receipt_store
    )

    # If high risk, flag for manual review
    if validation["risk_level"] == "high":
        logger.warning(f"[Task {self.request.id}] Receipt {receipt_id} flagged for review")
        flag_receipt_for_review(
            receipt_id=receipt_id,
            reason="LLaVA high risk hallucination",
            errors=validation["errors"]
        )

    return {
        "receipt_id": receipt_id,
        "validation_result": validation,
        "flagged": validation["risk_level"] == "high"
    }


@shared_task
def monitor_extraction_queue() -> Dict[str, Any]:
    """
    Monitor LLaVA extraction queue health.

    Returns:
        Queue stats: size, latency, error rate
    """
    from celery import current_app

    stats = {
        "timestamp": time.time(),
        "queue_size": 0,
        "active_tasks": 0,
        "avg_latency_ms": 0
    }

    try:
        # Get queue stats from Celery/Redis
        # This is simplified; real implementation depends on broker config
        inspector = current_app.control.inspect()
        active = inspector.active()
        if active:
            total_tasks = sum(len(tasks) for tasks in active.values())
            stats["active_tasks"] = total_tasks

        logger.info(f"Queue stats: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        return stats


# Celery chord: extract + validate + update DB
def extract_and_validate_receipt(
    receipt_id: int,
    image_path: str,
    receipt_total: Optional[float] = None,
    receipt_store: Optional[str] = None
):
    """
    Celery chord: LLaVA extraction followed by validation.

    Usage:
        extract_and_validate_receipt.delay(receipt_id, image_path, ...)
    """
    from celery import chord

    # Extract
    extraction_sig = extract_llava_async.s(
        receipt_id=receipt_id,
        image_path=image_path,
        receipt_total=receipt_total,
        receipt_store=receipt_store
    )

    # Validate (receives extraction result as input)
    validation_sig = validate_llava_extraction.s(
        receipt_id=receipt_id,
        receipt_total=receipt_total,
        receipt_store=receipt_store
    )

    # Chain: extract -> validate
    workflow = chord([extraction_sig])(validation_sig)
    return workflow


# Rate limiting helper
class ExtractionRateLimiter:
    """Rate limit LLaVA extraction to avoid GPU saturation."""

    MAX_CONCURRENT = 10  # Max 10 concurrent LLaVA tasks
    QUEUE_DEPTH_WARNING = 50  # Warn if queue > 50
    QUEUE_DEPTH_ERROR = 100   # Error if queue > 100

    @staticmethod
    def can_submit_task() -> bool:
        """Check if we can submit another LLaVA task."""
        from celery import current_app

        try:
            inspector = current_app.control.inspect()
            active = inspector.active()
            if not active:
                return True

            llava_tasks = sum(
                1 for tasks in active.values()
                for task in tasks
                if "llava" in task.get("name", "").lower()
            )

            if llava_tasks >= ExtractionRateLimiter.MAX_CONCURRENT:
                logger.warning(f"LLaVA task limit reached ({llava_tasks})")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to check task limit: {e}")
            return True  # Optimistic: allow submit if check fails

    @staticmethod
    def get_queue_depth() -> int:
        """Get current queue depth."""
        from celery import current_app

        try:
            inspector = current_app.control.inspect()
            reserved = inspector.reserved()
            if not reserved:
                return 0

            return sum(len(tasks) for tasks in reserved.values())
        except Exception as e:
            logger.error(f"Failed to get queue depth: {e}")
            return 0


from celery.exceptions import SoftTimeLimitExceeded
