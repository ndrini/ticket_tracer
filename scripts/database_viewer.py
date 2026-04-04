import sqlite3
import os
from pathlib import Path

# Configurazione percorso DB (deve corrispondere a quello in main.py)
BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "data" / "db" / "produzione.db"

def view_db():
    if not os.path.exists(DB_PATH):
        print(f"Errore: Il database non esiste in {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n" + "="*50)
    print("       RIEPILOGO DATABASE TICKET TRACER")
    print("="*50)

    # 1. Statistiche Generali
    cursor.execute("SELECT COUNT(*) FROM commerces")
    total_commerces = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM receipts")
    total_receipts = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_price) FROM receipt_lines")
    total_spend = cursor.fetchone()[0] or 0.0

    print(f"Negozi registrati: {total_commerces}")
    print(f"Scontrini totali:  {total_receipts}")
    print(f"Spesa totale:      {total_spend:.2f} €")
    print("-" * 50)

    # 2. Ultimi 10 Scontrini
    print("\nULTIMI 10 SCONTRINI:")
    query = """
    SELECT r.id, c.name, r.data_ora, SUM(rl.total_price) as totale
    FROM receipts r
    JOIN commerces c ON r.id_commerce = c.id
    LEFT JOIN receipt_lines rl ON r.id = rl.receipt_id
    GROUP BY r.id
    ORDER BY r.id DESC
    LIMIT 10
    """
    cursor.execute(query)
    recent_receipts = cursor.fetchall()

    if not recent_receipts:
        print("Nessun scontrino trovato.")
    else:
        print(f"{'ID':<4} | {'Negozio':<20} | {'Data/Ora':<20} | {'Totale':<8}")
        print("-" * 60)
        for row in recent_receipts:
            rid, name, dt, tot = row
            tot = tot or 0.0
            dt = dt or "N/D"
            print(f"{rid:<4} | {name[:20]:<20} | {dt:<20} | {tot:>6.2f} €")

    # 3. Top 5 Prodotti più acquistati
    print("\nTOP 5 PRODOTTI (per quantità):")
    query = """
    SELECT p.name, SUM(rl.quantity) as qty
    FROM receipt_lines rl
    JOIN products p ON rl.product_id = p.id
    GROUP BY p.id
    ORDER BY qty DESC
    LIMIT 5
    """
    cursor.execute(query)
    top_products = cursor.fetchall()
    
    for name, qty in top_products:
        print(f"- {name}: {qty}")

    conn.close()
    print("="*50 + "\n")

if __name__ == "__main__":
    view_db()
