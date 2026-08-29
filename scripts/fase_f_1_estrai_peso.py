"""
Fase F.1 — Estrai peso/quantità dai nomi prodotto.

Legge i nomi in `products`, estrae weight/unit con regex, salva in
`receipt_lines.quantity_value` e `quantity_unit`.

Usa due regex:
  1. Singolo: "1,5 KG", "500g", "0,5L"
  2. Pack: "2 x 1,5 KG", "3X500G"

Normalizza unità: G→KG, ML→LT, pz singoli→pz.

Uso:
    uv run python scripts/fase_f_1_estrai_peso.py
    uv run python scripts/fase_f_1_estrai_peso.py --db data/spese.db --dry-run
"""
import argparse
import re
import sqlite3
import sys


# Regex per singolo valore (es. "1,5 KG", "500g")
REGEX_SINGOLO = re.compile(
    r'(?i)(\d+(?:[.,]\d+)?)\s*(kg|kgs|g|gr|lt|l|ml|cl|un|pz)',
    re.IGNORECASE
)

# Regex per pack (es. "2 x 1,5 KG", "3X500G")
REGEX_PACK = re.compile(
    r'(?i)(\d+)\s*[xX*]\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs|g|gr|lt|l|ml|cl)',
    re.IGNORECASE
)

# Mappa di normalizzazione unità
UNIT_MAPPING = {
    'kg': 'kg', 'kgs': 'kg',
    'g': 'g', 'gr': 'g',
    'lt': 'lt', 'l': 'lt',
    'ml': 'ml', 'cl': 'ml',
    'un': 'pz', 'pz': 'pz',
}


def estrai_peso_da_nome(nome):
    """
    Estrae (quantity_value, quantity_unit) da un nome.

    Cerca prima pack, poi singolo.
    Restituisce (float, str) o (None, None).
    """
    if not nome:
        return None, None

    # Prova pack first (per evitare match parziale)
    match_pack = REGEX_PACK.search(nome)
    if match_pack:
        qty_pack, qty_singolo, unit = match_pack.groups()
        # Calcola: qty_pack * qty_singolo
        valore = float(qty_pack) * float(qty_singolo.replace(',', '.'))
        unit_norm = UNIT_MAPPING.get(unit.lower(), unit.lower())
        return valore, unit_norm

    # Prova singolo
    match_singolo = REGEX_SINGOLO.search(nome)
    if match_singolo:
        valore, unit = match_singolo.groups()
        valore = float(valore.replace(',', '.'))
        unit_norm = UNIT_MAPPING.get(unit.lower(), unit.lower())
        return valore, unit_norm

    return None, None


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n📥 Fase F.1 — Estrai peso dai nomi\n")

    # Leggi i nomi e estrai peso
    cursor.execute("""
        SELECT DISTINCT rl.id, p.name
        FROM receipt_lines rl
        JOIN products p ON rl.product_id = p.id
        ORDER BY rl.id
    """)

    rows = cursor.fetchall()

    updates = []
    extracted_count = 0

    for row in rows:
        line_id = row["id"]
        name = row["name"]

        qty_val, qty_unit = estrai_peso_da_nome(name)

        if qty_val is not None:
            updates.append((qty_val, qty_unit, line_id))
            extracted_count += 1

    print(f"Nomi analizzati: {len(rows)}")
    print(f"Peso estratto: {extracted_count} ({100*extracted_count//len(rows)}%)\n")

    if not args.dry_run and updates:
        # Aggiungi le colonne se non esistono
        try:
            cursor.execute("ALTER TABLE receipt_lines ADD COLUMN quantity_value REAL")
        except sqlite3.OperationalError:
            pass  # colonna già esiste

        try:
            cursor.execute("ALTER TABLE receipt_lines ADD COLUMN quantity_unit TEXT")
        except sqlite3.OperationalError:
            pass

        # Applica gli update
        for qty_val, qty_unit, line_id in updates:
            cursor.execute(
                "UPDATE receipt_lines SET quantity_value = ?, quantity_unit = ? WHERE id = ?",
                (qty_val, qty_unit, line_id)
            )

        conn.commit()
        print(f"✅ Applicate {len(updates)} righe con peso/quantità\n")

        # Verifica per unit
        cursor.execute("""
            SELECT quantity_unit, COUNT(*) as count
            FROM receipt_lines
            WHERE quantity_unit IS NOT NULL
            GROUP BY quantity_unit
            ORDER BY count DESC
        """)

        print("Distribuzione unità:")
        for unit_row in cursor.fetchall():
            unit, count = unit_row[0], unit_row[1]
            print(f"  {unit:5s}  {count:4d} righe")

    elif args.dry_run:
        print("(dry-run: nessun update)\n")
        # Mostra esempi
        print("Esempi di estrazione:\n")
        for i, (qty_val, qty_unit, line_id) in enumerate(updates[:10]):
            print(f"  {rows[line_id-1]['name']:50s} → {qty_val:6.2f} {qty_unit}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
