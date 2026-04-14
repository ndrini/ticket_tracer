import pytest
import os
import sqlite3
from unittest.mock import patch
import cv2

from app.db.db_manager import init_db
from app.etl.etl_engine import ReceiptPipeline
from app.etl.processor import OllamaProcessor
from app.db.inserter import insert_receipt_data

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ticket_e2e.db"
    init_db(str(db_file))
    return str(db_file)

def test_full_pipeline_e2e(temp_db):
    """
    Simula l'intero ciclo di vita di un'immagine scontrino:
    1. OCR (PaddleOCR re-utilizzato su real images test)
    2. Modulo Processore LLM (Mockato poichè richiede Ollama locale)
    3. Inserimento nel DB (Sqlite temporeaneo)
    """
    # 1. Pipeline OCR
    pipeline = ReceiptPipeline()
    debug_dir = os.path.join(
        os.path.dirname(__file__), "..", "data", "test", "cropped"
    )
    img_path = os.path.join(debug_dir, "crop_2025-many_brown_table.jpeg_0.jpg")
    
    if not os.path.exists(img_path):
        pytest.skip(f"Immagine mancante {img_path}")
        
    img = cv2.imread(img_path)
    ocr_lines = pipeline._run_single_ocr(img)
    
    assert len(ocr_lines) > 0, "OCR fallito, nessuna linea trovata"
    
    # 2. Modulo Processore LLM
    processor = OllamaProcessor(model_name="dummy")
    
    # Mocking Ollama (ipotizzando che il prompt LLM riesca ad estrarre correttamente)
    mock_json = '{"shop_name": "Ecoveritas", "date": "2024-03-22", "total": 5.40, "items": [{"name": "Pane", "original_name": "Farina de blat", "price": 2.20}]}'
    
    with patch("app.etl.processor.ollama.chat") as mock_chat:
        mock_chat.return_value = {"message": {"content": mock_json}}
        
        receipt_data = processor.process_receipt_text(ocr_lines)
    
    # 3. Inserimento nel DB
    receipt_id = insert_receipt_data(temp_db, receipt_data)
    
    # Verifica Finale
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id_commerce, data_ora FROM receipts WHERE id = ?", (receipt_id,))
    receipt = cursor.fetchone()
    assert receipt is not None
    assert receipt[1] == "2024-03-22"
    
    cursor.execute("SELECT name, aka FROM products")
    products = cursor.fetchall()
    assert len(products) == 1
    assert products[0][0] == "Pane"
    assert "Farina de blat" in products[0][1]
    
    conn.close()
