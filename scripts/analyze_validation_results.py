#!/usr/bin/env python3
"""
Week 1, Task 1.3: Analizza risultati validazione 80 scontrini
- Calcola statistiche aggregate
- Stratifica per negozio e complessità
- Genera report decisionale
"""

import json
from pathlib import Path
import numpy as np

print("\n" + "=" * 70)
print("Week 1, Task 1.3: Analisi Statistiche Validazione")
print("=" * 70)

# Carica risultati Task 1.2
print("\n📂 Caricamento risultati validazione...")
with open("data/validation_80_results.json") as f:
    validation_results = json.load(f)

summary = {k: v for k, v in validation_results.items() if k != "results_per_receipt"}
results = validation_results["results_per_receipt"]

print(f"   ✅ Caricati risultati per {len(results)} scontrini")

# Stratificazione per complessità
print("\n🎯 Stratificazione per complessità...")

complexity_stats = {"simple": [], "normal": [], "complex": []}

for sha256, receipt_data in results.items():
    complexity = "simple" if receipt_data["item_count"] <= 5 else "normal" if receipt_data["item_count"] <= 20 else "complex"

    accuracy_mean = receipt_data["accuracy_mean"]
    complexity_stats[complexity].append({
        "sha256": sha256,
        "accuracy": accuracy_mean,
        "store": receipt_data["store"],
        "items": receipt_data["item_count"]
    })

for complexity, samples in complexity_stats.items():
    if samples:
        accuracies = [s["accuracy"] for s in samples]
        print(f"\n   {complexity.upper()}:")
        print(f"     Campione: {len(samples)} scontrini")
        print(f"     Accuracy: {np.mean(accuracies):.1%} ± {np.std(accuracies):.1%}")
        print(f"     Range: {np.min(accuracies):.1%} → {np.max(accuracies):.1%}")

# Stratificazione per negozio (top 10)
print("\n🏪 Accuracy per negozio (top 10)...")

store_stats = {}
for sha256, receipt_data in results.items():
    store = receipt_data["store"]
    if store not in store_stats:
        store_stats[store] = []
    store_stats[store].append(receipt_data["accuracy_mean"])

store_sorted = sorted(store_stats.items(), key=lambda x: len(x[1]), reverse=True)

for store, accuracies in store_sorted[:10]:
    print(f"\n   {store}: {len(accuracies)} scontrini")
    print(f"     Accuracy: {np.mean(accuracies):.1%} ± {np.std(accuracies):.1%}")

# Hallucination stratificato
print("\n⚠️  Hallucination Distribution...")

hallucination_distribution = {"0": 0, "1": 0, "2": 0, "3+": 0}
for receipt_data in results.values():
    h_count = receipt_data["hallucination_count"]
    if h_count == 0:
        hallucination_distribution["0"] += 1
    elif h_count == 1:
        hallucination_distribution["1"] += 1
    elif h_count == 2:
        hallucination_distribution["2"] += 1
    else:
        hallucination_distribution["3+"] += 1

print("\n   Distribution:")
for bucket, count in hallucination_distribution.items():
    pct = 100 * count / len(results)
    print(f"     {bucket} hallucinations: {count} scontrini ({pct:.1f}%)")

# Confidence vs Accuracy correlation
print("\n📊 Confidence Score Analysis...")

confidences = []
accuracies = []
for receipt_data in results.values():
    for run in receipt_data["runs"]:
        confidences.append(run["confidence"])
        accuracies.append(run["accuracy"])

correlation = np.corrcoef(confidences, accuracies)[0, 1]
print(f"\n   Correlation (confidence vs accuracy): {correlation:.3f}")
print(f"   Confidence mean: {np.mean(confidences):.1%} ± {np.std(confidences):.1%}")

# Decision Tree
print("\n" + "=" * 70)
print("DECISION TREE")
print("=" * 70)

accuracy_mean = summary["accuracy_mean"]
hallucination_rate = summary["hallucination_rate"]
accuracy_std = summary["accuracy_std"]
moe = summary["accuracy_moe"]
improvement = summary["improvement"]

