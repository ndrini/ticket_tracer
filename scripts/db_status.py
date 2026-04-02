# scripts/db_status.py

import sqlite3
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "data" / "db" / "produzione.db"

def get_db_status():
    if not os.path.exists(DB_PATH):
        print(f"Database non trovato in {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 40)
    print("  STATO DATABASE TICKET TRACER")
    print("=" * 40)

    # 1. Conteggio scontrini
    cursor.execute("SELECT COUNT(*) FROM receipts")
    total_receipts = cursor.fetchone()[0]
    print(f"Scontrini totali: {total_receipts}")

    # 2. Elenco negozi (top 10)
    print("\nTop 10 Negozi:")
    cursor.execute("""
        SELECT c.name, COUNT(r.id) as num_receipts
        FROM commerces c
        JOIN receipts r ON c.id = r.id_commerce
        GROUP BY c.name
        ORDER BY num_receipts DESC
        LIMIT 10
    """)
    for name, count in cursor.fetchall():
        print(f"- {name}: {count} scontrini")

    # 3. Tabella Equivalenze (AKA)
    print("\nTabella Equivalenze Prodotti (Standard -> Alias):")
    cursor.execute("SELECT name, aka FROM products")
    products = cursor.fetchall()
    if not products:
        print("Nessun prodotto trovato.")
    for name, aka_json in products:
        aka_list = json.loads(aka_json)
        if aka_list:
            aliases = ", ".join(aka_list)
            print(f"- {name} (alias: {aliases})")
        else:
            print(f"- {name}")

    print("\n" + "=" * 40)
    conn.close()

if __name__ == "__main__":
    get_db_status()
