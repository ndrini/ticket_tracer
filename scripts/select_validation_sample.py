#!/usr/bin/env python3
"""
Week 1, Task 1.1: Seleziona 100 scontrini RAPPRESENTATIVI per validazione

Criteri:
- Diversità negozi (almeno 5 negozi diversi)
- Diversità complessità:
  * 30% semplici (1-5 items)
  * 50% normali (5-20 items)
  * 20% complessi (20+ items)
- Diversità temporale (3-4 mesi di dati)

Output: data/validation_sample_100.json (100 scontrini con metadati)
"""

import sqlite3
import json
from pathlib import Path
from collections import defaultdict
import random

print("\n" + "=" * 70)
print("Week 1, Task 1.1: Seleziona 100 Scontrini per Validazione")
print("=" * 70)

# Carica DB
conn = sqlite3.connect("data/spese.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Query: tutti i scontrini con extraction_method='geometric' (già estratti)
print("\n📊 Caricamento scontrini da DB...")
cursor.execute("""
    SELECT
        r.id,
        r.image_sha256,
        r.total_declared,
        r.date,
        COALESCE(c.name, 'Unknown') as store_name,
        COUNT(rl.id) as item_count
    FROM receipts r
    LEFT JOIN receipt_lines rl ON r.id = rl.receipt_id AND rl.name_quality = 'complete'
    LEFT JOIN commerces c ON r.id_commerce = c.id
    WHERE r.extraction_method = 'geometric'
    GROUP BY r.id
    ORDER BY r.date
""")

receipts = cursor.fetchall()
print(f"   ✅ Caricati {len(receipts)} scontrini grezzo")

# Filtra: solo scontrini con total_declared e date (dati completi)
receipts = [r for r in receipts if r["total_declared"] is not None and r["date"] is not None]
print(f"   ✅ Dopo filtering: {len(receipts)} scontrini con dati completi")

# Stratifica per complessità
print("\n📈 Stratificazione per complessità...")

simple = []      # 1-5 items
normal = []      # 5-20 items
complex_scontr = []  # 20+ items

for receipt in receipts:
    item_count = receipt["item_count"] or 0

    if item_count <= 5:
        simple.append(receipt)
    elif item_count <= 20:
        normal.append(receipt)
    else:
        complex_scontr.append(receipt)

print(f"   Semplici (1-5 items): {len(simple)}")
print(f"   Normali (5-20 items): {len(normal)}")
print(f"   Complessi (20+ items): {len(complex_scontr)}")

# Target: 30% simple, 50% normal, 20% complex
target_simple = int(100 * 0.30)      # 30
target_normal = int(100 * 0.50)      # 50
target_complex = int(100 * 0.20)     # 20

print(f"\n🎯 Target: {target_simple} semplici + {target_normal} normali + {target_complex} complessi")

# Sample stratificato
sample_simple = random.sample(simple, min(target_simple, len(simple)))
sample_normal = random.sample(normal, min(target_normal, len(normal)))
sample_complex = random.sample(complex_scontr, min(target_complex, len(complex_scontr)))

sample = sample_simple + sample_normal + sample_complex
random.shuffle(sample)

print(f"✅ Campionato: {len(sample_simple)} semplici + {len(sample_normal)} normali + {len(sample_complex)} complessi = {len(sample)} totali")

# Diversità negozi
print("\n🏪 Diversità per negozio...")

store_distribution = defaultdict(int)
for receipt in sample:
    store_distribution[receipt["store_name"]] += 1

stores = sorted(store_distribution.items(), key=lambda x: x[1], reverse=True)
print(f"   {len(stores)} negozi diversi nel campione:")
for store, count in stores[:10]:
    print(f"     {store}: {count}")

# Diversità temporale
print("\n📅 Copertura temporale...")

dates = sorted([receipt["date"] for receipt in sample if receipt["date"] is not None])
print(f"   Data minima: {dates[0]}")
print(f"   Data massima: {dates[-1]}")
print(f"   Span: {dates[-1]} - {dates[0]}")

# Salva sample in JSON
sample_data = []
for receipt in sample:
    sample_data.append({
        "id": receipt["id"],
        "sha256": receipt["image_sha256"],
        "total": float(receipt["total_declared"]),
        "date": receipt["date"],
        "store": receipt["store_name"],
        "item_count": receipt["item_count"],
        "complexity": "simple" if (receipt["item_count"] or 0) <= 5 else "normal" if (receipt["item_count"] or 0) <= 20 else "complex"
    })

output_path = Path("data/validation_sample_100.json")
with open(output_path, "w") as f:
    json.dump({
        "metadata": {
            "total": len(sample_data),
            "simple_count": len(sample_simple),
            "normal_count": len(sample_normal),
            "complex_count": len(sample_complex),
            "store_count": len(stores),
            "date_range": f"{dates[0]} to {dates[-1]}"
        },
        "samples": sample_data
    }, f, indent=2)

print(f"\n💾 Campione salvato: {output_path}")

# Statistiche finali
print("\n" + "=" * 70)
print("RIEPILOGO")
print("=" * 70)

print(f"\n✅ Scontrini selezionati: {len(sample)}")
print(f"✅ Negozi rappresentati: {len(stores)}")
print(f"✅ Complexità:")
print(f"   - Semplici (1-5 items): {len(sample_simple)} ({100*len(sample_simple)//len(sample)}%)")
print(f"   - Normali (5-20 items): {len(sample_normal)} ({100*len(sample_normal)//len(sample)}%)")
print(f"   - Complessi (20+ items): {len(sample_complex)} ({100*len(sample_complex)//len(sample)}%)")
print(f"✅ Periodo: {dates[0]} → {dates[-1]}")

# Verifica immagini disponibili
print(f"\n🖼️  Verifica immagini disponibili...")
missing_images = 0
for receipt in sample:
    image_path = Path("data/ritagli") / f"{receipt['image_sha256']}.jpg"
    if not image_path.exists():
        missing_images += 1

print(f"   ✅ Immagini disponibili: {len(sample) - missing_images}/{len(sample)}")
if missing_images > 0:
    print(f"   ⚠️  Immagini mancanti: {missing_images}")

print(f"\n✅ Pronto per Task 1.2: Validazione LLaVA su 100 scontrini")
print("=" * 70)

conn.close()
