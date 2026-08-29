"""
Fase E.5 — Applica la spezzatura dei nomi fused.

Legge le validazioni dalla fase E.4 e applica la spezzatura al database,
inserendo nuove righe per i prodotti spezzati.

Misura: FusedCoverage, ProduzioniNuove, ConflictRate.

Uso:
    uv run python scripts/fase_e_5_applica_spezzatura.py
    uv run python scripts/fase_e_5_applica_spezzatura.py --dry-run
"""
import argparse
import json
import sqlite3
import sys


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--validazioni", default="data/fase_e_validazioni_fused.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    with open(args.validazioni) as f:
        validazioni = json.load(f)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Conta i fused PRIMA
    cursor.execute("""
        SELECT COUNT(*) as n FROM receipt_lines
        WHERE name_quality = 'fused' AND extraction_method = 'geometric'
    """)
    count_fused_before = cursor.fetchone()["n"]

    # Conta i prodotti PRIMA
    cursor.execute("SELECT COUNT(*) as n FROM products")
    products_before = cursor.fetchone()["n"]

    print(f"\nBaseline:")
    print(f"  Righe fused: {count_fused_before}")
    print(f"  Prodotti totali: {products_before}\n")

    splits_applied = 0
    new_lines = 0
    conflict_tokens = 0

    if not args.dry_run:
        for key, validation in validazioni.items():
            if validation["decision"] != "SPLIT_OK":
                continue

            receipt_line_id = validation["receipt_line_id"]
            matches = validation["matches"]

            # Leggi la riga fused
            cursor.execute("""
                SELECT rl.id, rl.receipt_id, rl.total_price, rl.unity_price
                FROM receipt_lines rl
                WHERE rl.id = ?
            """, (receipt_line_id,))

            fused_line = cursor.fetchone()
            if not fused_line:
                continue

            # Estrai i prodotti dai match
            split_products = [m for m in matches if m["product_id"] is not None]

            if len(split_products) < 2:
                continue

            # Dividi il prezzo proporzionalmente
            # Assunzione semplice: prezzo uguale per ogni prodotto
            price_per_product = fused_line["total_price"] / len(split_products)

            # Inserisci nuove righe
            for prod_match in split_products:
                cursor.execute("""
                    INSERT INTO receipt_lines
                    (receipt_id, product_id, quantity, unity_price, total_price,
                     extraction_method, name_quality)
                    VALUES (?, ?, ?, ?, ?, 'geometric', 'split_from_fused')
                """, (
                    fused_line["receipt_id"],
                    prod_match["product_id"],
                    1,
                    price_per_product,
                    price_per_product
                ))

                new_lines += 1

            # Marca il fused come "consumed"
            cursor.execute("""
                UPDATE receipt_lines SET name_quality = 'split_done'
                WHERE id = ?
            """, (receipt_line_id,))

            splits_applied += 1

        conn.commit()

        print(f"Applicato:")
        print(f"  Spezzature applicate: {splits_applied}")
        print(f"  Nuove righe inserite: {new_lines}")

        # Conta DOPO
        cursor.execute("""
            SELECT COUNT(*) as n FROM receipt_lines
            WHERE name_quality = 'fused' AND extraction_method = 'geometric'
        """)
        count_fused_after = cursor.fetchone()["n"]

        cursor.execute("SELECT COUNT(*) as n FROM products")
        products_after = cursor.fetchone()["n"]

        fused_coverage = 100.0 * (count_fused_before - count_fused_after) / count_fused_before if count_fused_before > 0 else 0
        new_products = products_after - products_before

        print(f"\nAfter spezzatura:")
        print(f"  Righe fused rimanenti: {count_fused_after}  ({count_fused_before - count_fused_after} spezzate)")
        print(f"  FusedCoverage: {fused_coverage:.1f}%")
        print(f"  Prodotti totali: {products_after}")
        print(f"  Prodotti nuovi creati: {new_products}")

        # Semplice ConflictRate: conta i None
        conflict_count = sum(1 for v in validazioni.values()
                           if v["decision"] == "SPLIT_OK"
                           for m in v["matches"]
                           if m["product_id"] is None)
        total_tokens = sum(len(v["matches"]) for v in validazioni.values()
                          if v["decision"] == "SPLIT_OK")
        conflict_rate = 100.0 * conflict_count / total_tokens if total_tokens > 0 else 0

        print(f"  ConflictRate: {conflict_rate:.1f}% ({conflict_count}/{total_tokens} token non riconosciuti)\n")

        if fused_coverage < 50:
            print(f"⚠️  FusedCoverage bassa: {fused_coverage:.1f}%")

    else:
        print("(dry-run: nessun update applicato)\n")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
