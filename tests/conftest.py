# tests/conftest.py

import pytest

from app.etl.etl_engine import ReceiptPipeline


@pytest.fixture(scope="session")
def receipt_pipeline():
    """
    Inizializza la ReceiptPipeline una sola volta per sessione di test
    per evitare di ricaricare i pesanti modelli OCR a ogni test.
    """
    return ReceiptPipeline()
