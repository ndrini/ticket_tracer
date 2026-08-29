"""
Fase F.4 — Report: spesa per categoria.

Query finale: somma totale per categoria, percentuali.

Risponde: "Quanto spendo in Frutta? In Latticini? Etc."

Uso:
    uv run python scripts/fase_f_4_report_spesa_per_categoria.py
"""
import json
import sqlite3
import sys


def main(argv):
    db = "data/spese.db"

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    print("\n📊 Fase F.4 — Report Spesa per Categoria\n")

    # Query principale
    cursor.execute("""
        SELECT
            p.category,
            COUNT(DISTINCT rl.receipt_id) as num_scontrini,
            COUNT(rl.id) as num_righe,
            SUM(rl.total_price) as spesa_totale,
            AVG(rl.total_price) as prezzo_medio
        FROM receipt_lines rl
        JOIN products p ON rl.product_id = p.id
        WHERE p.category IS NOT NULL
        GROUP BY p.category
        ORDER BY spesa_totale DESC
    """)

    result = cursor.fetchall()

    # Calcola totale generale
    cursor.execute("SELECT SUM(total_price) as totale FROM receipt_lines")
    totale_generale = cursor.fetchone()[0] or 0.0

    print(f"Totale generale speso: €{totale_generale:.2f}\n")

    # Report per categoria
    report = {
        "metadata": {
            "phase": "F.4 — Report spesa per categoria",
            "total_spent": totale_generale,
            "currency": "EUR"
        },
        "categories": []
    }

    print(f"{'Categoria':<15} {'Spesa':<12} {'%':<6} {'Righe':<8} {'Scontrini':<10} {'Prezzo medio':<12}")
    print("=" * 80)

    for row in result:
        category, num_scontrini, num_righe, spesa, prezzo_medio = row
        if spesa is None:
            spesa = 0.0
        if prezzo_medio is None:
            prezzo_medio = 0.0

        percentuale = 100.0 * spesa / totale_generale if totale_generale > 0 else 0

        print(f"{category:<15} €{spesa:>9.2f}  {percentuale:>5.1f}%  {num_righe:>6d}  {num_scontrini:>8d}  €{prezzo_medio:>10.2f}")

        report["categories"].append({
            "category": category,
            "total_spent": spesa,
            "percentage": percentuale,
            "num_lines": num_righe,
            "num_receipts": num_scontrini,
            "avg_price": prezzo_medio
        })

    print("=" * 80)

    # Salva il report
    output_path = "data/fase_f_4_report_spesa.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport salvato: {output_path}\n")

    # Metriche di check
    cursor.execute("""
        SELECT COUNT(DISTINCT receipt_id) as num_scontrini,
               COUNT(*) as num_righe,
               SUM(total_price) as totale
        FROM receipt_lines
    """)
    rl_check = cursor.fetchone()

    print(f"Check sanità:")
    print(f"  Scontrini totali nel DB: {rl_check[0]}")
    print(f"  Righe totali nel DB: {rl_check[1]}")
    print(f"  Spesa totale (somma righe): €{rl_check[2] or 0:.2f}")
    print(f"  Spesa per categoria: €{sum(c['total_spent'] for c in report['categories']):.2f}")
    print(f"  ✓ Coerenza: {abs((rl_check[2] or 0) - sum(c['total_spent'] for c in report['categories'])) < 0.01}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
