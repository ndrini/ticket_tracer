import sqlite3
import datetime
import json
from app.db.db_manager import insert_product

def insert_receipt_data(db_path: str, receipt_data: dict, image_blob: bytes = None):
    """
    Inserisce i dati processati dall'LLM nel database SQLite.
    receipt_data è il JSON strutturato restituito da OllamaProcessor.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Trova o crea il commerce
        shop_name = receipt_data.get("shop_name", "Unknown")
        cursor.execute("SELECT id FROM commerces WHERE name = ?", (shop_name,))
        commerce_row = cursor.fetchone()
        
        if commerce_row:
            id_commerce = commerce_row[0]
        else:
            # Crea nuovo commerce (commerce_type rimarrà NULL)
            cursor.execute("INSERT INTO commerces (name, address) VALUES (?, ?)", (shop_name, ""))
            id_commerce = cursor.lastrowid
            
        # 2. Crea la receipt
        dt_str = receipt_data.get("date")
        if not dt_str:
            dt_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
        cursor.execute("INSERT INTO receipts (id_commerce, data_ora, immagine) VALUES (?, ?, ?)", 
                       (id_commerce, dt_str, image_blob))
        receipt_id = cursor.lastrowid
        
        # 3. Inserisci i `receipt_lines`
        items = receipt_data.get("items", [])
        for item in items:
            standard_name = item.get("name", "Unknown")
            original_name = item.get("original_name", "")
            price = item.get("price", 0.0)
            
            # Logica inline per inserimento prodotto (evita lock su db_pass a causa di un'altra connessione in insert_product)
            cursor.execute("SELECT aka FROM products WHERE name = ?", (standard_name,))
            existing_aka = cursor.fetchone()
            
            aka_list = [original_name] if original_name else []
            if existing_aka and existing_aka[0]:
                existing_aka_list = json.loads(existing_aka[0])
                for a in aka_list:
                    if a not in existing_aka_list:
                        existing_aka_list.append(a)
                aka_list = existing_aka_list
            
            cursor.execute("INSERT OR REPLACE INTO products (name, aka) VALUES (?, ?)", (standard_name, json.dumps(aka_list)))
            
            # Subito dopo salviamo il product id che serve su receipt_lines
            cursor.execute("SELECT id FROM products WHERE name = ?", (standard_name,))
            prod_row = cursor.fetchone()
            
            if prod_row:
                product_id = prod_row[0]
                # Inserisci riga: qui default su quantity 1 (nell'LLM basterebbe aggiungere estrazione quantity se si complica)
                cursor.execute(
                    "INSERT INTO receipt_lines (receipt_id, product_id, quantity, unity_price, total_price) VALUES (?, ?, ?, ?, ?)",
                    (receipt_id, product_id, 1, price, price)
                )
        
        conn.commit()
        return receipt_id
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
