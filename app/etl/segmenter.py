"""
Receipt segmentation by text-line detection.

Promoted from scripts/segmenta_detector.py, which reached 6/6 exact counts on
the reference photos and 10/10 on ten photos never seen during development.
The reasoning, the measurements and every discarded approach are recorded in
scripts/segmenta_detector.md.

The idea in one line: a receipt IS the cluster of its own text lines. Chasing
the paper edge is ill-posed here, because light thermal paper on a light table
carries almost no brightness step — the reason four earlier attempts failed.
"""
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# How many times a suspect box may be straightened and split again. Stacked
# receipts give up one seam per pass, so a few passes are needed; the cap stops
# a box that keeps looking suspect from recursing forever.
MAX_RETRY = 3


class ReceiptSegmenter:
    """Cuts a photo into one crop per receipt."""

    def __init__(self, empty_frac=0.05, min_valley=15, pad_frac=0.02):
        # Defaults sit at the centre of a measured plateau, not at a tuned
        # optimum: 6/6 holds for empty_frac 0.03-0.08 crossed with min_valley
        # 10-20px, and four of the six photos are correct at every setting.
        self.empty_frac = empty_frac
        self.min_valley = min_valley
        self.pad_frac = pad_frac
        self._det = None

    @property
    def detector(self):
        """PaddleOCR text detector, created on first use."""
        if self._det is None:
            from paddleocr import TextDetection
            # oneDNN raises ConvertPirAttribute2RuntimeAttribute on this build.
            self._det = TextDetection(enable_mkldnn=False)
        return self._det

    def detect_lines(self, img):
        return [np.asarray(p) for p in self.detector.predict(img)[0]["dt_polys"]]

    def x_coverage(self, polys, width):
        """How many text lines span each image column."""
        cov = np.zeros(width, dtype=int)
        for p in polys:
            lo = max(0, int(p[:, 0].min()))
            hi = min(width, int(p[:, 0].max()) + 1)
            if hi > lo:
                cov[lo:hi] += 1
        return cov

    def separators(self, cov):
        """
        Columns of (near-)absent text that split one receipt from the next.

        The level is relative to the photo's own text density, so it does not
        move with how much of the frame the receipts fill. Near-absent rather
        than strictly empty because touching receipts thin the coverage without
        ever zeroing it, and demanding a true zero merged them.

        Runs touching the border are ignored: those are the outer margins.
        """
        if not cov.any():
            return []
        level = self.empty_frac * float(np.percentile(cov[cov > 0], 75))
        low = cov <= level

        runs, start = [], None
        for i, is_low in enumerate(low):
            if is_low and start is None:
                start = i
            if not is_low and start is not None:
                runs.append((start, i - start))
                start = None
        if start is not None:
            runs.append((start, len(cov) - start))

        return [r for r in runs
                if r[0] > 0 and r[0] + r[1] < len(cov) and r[1] >= self.min_valley]

    def boxes_from_lines(self, polys, w, h):
        """Group text lines on empty columns, one box per group."""
        if not polys:
            return []
        cuts = [r[0] + r[1] // 2 for r in self.separators(self.x_coverage(polys, w))]
        bounds = [0] + cuts + [w]

        boxes = []
        for left, right in zip(bounds, bounds[1:]):
            group = [p for p in polys if left <= p[:, 0].mean() < right]
            if not group:
                continue
            x1 = min(p[:, 0].min() for p in group)
            x2 = max(p[:, 0].max() for p in group)
            y1 = min(p[:, 1].min() for p in group)
            y2 = max(p[:, 1].max() for p in group)
            # Pad outwards: the paper extends a little past its printing.
            px, py = self.pad_frac * (x2 - x1), self.pad_frac * (y2 - y1)
            bx, by = max(0, x1 - px), max(0, y1 - py)
            boxes.append([int(bx), int(by),
                          int(min(w, x2 + px) - bx), int(min(h, y2 + py) - by)])
        return boxes

    @staticmethod
    def is_suspect(box, frame_w, n_lines, max_w_frac=0.45, max_lines=120):
        """
        Does this box look like several receipts caught in one?

        Two independent signs, either one enough. Over thirty boxes measured on
        ten photos, the single box known to hold three receipts is the only one
        past either line, and neither is a close call:

            width / frame   others 0.15..0.37    the merged box 0.56
            text lines      others 10..95        the merged box 206
        """
        return box[2] / float(frame_w) > max_w_frac or n_lines > max_lines

    @staticmethod
    def drop_contained(boxes, frac=0.80):
        """
        Remove any box sitting (almost) entirely inside another.

        Domain rule stated by the user: receipts are laid side by side, never
        meaningfully stacked, so a nested box is not a second receipt but a
        piece of the same one. It appears when a slanted receipt has a column
        poor in text (the gap between description and price) and the projection
        carves out a sliver holding only the digits.
        """
        keep = []
        for i, b in enumerate(boxes):
            area = b[2] * b[3]
            if area <= 0:
                continue
            nested = False
            for j, o in enumerate(boxes):
                if i == j or o[2] * o[3] <= area:
                    continue
                ix = max(0, min(b[0] + b[2], o[0] + o[2]) - max(b[0], o[0]))
                iy = max(0, min(b[1] + b[3], o[1] + o[3]) - max(b[1], o[1]))
                if (ix * iy) / area >= frac:
                    nested = True
                    break
            if not nested:
                keep.append(b)
        return keep

    def retry_rotated(self, img, box):
        """
        Second pass over a suspect region, straightened on its own.

        Receipts lying at an angle defeat the column projection: text slanted by
        a few degrees smears sideways and fills the gaps between sheets.
        Straightening the WHOLE photo was measured making things worse (4->3,
        3->2, 4->2 groups), because rotating about the frame centre slides the
        outer receipts across each other. Rotating only the suspect crop avoids
        that — nothing else in the photo moves.
        """
        x, y, w, h = box
        crop = img[y:y + h, x:x + w]
        if crop.size == 0:
            return None

        polys = self.detect_lines(crop)
        if len(polys) < 4:
            return None

        angles = []
        for p in polys:
            (bw, bh), a = cv2.minAreaRect(p.astype(np.float32))[1:]
            angles.append(a - 90 if bw < bh else a)
        angles = np.array(angles)
        angles = angles[np.abs(angles) < 45]
        if angles.size == 0:
            return None
        tilt = float(np.median(angles))
        if abs(tilt) < 1.0:
            return None  # already straight: a second look finds the same thing

        m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), tilt, 1.0)
        straight = cv2.warpAffine(crop, m, (w, h), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)
        found = self.boxes_from_lines(self.detect_lines(straight), w, h)
        if len(found) < 2:
            return None  # no new split: keep the original box

        # Map back to the full photo: corners are rotated back, then enclosed.
        inv = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -tilt, 1.0)
        out = []
        for bx, by, bw, bh in found:
            pts = np.array([[bx, by], [bx + bw, by],
                            [bx + bw, by + bh], [bx, by + bh]], dtype=np.float32)
            back = (inv[:, :2] @ pts.T).T + inv[:, 2]
            x1, y1 = back[:, 0].min(), back[:, 1].min()
            x2, y2 = back[:, 0].max(), back[:, 1].max()
            out.append([int(max(0, x1)) + x, int(max(0, y1)) + y,
                        int(min(w, x2) - max(0, x1)), int(min(h, y2) - max(0, y1))])
        return out

    def boxes(self, img):
        """One box per receipt, as [x, y, w, h]."""
        h, w = img.shape[:2]
        polys = self.detect_lines(img)
        if not polys:
            return []

        def resolve(box, depth=0):
            bx, by, bw, bh = box
            n = sum(1 for p in polys
                    if bx <= p[:, 0].mean() < bx + bw
                    and by <= p[:, 1].mean() < by + bh)
            if depth >= MAX_RETRY or not self.is_suspect(box, w, n):
                return [box]
            split = self.retry_rotated(img, box)
            if not split:
                return [box]
            # Straightening exposes one seam at a time when receipts are stacked
            # at different angles: the first pass over three merged slips freed
            # one and left the other two together, still holding 195 text lines.
            return [out for piece in split for out in resolve(piece, depth + 1)]

        found = [b for box in self.boxes_from_lines(polys, w, h) for b in resolve(box)]
        return sorted(self.drop_contained(found), key=lambda b: b[0])

    def crops(self, img):
        """The image content of each receipt box."""
        return [img[y:y + h, x:x + w] for x, y, w, h in self.boxes(img)]
