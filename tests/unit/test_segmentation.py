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


def _receipt_with_text(img, x0, y0, x1, y1, line_step=14):
    """Paint a light receipt carrying dark horizontal text lines."""
    img[y0:y1, x0:x1] = (245, 245, 245)
    for y in range(y0 + 10, y1 - 8, line_step):
        img[y:y + 4, x0 + 12:x1 - 12] = (30, 30, 30)
    return img


class TestSegmentByTextDensity:
    """
    Tests for _segment_by_text_density, the method that replaced colour as the
    primary signal. See section 5 of the plan for the measurements behind it.
    """

    def test_finds_receipt_on_light_background(self, pipeline):
        """
        The case colour could not handle: a light receipt on a LIGHT background.
        Saturation cannot separate them; text density can.
        """
        img = np.full((600, 400, 3), 235, dtype=np.uint8)  # light background
        _receipt_with_text(img, 80, 60, 320, 520)

        result = pipeline._segment_by_text_density(img)

        assert result.confident
        assert len(result) >= 1
        biggest = result[0]
        coverage = (biggest.shape[0] * biggest.shape[1]) / float(600 * 400)
        assert coverage < WHOLE_FRAME_AREA_FRAC, (
            f"text block covers {coverage:.0%} of the frame: morphology glued "
            "everything together, the defect this method exists to avoid"
        )

    def test_separates_two_receipts(self, pipeline):
        img = np.full((700, 400, 3), 235, dtype=np.uint8)
        _receipt_with_text(img, 60, 40, 340, 290)
        _receipt_with_text(img, 60, 420, 340, 660)

        result = pipeline._segment_by_text_density(img)

        assert result.confident
        assert len(result) >= 2

    def test_blank_image_is_not_confident(self, pipeline):
        """No text at all: a failure, and it must say so."""
        img = np.full((400, 300, 3), 200, dtype=np.uint8)

        result = pipeline._segment_by_text_density(img)

        assert not result.confident
        assert result.reason
        assert result.method == "text_density"

    def test_result_is_a_segmentation_result(self, pipeline):
        img = np.full((400, 300, 3), 235, dtype=np.uint8)
        _receipt_with_text(img, 50, 40, 250, 360)

        result = pipeline._segment_by_text_density(img)

        assert isinstance(result, SegmentationResult)
        assert result.method == "text_density"


class TestSegmentReceiptsUsesTextDensity:
    """_segment_receipts must prefer text density and keep colour as fallback."""

    def test_text_density_is_the_primary_method(self, pipeline):
        img = np.full((600, 400, 3), 235, dtype=np.uint8)
        _receipt_with_text(img, 80, 60, 320, 520)

        with patch.object(pipeline, '_get_vision_count', return_value=1):
            result = pipeline._segment_receipts(img, "dummy.jpg")

        assert result.method == "text_density"

    def test_falls_back_to_colour_when_text_density_fails(self, pipeline):
        """A blank image defeats text density; colour is then attempted."""
        img = _two_receipts_on_saturated_background()

        with patch.object(
            pipeline, '_segment_by_text_density',
            return_value=SegmentationResult(
                crops=[img], method="text_density", confident=False, reason="forced"
            ),
        ):
            with patch.object(pipeline, '_get_vision_count', return_value=2):
                result = pipeline._segment_receipts(img, "dummy.jpg")

        assert result.method == "color_islands"


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
