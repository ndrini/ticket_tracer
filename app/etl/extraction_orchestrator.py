"""
Extraction Orchestrator: Routes receipts to HYBRID or GEOMETRIC based on A/B test flag.

Main entry point for extraction API/batch jobs.
"""

import logging
from typing import Optional, Any
from app.config.ab_test import should_use_hybrid, get_ab_group
from app.etl.hybrid_extraction_pipeline import (
    HybridExtractionPipeline,
    ExtractionResult,
    ExtractionMethod
)

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """Route extraction to HYBRID or GEOMETRIC based on A/B assignment."""

    def __init__(
        self,
        hybrid_pipeline: HybridExtractionPipeline,
        geometric_extractor: Any  # GeometricExtractor
    ):
        self.hybrid = hybrid_pipeline
        self.geometric = geometric_extractor

    def extract(
        self,
        receipt_id: int,
        receipt_image: Any,
        receipt_total: Optional[float] = None,
        receipt_store: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract from receipt, routing to HYBRID or GEOMETRIC.

        Args:
            receipt_id: Database receipt ID
            receipt_image: Image data
            receipt_total: Known total (for validation)
            receipt_store: Store name

        Returns:
            ExtractionResult (unified format)
        """
        # A/B assignment (deterministic per receipt_id)
        use_hybrid = should_use_hybrid(receipt_id)
        ab_group = get_ab_group(receipt_id)

        logger.info(f"[Receipt {receipt_id}] A/B group: {ab_group}")

        if use_hybrid:
            # TREATMENT: Hybrid pipeline
            logger.debug(f"[Receipt {receipt_id}] Routing to HYBRID")
            result = self.hybrid.extract(
                receipt_id=receipt_id,
                receipt_image=receipt_image,
                receipt_total=receipt_total,
                receipt_store=receipt_store,
                use_llava_async=True
            )
        else:
            # CONTROL: Geometric only
            logger.debug(f"[Receipt {receipt_id}] Routing to GEOMETRIC (control)")
            geo_result = self.geometric.extract(receipt_image)

            result = ExtractionResult(
                receipt_id=receipt_id,
                method=ExtractionMethod.GEOMETRIC,
                items=geo_result.items,
                confidence=geo_result.confidence,
                total_extracted=geo_result.total,
                flags=["ab_control_group"],
                risk_level="low" if geo_result.success else "high"
            )

        return result

    def extract_batch(
        self,
        receipts: list  # [{"receipt_id", "receipt_image", "receipt_total", "receipt_store"}, ...]
    ) -> list:
        """Extract from multiple receipts."""
        results = []
        for receipt in receipts:
            result = self.extract(
                receipt_id=receipt.get("receipt_id"),
                receipt_image=receipt.get("receipt_image"),
                receipt_total=receipt.get("receipt_total"),
                receipt_store=receipt.get("receipt_store")
            )
            results.append(result)
        return results


# Factory function for dependency injection
def create_orchestrator(
    hybrid_pipeline: HybridExtractionPipeline,
    geometric_extractor: Any
) -> ExtractionOrchestrator:
    """Create orchestrator with pipeline instances."""
    return ExtractionOrchestrator(hybrid_pipeline, geometric_extractor)
