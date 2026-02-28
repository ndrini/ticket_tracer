# tests/test_ocr.py

import pytest

from app.ocr.ocr_engine import process_receipt


def test_process_simple_receipt():
    # Prepara uno scontrino d'esempio (anche una piccola immagine ritagliata)
    image_path = "tests/fixtures/sample_receipt.jpg"

    # Questo fallirà sicuramente perché process_receipt non esiste ancora!
    # E fallirà anche l'import sopra se il modulo non esiste.
    data = process_receipt(image_path)

    assert "store" in data
    assert float(data["total"]) > 0
    assert len(data["items"]) > 0
    assert float(data["total"]) > 0
    assert len(data["items"]) > 0
