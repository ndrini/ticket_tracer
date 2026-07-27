"""Unit tests for receipt segmentation.

Rewritten for the current API: _segment_by_projection was removed in b977871
and replaced by _segment_by_color_islands. These tests assert the FASE 0
contract from private/2026-07-26_PIANO_ESTRAZIONE.md — a failed segmentation
must be distinguishable from a genuine single receipt.
"""
import numpy as np
import pytest
from unittest.mock import patch

from app.etl.etl_engine import ReceiptPipeline, SegmentationResult, WHOLE_FRAME_AREA_FRAC


@pytest.fixture
def pipeline(receipt_pipeline):
    """Reuse the session-scoped pipeline fixture from conftest."""
    return receipt_pipeline


def _two_receipts_on_saturated_background(h=600, w=400):
    """
    Synthetic image matching the algorithm's premise: two desaturated (light)
    receipts on a saturated background. Built in BGR so that the background is
    strongly coloured and the receipts are near-white.
    """
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (20, 90, 200)  # saturated orange-brown background
    img[50:250, 60:340] = (245, 245, 245)  # receipt 1
    img[350:550, 60:340] = (245, 245, 245)  # receipt 2
    return img


def _single_receipt_on_saturated_background(h=600, w=400):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (20, 90, 200)
    img[80:520, 60:340] = (245, 245, 245)
    return img


class TestSegmentationResult:
    """The result type must stay usable where a plain list was used before."""

    def test_result_behaves_like_a_list(self):
        crops = [np.zeros((10, 10, 3), dtype=np.uint8)] * 2
        res = SegmentationResult(crops=crops, method="test", confident=True)

        assert len(res) == 2
        assert res[0].shape == (10, 10, 3)
        assert len(list(res)) == 2


class TestSegmentByColorIslands:
    """Tests for _segment_by_color_islands."""

    def test_splits_two_receipts_on_saturated_background(self, pipeline):
        """When the premise holds, the two receipts are separated confidently."""
        img = _two_receipts_on_saturated_background()

        result = pipeline._segment_by_color_islands(img, min_area_frac=0.05)

        assert len(result) == 2
        assert result.confident
        for crop in result:
            assert crop.shape[0] > 0 and crop.shape[1] > 0

    def test_single_receipt_is_confident(self, pipeline):
        """One receipt that does not fill the frame is a real result."""
        img = _single_receipt_on_saturated_background()

        result = pipeline._segment_by_color_islands(img, min_area_frac=0.05)

        assert len(result) == 1
        assert result.confident

    def test_whole_frame_island_is_not_confident(self, pipeline):
        """
        Regression test for F1: a uniformly light image makes every pixel pass
        the saturation mask, so the single 'island' is the whole frame. That is
        a failure and must be reported as one, not returned as a crop.
        """
        img = np.full((600, 400, 3), 240, dtype=np.uint8)

        result = pipeline._segment_by_color_islands(img, min_area_frac=0.05)

        assert len(result) == 1
        assert not result.confident
        assert "frame" in result.reason

    def test_empty_image_is_not_confident(self, pipeline):
        """A black image yields no island: failure, reported as such."""
        img = np.zeros((400, 200, 3), dtype=np.uint8)

        result = pipeline._segment_by_color_islands(img)

        assert len(result) >= 1
        assert not result.confident
        assert result.reason

    def test_min_area_frac_controls_sensitivity(self, pipeline):
        """A lower threshold admits islands a higher one rejects."""
        img = _two_receipts_on_saturated_background()

        relaxed = pipeline._segment_by_color_islands(img, min_area_frac=0.02)
        strict = pipeline._segment_by_color_islands(img, min_area_frac=0.9)

        assert len(relaxed) >= len(strict)
        assert not strict.confident  # nothing survives a 90% area threshold


class TestGetVisionCount:
    """The VLM must not answer '1' when it cannot answer at all."""

    def test_returns_none_when_vlm_unavailable(self, pipeline, tmp_path):
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"not-a-real-image")

        with patch("app.etl.etl_engine.ollama.chat", side_effect=RuntimeError("no model")):
            count = pipeline._get_vision_count(str(img_file))

        assert count is None, "unavailable VLM must be None, never 1"

    def test_returns_none_on_unparseable_reply(self, pipeline, tmp_path):
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"not-a-real-image")

        reply = {'message': {'content': 'I cannot tell'}}
        with patch("app.etl.etl_engine.ollama.chat", return_value=reply):
            count = pipeline._get_vision_count(str(img_file))

        assert count is None

    def test_parses_count_from_reply(self, pipeline, tmp_path):
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"not-a-real-image")

        reply = {'message': {'content': 'There are 3 receipts'}}
        with patch("app.etl.etl_engine.ollama.chat", return_value=reply):
            count = pipeline._get_vision_count(str(img_file))

        assert count == 3


class TestSegmentReceipts:
    """Tests for _segment_receipts (CV + VLM arbitration)."""

    def test_cv_finds_multiple_vlm_not_consulted(self, pipeline):
        """When CV splits confidently, the VLM is not needed."""
        img = _two_receipts_on_saturated_background()

        with patch.object(pipeline, '_get_vision_count', return_value=1) as mock_vlm:
            result = pipeline._segment_receipts(img, "dummy.jpg")

        assert len(result) == 2
        mock_vlm.assert_not_called()

    def test_single_receipt_confirmed_by_vlm(self, pipeline):
        img = _single_receipt_on_saturated_background()

        with patch.object(pipeline, '_get_vision_count', return_value=1):
            result = pipeline._segment_receipts(img, "dummy.jpg")

        assert len(result) == 1
        assert result.confident
        assert result.vision_count == 1

    def test_unavailable_vlm_does_not_confirm(self, pipeline):
        """
        Regression test for F3: with no model installed the VLM used to return 1,
        silently 'agreeing' with CV. Now it returns None and the result carries
        a warning that the single-receipt outcome is unverified.
        """
        img = _single_receipt_on_saturated_background()

        with patch.object(pipeline, '_get_vision_count', return_value=None):
            result = pipeline._segment_receipts(img, "dummy.jpg")

        assert result.vision_count is None
        assert any("unverified" in w for w in result.warnings)

    def test_failed_split_reports_disagreement(self, pipeline):
        """
        CV cannot split but the VLM insists on several receipts: the recovery
        path runs and, if it also fails, the result says so.
        """
        img = np.full((600, 400, 3), 240, dtype=np.uint8)  # whole-frame failure

        with patch.object(pipeline, '_get_vision_count', return_value=2), \
             patch.object(pipeline, '_segment_receipts_ocr_guided', return_value=[img]):
            result = pipeline._segment_receipts(img, "dummy.jpg")

        assert not result.confident
        assert result.vision_count == 2
        assert "2" in result.reason


class TestWholeFrameThreshold:
    def test_threshold_is_a_sane_fraction(self):
        assert 0.5 < WHOLE_FRAME_AREA_FRAC < 1.0
