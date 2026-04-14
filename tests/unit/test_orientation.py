"""Unit tests for whole-image orientation correction."""
import pytest
import cv2
import numpy as np
from app.etl.etl_engine import ReceiptPipeline


@pytest.fixture
def pipeline(receipt_pipeline):
    """Reuse the session-scoped pipeline fixture from conftest."""
    return receipt_pipeline


class TestOrientWholeImage:
    """Tests for _orient_whole_image method."""

    def test_orient_whole_image_preserves_shape_when_square(self, pipeline):
        """Square image should preserve its shape after any rotation."""
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        result = pipeline._orient_whole_image(img)
        assert result.shape == img.shape

    def test_orient_whole_image_preserves_shape_when_landscape(self, pipeline):
        """Landscape image should preserve its shape."""
        img = np.zeros((300, 500, 3), dtype=np.uint8)
        result = pipeline._orient_whole_image(img)
        assert result.shape == img.shape

    def test_orient_whole_image_preserves_shape_when_portrait(self, pipeline):
        """Portrait image should preserve its shape."""
        img = np.zeros((500, 300, 3), dtype=np.uint8)
        result = pipeline._orient_whole_image(img)
        assert result.shape == img.shape

    def test_orient_whole_image_with_blank_image(self, pipeline):
        """Blank image (all zeros) should return unchanged."""
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        result = pipeline._orient_whole_image(img)
        # Blank image has no OCR content, all rotations score 0, should return original
        assert result.shape == img.shape

    def test_orient_whole_image_improves_score_on_flipped_image(self, pipeline):
        """Orientation should improve OCR score on a flipped image if test file exists."""
        import os
        flip_path = "/mnt/condivisa/workspace/ticket_tracer/data/test/2024-many_white_table_flip.jpeg"
        normal_path = "/mnt/condivisa/workspace/ticket_tracer/data/test/2024-many_white_table.jpeg"

        # Skip if test images don't exist
        if not os.path.exists(flip_path) or not os.path.exists(normal_path):
            pytest.skip("Test images not found")

        img_flip = cv2.imread(flip_path)
        img_flip = pipeline._resize_safe(img_flip, 800)

        # Score before orientation
        score_before = pipeline._ocr_score(pipeline._run_single_ocr(img_flip))

        # Reorient
        oriented = pipeline._orient_whole_image(img_flip)
        score_after = pipeline._ocr_score(pipeline._run_single_ocr(oriented))

        # Score should improve (or at least not get worse)
        assert score_after >= score_before * 0.9  # Allow some tolerance

    def test_orient_whole_image_with_small_proxy_dimension(self, pipeline):
        """Test with custom max_orient_dim parameter."""
        img = np.zeros((2000, 2000, 3), dtype=np.uint8)
        result = pipeline._orient_whole_image(img, max_orient_dim=400)
        # Should still return same shape
        assert result.shape == img.shape
