# app/db/database.py

import sqlite3


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Tabella principale per le statistiche
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            store TEXT,
            raw_name TEXT,
            standard_name TEXT,
            category TEXT,
            price REAL,
            language TEXT
        )
    """
    )

    # Tabella Dizionario per il multilingua e alias
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_dictionary (
            raw_text TEXT PRIMARY KEY,
            standard_name TEXT,
            category TEXT,
            language TEXT
        )
    """
    )

    conn.commit()
    conn.close()


def insert_product(db_path, raw_text, standard_name, category, language):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO product_dictionary (raw_text, standard_name, category, language)
        VALUES (?, ?, ?, ?)
    """,
        (raw_text, standard_name, category, language),
    )

    conn.commit()
    conn.close()
