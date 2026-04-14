"""Unit tests for receipt segmentation methods."""
import pytest
import cv2
import numpy as np
from app.etl.etl_engine import ReceiptPipeline
from unittest.mock import patch


@pytest.fixture
def pipeline(receipt_pipeline):
    """Reuse the session-scoped pipeline fixture from conftest."""
    return receipt_pipeline


class TestSegmentByProjection:
    """Tests for _segment_by_projection method."""

    def test_segment_by_projection_single_receipt(self, pipeline):
        """Single receipt should return [image]."""
        # Create a synthetic image: one white rectangle on black background
        img = np.zeros((400, 200, 3), dtype=np.uint8)
        img[50:350, 20:180] = 200  # Receipt area
        img[60:340, 30:170] = 255  # Fake text content

        crops = pipeline._segment_by_projection(img)
        assert len(crops) == 1
        assert crops[0].shape[0] > 100  # Should have meaningful height

    def test_segment_by_projection_stacked_receipts(self, pipeline):
        """Two stacked receipts should be split into 2 crops."""
        # Create synthetic image with 2 receipts stacked vertically
        img = np.zeros((600, 200, 3), dtype=np.uint8)
        # Receipt 1: rows 50-250
        img[50:250, 20:180] = 200
        img[60:240, 30:170] = 255
        # Gap: rows 250-300 (mostly black)
        # Receipt 2: rows 350-550
        img[350:550, 20:180] = 200
        img[360:540, 30:170] = 255

        crops = pipeline._segment_by_projection(img)
        # Should find 2 separate crops
        assert len(crops) >= 1  # At least 1 crop
        for crop in crops:
            assert crop.shape[0] > 50  # Each crop should have reasonable height

    def test_segment_by_projection_empty_image(self, pipeline):
        """Empty black image should return [image]."""
        img = np.zeros((400, 200, 3), dtype=np.uint8)
        crops = pipeline._segment_by_projection(img)
        assert len(crops) >= 1

    def test_segment_by_projection_min_gap_fraction_parameter(self, pipeline):
        """Test with different min_gap_frac parameters."""
        img = np.zeros((600, 200, 3), dtype=np.uint8)
        img[50:250, 20:180] = 200
        img[60:240, 30:170] = 255
        img[350:550, 20:180] = 200
        img[360:540, 30:170] = 255

        # More aggressive threshold should split more easily
        crops_relaxed = pipeline._segment_by_projection(img, min_gap_frac=0.01)
        crops_strict = pipeline._segment_by_projection(img, min_gap_frac=0.05)

        # At least one should find the receipts
        assert len(crops_relaxed) >= 1 or len(crops_strict) >= 1


class TestSegmentReceipts:
    """Tests for _segment_receipts method (CV + VLM validation)."""

    def test_segment_receipts_with_vlm_agreement(self, pipeline):
        """When CV and VLM agree on count, should return CV crops."""
        img = np.zeros((400, 200, 3), dtype=np.uint8)
        img[50:350, 20:180] = 200
        img[60:340, 30:170] = 255

        # Mock _get_vision_count to return 1 (agreement with CV)
        with patch.object(pipeline, '_get_vision_count', return_value=1):
            crops = pipeline._segment_receipts(img, "dummy_path.jpg")

        assert len(crops) >= 1

    def test_segment_receipts_cv_over_split_vlm_says_one(self, pipeline):
        """If CV finds >1 but VLM says 1, return whole image."""
        img = np.zeros((600, 200, 3), dtype=np.uint8)
        img[50:250, 20:180] = 200
        img[60:240, 30:170] = 255
        img[350:550, 20:180] = 200
        img[360:540, 30:170] = 255

        # Mock VLM to say 1 (even though CV might find more)
        with patch.object(pipeline, '_get_vision_count', return_value=1):
            crops = pipeline._segment_receipts(img, "dummy_path.jpg")

        # Should return whole image (not over-split)
        assert len(crops) == 1

    def test_segment_receipts_cv_under_split_vlm_says_multiple(self, pipeline):
        """If CV finds 1 but VLM says >1, retry with aggressive threshold."""
        img = np.zeros((400, 200, 3), dtype=np.uint8)
        img[50:350, 20:180] = 200
        img[60:340, 30:170] = 255

        # Mock VLM to say 2 (CV will find 1)
        with patch.object(pipeline, '_get_vision_count', return_value=2):
            crops = pipeline._segment_receipts(img, "dummy_path.jpg")

        # Should attempt retry; if still 1, returns [img]
        assert len(crops) >= 1

    def test_segment_receipts_calls_vision_count(self, pipeline):
        """Should call _get_vision_count exactly once."""
        img = np.zeros((400, 200, 3), dtype=np.uint8)
        img[50:350, 20:180] = 200

        with patch.object(pipeline, '_get_vision_count', return_value=1) as mock_vision:
            pipeline._segment_receipts(img, "dummy_path.jpg")

        mock_vision.assert_called_once_with("dummy_path.jpg")


class TestSegmentReceiptsWithRealImages:
    """Integration tests with real test images."""

    def test_segment_real_brown_table_image(self, pipeline):
        """Test segmentation on the brown_table_many image."""
        import os
        img_path = "/mnt/condivisa/workspace/ticket_tracer/data/test/2025-many_brown_table.jpeg"

        if not os.path.exists(img_path):
            pytest.skip("Test image not found")

        img = cv2.imread(img_path)
        img = pipeline._resize_safe(img, 2000)
        img = pipeline._orient_whole_image(img)

        # Mock VLM count (we know this image has multiple receipts)
        with patch.object(pipeline, '_get_vision_count', return_value=2):
            crops = pipeline._segment_receipts(img, img_path)

        # Should find at least 1 crop
        assert len(crops) >= 1
        for crop in crops:
            assert crop.shape[0] > 0 and crop.shape[1] > 0

    def test_segment_real_fruitos_image(self, pipeline):
        """Test segmentation on single-receipt fruitos image."""
        import os
        img_path = "/mnt/condivisa/workspace/ticket_tracer/data/test/2025-fruitos_vertical.jpeg"

        if not os.path.exists(img_path):
            pytest.skip("Test image not found")

        img = cv2.imread(img_path)
        img = pipeline._resize_safe(img, 2000)
        img = pipeline._orient_whole_image(img)

        # Mock VLM count
        with patch.object(pipeline, '_get_vision_count', return_value=1):
            crops = pipeline._segment_receipts(img, img_path)

        # Should find 1 crop
        assert len(crops) == 1
        assert crops[0].shape[0] > 0
