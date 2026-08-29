"""
Week 2, Task 2.1: Hybrid Extraction Pipeline

Architecture:
1. GEOMETRIC (Primary): Fast, deterministic, 58% accuracy
2. LLaVA (Fallback): Slower, 74% accuracy, async GPU

Logic:
- Try Geometric first
- If confidence > 50%, return Geometric result
- Else, queue LLaVA async, validate output, return
- If validation fails, mark for manual review
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ExtractionMethod(str, Enum):
    GEOMETRIC = "geometric"
    LLAVA_FALLBACK = "llava_fallback"
    GEOMETRIC_FALLBACK = "geometric_fallback_after_llava_error"
    MANUAL_REVIEW = "manual_review"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ExtractionResult:
    """Result of extraction (unified format)."""
    receipt_id: int
    method: ExtractionMethod
    items: List[Dict[str, Any]]  # [{"name": str, "price": float}, ...]
    confidence: float  # 0.0 - 1.0
    total_extracted: Optional[float]
    flags: List[str]  # e.g., ["verified_llava_low_risk", "requires_manual_review"]
    risk_level: RiskLevel
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "method": self.method.value,
            "risk_level": self.risk_level.value
        }


class HybridExtractionPipeline:
    """Hybrid extraction: Geometric → LLaVA fallback."""

    def __init__(
        self,
        geometric_extractor,
        llava_extractor,
        validator,
        confidence_threshold: float = 0.50
    ):
        """
        Args:
            geometric_extractor: GeometricExtractor instance
            llava_extractor: LLaVAExtractor instance (with async support)
            validator: LLaVAValidator instance
            confidence_threshold: Use LLaVA fallback if confidence <= this
        """
        self.geometric = geometric_extractor
        self.llava = llava_extractor
        self.validator = validator
        self.confidence_threshold = confidence_threshold

    def extract(
        self,
        receipt_id: int,
        receipt_image: Any,
        receipt_total: Optional[float] = None,
        receipt_store: Optional[str] = None,
        use_llava_async: bool = True
    ) -> ExtractionResult:
        """
        Extract products from receipt using hybrid approach.

        Args:
            receipt_id: Database receipt ID
            receipt_image: Image data (path or array)
            receipt_total: Known receipt total (for validation)
            receipt_store: Store name (for context)
            use_llava_async: If True, queue LLaVA async; if False, block

        Returns:
            ExtractionResult with unified format
        """
        # Step 1: Geometric (always try first)
        logger.info(f"[{receipt_id}] Trying Geometric extraction...")
        geo_result = self.geometric.extract(receipt_image)

        if geo_result.success and geo_result.confidence > self.confidence_threshold:
            logger.info(
                f"[{receipt_id}] Geometric SUCCESS (confidence {geo_result.confidence:.1%}), "
                f"extracted {len(geo_result.items)} items"
            )
            return ExtractionResult(
                receipt_id=receipt_id,
                method=ExtractionMethod.GEOMETRIC,
                items=geo_result.items,
                confidence=geo_result.confidence,
                total_extracted=geo_result.total,
                flags=[],
                risk_level=RiskLevel.LOW
            )

        # Step 2: Geometric failed or low confidence → try LLaVA fallback
        logger.info(
            f"[{receipt_id}] Geometric failed/low confidence ({geo_result.confidence:.1%}), "
            f"falling back to LLaVA..."
        )

        try:
            if use_llava_async:
                # Queue LLaVA async, don't block
                logger.info(f"[{receipt_id}] Queuing LLaVA async task...")
                llava_result = self.llava.extract_async(
                    receipt_id=receipt_id,
                    receipt_image=receipt_image
                )
                # Note: In production, this returns immediately; result comes later via callback
                # For now, simulate sync behavior
            else:
                # Block for LLaVA (for testing/debugging)
                logger.info(f"[{receipt_id}] Blocking LLaVA extraction...")
                llava_result = self.llava.extract(receipt_image)

            if not llava_result.success or not llava_result.items:
                logger.warning(f"[{receipt_id}] LLaVA extraction failed")
                return ExtractionResult(
                    receipt_id=receipt_id,
                    method=ExtractionMethod.MANUAL_REVIEW,
                    items=[],
                    confidence=0.0,
                    total_extracted=None,
                    flags=["llava_extraction_failed", "requires_manual_review"],
                    risk_level=RiskLevel.HIGH,
                    error_message="Both Geometric and LLaVA failed"
                )

            # Step 3: Validate LLaVA output
            logger.info(f"[{receipt_id}] Validating LLaVA output...")
            validation = self.validator.validate(
                items=llava_result.items,
                receipt_total=receipt_total,
                receipt_store=receipt_store
            )

            # Step 4: Decide action based on validation
            if validation["valid"] and validation["risk_level"] == "low":
                logger.info(
                    f"[{receipt_id}] LLaVA VALIDATED (low risk), "
                    f"extracted {len(llava_result.items)} items"
                )
                return ExtractionResult(
                    receipt_id=receipt_id,
                    method=ExtractionMethod.LLAVA_FALLBACK,
                    items=llava_result.items,
                    confidence=llava_result.confidence,
                    total_extracted=llava_result.total,
                    flags=["verified_llava_low_risk"],
                    risk_level=RiskLevel.LOW
                )

            elif validation["valid"] and validation["risk_level"] == "medium":
                logger.warning(
                    f"[{receipt_id}] LLaVA has MEDIUM RISK, "
                    f"flagging for review. Errors: {validation['errors']}"
                )
                return ExtractionResult(
                    receipt_id=receipt_id,
                    method=ExtractionMethod.LLAVA_FALLBACK,
                    items=llava_result.items,
                    confidence=llava_result.confidence,
                    total_extracted=llava_result.total,
                    flags=["requires_human_review", f"validation_errors: {', '.join(validation['errors'][:2])}"],
                    risk_level=RiskLevel.MEDIUM
                )

            else:  # High risk or invalid
                logger.error(
                    f"[{receipt_id}] LLaVA HIGH RISK / INVALID, "
                    f"marking manual review. Errors: {validation['errors']}"
                )
                return ExtractionResult(
                    receipt_id=receipt_id,
                    method=ExtractionMethod.MANUAL_REVIEW,
                    items=llava_result.items,  # Keep items but flag
                    confidence=0.0,
                    total_extracted=None,
                    flags=["llava_high_risk_hallucination", "requires_manual_review"],
                    risk_level=RiskLevel.HIGH,
                    error_message=f"Validation errors: {', '.join(validation['errors'][:3])}"
                )

        except Exception as e:
            logger.error(f"[{receipt_id}] LLaVA extraction exception: {e}")
            # Fallback to Geometric anyway (it's always available)
            logger.info(f"[{receipt_id}] Falling back to Geometric due to LLaVA error...")
            return ExtractionResult(
                receipt_id=receipt_id,
                method=ExtractionMethod.GEOMETRIC_FALLBACK,
                items=geo_result.items if geo_result.success else [],
                confidence=geo_result.confidence if geo_result.success else 0.0,
                total_extracted=geo_result.total,
                flags=["llava_error_fallback_to_geometric"],
                risk_level=RiskLevel.MEDIUM,
                error_message=f"LLaVA error: {str(e)}"
            )

    def extract_batch(
        self,
        receipts: List[Dict],
        use_llava_async: bool = True
    ) -> List[ExtractionResult]:
        """
        Extract from multiple receipts.

        Args:
            receipts: List of {receipt_id, receipt_image, receipt_total, receipt_store}
            use_llava_async: Queue LLaVA async for each

        Returns:
            List of ExtractionResult
        """
        results = []
        for receipt in receipts:
            result = self.extract(
                receipt_id=receipt.get("receipt_id"),
                receipt_image=receipt.get("receipt_image"),
                receipt_total=receipt.get("receipt_total"),
                receipt_store=receipt.get("receipt_store"),
                use_llava_async=use_llava_async
            )
            results.append(result)
        return results


# Metrics helper
class ExtractionMetrics:
    """Track extraction metrics for monitoring."""

    def __init__(self):
        self.total_receipts = 0
        self.method_counts = {
            ExtractionMethod.GEOMETRIC.value: 0,
            ExtractionMethod.LLAVA_FALLBACK.value: 0,
            ExtractionMethod.GEOMETRIC_FALLBACK.value: 0,
            ExtractionMethod.MANUAL_REVIEW.value: 0
        }
        self.risk_distribution = {
            RiskLevel.LOW.value: 0,
            RiskLevel.MEDIUM.value: 0,
            RiskLevel.HIGH.value: 0
        }

    def record(self, result: ExtractionResult):
        """Record metrics for one extraction."""
        self.total_receipts += 1
        self.method_counts[result.method.value] += 1
        self.risk_distribution[result.risk_level.value] += 1

    def summary(self) -> Dict[str, Any]:
        """Get summary metrics."""
        return {
            "total_receipts": self.total_receipts,
            "method_distribution": {
                k: 100 * v / self.total_receipts if self.total_receipts > 0 else 0
                for k, v in self.method_counts.items()
            },
            "risk_distribution": {
                k: 100 * v / self.total_receipts if self.total_receipts > 0 else 0
                for k, v in self.risk_distribution.items()
            },
            "fallback_rate": 100 * (
                self.method_counts[ExtractionMethod.LLAVA_FALLBACK.value] +
                self.method_counts[ExtractionMethod.GEOMETRIC_FALLBACK.value]
            ) / self.total_receipts if self.total_receipts > 0 else 0
        }
