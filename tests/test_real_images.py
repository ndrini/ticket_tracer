# tests/test_real_images.py

import os

import cv2
import pytest


def test_process_real_images_and_debug_crops(receipt_pipeline):
    """
    Questo test itera sulle immagini reali in data/test.
    1. Esegue il ritaglio (cropping).
    2. Salva i ritagli in exports/debug_crops per verifica visiva.
    """
    base_dir = "data/test"
    debug_dir = "exports/debug_crops"
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
        crops = receipt_pipeline._detect_and_crop_receipts(full_path)

        assert len(crops) > 0, f"Nessuno scontrino rilevato in {img_file}"

        for i, crop in enumerate(crops):
            # Salva il ritaglio su disco
            output_filename = f"crop_{img_file}_{i}.jpg"
            output_path = os.path.join(debug_dir, output_filename)
            cv2.imwrite(output_path, crop)
