# tests/test_db.py

import json
import os
import sqlite3

import pytest

from app.db.db_manager import init_db, insert_product, seed_db


def test_database_creation():
    db_path = "data/test_spese.db"
    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Remove the test db if it already exists
    if os.path.exists(db_path):
        os.remove(db_path)

    # Initialize the database
    init_db(db_path)
    assert os.path.exists(db_path)


def test_insert_and_map_product():
    db_path = "data/test_spese.db"
    # Ensure the DB is initialized
    init_db(db_path)

    # Test if the system correctly saves a product with aliases
    insert_product(db_path, "Yogurt", ["Joghurt", "Jogurt"])

    # Verification
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, aka FROM products WHERE name = ?",
        ("Yogurt",),
    )
    result = cursor.fetchone()
    conn.close()

    assert result == (
        "Yogurt",
        json.dumps(["Joghurt", "Jogurt"]),
    ), "Product alias mapping failed"


def test_db_schema_integrity():
    db_path = "data/test_spese.db"
    # Initialize the DB to ensure tables exist
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verify the presence of new tables
    tables_to_check = [
        "shop_type",
        "shops",
        "products",
        "tickets",
        "ticket_lines",
    ]

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row[0] for row in cursor.fetchall()]

    for table in tables_to_check:
        assert table in existing_tables, f"Missing table: {table}"

    conn.close()


def test_seed_db():
    db_path = "data/test_spese.db"
    yaml_path = "data/test_data.yaml"

    init_db(db_path)
    seed_db(db_path, yaml_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT count(*) FROM shops")
    count = cursor.fetchone()[0]
    assert count > 0, "Seeding did not insert data into the shops table"


#     conn.close()
#     conn.close()


# def test_update_product_aka_value():
#     db_path = "data/test_spese.db"
#     yaml_path = "data/test_data.yaml"

#     init_db(db_path)
#     seed_db(db_path, yaml_path)

#     conn = sqlite3.connect(db_path)
#     cursor = conn.cursor()
#     # Update the product alias
#     update_product_aka_value(db_path, "Joghurt", "Yogurt", "Alimentari", "DE")

#     # Verify the update
#     cursor.execute(
#         "SELECT standard_name FROM product_dictionary WHERE raw_text = ?", ("Joghurt",)
#     )
#     result = cursor.fetchone()
#     conn.close()

#     assert result == ("Yogurt",), "Product alias update failed"
#     assert result == ("Yogurt",), "Product alias update failed"
#     assert result == ("Yogurt",), "Product alias update failed"
#     assert result == ("Yogurt",), "Product alias update failed"
#     assert result == ("Yogurt",), "Product alias update failed"
