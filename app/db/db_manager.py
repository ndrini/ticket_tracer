# app/db/database.py

import json
import sqlite3

import yaml


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- New Tables from ER Diagram ---

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shop_type (
            id INTEGER PRIMARY KEY,
            nome TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY,
            nome TEXT,
            indirizzo TEXT,
            id_tipo_punto_vendita INTEGER,
            FOREIGN KEY(id_tipo_punto_vendita) REFERENCES shop_type(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            nome_base TEXT,
            varianti TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            id_punto_vendita INTEGER,
            data_ora TEXT,
            immagine BLOB,
            FOREIGN KEY(id_punto_vendita) REFERENCES shops(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_lines (
            id INTEGER PRIMARY KEY,
            id_scontrino INTEGER,
            id_prodotto INTEGER,
            quantity INTEGER,
            unity_price REAL,
            unit char,
            total_price REAL,
            FOREIGN KEY(id_scontrino) REFERENCES tickets(id),
            FOREIGN KEY(id_prodotto) REFERENCES products(id)
        )
    """
    )

    # Dictionary Table for multilingual support and aliases
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


def seed_db(db_path, yaml_path):
    """Populates the database with data present in the YAML file."""
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Insertion order to respect Foreign Keys
    tables = [
        "shop_type",
        "shops",
        "products",
        "tickets",
        "ticket_lines",
    ]

    for table in tables:
        if table in data:
            rows = data[table]
            for row in rows:
                columns = ", ".join(row.keys())
                placeholders = ", ".join(["?"] * len(row))
                values = [
                    json.dumps(v) if isinstance(v, (list, dict)) else v
                    for v in row.values()
                ]
                sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
                cursor.execute(sql, values)

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
    conn.close()


def update_product_aka_value(db_path, raw_text, standard_name, category, language):
    """
    Add another alias for the same product in the dictionary. This allows us to have multiple raw_text entries mapping to the same standard_name.
    For example, "Joghurt" and "Jogurt" can both map to "Yogurt".
    """
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
    conn.close()
