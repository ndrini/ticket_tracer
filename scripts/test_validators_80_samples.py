#!/usr/bin/env python3
"""
Week 1, Task 1.5: Test validators su 80 scontrini

Misura:
- Hallucination detection rate (% of hallucinations flagged for review)
- False positive rate (% of valid receipts flagged)
- Manual review rate (total flagged)
- Validators sono un FILTER, non eliminano hallucination
"""

import json
import sqlite3
from pathlib import Path
import numpy as np
import sys

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.etl.llava_validators import LLaVAValidator, validate_batch

print("\n" + "=" * 70)
print("Week 1, Task 1.5: Test Validators su 80 Scontrini")
print("=" * 70)

# Carica sample metadata
print("\n📋 Caricamento sample metadata...")
with open("data/validation_sample_100.json") as f:
    sample_data = json.load(f)

samples = sample_data["samples"]
print(f"   ✅ Caricati {len(samples)} scontrini")

# Carica validation results (from Task 1.2)
print("\n📊 Caricamento risultati Task 1.2...")
with open("data/validation_80_results.json") as f:
    validation_results = json.load(f)

results_per_receipt = validation_results["results_per_receipt"]
print(f"   ✅ Caricati risultati per {len(results_per_receipt)} scontrini")

# Carica Geometric baseline dal DB
print("\n🔍 Caricamento baseline Geometric...")
conn = sqlite3.connect("data/spese.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

geometric_baseline = {}
skipped_count = 0

for sample in samples:
    receipt_id = sample["id"]

    cursor.execute("""
        SELECT p.name, rl.total_price
        FROM receipt_lines rl
        JOIN products p ON rl.product_id = p.id
        WHERE rl.receipt_id = ? AND rl.name_quality = 'complete'
        ORDER BY rl.id
    """, (receipt_id,))

    items = cursor.fetchall()
    items_list = [{"name": row["name"], "price": float(row["total_price"])} for row in items]

    # Skip scontrini with corrupted baseline (sum way off)
    if items_list:
        item_sum = sum(i["price"] for i in items_list)
        if abs(item_sum - sample["total"]) / max(sample["total"], 0.01) > 0.20:
            # Skip: corrupted baseline (>20% mismatch)
            skipped_count += 1
            continue

    geometric_baseline[sample["sha256"]] = {
        "items": items_list,
        "total": sample["total"],
        "store": sample["store"]
    }

print(f"   ✅ Caricati baseline per {len(geometric_baseline)} scontrini")
print(f"   ⚠️  Skipped {skipped_count} scontrini con corrupted baseline")

# Simula LLaVA extractions con hallucination e testa validators
print("\n🔄 Simulazione LLaVA + Testing Validators...")

validator = LLaVAValidator()

validation_stats = {
    "total_scontrini": 0,
    "hallucinated_scontrini": 0,
    "hallucinations_flagged": 0,
    "valid_flagged": 0,
    "valid_not_flagged": 0
}

per_receipt_stats = {}

for idx, sample in enumerate(samples, 1):
    sha256 = sample["sha256"]
    if sha256 not in geometric_baseline:
        continue  # Skip corrupted baseline
    baseline = geometric_baseline[sha256]
    llava_results = results_per_receipt[sha256]

    # Simula LLaVA extraction basato su accuracies da Task 1.2
    accuracy_mean = llava_results["accuracy_mean"]
    hallucination_count = llava_results["hallucination_count"]

    # Create simulated LLaVA extraction
    baseline_items = baseline["items"]
    n_correct = int(len(baseline_items) * accuracy_mean)

    simulated_items = baseline_items[:n_correct].copy()
    has_hallucination = False

    # Add hallucinated item if applicable
    if hallucination_count > 0:
        fake_item = {
            "name": "HALLUCINATED_PRODUCT_XYZ",
            "price": 9.99  # Suspicious value
        }
        simulated_items.append(fake_item)
        has_hallucination = True

    # Validate
    validation = validator.validate(
        items=simulated_items,
        receipt_total=baseline["total"],
        receipt_store=baseline["store"]
    )

    # Is this scontrino flagged for manual review?
    is_flagged = validation["actionable"] in ["manual_review", "accept_with_flag"]

    # Track stats
    validation_stats["total_scontrini"] += 1

    if has_hallucination:
        validation_stats["hallucinated_scontrini"] += 1
        if is_flagged:
            validation_stats["hallucinations_flagged"] += 1
    else:
        if is_flagged:
            validation_stats["valid_flagged"] += 1
        else:
            validation_stats["valid_not_flagged"] += 1

    per_receipt_stats[sha256] = {
        "items_count": len(simulated_items),
        "has_hallucination": has_hallucination,
        "is_flagged": is_flagged,
        "validation_result": validation,
        "action": validation["actionable"]
    }

    if idx % 20 == 0:
        print(f"   [{idx}/80] Validati...")

# Analyze results
print("\n📈 Analisi Risultati Validators...")

# Recalculate total based on actual validated scontrini
total_validated = len(per_receipt_stats)

hallucination_base_count = validation_stats["hallucinated_scontrini"]
hallucination_detected = validation_stats["hallucinations_flagged"]
total_flagged = hallucination_detected + validation_stats["valid_flagged"]
manual_review_rate = 100 * total_flagged / 80

print(f"\n   Hallucination Detection Rate:")
print(f"     Baseline (2.1%): {hallucination_base_count} scontrini con hallucination")
print(f"     Flagged by validators: {hallucination_detected}")
if hallucination_base_count > 0:
    detection_rate = 100 * hallucination_detected / hallucination_base_count
    print(f"     Detection rate: {detection_rate:.1f}%")

print(f"\n   False Positive Rate (valid receipts flagged):")
print(f"     Valid scontrini: {validation_stats['valid_not_flagged'] + validation_stats['valid_flagged']}")
print(f"     Erroneously flagged: {validation_stats['valid_flagged']}")
if (validation_stats['valid_not_flagged'] + validation_stats['valid_flagged']) > 0:
    fp_rate = 100 * validation_stats['valid_flagged'] / (validation_stats['valid_not_flagged'] + validation_stats['valid_flagged'])
    print(f"     False positive rate: {fp_rate:.1f}%")

print(f"\n   Manual Review Distribution (n={total_validated}):")
print(f"     Valid + clean: {validation_stats['valid_not_flagged']} ({100*validation_stats['valid_not_flagged']/total_validated:.1f}%)")
print(f"     Valid but flagged (false positives): {validation_stats['valid_flagged']} ({100*validation_stats['valid_flagged']/total_validated:.1f}%)")
print(f"     Hallucinated + flagged (true positives): {hallucination_detected} ({100*hallucination_detected/total_validated:.1f}%)")
print(f"     Hallucinated but not flagged (false negatives): {hallucination_base_count - hallucination_detected} ({100*(hallucination_base_count - hallucination_detected)/total_validated:.1f}%)")

# Recalculate manual review rate
manual_review_rate = 100 * total_flagged / total_validated
print(f"\n   Total Manual Review Rate: {manual_review_rate:.1f}%")

# Save results
analysis = {
    "timestamp": __import__('time').time(),
    "sample_size": total_validated,
    "skipped_corrupted": skipped_count,
    "hallucination_stats": {
        "baseline_count": hallucination_base_count,
        "baseline_rate": 100 * hallucination_base_count / total_validated if total_validated > 0 else 0,
        "detected": hallucination_detected,
        "detection_rate": 100 * hallucination_detected / hallucination_base_count if hallucination_base_count > 0 else 0,
        "missed": hallucination_base_count - hallucination_detected
    },
    "false_positive_rate": 100 * validation_stats['valid_flagged'] / (validation_stats['valid_not_flagged'] + validation_stats['valid_flagged']) if (validation_stats['valid_not_flagged'] + validation_stats['valid_flagged']) > 0 else 0,
    "manual_review_rate": manual_review_rate,
    "per_receipt_validation": per_receipt_stats
}

output_path = Path("data/validation_80_validators_results.json")
with open(output_path, "w") as f:
    json.dump(analysis, f, indent=2)

print(f"\n💾 Risultati salvati: {output_path}")

# Final recommendation
print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)

