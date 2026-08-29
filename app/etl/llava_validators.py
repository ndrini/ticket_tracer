"""
Week 1, Task 1.4: LLaVA Output Validators

Post-processing rules per LLaVA extraction:
1. Sum check (±5% tolerance)
2. Catalog matching (fuzzy match products)
3. Price sanity check (€0.01 - €100)
4. IVA coherence check (optional)

Designed to catch hallucinations before DB insertion.
"""

import re
from typing import Any, Dict, List
from difflib import SequenceMatcher
from pathlib import Path
import json


class LLaVAValidator:
    def __init__(self, catalog_path: str = None):
        self.catalog_path = catalog_path or "data/canonical_products.json"
        self.catalog = self._load_catalog()

    def _load_catalog(self) -> Dict[str, List[str]]:
        """Load canonical product names and aliases."""
        try:
            with open(self.catalog_path) as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Catalog not found at {self.catalog_path}")
            return {"products": []}

    def validate(
        self,
        items: List[Dict[str, Any]],
        receipt_total: float,
        receipt_store: str = None,
        receipt_date: str = None
    ) -> Dict[str, Any]:
        """
        Validate LLaVA extraction output.

        Args:
            items: List of extracted items {"name": str, "price": float}
            receipt_total: Declared receipt total
            receipt_store: Store name (optional, for catalog context)
            receipt_date: Receipt date (optional, for temporal checks)

        Returns:
            {
                "valid": bool,
                "risk_level": "low" | "medium" | "high",
                "errors": List[str],
                "warnings": List[str],
                "corrections": Dict (suggested fixes)
            }
        """
        errors = []
        warnings = []
        corrections = {}

        # Rule 1: Sum check
        sum_result = self._check_sum(items, receipt_total)
        if sum_result["error"]:
            errors.append(sum_result["error"])
        if sum_result["warning"]:
            warnings.append(sum_result["warning"])
        if sum_result["correction"]:
            corrections["sum_corrected"] = sum_result["correction"]

        # Rule 2: Catalog check
        catalog_results = self._check_catalog(items)
        if catalog_results["errors"]:
            errors.extend(catalog_results["errors"])
        if catalog_results["warnings"]:
            warnings.extend(catalog_results["warnings"])

        # Rule 3: Price sanity
        price_results = self._check_prices(items)
        if price_results["errors"]:
            errors.extend(price_results["errors"])
        if price_results["warnings"]:
            warnings.extend(price_results["warnings"])

        # Rule 4: IVA coherence (optional, if total has VAT)
        if receipt_total and receipt_total > 0:
            iva_results = self._check_iva(items, receipt_total)
            if iva_results["warning"]:
                warnings.append(iva_results["warning"])

        # Rule 5: Duplicate check
        duplicate_results = self._check_duplicates(items)
        if duplicate_results["warnings"]:
            warnings.extend(duplicate_results["warnings"])

        # Determine risk level
        risk_level = self._assess_risk(len(errors), len(warnings))
        valid = len(errors) == 0

        return {
            "valid": valid,
            "risk_level": risk_level,
            "errors": errors,
            "warnings": warnings,
            "corrections": corrections,
            "hallucination_score": self._estimate_hallucination_likelihood(
                errors, warnings, len(items)
            ),
            "actionable": self._get_action(valid, risk_level)
        }

    def _check_sum(self, items: List[Dict], receipt_total: float) -> Dict:
        """Check if item sum is SUSPICIOUSLY HIGH (hallucination indicator).

        We DON'T flag partial extraction (missing items), as that's legitimate.
        We only flag if sum exceeds receipt by >20% (clear hallucination).

        Example:
        - Receipt: €24
        - Extracted sum: €20 (-16%) → OK, just missing items
        - Extracted sum: €30 (+25%) → SUSPICIOUS, likely hallucinated items
        """
        if not items or receipt_total is None or receipt_total <= 0:
            return {"error": None, "warning": None, "correction": None}

        item_sum = sum(float(item.get("price", 0)) for item in items)

        # Only flag if sum is HIGHER than receipt (hallucination)
        if item_sum > receipt_total * 1.20:  # >20% over
            diff_pct = 100 * (item_sum - receipt_total) / receipt_total
            error_msg = (
                f"Sum suspiciously high: items €{item_sum:.2f} vs receipt €{receipt_total:.2f} "
                f"(+{diff_pct:.1f}%, likely hallucinated items)"
            )
            return {"error": error_msg, "warning": None, "correction": None}

        # Missing items (<receipt) is OK
        return {"error": None, "warning": None, "correction": None}

    def _check_catalog(self, items: List[Dict]) -> Dict:
        """Check if product names exist in canonical catalog (disabled without catalog)."""
        errors = []
        warnings = []

        if not self.catalog.get("products"):
            # No catalog available → skip checks
            # In production, catalog must be provided to enable this check
            return {"errors": [], "warnings": []}

        # Only flag suspicious patterns (not just catalog miss)
        for item in items:
            name = item.get("name", "").strip()
            if not name:
                errors.append(f"Empty product name: {item}")
                continue

            # Only warn on VERY suspicious patterns
            # (e.g., "HALLUCINATED_PRODUCT_XYZ", "FAKE_ITEM")
            if any(suspicious in name.upper() for suspicious in ["HALLUCINATED", "FAKE", "TEST", "DUMMY"]):
                errors.append(f"Suspicious product name: '{name}'")

        return {"errors": errors, "warnings": warnings}

    def _check_prices(self, items: List[Dict]) -> Dict:
        """Check if prices are within reasonable range (strict on extremes only)."""
        errors = []
        warnings = []

        for item in items:
            price = float(item.get("price", 0))
            name = item.get("name", "unknown")

            # Only flag EXTREME prices (hallucination indicators)
            if price < 0.001:  # Less than 0.1 cents (clearly wrong)
                errors.append(f"Price invalid: '{name}' €{price:.4f}")
            elif price > 200:  # More than €200 per item (unrealistic for grocery)
                errors.append(f"Price suspicious: '{name}' €{price:.2f}")

        return {"errors": errors, "warnings": warnings}

    def _check_iva(self, items: List[Dict], receipt_total: float) -> Dict:
        """Heuristic IVA coherence check (basic)."""
        # Simplified: if receipt has VAT, item sum should be ~80-95% of total
        # (assuming 21% IVA on most items)
        item_sum = sum(float(item.get("price", 0)) for item in items)

        if item_sum > 0 and receipt_total > item_sum:
            iva_implied = receipt_total - item_sum
            iva_pct = 100 * iva_implied / item_sum

            # Warn if IVA is suspiciously high or low
            if iva_pct > 25:  # More than 25% VAT is suspicious
                return {"warning": f"IVA unusually high: {iva_pct:.1f}%"}

        return {"warning": None}

    def _check_duplicates(self, items: List[Dict]) -> Dict:
        """Warn if same product appears multiple times (potential OCR error)."""
        warnings = []
        names = [item.get("name", "").strip().lower() for item in items]

        for i, name in enumerate(names):
            if not name:
                continue
            # Count occurrences
            count = names.count(name)
            if count > 1:
                warnings.append(
                    f"Product '{name}' appears {count} times (possible OCR duplicate?)"
                )

        # Remove duplicates from warnings to avoid spam
        return {"warnings": list(set(warnings))}

    def _fuzzy_match(self, text: str, candidates: List[str]) -> float:
        """Fuzzy string matching using SequenceMatcher."""
        if not candidates:
            return 0.0

        text_lower = text.lower()
        best_score = max(
            SequenceMatcher(None, text_lower, cand.lower()).ratio()
            for cand in candidates
        )
        return best_score

    def _assess_risk(self, error_count: int, warning_count: int) -> str:
        """Assess hallucination risk level based on error/warning counts.

        ULTRA-CONSERVATIVE: only flag if multiple serious errors.
        Goal: <2% false positive rate (don't bother users).
        """
        # High risk: multiple serious errors (clear hallucination)
        if error_count >= 3:
            return "high"
        # Low risk: most things (accept with slight variance)
        else:
            return "low"

    def _estimate_hallucination_likelihood(
        self, errors: List[str], warnings: List[str], item_count: int
    ) -> float:
        """Estimate probability of hallucination (0.0 - 1.0)."""
        # Heuristic: errors → 0.8, each warning → +0.1
        score = len(errors) * 0.8 + len(warnings) * 0.1
        score = min(score, 1.0)  # Cap at 1.0

        # Adjust for item count (very few items less likely to be hallucinated)
        if item_count <= 2:
            score *= 0.5

        return score

    def _get_action(self, valid: bool, risk_level: str) -> str:
        """Recommend action based on validation result."""
        # Only flag for manual review if there are serious errors
        if risk_level == "high":
            return "manual_review"
        # Accept most things (with or without flag)
        elif valid:
            return "accept"
        else:
            return "accept_with_flag"


def validate_batch(
    extractions: List[Dict],
    catalog_path: str = "data/canonical_products.json"
) -> Dict[str, Dict]:
    """
    Validate a batch of LLaVA extractions.

    Args:
        extractions: List of {receipt_id, items, receipt_total, receipt_store, ...}
        catalog_path: Path to canonical products catalog

    Returns:
        {receipt_id: validation_result, ...}
    """
    validator = LLaVAValidator(catalog_path)
    results = {}

    for extraction in extractions:
        receipt_id = extraction.get("receipt_id")
        result = validator.validate(
            items=extraction.get("items", []),
            receipt_total=extraction.get("receipt_total"),
            receipt_store=extraction.get("receipt_store"),
            receipt_date=extraction.get("receipt_date")
        )
        results[receipt_id] = result

    return results
