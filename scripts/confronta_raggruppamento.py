"""
Settle the disagreement between the two second opinions, with data.

Vibe: use a GLOBAL vertical projection, cut at the valleys.
Cursor: global projection breaks when receipts differ in height/position;
        merge bounding boxes locally by horizontal overlap + vertical gap.

Both cannot be right. We implement both and count how close each gets to the
receipt counts a human established:
    07.47.51 -> 5 receipts
    07.53.17 -> 4 receipts
    07.57.06 -> 2 receipts
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())
from app.etl.etl_engine import ReceiptPipeline  # noqa: E402

TRUTH = {
    "2025-02-20 07.47.51.jpg": 5,
    "2025-02-20 07.53.17.jpg": 4,
    "2025-02-20 07.57.06.jpg": 2,
    "2025-03-15 10.33.47.jpg": 2,   # horizontal photo, two Mercadona receipts
    "2025-03-15 10.29.00.jpg": None,  # unknown, reported only
}

PATHS = {
    "2025-02-20 07.47.51.jpg": "data/pictures_not_yet_used/2025-02-20 07.47.51.jpg",
    "2025-02-20 07.53.17.jpg": "data/pictures_not_yet_used/2025-02-20 07.53.17.jpg",
    "2025-02-20 07.57.06.jpg": "data/pictures_archived/2025-02-20 07.57.06.jpg",
    "2025-03-15 10.33.47.jpg": "data/pictures_not_yet_used/2025-03-15 10.33.47.jpg",
    "2025-03-15 10.29.00.jpg": "data/pictures_archived/2025-03-15 10.29.00.jpg",
}


def text_mask(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    m = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15)))
    return binary, m


def raw_boxes(mask, total, min_frac=0.005):
    n, labels = cv2.connectedComponents(mask)
    boxes = []
    for lab in range(1, n):
        comp = (labels == lab).astype(np.uint8) * 255
        if cv2.countNonZero(comp) < total * min_frac:
            continue
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            boxes.append(cv2.boundingRect(cnts[0]))
    return boxes


def method_projection(binary, total):
    """Vibe: global column histogram, cut at valleys."""
    proj = (binary > 0).sum(axis=0).astype(np.float32)
    if proj.max() == 0:
        return 0
    norm = proj / proj.max()
    # A valley = column with almost no ink.
    valley = norm < 0.05
    # Count runs of non-valley = candidate receipts.
    runs, in_run = 0, False
    min_w = binary.shape[1] * 0.03
    run_len = 0
    for v in valley:
        if not v:
            run_len += 1
            in_run = True
        else:
            if in_run and run_len >= min_w:
                runs += 1
            in_run, run_len = False, 0
    if in_run and run_len >= min_w:
        runs += 1
    return runs


def ink_density(binary, box):
    x, y, w, h = box
    patch = binary[y:y + h, x:x + w]
    return (patch > 0).mean() if patch.size else 0.0


def text_line_count(binary, box):
    """Count horizontal ink runs inside the box: real text has many lines."""
    x, y, w, h = box
    patch = binary[y:y + h, x:x + w]
    if patch.size == 0:
        return 0
    rows = (patch > 0).sum(axis=1) / float(w)
    active = rows > 0.05
    lines, prev = 0, False
    for a in active:
        if a and not prev:
            lines += 1
        prev = a
    return lines


def method_merge(boxes, binary, total, iox_thr=0.5, gap_k=3.0):
    """Cursor: merge by horizontal overlap + vertical proximity."""
    # Filter obvious non-text first.
    kept = []
    for b in boxes:
        if ink_density(binary, b) < 0.03:
            continue          # empty table
        if text_line_count(binary, b) < 3:
            continue          # barcode / stray mark
        kept.append(b)

    if not kept:
        return []

    heights = [b[3] for b in kept]
    med_h = float(np.median(heights))
    max_gap = gap_k * med_h

    merged = [list(b) for b in kept]
    changed = True
    while changed:
        changed = False
        out = []
        while merged:
            cur = merged.pop(0)
            cx1, cx2 = cur[0], cur[0] + cur[2]
            i = 0
            while i < len(merged):
                o = merged[i]
                ox1, ox2 = o[0], o[0] + o[2]
                inter = max(0, min(cx2, ox2) - max(cx1, ox1))
                iox = inter / float(min(cur[2], o[2])) if min(cur[2], o[2]) else 0
                gap = max(cur[1], o[1]) - min(cur[1] + cur[3], o[1] + o[3])
                if iox >= iox_thr and gap <= max_gap:
                    nx1, ny1 = min(cur[0], o[0]), min(cur[1], o[1])
                    nx2 = max(cur[0] + cur[2], o[0] + o[2])
                    ny2 = max(cur[1] + cur[3], o[1] + o[3])
                    cur = [nx1, ny1, nx2 - nx1, ny2 - ny1]
                    cx1, cx2 = cur[0], cur[0] + cur[2]
                    merged.pop(i)
                    changed = True
                    i = 0
                else:
                    i += 1
            out.append(cur)
        merged = out
    return merged


def main():
    p = ReceiptPipeline()
    print(f"{'foto':<26} {'reali':>5} {'grezze':>7} {'proiez':>7} {'merge':>6}")
    print("-" * 58)
    for name, path in PATHS.items():
        img = cv2.imread(path)
        if img is None:
            continue
        img = p._resize_safe(img, 2000)
        img = p._orient_whole_image(img, 800)
        total = img.shape[0] * img.shape[1]

        binary, mask = text_mask(img)
        boxes = raw_boxes(mask, total)
        n_proj = method_projection(binary, total)
        n_merge = len(method_merge(boxes, binary, total))

        truth = TRUTH[name]
        t = str(truth) if truth else "?"
        print(f"{name[:24]:<26} {t:>5} {len(boxes):7d} {n_proj:7d} {n_merge:6d}")


if __name__ == "__main__":
    main()