detection_rate = analysis["hallucination_stats"]["detection_rate"]
fp_rate = analysis["false_positive_rate"]

if detection_rate >= 80 and fp_rate < 3 and manual_review_rate < 8:
    recommendation = "✅ VALIDATORS APPROVED"
    print(f"\n{recommendation}")
    print(f"✅ Detects {detection_rate:.1f}% of hallucinations (target ≥80%)")
    print(f"✅ False positive rate {fp_rate:.1f}% (target <3%)")
    print(f"✅ Manual review rate {manual_review_rate:.1f}% (target <8%)")
    print(f"✅ Ready for Week 2 production implementation")
elif detection_rate >= 60 and fp_rate < 5 and manual_review_rate < 10:
    recommendation = "⚠️  VALIDATORS ACCEPTABLE WITH TUNING"
    print(f"\n{recommendation}")
    print(f"⚠️  Detects {detection_rate:.1f}% of hallucinations (borderline ≥60%)")
    print(f"⚠️  False positive rate {fp_rate:.1f}% (borderline <5%)")
    print(f"⚠️  Manual review rate {manual_review_rate:.1f}% (borderline <10%)")
    print(f"→ Proceed but monitor manual review volume in Week 3")
else:
    recommendation = "❌ VALIDATORS NEED SIGNIFICANT TUNING"
    print(f"\n{recommendation}")
    print(f"❌ Detects only {detection_rate:.1f}% of hallucinations (too low)")
    print(f"❌ False positive rate {fp_rate:.1f}% (too high, bothers users)")
    print(f"→ Adjust validator thresholds and re-test before Week 2")

conn.close()

print("\n✅ Task 1.5 Completato")
print("=" * 70)
