"""
Receipt segmentation by text-line detection, then splitting on empty columns.

Replaces the bottom-up pipeline (adaptiveThreshold -> grow -> merge -> ink
filter), which plateaued at 4/6 exact counts and could not be improved: every
threshold change fixed one photo and broke another.

The reason it plateaued is visible at its very first step. On 07.47.51 the
first raw connected component measured 469x1500 — the full height of the frame
— because adaptiveThreshold welds the text of two adjacent receipts into one
blob before any later stage can see them apart. No downstream tuning recovers
information destroyed at that point.

A pretrained text detector does not weld them: it segments individual text
lines, so five receipts standing side by side stay five sets of lines. Two
consequences, both measured:

  1. Splitting becomes trivial. Project every detected line onto the x axis and
     the gaps between receipts are literally empty columns, 62-111px wide,
     while no receipt contains one. There is no threshold to tune.

  2. The wood false positives disappear at the source. The old filter had to
     tell print from wood grain and could not: a wood strip scored a text
     rhythm of 1.016, HIGHER than a genuine receipt at 0.57. The detector
     simply reports no text lines on bare wood, so the region is never
     proposed.

Domain rule this rests on: a receipt IS the cluster of its own text lines.
Chasing the paper edge was the wrong problem — on light thermal paper over a
light table that edge carries almost no signal, which is why brightness-based
attempts failed four times before this.

Measured over the six reference photos, exact counts:

    valley width ->    10    15    20    25    30    40
    f=0.03            6/6   6/6   5/6   5/6   5/6   4/6
    f=0.05            6/6   6/6   6/6   5/6   5/6   4/6
    f=0.08            6/6   6/6   6/6   5/6   5/6   4/6

6/6 holds over a plateau rather than at one lucky point, and four of the six
photos are correct at every setting tried. Defaults sit in the middle of it.
"""
import os
import sys
import warnings

import cv2
import numpy as np

warnings.filterwarnings("ignore")
os.environ.setdefault("GLOG_minloglevel", "3")
sys.path.insert(0, os.getcwd())

CACHE = "data/cache_oriented"
OUT_DIR = "exports/detector"

CASES = [
    ("07.47.51", 5), ("07.53.17", 4), ("07.57.06", 2),
    ("10.33.47", 2), ("21.12.47", 1), ("21.25.11", 1),
]

PALETTE = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 200),
           (255, 0, 255), (0, 128, 255), (128, 0, 255), (0, 255, 128)]


def detect_lines(img, _cache={}):
    """Text-line polygons from PaddleOCR's detector (no recognition needed)."""
    if "det" not in _cache:
        from paddleocr import TextDetection
        # oneDNN raises ConvertPirAttribute2RuntimeAttribute on this build.
        _cache["det"] = TextDetection(enable_mkldnn=False)
    return _cache["det"].predict(img)[0]["dt_polys"]


def x_coverage(polys, width):
    """How many text lines span each image column."""
    cov = np.zeros(width, dtype=int)
    for p in polys:
        p = np.asarray(p)
        cov[int(p[:, 0].min()):int(p[:, 0].max()) + 1] += 1
    return cov


def separators(cov, empty_frac=0.05, min_width=15):
    """
    Columns of (near-)absent text that split one receipt from the next.

    The level is relative to the photo's own text density, not an absolute
    count, so it does not move with how much of the frame the receipts fill.
    Near-absent rather than strictly empty because on 07.53.17 two receipts
    touch: the gap between them thins the coverage without ever zeroing it,
    and requiring a true zero merged them (3 found instead of 4).

    Runs touching the image border are ignored — those are the margins around
    the outermost receipts, not gaps between two of them.
    """
    if not cov.any():
        return []
    level = empty_frac * float(np.percentile(cov[cov > 0], 75))
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
            if r[0] > 0 and r[0] + r[1] < len(cov) and r[1] >= min_width]


def drop_contained(boxes, frac=0.80):
    """
    Remove any box that sits (almost) entirely inside another one.

    Receipts are laid out side by side, never stacked one on top of another, so
    a box nested inside a bigger one is never a second receipt — it is a piece
    of the same one. This happens when a slanted receipt has a column poor in
    text (the gap between description and price): the projection reads it as a
    separator and carves a sliver out of the middle of the sheet. On
    2025-09-06 10.43.15 that sliver was the price column alone, digits with no
    item names.
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


def segment(img, pad_frac=0.02):
    """One box per receipt: the bounding box of each text-line cluster."""
    h, w = img.shape[:2]
    polys = [np.asarray(p) for p in detect_lines(img)]
    if not polys:
        return []

    cuts = [r[0] + r[1] // 2 for r in separators(x_coverage(polys, w))]
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
        px, py = pad_frac * (x2 - x1), pad_frac * (y2 - y1)
        boxes.append([int(max(0, x1 - px)), int(max(0, y1 - py)),
                      int(min(w, x2 + px) - max(0, x1 - px)),
                      int(min(h, y2 + py) - max(0, y1 - py))])
    return drop_contained(boxes)


def contact_sheet(img, boxes, title, panel_h=560):
    """Original with numbered regions, then every crop side by side."""
    marked = img.copy()
    for i, (x, y, w, h) in enumerate(boxes):
        color = PALETTE[i % len(PALETTE)]
        cv2.rectangle(marked, (x, y), (x + w, y + h), color, 8)
        cv2.putText(marked, str(i + 1), (x + 12, y + 64),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, color, 6)

    def thumb(im):
        if im.shape[0] == 0 or im.shape[1] == 0:
            return None
        s = panel_h / float(im.shape[0])
        return cv2.resize(im, (max(1, int(im.shape[1] * s)), panel_h))

    panels = [thumb(marked)]
    for i, (x, y, w, h) in enumerate(boxes):
        t = thumb(img[y:y + h, x:x + w])
        if t is None:
            continue
        cv2.rectangle(t, (0, 0), (t.shape[1] - 1, t.shape[0] - 1),
                      PALETTE[i % len(PALETTE)], 4)
        panels.append(t)

    sep = np.full((panel_h, 10, 3), 255, dtype=np.uint8)
    stacked = []
    for p in panels:
        stacked.extend([p, sep])
    sheet = np.hstack(stacked[:-1])

    header = np.full((56, sheet.shape[1], 3), 255, dtype=np.uint8)
    cv2.putText(header, title, (12, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (0, 0, 0), 2)
    return np.vstack([header, sheet])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"{'foto':<12} {'reali':>5} {'trovati':>8}  esito")
    print("-" * 40)
    exact = 0
    for key, truth in CASES:
        img = cv2.imread(os.path.join(CACHE, key + ".jpg"))
        if img is None:
            print(f"{key:<12} {truth:5d}   (non in cache)")
            continue
        boxes = sorted(segment(img), key=lambda b: b[0])
        n = len(boxes)
        exact += n == truth
        esito = "OK" if n == truth else (
            "sotto-conta" if n < truth else "sovra-conta")
        print(f"{key:<12} {truth:5d} {n:8d}  {esito}")

        title = f"{key}   reali={truth}   trovati={n}   {esito}"
        cv2.imwrite(os.path.join(OUT_DIR, f"{key}_detector.jpg"),
                    contact_sheet(img, boxes, title),
                    [cv2.IMWRITE_JPEG_QUALITY, 80])

    print()
    print(f"esatti: {exact}/{len(CASES)}")
    print(f"\nFogli visivi in {OUT_DIR}/")


if __name__ == "__main__":
    main()
