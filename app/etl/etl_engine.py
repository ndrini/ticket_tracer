import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
import ollama
from paddleocr import PaddleOCR
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# A crop covering more than this fraction of the frame is not a segmentation:
# it is the input handed back unchanged. Measured on the DIA reference image,
# where the failing HSV mask produced a single island covering 92% of the frame.
WHOLE_FRAME_AREA_FRAC = 0.85


@dataclass
class SegmentationResult:
    """
    Outcome of a segmentation attempt.

    The point of this type is to make failure visible. Previously a failed
    segmentation returned `[img]`, which is indistinguishable from the legitimate
    "there is exactly one receipt, here it is". Callers could not tell a crop
    from a surrender, so three successive rewrites of the algorithm were judged
    blind. `confident` now carries that distinction explicitly.
    """

    crops: list
    method: str
    confident: bool
    reason: str = ""
    vision_count: Optional[int] = None
    warnings: list = field(default_factory=list)

    def __len__(self):
        # Backwards compatibility: callers still treat the result as a crop list.
        return len(self.crops)

    def __iter__(self):
        return iter(self.crops)

    def __getitem__(self, idx):
        return self.crops[idx]


class ReceiptPipeline:
    def __init__(self, vision_model: str = "moondream:1.8b",
                 quarantine_dir: str = "exports/quarantine"):
        # Vision model used only to count receipts (see _get_vision_count).
        # Kept as a constructor argument so the model name lives in one place
        # instead of being buried in the call site.
        self.vision_model = vision_model

        # Where images the pipeline could not segment are recorded.
        self.quarantine_dir = quarantine_dir

        # Outcome of the most recent segmentation, for callers and tests.
        self.last_segmentation: Optional[SegmentationResult] = None

        # Orientation classifier and text detector, loaded lazily: constructing
        # them costs a few seconds, and callers that never orient an image
        # should not pay that.
        self._doc_ori = None
        self._det_only = None

        # Inizializziamo PaddleOCR.
        self.ocr = PaddleOCR(
            lang="es", 
            enable_mkldnn=False,
            cpu_threads=3,
            use_doc_orientation_classify=False,
            use_textline_orientation=False
        )

    def process_image(self, image_path):
        """Immagine → lista di dati strutturati (uno per scontrino)."""
        receipts_lines, _ = self.extract_raw_ocr(image_path)
        return [self.parse_raw_data(lines) for lines in receipts_lines]

    def _get_vision_count(self, image_path: str) -> Optional[int]:
        """
        Use a VLM to count the separate receipts in the image.

        Returns the count, or None when the VLM could not answer (model missing,
        Ollama unreachable, unparseable reply).

        None is not 1. The previous version collapsed both into 1, which meant
        that with no model installed the "arbiter" silently agreed with whatever
        the CV found — a plausible-looking answer that made the recovery branch
        in _segment_receipts unreachable dead code.
        """
        try:
            with open(image_path, 'rb') as f:
                img_bytes = f.read()

            prompt = "Identify the separate physical receipts or pieces of paper in this image. They might be stacked vertically or overlapping. Answer ONLY with the total count (e.g. 1, 2, 3)."
            res = ollama.chat(model=self.vision_model, messages=[
                {'role': 'user', 'content': prompt, 'images': [img_bytes]}
            ])

            count_str = res['message']['content'].strip()
            import re
            match = re.search(r'\d+', count_str)
            if not match:
                logger.warning("VLM reply not parseable as a count: %r", count_str)
                return None
            return int(match.group())
        except Exception as e:
            # Environment failure, not a receipt-count of 1.
            logger.warning("VLM unavailable (%s): %s", self.vision_model, e)
            return None

    # Rotation that undoes each orientation label reported by the classifier.
    _UNDO_ROTATION = {
        "0": None,
        "90": cv2.ROTATE_90_COUNTERCLOCKWISE,
        "180": cv2.ROTATE_180,
        "270": cv2.ROTATE_90_CLOCKWISE,
    }

    @property
    def _orientation_classifier(self):
        """PP-LCNet document-orientation model, created on first use."""
        if self._doc_ori is None:
            from paddleocr import DocImgOrientationClassification
            self._doc_ori = DocImgOrientationClassification()
        return self._doc_ori

    @property
    def _text_detector(self):
        """Text-line detector alone, without the recognition stage."""
        if self._det_only is None:
            from paddleocr import TextDetection
            # oneDNN raises ConvertPirAttribute2RuntimeAttribute on this build.
            self._det_only = TextDetection(enable_mkldnn=False)
        return self._det_only

    def _orient_whole_image(self, img: np.ndarray, max_orient_dim: int = 800) -> np.ndarray:
        """
        Correct the orientation of the full image (containing one or more receipts).

        All receipts in a single photo are assumed to share the same orientation.

        This used to try all four rotations and score each one with a FULL OCR pass
        — detection plus text recognition — which cost ~210s per photo and made it
        by far the slowest stage of the pipeline (segmentation itself takes ~14s).
        Recognition was doing work we throw away: it read the words only to count
        how many were legible.

        A classifier trained for exactly this question answers it in ~0.02s, four
        orders of magnitude faster. Checked against the previous implementation on
        ten photos, including four needing a 180 degree turn: same rotation on
        10/10 (mean pixel difference 1.4-2.2 of 255, i.e. JPEG noise alone).

        Note that 180 degrees is the case a cheaper geometric heuristic cannot
        settle — upside-down text still yields wide, horizontal line boxes — which
        is why this uses the trained classifier rather than line shape.

        Args:
            img: input image (BGR)
            max_orient_dim: max dimension of the proxy fed to the classifier

        Returns: image rotated to the best orientation
        """
        proxy = self._resize_safe(img, max_dim=max_orient_dim)

        # An image with no writing has no orientation to recover, yet the
        # classifier still returns a label for it (a blank frame comes back as
        # "270" with score 0.26) and acting on that would turn a correct frame
        # sideways. Confidence alone cannot gate this: a genuine photo here
        # scored 0.34 while blank input scored 0.27, so the two ranges very
        # nearly touch. Asking whether any text is present is the reliable
        # question, and one OCR pass on the small proxy answers it — still a
        # detection alone answers it in a fraction of a second.
        if not self._has_text(proxy):
            return img

        try:
            result = self._orientation_classifier.predict(proxy)[0]
            label = result["label_names"][0]
        except Exception as e:
            # Orientation is an optimisation, not a requirement: leaving the photo
            # as it came in is better than failing the whole extraction.
            logger.warning("Orientation classifier unavailable: %s", e)
            return img

        code = self._UNDO_ROTATION.get(label)
        oriented = img if code is None else cv2.rotate(img, code)
        return self._fix_upside_down(oriented, max_orient_dim)

    # How much better the flipped reading must be before we turn the photo.
    _UPSIDE_DOWN_MARGIN = 0.15

    def _fix_upside_down(self, img: np.ndarray, max_dim: int) -> np.ndarray:
        """
        Catch the 180-degree mistakes the orientation classifier still makes.

        Measured on a full run over 96 real photos: 13 of them came out upside
        down, 13% of all receipts. The signature in the OCR text is unmistakable
        — "60'1" is "1,09" read from below — and it is not an edge case the
        classifier is unsure about: on one of those photos it answered "0" (no
        rotation needed) with confidence 0.826. Its own score cannot separate
        these errors, so a second opinion is needed.

        OCR confidence provides it, because a recogniser reading upside-down
        text is guessing and says so:

            photo already correct     0.873 upright vs 0.532 flipped
            photo upside down         0.549 upright vs 0.896 flipped

        Cheap enough to be worth it: the comparison runs on a small proxy, and
        it only decides between two candidates rather than four.
        """
        proxy = self._resize_safe(img, max_dim=max_dim)
        try:
            upright = self._mean_ocr_confidence(proxy)
            flipped = self._mean_ocr_confidence(cv2.rotate(proxy, cv2.ROTATE_180))
        except Exception as e:
            logger.warning("Upside-down check failed: %s", e)
            return img

        # The margin keeps a near-tie from flipping a correct photo. Measured
        # over 22 crops, the two orientations are never close: the smallest
        # separation is 0.276 and nothing at all falls below 0.25, so the
        # threshold sits inside an empty gap rather than among the data. That
        # gap is why a plain margin suffices here and a relative or
        # letters-versus-digits criterion would only add moving parts.
        if flipped > upright + self._UPSIDE_DOWN_MARGIN:
            logger.info("Photo was upside down (%.2f -> %.2f), rotated 180",
                        upright, flipped)
            return cv2.rotate(img, cv2.ROTATE_180)
        return img

    def _mean_ocr_confidence(self, img: np.ndarray) -> float:
        """How sure the recogniser is about what it read. Low means garbage."""
        lines = self._run_single_ocr(img) or []
        if not lines:
            return 0.0
        return float(np.mean([line[1][1] for line in lines]))

    def _has_text(self, img: np.ndarray) -> bool:
        """
        Does this image contain any printed text at all?

        Detection only: we need to know whether words are present, not what they
        say, and reading them costs about thirty times more than finding them.
        """
        try:
            return len(self._text_detector.predict(img)[0]["dt_polys"]) > 0
        except Exception:
            # If we cannot tell, assume there is text: orienting a photo that
            # has some is the common case, and the classifier handles it.
            return True

    def _segment_by_text_density(self, img: np.ndarray, min_area_frac: float = 0.01) -> SegmentationResult:
        """
        Segment receipts by locating dense blocks of printed text.

        Rationale: colour is the wrong signal. A white receipt on a light table
        has the same saturation as its background, so the HSV mask swallows both
        (F1). What actually distinguishes a receipt is that it is covered in
        printed text while the table is not.

        Two details matter, both established by measurement:

        1. Adaptive thresholding, not a global one — it survives uneven lighting
           and shadows, which is exactly where the fixed saturation threshold died.
        2. ANISOTROPIC morphology. A square kernel merges ink into one blob
           covering the whole frame (measured: ink at 8.4% of pixels inflated to
           49.8% by an 18x18 close). Receipt text runs in horizontal lines, so we
           close along x first to build lines, then along y to stack lines into a
           block. Measured on 25 real images: largest island median 33.6%,
           0/25 above the 85% failure threshold.

        Args:
            img: input image (BGR), already oriented
            min_area_frac: minimum block size as a fraction of the frame

        Returns: SegmentationResult
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        total_area = h * w
        min_area = int(total_area * min_area_frac)

        # Step 1: adaptive threshold, inverted so that ink becomes foreground.
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
        )

        # Step 2: merge characters along the text direction (horizontal).
        kernel_x = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
        merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_x)

        # Step 3: drop isolated speckles before they get merged vertically.
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        merged = cv2.morphologyEx(merged, cv2.MORPH_OPEN, kernel_open)

        # Step 4: stack text lines into a receipt-shaped block.
        kernel_y = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
        merged = cv2.morphologyEx(merged, cv2.MORPH_CLOSE, kernel_y)

        # Step 5: each surviving component is a candidate receipt.
        num_labels, labels = cv2.connectedComponents(merged)

        boxes = []
        for label in range(1, num_labels):
            component = (labels == label).astype(np.uint8) * 255
            if cv2.countNonZero(component) < min_area:
                continue
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            boxes.append(cv2.boundingRect(contours[0]))

        if not boxes:
            return SegmentationResult(
                crops=[img],
                method="text_density",
                confident=False,
                reason=(
                    f"no text block above {min_area_frac:.0%} of the frame; "
                    f"image may be blank, out of focus or not a receipt"
                ),
            )

        # Largest first: the dominant text block is the most likely receipt.
        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)

        crops = []
        pad = 12
        for x, y, bw, bh in boxes:
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(w, x + bw + pad), min(h, y + bh + pad)
            crop = img[y1:y2, x1:x2]
            if crop.shape[0] > 0 and crop.shape[1] > 0:
                crops.append(crop)

        # Same whole-frame guard as the colour method: a block covering the
        # entire image means the morphology glued everything together again.
        covered = (crops[0].shape[0] * crops[0].shape[1]) / float(total_area)
        if len(crops) == 1 and covered > WHOLE_FRAME_AREA_FRAC:
            return SegmentationResult(
                crops=crops,
                method="text_density",
                confident=False,
                reason=(
                    f"single text block covers {covered:.0%} of the frame "
                    f"(> {WHOLE_FRAME_AREA_FRAC:.0%})"
                ),
            )

        return SegmentationResult(crops=crops, method="text_density", confident=True)

    def _segment_by_color_islands(self, img: np.ndarray, min_area_frac: float = 0.05) -> list:
        """
        Segment image into individual receipts by detecting low-saturation islands.

        NOTE: superseded by _segment_by_text_density. Kept as a fallback because
        it still wins when receipts sit on a strongly coloured background.
        Its failure mode is documented as F1 in the plan: on light backgrounds
        the saturation threshold does not discriminate at all.

        Algorithm:
        1. Convert to HSV color space
        2. Create mask: pixels with LOW saturation (white/light receipts)
        3. Apply morphological cleanup
        4. Find connected components (islands)
        5. Extract bounding box for each island

        Args:
            img: input image (BGR)
            min_area_frac: minimum island size as fraction of total image area

        Returns: list of cropped receipt images
        """
        h, w = img.shape[:2]
        total_area = h * w
        min_area = int(total_area * min_area_frac)

        # Step 1: Convert to HSV
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Step 2: Create mask for low-saturation pixels (white/light receipts)
        # Receipts are white/light (low saturation), background is brown (high saturation)
        saturation = hsv[:, :, 1]

        # Keep only pixels with saturation < 80 (low saturation = receipts, more selective)
        fg_mask = (saturation < 80).astype(np.uint8) * 255

        # Also exclude very dark pixels (shadows, text)
        value = hsv[:, :, 2]
        fg_mask = cv2.bitwise_and(fg_mask, (value > 40).astype(np.uint8) * 255)

        # Step 3: Morphological cleanup to merge nearby components (smaller kernel)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        # Step 4: Find connected components (islands)
        num_labels, labels = cv2.connectedComponents(fg_mask)

        # Step 5: Extract crops for each island
        crops = []
        for label in range(1, num_labels):  # 0 is background
            # Get mask for this component
            component_mask = (labels == label).astype(np.uint8) * 255

            # Check minimum area
            area = cv2.countNonZero(component_mask)
            if area < min_area:
                continue

            # Get bounding box
            contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue

            x, y, w_box, h_box = cv2.boundingRect(contours[0])

            # Add small padding
            pad = 10
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + w_box + pad)
            y2 = min(h, y + h_box + pad)

            crop = img[y1:y2, x1:x2]
            if crop.shape[0] > 0 and crop.shape[1] > 0:
                crops.append(crop)

        # No island survived: the mask told us nothing about where receipts are.
        if not crops:
            return SegmentationResult(
                crops=[img],
                method="color_islands",
                confident=False,
                reason=(
                    f"no island above {min_area_frac:.0%} of the frame "
                    f"({num_labels - 1} components found); returning the whole image"
                ),
            )

        # A single island covering nearly the whole frame is the failure mode
        # documented in private/2026-07-26_PIANO_ESTRAZIONE.md (F1): the mask
        # swallowed background and receipt alike, so the "crop" is the input.
        if len(crops) == 1:
            covered = (crops[0].shape[0] * crops[0].shape[1]) / float(total_area)
            if covered > WHOLE_FRAME_AREA_FRAC:
                return SegmentationResult(
                    crops=crops,
                    method="color_islands",
                    confident=False,
                    reason=(
                        f"single island covers {covered:.0%} of the frame "
                        f"(> {WHOLE_FRAME_AREA_FRAC:.0%}): saturation threshold did "
                        f"not separate receipt from background"
                    ),
                )

        return SegmentationResult(crops=crops, method="color_islands", confident=True)

    def _find_dominant_color(self, img: np.ndarray) -> tuple:
        """
        Find the dominant background color (excluding dark text pixels).
        Uses K-means on bright pixels only (brightness > 50).

        Returns: BGR color tuple (B, G, R)
        """
        # Convert to grayscale to filter out dark pixels
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Filter: keep only bright pixels (background is typically light)
        bright_mask = gray > 50
        bright_pixels_img = img[bright_mask]

        # If no bright pixels, fall back to corners
        if len(bright_pixels_img) == 0:
            h, w = img.shape[:2]
            sample_size = int(max(h, w) * 0.1)
            corners = np.vstack([
                img[:sample_size, :sample_size].reshape(-1, 3),
                img[:sample_size, -sample_size:].reshape(-1, 3),
                img[-sample_size:, :sample_size].reshape(-1, 3),
                img[-sample_size:, -sample_size:].reshape(-1, 3),
            ])
            return tuple(np.median(corners, axis=0).astype(np.uint8))

        # K-means on bright pixels only
        pixels_float = bright_pixels_img.astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(pixels_float, 3, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

        # Flatten labels and count frequency
        labels = labels.flatten()
        unique, counts = np.unique(labels, return_counts=True)
        most_frequent_label = unique[np.argmax(counts)]

        # Return the most frequent bright color
        centers = centers.astype(np.uint8)
        return tuple(centers[most_frequent_label])

    def _split_by_projection_axis(self, img: np.ndarray, binary: np.ndarray,
                                   projection: np.ndarray, axis: int,
                                   min_gap_frac: float, min_region_frac: float) -> list:
        """
        Helper for _segment_by_projection. Splits image along a given axis
        based on projection profile gaps.

        Args:
            img: original image
            binary: binarized image
            projection: 1D projection profile (row or column sums)
            axis: 0 for horizontal split (rows), 1 for vertical split (cols)
            min_gap_frac, min_region_frac: thresholds

        Returns: list of cropped images
        """
        h, w = img.shape[:2]
        img_len = h if axis == 0 else w
        min_gap_size = max(int(img_len * min_gap_frac), 1)
        min_region_size = max(int(img_len * min_region_frac), 1)

        # Find gap rows/cols: foreground < 1% of opposite dimension
        gap_threshold = 0.01
        gap_mask = projection < gap_threshold

        # Morphological cleanup: suppress isolated gaps within content
        kernel_size = max(5, int(img_len * 0.01))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, 1) if axis == 0 else (1, kernel_size))
        gap_mask = cv2.morphologyEx(gap_mask.astype(np.uint8), cv2.MORPH_OPEN, kernel).astype(bool)

        # Find contiguous gap bands
        gap_indices = np.where(gap_mask)[0]
        if len(gap_indices) == 0:
            return []

        gap_bands = []
        band_start = gap_indices[0]
        for i in range(1, len(gap_indices)):
            if gap_indices[i] - gap_indices[i-1] > 1:
                band_end = gap_indices[i-1]
                if band_end - band_start + 1 >= min_gap_size:
                    gap_bands.append((band_start, band_end))
                band_start = gap_indices[i]
        # Add last band
        if gap_indices[-1] - band_start + 1 >= min_gap_size:
            gap_bands.append((band_start, gap_indices[-1]))

        if not gap_bands:
            return []

        # Create crops by splitting at gap midpoints
        crops = []
        prev_end = 0

        for gap_start, gap_end in gap_bands:
            crop_end = (gap_start + gap_end) // 2
            crop_size = crop_end - prev_end

            if crop_size >= min_region_size:
                if axis == 0:
                    crop = img[prev_end:crop_end, :]
                else:
                    crop = img[:, prev_end:crop_end]
                crops.append(crop)

            prev_end = gap_end + 1

        # Add final region
        final_size = img_len - prev_end
        if final_size >= min_region_size:
            if axis == 0:
                crop = img[prev_end:, :]
            else:
                crop = img[:, prev_end:]
            crops.append(crop)

        return crops

    def _segment_receipts_ocr_guided(self, img: np.ndarray, eps: float = 80) -> list:
        """
        Segment receipts using OCR-guided clustering (Plan B).

        Strategy:
        1. Run OCR on full image to extract text bounding boxes
        2. Cluster OCR box centers using DBSCAN
        3. Group lines by cluster
        4. Extract bounding box crop for each cluster

        Args:
            img: input image (already oriented)
            eps: DBSCAN epsilon (distance threshold for clustering)

        Returns: list of cropped receipt images
        """
        # Run OCR on full image
        lines = self._run_single_ocr(img)

        if not lines or len(lines) < 5:
            return [img]  # Fallback if insufficient text detected

        # Extract centers of OCR bounding boxes
        points = []
        for line in lines:
            if line[0]:  # if box exists
                box = np.array(line[0])
                cx = box[:, 0].mean()
                cy = box[:, 1].mean()
                points.append([cx, cy])

        if len(points) < 5:
            return [img]

        points = np.array(points)

        # Cluster text centers using DBSCAN
        clustering = DBSCAN(eps=eps, min_samples=5).fit(points)
        labels = clustering.labels_

        # Group lines by cluster label
        clusters = {}
        for idx, label in enumerate(labels):
            if label >= 0:  # Ignore noise points (label == -1)
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(lines[idx])

        if not clusters:
            return [img]

        # Extract bounding box crop for each cluster
        crops = []
        for cluster_idx in sorted(clusters.keys()):
            cluster_lines = clusters[cluster_idx]
            crop = self._crop_from_ocr_lines(img, cluster_lines)
            if crop is not None:
                crops.append(crop)

        return crops if crops else [img]

    def _segment_receipts(self, img: np.ndarray, image_path: str) -> list:
        """
        Segment the image into individual receipts using color-based island detection.

        Strategy:
        1. Use color-based island detection (robust to textured backgrounds)
        2. Trust CV result when it finds > 1 receipt (good saturation discrimination)
        3. Use VLM count only as validation for 1 receipt case

        Args:
            img: already oriented image
            image_path: path to original image (for VLM validation)

        Returns: SegmentationResult (iterable as a list of crops)
        """
        # Primary method: text density. Colour was measured to be the wrong
        # signal (F1); printed text is what actually marks a receipt.
        result = self._segment_by_text_density(img, min_area_frac=0.01)

        # If text density fails outright, fall back to the colour method, which
        # still works when receipts lie on a strongly coloured background.
        if not result.confident:
            fallback = self._segment_by_color_islands(img, min_area_frac=0.05)
            if fallback.confident:
                fallback.reason = "text density failed; recovered via colour islands"
                result = fallback

        # Multiple distinct regions: the segmentation discriminated, trust it.
        if len(result) > 1 and result.confident:
            return result

        expected_n = self._get_vision_count(image_path)
        result.vision_count = expected_n

        # A confident single crop that the VLM also calls 1: genuine single receipt.
        if result.confident and expected_n == 1:
            return result

        # The VLM could not answer. Do not read that as agreement.
        if expected_n is None:
            result.warnings.append(
                "VLM unavailable: single-receipt result is unverified"
            )
            if not result.confident:
                result.reason += "; VLM unavailable, cannot cross-check"
            return result

        # CV found one region but the VLM sees several, or CV is not confident:
        # this is the recovery path. It was previously unreachable whenever
        # Ollama was missing, because the VLM always claimed to see 1.
        if expected_n > 1 or not result.confident:
            # Lower the area floor: a receipt the VLM sees may be small enough
            # to have been filtered out at the default threshold.
            retry = self._segment_by_text_density(img, min_area_frac=0.005)
            if len(retry) > 1 and retry.confident:
                retry.vision_count = expected_n
                retry.reason = "recovered with lower text-density floor (0.5%)"
                return retry

            retry = self._segment_by_color_islands(img, min_area_frac=0.02)
            if len(retry) > 1:
                retry.vision_count = expected_n
                retry.reason = "recovered via colour islands, min_area_frac=0.02"
                return retry

            ocr_crops = self._segment_receipts_ocr_guided(img, eps=40)
            if len(ocr_crops) > 1:
                return SegmentationResult(
                    crops=ocr_crops,
                    method="ocr_guided",
                    confident=True,
                    reason="recovered via OCR-guided clustering",
                    vision_count=expected_n,
                )

            # Every strategy failed to split. Say so rather than returning a
            # bare list that looks like success.
            return SegmentationResult(
                crops=result.crops,
                method=result.method,
                confident=False,
                reason=(
                    f"VLM expected {expected_n} receipts, no strategy could split "
                    f"the image; falling back to a single region"
                ),
                vision_count=expected_n,
                warnings=result.warnings,
            )

        return result

    def extract_raw_ocr(self, image_path):
        """
        Four-stage pipeline for receipt extraction and OCR:
        1. Load and resize image
        2. Whole-image orientation correction (all receipts have the same orientation)
        3. Segmentation into individual receipts via projection profiles
        4. OCR on each receipt

        Returns: (list of OCR line clusters, list of cropped receipt images)
        """
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Impossibile leggere: {image_path}")

        # Stage 1: Resize to working resolution
        image = self._resize_safe(image, max_dim=2000)

        # Stage 2: Whole-image orientation correction (ONCE, not per-crop)
        image = self._orient_whole_image(image, max_orient_dim=800)

        # Stage 3: Segment into individual receipts
        segmentation = self._segment_receipts(image, image_path)
        self.last_segmentation = segmentation

        # Announce a failed segmentation instead of letting it pass as success.
        if not segmentation.confident:
            logger.warning(
                "Segmentation not confident for %s [%s]: %s",
                image_path, segmentation.method, segmentation.reason,
            )
            self._quarantine(image_path, segmentation.reason)
        for warning in segmentation.warnings:
            logger.warning("Segmentation warning for %s: %s", image_path, warning)

        # Stage 4: OCR each crop (orientation already correct from Stage 2)
        all_clusters = []
        all_crops = []
        for crop in segmentation.crops:
            lines = self._run_single_ocr(crop)
            if len(lines) >= 5:  # Minimum content threshold
                all_clusters.append(lines)
                all_crops.append(crop)

        if not all_clusters:
            logger.warning("No crop reached the minimum OCR content threshold: %s", image_path)
            self._quarantine(image_path, "no crop produced at least 5 OCR lines")
            return [[]], [image]

        return all_clusters, all_crops

    def _quarantine(self, image_path: str, reason: str) -> None:
        """
        Record an image the pipeline could not handle, so failures accumulate
        somewhere visible instead of vanishing. Never raises: quarantine is
        diagnostics, and must not take down a running batch.
        """
        try:
            import datetime
            import os

            os.makedirs(self.quarantine_dir, exist_ok=True)
            log_path = os.path.join(self.quarantine_dir, "quarantine.log")
            stamp = datetime.datetime.now().isoformat(timespec="seconds")
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp}\t{image_path}\t{reason}\n")
        except Exception as e:  # pragma: no cover - diagnostics must not break the run
            logger.debug("Could not write quarantine record: %s", e)


    def _resize_safe(self, image: np.ndarray, max_dim: int = 2000) -> np.ndarray:
        h, w = image.shape[:2]
        if max(h, w) <= max_dim:
            return image
        scale = max_dim / float(max(h, w))
        return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


    def _crop_from_ocr_lines(self, img: np.ndarray, lines: list) -> np.ndarray:
        """
        Extract a crop from an image based on OCR line bounding boxes.
        Returns the smallest rectangle containing all lines in the cluster.
        """
        if not lines or not lines[0]:
            return None

        try:
            # Collect all points from all lines
            all_pts = []
            for line in lines:
                if line and line[0]:
                    all_pts.extend(line[0])

            if not all_pts:
                return None

            all_pts = np.array(all_pts)
            x, y, w, h = cv2.boundingRect(all_pts)

            # Add padding
            pad = 10
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(img.shape[1], x + w + pad)
            y2 = min(img.shape[0], y + h + pad)

            crop = img[y1:y2, x1:x2]
            if crop.shape[0] > 0 and crop.shape[1] > 0:
                return crop
        except Exception:
            pass

        return None

    def _orient_receipt(self, img: np.ndarray) -> np.ndarray:
        """
        Correct orientation of a single receipt by testing 4 rotations.
        Uses OCR score to pick the best rotation (0°, 90°, 180°, 270°).
        Returns the image rotated to the best orientation.
        """
        rotations = {
            0: None,
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        best_score = -1
        best_img = img

        for deg, code in rotations.items():
            rotated = img if code is None else cv2.rotate(img, code)
            lines = self._run_single_ocr(rotated)
            score = self._ocr_score(lines)
            if score > best_score:
                best_score = score
                best_img = rotated

        return best_img

    def _ocr_score(self, lines: list) -> float:
        if not lines: return 0.0
        scores = [l[1][1] for l in lines]
        return len(lines) * (sum(scores)/len(scores))

    def _run_single_ocr(self, image_input):
        """PaddleOCR su immagine singola."""
        try:
            res = self.ocr.predict(image_input)
        except Exception:
            try:
                res = self.ocr.ocr(image_input)
            except Exception:
                return []
        if not res or not res[0]: return []
        return self._extract_lines_from_res(res[0])

    def _extract_lines_from_res(self, res_obj):
        if isinstance(res_obj, list):
            if res_obj and isinstance(res_obj[0], list): return res_obj
        elif hasattr(res_obj, 'get') or isinstance(res_obj, dict):
            rec_texts = res_obj.get('rec_texts', [])
            rec_scores = res_obj.get('rec_scores', [])
            dt_polys = res_obj.get('dt_polys', [])
            lines = []
            for i in range(len(rec_texts)):
                box = dt_polys[i].tolist() if i < len(dt_polys) and hasattr(dt_polys[i], 'tolist') else []
                lines.append([box, (rec_texts[i], rec_scores[i] if i < len(rec_scores) else 1.0)])
            return lines
        return []






    def parse_raw_data(self, raw_ocr_output):
        """Ricostruisce le righe di testo."""
        if not raw_ocr_output: return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}
        
        def get_y_center(line): return sum([p[1] for p in line[0]]) / 4
        def get_x_start(line): return min([p[0] for p in line[0]])
        
        sorted_lines = sorted(raw_ocr_output, key=get_y_center)
        rows = []
        if sorted_lines:
            curr_row = [sorted_lines[0]]
            for l in sorted_lines[1:]:
                if get_y_center(l) - get_y_center(curr_row[-1]) < 15: # Soglia riga 15px
                    curr_row.append(l)
                else:
                    rows.append(sorted(curr_row, key=get_x_start))
                    curr_row = [l]
            rows.append(sorted(curr_row, key=get_x_start))
        
        reconstructed_text = []
        for r in rows:
            reconstructed_text.append(" ".join([l[1][0] for l in r]))
            
        return reconstructed_text # Passiamo il testo reconstruction al processore
