"""
Fase E.1 — Catalogo grezzo dai nomi 'complete'.

Legge le righe con name_quality='complete' dal database, deduplica sui nomi
normalizzati (case-insensitive, whitespace), e crea una tabella di prodotti
canonici.

Questo è il primo passo dell'Opzione C (iterativa): catalogo su dati reali,
normalizzazione supervisionata successiva.

Uso:
    uv run python scripts/fase_e_1_catalogo_grezzo.py
    uv run python scripts/fase_e_1_catalogo_grezzo.py --db data/spese.db
"""
import argparse
import json
import sqlite3
import sys


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db", help="Database SQLite")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Leggi i nomi 'complete' dalle righe geometriche
    cursor.execute("""
        SELECT DISTINCT
            LOWER(TRIM(p.name)) as canonical_name,
            p.name as original_name,
            COUNT(*) as count
        FROM receipt_lines rl
        JOIN products p ON rl.product_id = p.id
        WHERE rl.name_quality = 'complete'
          AND rl.extraction_method = 'geometric'
        GROUP BY canonical_name
        ORDER BY count DESC, canonical_name
    """)

    rows = cursor.fetchall()
    n_canonical = len(rows)

    print(f"\nCatalogo grezzo da {n_canonical} nomi unici")
    print(f"Distribuzione di frequenza (top 30):\n")

    catalogo_grezzo = []
    for i, row in enumerate(rows):
        canonical = row["canonical_name"]
        original = row["original_name"]
        count = row["count"]
        catalogo_grezzo.append({
            "id": i + 1,
            "canonical_name": canonical,
            "original_name": original,
            "frequency": count
        })

        if i < 30:
            print(f"  {i+1:4d}. '{canonical:40s}' ({count:3d}x)  [orig: {original}]")

    if n_canonical > 30:
        print(f"  ... ({n_canonical - 30} altri)\n")
    else:
        print()

    # Salva il catalogo grezzo come JSON
    output_path = "data/fase_e_1_catalogo_grezzo.json"
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_canonical_names": n_canonical,
                "source": "receipt_lines where name_quality='complete' and extraction_method='geometric'",
                "phase": "E.1 — Catalogo grezzo"
            },
            "catalogo": catalogo_grezzo
        }, f, indent=2)

    print(f"Salvato: {output_path}")

    # Statistiche di cobertura
    cursor.execute("""
        SELECT
            COUNT(*) as total_righe,
            SUM(CASE WHEN name_quality = 'complete' AND extraction_method = 'geometric' THEN 1 ELSE 0 END) as complete_righe
        FROM receipt_lines
    """)
    stats = cursor.fetchone()
    total = stats["total_righe"]
    complete = stats["complete_righe"]

    print(f"\nMetriche:")
    print(f"  Righe totali nel database:      {total}")
    print(f"  Righe 'complete' geometriche:  {complete}  ({100*complete//total}%)")
    print(f"  Nomi unici deduplicated:       {n_canonical}  ({100*n_canonical//complete:.1f}% di riduzione)")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
