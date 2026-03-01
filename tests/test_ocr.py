# tests/test_ocr.py

import os

import pytest

from app.etl.etl_engine import ReceiptPipeline


def test_pipeline_structure():
    """
    Testa che la pipeline sia inizializzata correttamente e che
    la struttura dei dati in uscita sia compatibile con il database.
    Non esegue vero OCR per velocità, ma verifica il contratto dell'interfaccia.
    """
    pipeline = ReceiptPipeline()

    # Simuliamo un output grezzo dell'OCR (lista di box e testi)
    # Formato PaddleOCR tipico: [[[x,y], [x,y]...], ("testo", confidenza)]
    mock_ocr_result = [
        [[[10, 10], [50, 10], [50, 20], [10, 20]], ("Esselunga", 0.99)],
        [[[10, 50], [100, 50], [100, 60], [10, 60]], ("Latte UHT", 0.95)],
        [[[200, 50], [250, 50], [250, 60], [200, 60]], ("1.50", 0.98)],
        [[[10, 100], [50, 100], [50, 110], [10, 110]], ("TOTALE", 0.99)],
        [[[200, 100], [250, 100], [250, 110], [200, 110]], ("1.50", 0.99)],
    ]

    # Simuliamo il passaggio di parsing (che normalmente farebbe l'LLM)
    # Qui testiamo la logica di assemblaggio finale
    parsed_data = pipeline.parse_raw_data(mock_ocr_result)

    # Asserzioni sulla struttura
    assert "shop_name" in parsed_data
    assert "total" in parsed_data
    assert "date" in parsed_data
    assert "items" in parsed_data
    assert isinstance(parsed_data["items"], list)

    # Verifica che i dati simulati siano stati catturati (logica di base)
    # Nota: Senza LLM attivo, questo test verificherà solo che la funzione esista e ritorni un dict
    assert isinstance(parsed_data, dict)
    # Nota: Senza LLM attivo, questo test verificherà solo che la funzione esista e ritorni un dict
    assert isinstance(parsed_data, dict)
