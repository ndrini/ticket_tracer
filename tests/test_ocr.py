# tests/test_ocr.py

import pytest

from app.etl.etl_engine import process_receipt


def test_process_simple_receipt():
    # Prepare a sample receipt (even a small cropped image)
    image_path = "tests/fixtures/sample_receipt.jpg"

    # This will definitely fail because process_receipt does not exist yet!
    data = process_receipt(image_path)

    assert "store" in data
    assert float(data["total"]) > 0
    assert len(data["items"]) > 0
    assert float(data["total"]) > 0
    assert len(data["items"]) > 0
