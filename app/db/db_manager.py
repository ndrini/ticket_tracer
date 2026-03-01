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
            name TEXT,
            aka ARRAY
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            id_commerce INTEGER,
            data_ora TEXT,
            immagine BLOB,
            FOREIGN KEY(id_commerce) REFERENCES commerces(id)
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
