import sqlite3


def calculate_statistics(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- Total Spent per Commerce ---
    cursor.execute(
        """
        SELECT c.name, SUM(tl.total_price) as total_spent
        FROM commerces c
        JOIN tickets t ON c.id = t.id_commerce
        JOIN ticket_lines tl ON t.id = tl.id_scontrino
        GROUP BY c.name
    """
    )
    total_spent_per_commerce = cursor.fetchall()

    # --- Total Spent per Product ---
    cursor.execute(
        """
        SELECT p.name, SUM(tl.total_price) as total_spent
        FROM products p
        JOIN ticket_lines tl ON p.id = tl.id_prodotto
        GROUP BY p.name
    """
    )
    total_spent_per_product = cursor.fetchall()

    # --- Monthly Spending Trends ---
    cursor.execute(
        """
        SELECT strftime('%Y-%m', t.data_ora) as month, SUM(tl.total_price) as total_spent
        FROM tickets t
        JOIN ticket_lines tl ON t.id = tl.id_scontrino
        GROUP BY month
    """
    )
    monthly_spending_trends = cursor.fetchall()

    conn.close()

    return {
        "total_spent_per_commerce": total_spent_per_commerce,
        "total_spent_per_product": total_spent_per_product,
        "monthly_spending_trends": monthly_spending_trends,
    }
