import json
import os
import sqlite3

import pytest

from app.db.db_manager import init_db
from app.db.inserter import insert_receipt_data


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ticket.db"
    init_db(str(db_file))
    return str(db_file)


def test_insert_receipt_data(temp_db):
    """Verifica che insert_receipt_data popoli commerces, receipts, products, e receipt_lines correttamente."""
    receipt_data = {
        "shop_name": "Ecoveritas",
        "date": "2024-03-22",
        "total": 5.40,
        "items": [
            {"name": "Pane", "original_name": "Pan rústic", "price": 2.20},
            {"name": "Latte", "original_name": "Llet", "price": 0.80},
            {"name": "Pane", "original_name": "Pan baguette", "price": 2.40},
        ],
    }

    receipt_id = insert_receipt_data(temp_db, receipt_data)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Check Commerce
    cursor.execute("SELECT id, name FROM commerces")
    commerces = cursor.fetchall()
    assert len(commerces) == 1
    assert commerces[0][1] == "Ecoveritas"
    commerce_id = commerces[0][0]

    # Check Receipt
    cursor.execute("SELECT id, id_commerce, data_ora FROM receipts")
    receipts = cursor.fetchall()
    assert len(receipts) == 1
    assert receipts[0][0] == receipt_id
    assert receipts[0][1] == commerce_id
    assert receipts[0][2] == "2024-03-22"

    # Check Products & Aliases
    cursor.execute("SELECT name, aka FROM products ORDER BY name ASC")
    products = cursor.fetchall()
    assert len(products) == 2
    # Alphabetical order: Latte, Pane
    assert products[0][0] == "Latte"
    latte_aka = json.loads(products[0][1])
    assert "Llet" in latte_aka

    assert products[1][0] == "Pane"
    pane_aka = json.loads(products[1][1])
    assert "Pan rústic" in pane_aka
    assert "Pan baguette" in pane_aka

    # Check Receipt lines (should be 3)
    cursor.execute("SELECT receipt_id, total_price FROM receipt_lines")
    lines = cursor.fetchall()
    assert len(lines) == 3
    prices = [l[1] for l in lines]
    assert 2.20 in prices
    assert 0.80 in prices
    assert 2.40 in prices

    conn.close()
