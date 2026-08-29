"""
Fase F.3 — Applica le categorie al database.

Legge le proposte da F.2, crea un file di validazioni con categorizzazione
manuale (simulata come auto-approve per test).

Nel workflow reale: l'utente revede i 1242 "Altro" e li categorizza.

Uso:
    uv run python scripts/fase_f_3_applica_categorie.py
    uv run python scripts/fase_f_3_applica_categorie.py --db data/spese.db --dry-run
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path


# Miglioramento della categorizzazione manuale (simulato)
# In realtà questi sarebbero validati dall'utente
MANUAL_OVERRIDES = {
    "amanida quatre estac": "Verdure",  # insalata
    "guacamole": "Frutta",  # tecnicamente frutto
    "formatge ratllat piz": "Latticini",  # formaggio grattugiato
    "form. burgos natural": "Latticini",  # formaggio Burgos
    "estac.consum 250": "Latticini",  # formaggio (consumo)
    "mozzar.ratll.consum": "Latticini",  # mozzarella grattugiata
    "pernil s. extra fi": "Carne",  # prosciutto
    "pza alvocat extra cal fruitós": "Frutta",  # avocado
    "mortadel-la italiana": "Carne",
    "llet sen.consum 1l": "Latticini",  # latte
    "tomaquet triturat ex": "Verdure",  # pomodoro tritato
}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    print("\n📥 Fase F.3 — Applica categorie\n")

    # Leggi le proposte
    with open("data/fase_f_2_categorie_proposte.json") as f:
        proposte_data = json.load(f)

    proposte = proposte_data["proposte"]

    # Crea validazioni: applica override manuali dove disponibili
    validazioni = {}
    for key, prop in proposte.items():
        prod_name = prop["name"].lower().strip()
        if prod_name in MANUAL_OVERRIDES:
            categoria = MANUAL_OVERRIDES[prod_name]
            approved = True
        else:
            categoria = prop["category"]
            approved = prop["confidence"] == "high"

        validazioni[key] = {
            "product_id": prop["product_id"],
            "name": prop["name"],
            "category": categoria,
            "approved": approved,
            "approved_by": "auto" if approved else "manual_required"
        }

    # Salva le validazioni
    output_path = "data/fase_f_3_categorie_applicate.json"
    with open(output_path, "w") as f:
        json.dump(validazioni, f, indent=2)

    print(f"Validazioni salvate: {output_path}\n")

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    if not args.dry_run:
        # Aggiungi colonna category se non esiste
        try:
            cursor.execute("ALTER TABLE products ADD COLUMN category TEXT")
        except sqlite3.OperationalError:
            pass  # già esiste

        # Applica le categorie
        for key, validation in validazioni.items():
            cursor.execute(
                "UPDATE products SET category = ? WHERE id = ?",
                (validation["category"], validation["product_id"])
            )

        conn.commit()

        # Statistiche
        cursor.execute("""
            SELECT category, COUNT(*) as count, SUM(
                COALESCE((SELECT COUNT(*) FROM receipt_lines rl WHERE rl.product_id = p.id), 0)
            ) as total_usage
            FROM products p
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
        """)

        print("Categorie applicate:\n")
        for row in cursor.fetchall():
            category, count, usage = row[0], row[1], row[2] or 0
            print(f"  {category:15s}  {count:4d} prodotti  ({usage:4d} righe nei receipts)")

        # Coverage
        cursor.execute("SELECT COUNT(*) as n FROM products WHERE category IS NOT NULL")
        categorized = cursor.fetchone()[0]
        total = len(proposte)

        print(f"\nCategorizzazione coverage: {categorized}/{total} ({100*categorized//total}%)")

    else:
        print("(dry-run: nessun update)\n")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
