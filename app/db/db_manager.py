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
        CREATE TABLE IF NOT EXISTS commerce_type (
            id INTEGER PRIMARY KEY,
            name TEXT,
            gender TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS commerces (
            id INTEGER PRIMARY KEY,
            name  TEXT,
            address TEXT,
            commerce_type INTEGER,
            FOREIGN KEY(commerce_type) REFERENCES commerce_type(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            aka ARRAY,
            -- Senza questa colonna il report per tipologia e' impossibile.
            -- Si popola in una fase successiva, sul catalogo dei prodotti
            -- distinti e non riga per riga: chiedendo la categoria a ogni
            -- riga, lo stesso pane finirebbe in "Pane" su uno scontrino e in
            -- "Alimentari" su un altro.
            category TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY,
            id_commerce INTEGER,
            data_ora TEXT,
            immagine BLOB,
            -- Identita' dello scontrino: l'hash del suo ritaglio. UNIQUE rende
            -- il caricamento idempotente, cosi' rilanciarlo non duplica nulla.
            image_sha256 TEXT UNIQUE,
            -- Il totale stampato sulla carta e quello ricavato dalle righe: la
            -- loro differenza dice quanto ci si puo' fidare di questo record.
            total_declared REAL,
            total_computed REAL,
            validation_status TEXT,
            validation_delta REAL,
            foto_origine TEXT,
            extraction_method TEXT DEFAULT 'llm',
            FOREIGN KEY(id_commerce) REFERENCES commerces(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS receipt_lines (
            id INTEGER PRIMARY KEY,
            receipt_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unity_price REAL,
            unit char,
            total_price REAL,
            extraction_method TEXT DEFAULT 'llm',
            name_quality TEXT DEFAULT NULL,
            FOREIGN KEY(receipt_id) REFERENCES receipts(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    """
    )

    # # Dictionary Table for multilingual support and aliases
    # cursor.execute(
    #     """
    #     CREATE TABLE IF NOT EXISTS product_dictionary (
    #         raw_text TEXT PRIMARY KEY,
    #         standard_name TEXT,
    #         category TEXT,
    #         language TEXT
    #     )
    # """
    # )

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
        "commerce_type",
        "commerces",
        "products",
        "receipts",
        "receipt_lines",
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


def insert_product(db_path, standard_name, aka_list: list[str]):
    """Inserts a new product into the products table. The aka_list allows us to store multiple aliases for the same product.
    For example, "Joghurt" and "Jogurt" can both be stored as aliases for "Yogurt".

    If the product already exists (based on standard_name), we can update the aka_list to include any new aliases without creating duplicate entries.
    """

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # search for existing product by standard_name
    cursor.execute(
        """
        SELECT aka FROM products WHERE name = ?
    """,
        (standard_name,),
    )
    existing_aka = cursor.fetchone()
    if existing_aka:
        existing_aka_list = json.loads(existing_aka[0])
        for item in aka_list:
            if item not in existing_aka_list:
                existing_aka_list.append(item)
        aka_list = existing_aka_list

    # insert or update product

    cursor.execute(
        """
        INSERT OR REPLACE INTO products (name, aka)
        VALUES (?, ?)
    """,
        (standard_name, json.dumps(aka_list)),
    )

    conn.commit()
    conn.close()


# def update_product_aka_value(db_path, standard_name, new_alias):
#     """
#     Add another alias for the same product in the dictionary. This allows us to have multiple raw_text entries mapping to the same standard_name.
#     For example, "Joghurt" and "Jogurt" can both map to "Yogurt".
#     """
#     conn = sqlite3.connect(db_path)
#     cursor = conn.cursor()

#     cursor.execute(
#         """
#         INSERT OR REPLACE INTO products (standard_name, aka)
#         VALUES (?, ?, ?, ?)
#     """,
#         (standard_name, aka_list),
#     )

#     conn.commit()
#     conn.close()
#     conn.close()
