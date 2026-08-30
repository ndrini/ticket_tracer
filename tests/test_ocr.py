# tests/test_ocr.py

import pytest


# PaddleOCR's shape: [[corner points], (text, confidence)].
# Two words on the same line (y=50) plus a header and a total.
MOCK_OCR = [
    [[[10, 10], [50, 10], [50, 20], [10, 20]], ("Esselunga", 0.99)],
    [[[10, 50], [100, 50], [100, 60], [10, 60]], ("Latte UHT", 0.95)],
    [[[200, 50], [250, 50], [250, 60], [200, 60]], ("1.50", 0.98)],
    [[[10, 100], [50, 100], [50, 110], [10, 110]], ("TOTALE", 0.99)],
    [[[200, 100], [250, 100], [250, 110], [200, 110]], ("1.50", 0.99)],
]


def test_parse_raw_data_restituisce_una_riga_per_riga_visiva(receipt_pipeline):
    """The contract: fragments in, one string per visual line out.

    This test used to assert a dict with shop_name/total/date/items. That was a
    stale contract: the function returns reconstructed text, and its only caller
    (etl_engine.py, process_image) treats it as a list. The old assertion still
    "worked" because `"shop_name" in [...]` is a valid membership test on a
    list — it just answered a different question, and hid the real defect.
    """
    righe = receipt_pipeline.parse_raw_data(MOCK_OCR)

    assert isinstance(righe, list)
    assert all(isinstance(r, str) for r in righe)
    assert righe == ["Esselunga", "Latte UHT 1.50", "TOTALE 1.50"]


def test_i_frammenti_sulla_stessa_riga_si_uniscono_da_sinistra(receipt_pipeline):
    """Fragments sharing a y-centre become one line, ordered by x."""
    righe = receipt_pipeline.parse_raw_data(MOCK_OCR)

    assert "Latte UHT 1.50" in righe, "nome e prezzo devono stare sulla stessa riga"
    assert "1.50 Latte UHT" not in righe, "l'ordine orizzontale non e' rispettato"


def test_ocr_vuoto_restituisce_una_lista_vuota(receipt_pipeline):
    """The branch that was broken.

    It returned {"shop_name": "Unknown", "date": None, "total": 0.0,
    "items": []} — a leftover of an older contract. An unreadable photo then
    handed the caller a mapping where it expects lines of text, and the damage
    showed up much later as a receipt called "Unknown" with no items.
    """
    assert receipt_pipeline.parse_raw_data([]) == []
    assert receipt_pipeline.parse_raw_data(None) == []


def test_il_tipo_di_ritorno_e_lo_stesso_sui_due_rami(receipt_pipeline):
    """One function, one return type. Guards the defect from coming back."""
    pieno = receipt_pipeline.parse_raw_data(MOCK_OCR)
    vuoto = receipt_pipeline.parse_raw_data([])

    assert type(pieno) is type(vuoto) is list
