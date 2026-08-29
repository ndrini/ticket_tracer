"""
Fase H.4 — Report spesa per categoria e mese.

Legge receipts.date e genera breakdown mensile: "Frutta Gennaio €X, Febbraio €Y".

Uso:
    uv run python scripts/fase_h_2_report_per_mese.py
    uv run python scripts/fase_h_2_report_per_mese.py --start 2025-01-01 --end 2025-12-31
"""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    print("\n📊 Fase H.4 — Report Spesa per Categoria e Mese\n")

    # Query: spesa per (categoria, mese)
    where_clause = "WHERE r.date IS NOT NULL"
    params = []

    if args.start:
        where_clause += " AND r.date >= ?"
        params.append(args.start)
    if args.end:
        where_clause += " AND r.date <= ?"
        params.append(args.end)

    query = f"""
        SELECT
            p.category,
            DATE(r.date, 'start of month') as mese,
            SUM(rl.total_price) as spesa,
            COUNT(DISTINCT r.id) as num_scontrini,
            COUNT(rl.id) as num_righe
        FROM receipt_lines rl
        JOIN products p ON rl.product_id = p.id
        JOIN receipts r ON rl.receipt_id = r.id
        {where_clause}
        GROUP BY category, mese
        ORDER BY mese DESC, spesa DESC
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Struttura: {categoria: {mese: spesa}}
    data_by_category = defaultdict(lambda: {})
    mesi_unici = set()
    totale_generale = 0.0

    for row in rows:
        category, mese, spesa, num_scontrini, num_righe = row
        data_by_category[category][mese] = {
            "spesa": spesa,
            "num_scontrini": num_scontrini,
            "num_righe": num_righe
        }
        mesi_unici.add(mese)
        totale_generale += spesa

    mesi_ordinati = sorted(mesi_unici, reverse=True)

    print(f"Periodo: {min(mesi_ordinati)} → {max(mesi_ordinati)}")
    print(f"Totale: €{totale_generale:.2f}\n")

    # Report tabellare
    print("Categoria       " + "  ".join(f"{m[:7]}" for m in mesi_ordinati) + "  TOTALE")
    print("=" * (80 + len(mesi_ordinati) * 10))

    report_json = {
        "metadata": {
            "phase": "H.4 — Report per mese",
            "period_start": min(mesi_ordinati) if mesi_ordinati else None,
            "period_end": max(mesi_ordinati) if mesi_ordinati else None,
            "total_spent": totale_generale
        },
        "categories": {}
    }

    for category in sorted(data_by_category.keys()):
        riga = f"{category:15}"
        totale_cat = 0.0

        for mese in mesi_ordinati:
            if mese in data_by_category[category]:
                spesa = data_by_category[category][mese]["spesa"]
                riga += f"  €{spesa:7.2f}"
                totale_cat += spesa
            else:
                riga += "  €   0.00"

        riga += f"  €{totale_cat:7.2f}"
        print(riga)

        report_json["categories"][category] = {
            "total": totale_cat,
            "percentage": 100.0 * totale_cat / totale_generale if totale_generale > 0 else 0,
            "per_month": {
                mese: {
                    "spesa": data_by_category[category][mese]["spesa"],
                    "num_scontrini": data_by_category[category][mese]["num_scontrini"],
                    "num_righe": data_by_category[category][mese]["num_righe"]
                }
                for mese in mesi_ordinati
                if mese in data_by_category[category]
            }
        }

    print("=" * (80 + len(mesi_ordinati) * 10))

    # Salva il report JSON
    output_path = "data/fase_h_2_report_per_mese.json"
    with open(output_path, "w") as f:
        json.dump(report_json, f, indent=2)

    print(f"\nReport salvato: {output_path}\n")

    # Trend: categoria che aumenta/diminuisce
    if len(mesi_ordinati) >= 2:
        print("Trend (prime e ultime date):\n")
        prima_data = mesi_ordinati[-1]  # mese più vecchio
        ultima_data = mesi_ordinati[0]  # mese più recente

        for category in sorted(data_by_category.keys()):
            spesa_prima = data_by_category[category].get(prima_data, {}).get("spesa", 0)
            spesa_ultima = data_by_category[category].get(ultima_data, {}).get("spesa", 0)

            if spesa_prima > 0:
                trend = ((spesa_ultima - spesa_prima) / spesa_prima) * 100
                direction = "↑" if trend > 0 else "↓" if trend < 0 else "→"
                print(f"  {direction} {category:15} {prima_data}: €{spesa_prima:7.2f} → {ultima_data}: €{spesa_ultima:7.2f} ({trend:+.1f}%)")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
