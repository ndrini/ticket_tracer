# tests/test_real_images.py

import os

import cv2
import pytest


def test_cropped_receipt_text_contains_expected_words(receipt_pipeline):
    """Verifica che i crop noti contengano i testi previsti."""
    debug_dir = os.path.join(os.path.dirname(__file__), "..", "exports", "debug_crops")
    crop_paths = [
        os.path.join(debug_dir, "crop_2025-many_brown_table.jpeg_0.jpg"),
        os.path.join(debug_dir, "crop_2025-many_brown_table.jpeg_1.jpg"),
    ]

    missing = [p for p in crop_paths if not os.path.exists(p)]
    if missing:
        pytest.skip(f"Crop mancanti: {missing}")

    expected = ["evoceritas", "e farina de bolar a sensa vluten"]
    found_text = ""
    for p in crop_paths:
        img = cv2.imread(p)
        assert img is not None, f"Impossibile leggere {p}"
        ocr_data = receipt_pipeline._run_ocr(img)
        # Estrai solo i testi
        texts = [tup[1][0] for tup in ocr_data if len(tup) > 1 and len(tup[1]) > 0]
        found_text += " ".join(texts).lower()

    for expected_phrase in expected:
        assert (
            expected_phrase in found_text
        ), f"Non trovato '{expected_phrase}' in crop OCR: {found_text[:200]}..."