print(f"\nPrecision: accuracy {accuracy_mean:.1%} ± {accuracy_std:.1%} (MoE ±{moe:.1%})")
print(f"Hallucination: {hallucination_rate:.1f}%")
print(f"Improvement vs Geometric: +{improvement:.1%}")

print("\n" + "-" * 70)
print("DECISIONE")
print("-" * 70)

# Criterio 1: Accuracy
if accuracy_mean >= 0.75:
    print(f"✅ Accuracy {accuracy_mean:.1%} ≥ 75% [PASS]")
elif accuracy_mean >= 0.70:
    print(f"⚠️  Accuracy {accuracy_mean:.1%} [75% - 70%] [BORDERLINE]")
else:
    print(f"❌ Accuracy {accuracy_mean:.1%} < 70% [FAIL]")

# Criterio 2: Hallucination
if hallucination_rate < 3:
    print(f"✅ Hallucination {hallucination_rate:.1f}% < 3% [PASS]")
elif hallucination_rate < 5:
    print(f"⚠️  Hallucination {hallucination_rate:.1f}% [3-5%] [BORDERLINE]")
else:
    print(f"❌ Hallucination {hallucination_rate:.1f}% ≥ 5% [FAIL]")

# Criterio 3: Improvement
if improvement >= 0.15:
    print(f"✅ Improvement +{improvement:.1%} ≥ 15% [STRONG]")
elif improvement >= 0.10:
    print(f"✅ Improvement +{improvement:.1%} ≥ 10% [PASS]")
else:
    print(f"❌ Improvement +{improvement:.1%} < 10% [FAIL]")

# Criterio 4: Variance
if accuracy_std <= 0.05:
    print(f"✅ Variance {accuracy_std:.1%} ≤ 5% [STABLE]")
elif accuracy_std <= 0.08:
    print(f"⚠️  Variance {accuracy_std:.1%} [5-8%] [ACCEPTABLE]")
else:
    print(f"❌ Variance {accuracy_std:.1%} > 8% [UNSTABLE]")

# Decisione finale
print("\n" + "=" * 70)

decision_points = 0
if accuracy_mean >= 0.70:
    decision_points += 1
if hallucination_rate < 5:
    decision_points += 1
if improvement >= 0.10:
    decision_points += 1
if accuracy_std <= 0.08:
    decision_points += 1

if decision_points == 4:
    final_decision = "🟢 GO - Proceed to Week 2"
    recommendation = "LLaVA è pronto per produzione. Implementa hybrid pipeline."
elif decision_points == 3:
    final_decision = "🟡 GO WITH CAUTION - Conditional approval"
    recommendation = "LLaVA pronto ma monitora hallucination durante rollout."
elif decision_points >= 2:
    final_decision = "🟡 SLOW ROLLOUT - Proceed with A/B test first"
    recommendation = "Testa su 10% traffico prima di produzione completa."
else:
    final_decision = "🔴 NO-GO - Do not proceed"
    recommendation = "Hybrid approach non approvato. Riconsiderare strategia."

print(f"\n{final_decision}")
print(f"\nRaccomandazione: {recommendation}")

# Salva analisi
analysis_output = {
    "summary": summary,
    "complexity_stats": {
        k: {
            "count": len(v),
            "accuracy_mean": float(np.mean([x["accuracy"] for x in v])) if v else None,
            "accuracy_std": float(np.std([x["accuracy"] for x in v])) if v else None
        }
        for k, v in complexity_stats.items()
    },
    "store_stats": {
        store: {
            "count": len(accs),
            "accuracy_mean": float(np.mean(accs)),
            "accuracy_std": float(np.std(accs))
        }
        for store, accs in store_sorted
    },
    "hallucination_distribution": hallucination_distribution,
    "confidence_accuracy_correlation": float(correlation),
    "decision_points": decision_points,
    "final_decision": final_decision,
    "recommendation": recommendation
}

output_path = Path("data/validation_80_analysis.json")
with open(output_path, "w") as f:
    json.dump(analysis_output, f, indent=2)

print(f"\n💾 Analisi salvata: {output_path}")

print("\n✅ Task 1.3 Completato")
print("=" * 70)
