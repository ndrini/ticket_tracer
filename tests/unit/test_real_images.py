# tests/test_real_images.py

import os

import cv2
import pytest


# Real images + a real PaddleOCR pipeline: this is an integration test living
# in tests/unit/. Without the marker it blocks the whole suite, because
# importing PaddleOCR reaches out to the model hosters and hangs offline.
pytestmark = pytest.mark.integration


def test_process_real_images_and_debug_crops(receipt_pipeline):
    """
    Questo test itera sulle immagini reali in data/test.
    1. Esegue il ritaglio (cropping).
    2. Salva i ritagli in exports/debug_crops per verifica visiva.
    """
    base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "test")
    debug_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "exports", "debug_crops"
    )
    os.makedirs(debug_dir, exist_ok=True)

    # Trova tutte le immagini jpg/jpeg nella cartella di test
    image_files = [
        f for f in os.listdir(base_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if not image_files:
        pytest.skip("Nessuna immagine trovata in data/test")

    for img_file in image_files:
        full_path = os.path.join(base_dir, img_file)
        print(f"\nProcessing: {img_file}")

        # 1. Testiamo il metodo interno di ritaglio per salvare le immagini di debug
        _, crops = receipt_pipeline.extract_raw_ocr(full_path)

        assert len(crops) > 0, f"Nessuno scontrino rilevato in {img_file}"
        for i, crop in enumerate(crops):
            # Salva il ritaglio su disco
            output_filename = f"crop_{img_file}_{i}.jpg"
            output_path = os.path.join(debug_dir, output_filename)
            written = cv2.imwrite(output_path, crop)
            assert written, f"Impossibile salvare il crop {output_filename}"

        # TODO testiamo che leggendo i ritagli salvati, si estragga il testo atteso
