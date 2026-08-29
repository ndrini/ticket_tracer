#!/usr/bin/env python3
"""
Daily A/B Test Report

Runs every morning to analyze results and recommend next action.
Usage: uv run python scripts/run_ab_test_daily_report.py
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path.cwd() / "app"))

from metrics.ab_test_analyzer import ABTestAnalyzer
from config.ab_test import (
    ACCURACY_IMPROVEMENT_TARGET,
    HALLUCINATION_RATE_MAX,
    MANUAL_REVIEW_RATE_MAX,
    LATENCY_P99_MAX,
    get_rollout_stats
)

print("\n" + "=" * 70)
print("A/B TEST DAILY REPORT")
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

analyzer = ABTestAnalyzer()
today = date.today()

# Get results from last 24h
yesterday = today - timedelta(days=1)
results = analyzer.get_cumulative_results(yesterday, today)

if results.get("status") == "insufficient_data":
    print("\n⏳ Insufficient data (need ≥5 samples per group)")
    print(f"   Check back tomorrow.")
    sys.exit(0)

print("\n📊 RESULTS (24h)")
print("-" * 70)

geometric = results["geometric"]
hybrid = results["hybrid"]

print(f"\nGEOMETRIC (Control):")
print(f"  Samples: {geometric.get('count', 0)}")
print(f"  Success Rate: {geometric.get('success_rate', 0):.1f}%")
print(f"  Avg Confidence: {geometric.get('avg_confidence', 0):.1%}")
print(f"  Avg Latency: {geometric.get('avg_latency_ms', 0):.0f}ms")
print(f"  Hallucination: {geometric.get('hallucination_rate', 0):.1f}%")
print(f"  Manual Review: {geometric.get('manual_review_rate', 0):.1f}%")

print(f"\nHYBRID (Treatment):")
print(f"  Samples: {hybrid.get('count', 0)}")
print(f"  Success Rate: {hybrid.get('success_rate', 0):.1f}%")
print(f"  Avg Confidence: {hybrid.get('avg_confidence', 0):.1%}")
print(f"  Avg Latency: {hybrid.get('avg_latency_ms', 0):.0f}ms")
print(f"  Hallucination: {hybrid.get('hallucination_rate', 0):.1f}%")
print(f"  Manual Review: {hybrid.get('manual_review_rate', 0):.1f}%")

# Improvements
improvement = results["improvement"]
print(f"\nIMPROVEMENT:")
print(f"  Success Rate Δ: {improvement.get('absolute', 0):+.1f}% (relative: {improvement.get('relative', 0):+.1%})")
print(f"  Status: {improvement.get('status', 'unknown').upper()}")

# Decision gates
print("\n" + "=" * 70)
print("DECISION GATES")
print("=" * 70)

gates_passed = 0
gates_total = 4

# Gate 1: Accuracy improvement
if improvement.get('absolute', 0) >= ACCURACY_IMPROVEMENT_TARGET * 100:
    print(f"\n✅ Gate 1: Accuracy improvement ≥ {ACCURACY_IMPROVEMENT_TARGET*100:.0f}%")
    gates_passed += 1
else:
    print(f"\n❌ Gate 1: Accuracy improvement < {ACCURACY_IMPROVEMENT_TARGET*100:.0f}%")
    print(f"   Current: {improvement.get('absolute', 0):+.1f}%")

# Gate 2: Hallucination rate
hybrid_halluc = hybrid.get('hallucination_rate', 999)
if hybrid_halluc < HALLUCINATION_RATE_MAX * 100:
    print(f"✅ Gate 2: Hallucination rate < {HALLUCINATION_RATE_MAX*100:.1f}%")
    gates_passed += 1
else:
    print(f"❌ Gate 2: Hallucination rate ≥ {HALLUCINATION_RATE_MAX*100:.1f}%")
    print(f"   Current: {hybrid_halluc:.1f}%")

# Gate 3: Manual review rate
hybrid_review = hybrid.get('manual_review_rate', 999)
if hybrid_review < MANUAL_REVIEW_RATE_MAX * 100:
    print(f"✅ Gate 3: Manual review rate < {MANUAL_REVIEW_RATE_MAX*100:.1f}%")
    gates_passed += 1
else:
    print(f"❌ Gate 3: Manual review rate ≥ {MANUAL_REVIEW_RATE_MAX*100:.1f}%")
    print(f"   Current: {hybrid_review:.1f}%")

# Gate 4: Latency acceptable
hybrid_latency = hybrid.get('avg_latency_ms', 0)
if hybrid_latency < LATENCY_P99_MAX:
    print(f"✅ Gate 4: Latency < {LATENCY_P99_MAX}ms")
    gates_passed += 1
else:
    print(f"❌ Gate 4: Latency ≥ {LATENCY_P99_MAX}ms")
    print(f"   Current: {hybrid_latency:.0f}ms")

# Recommendation
print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)

current_ratio = get_rollout_stats()["hybrid_ratio"]

if gates_passed >= 3:
    print(f"\n🟢 PROCEED WITH ROLLOUT")
    if current_ratio < 0.5:
        print(f"   Scale HYBRID_EXTRACTION_RATIO from {current_ratio*100:.0f}% → 50%")
    elif current_ratio < 1.0:
        print(f"   Scale HYBRID_EXTRACTION_RATIO from {current_ratio*100:.0f}% → 100%")
    else:
        print(f"   ✅ Already at 100% - continue monitoring")
elif gates_passed >= 2:
    print(f"\n🟡 HOLD & MONITOR")
    print(f"   Keep HYBRID_EXTRACTION_RATIO at {current_ratio*100:.0f}%")
    print(f"   Collect more data (target: 100+ samples per group)")
    print(f"   {gates_total - gates_passed} gate(s) still failing")
else:
    print(f"\n🔴 PAUSE ROLLOUT")
    print(f"   Revert to HYBRID_EXTRACTION_RATIO = 0.0")
    print(f"   Investigate root cause")
    print(f"   {gates_total - gates_passed} gate(s) failing")

# Statistical significance
print("\n" + "=" * 70)
print("STATISTICAL TEST")
print("=" * 70)

stat_test = analyzer.statistical_test(yesterday, today)

if stat_test.get("status") == "insufficient_data":
    print("\n⏳ Need more samples for t-test (target: 30+ per group)")
else:
    print(f"\nTwo-Sample T-Test:")
    print(f"  t-statistic: {stat_test.get('t_statistic', 0):.3f}")
    print(f"  p-value: {stat_test.get('p_value', 1):.4f}")
    print(f"  Significant (α=0.05): {'Yes ✅' if stat_test.get('is_significant') else 'No ❌'}")
    print(f"  Effect size (Cohen's d): {stat_test.get('cohens_d', 0):.3f}")

print("\n" + "=" * 70)
print("✅ Report Complete")
print("=" * 70)
