# tests/test_db.py

import os
import sqlite3

import pytest

from app.db.database import init_db, insert_product


def test_database_creation():
    db_path = "data/test_spese.db"
    # Assicuriamoci che la directory esista
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Rimuoviamo il db di test se esiste già
    if os.path.exists(db_path):
        os.remove(db_path)

    # Inizializziamo il database
    init_db(db_path)
    assert os.path.exists(db_path)


def test_insert_and_map_product():
    db_path = "data/test_spese.db"
    # Assicuriamoci che il DB sia inizializzato
    init_db(db_path)

    # Testiamo se il sistema salva correttamente un alias multilingua
    insert_product(db_path, "Joghurt", "Yogurt", "Alimentari", "DE")

    # Verifica
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT standard_name, category, language FROM product_dictionary WHERE raw_text = ?",
        ("Joghurt",),
    )
    result = cursor.fetchone()
    conn.close()

    assert result == ("Yogurt", "Alimentari", "DE")


def test_db_schema_integrity():
    db_path = "data/test_spese.db"
    # Inizializziamo il DB per assicurarci che le tabelle esistano
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verifichiamo la tabella 'purchases'
    cursor.execute("PRAGMA table_info(purchases)")
    columns = [column[1] for column in cursor.fetchall()]

    expected_columns = [
        "id",
        "date",
        "store",
        "raw_name",
        "standard_name",
        "category",
        "price",
        "language",
    ]

    for col in expected_columns:
        assert col in columns, f"Colonna mancante nella tabella purchases: {col}"

    # Verifichiamo la tabella 'product_dictionary'
    cursor.execute("PRAGMA table_info(product_dictionary)")
    dict_columns = [column[1] for column in cursor.fetchall()]

    assert "raw_text" in dict_columns
    assert "standard_name" in dict_columns

    conn.close()
