"""
Generate visual contact sheets: original image with detected regions outlined,
next to the individual crops. Lets a human judge segmentation quality at a
glance instead of reading numbers.

Output: exports/debug_crops/<name>_sheet.jpg (one per image)
"""
import glob
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())
from app.etl.etl_engine import ReceiptPipeline  # noqa: E402

OUT_DIR = "exports/debug_crops"
PALETTE = [
    (0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 200),
    (255, 0, 255), (0, 128, 255), (128, 0, 255), (0, 255, 128),
]


def thumb(img, height):
    """Scale an image to a fixed height, preserving aspect."""
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return None
    scale = height / float(h)
    return cv2.resize(img, (max(1, int(w * scale)), height), interpolation=cv2.INTER_AREA)


def build_sheet(pipeline, path, panel_h=560):
    img = cv2.imread(path)
    if img is None:
        return None, 0
    img = pipeline._resize_safe(img, 2000)

    # Go through stage 2 exactly like the real pipeline does. Skipping it made
    # the earlier sheets show a segmentation the pipeline never performs: on
    # 07.47.51 it turned 5 correct regions into 2, one covering the whole frame.
    img = pipeline._orient_whole_image(img, max_orient_dim=800)

    total = img.shape[0] * img.shape[1]
    result = pipeline._segment_by_text_density(img, min_area_frac=0.01)

    # Recompute the boxes so we can draw them on the original.
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    m = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15)))
    n_lab, labels = cv2.connectedComponents(m)

    boxes = []
    for label in range(1, n_lab):
        comp = (labels == label).astype(np.uint8) * 255
        if cv2.countNonZero(comp) < total * 0.01:
            continue
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            boxes.append(cv2.boundingRect(contours[0]))
    boxes.sort(key=lambda b: b[2] * b[3], reverse=True)

    # Panel 1: original with numbered boxes.
    marked = img.copy()
    for i, (x, y, bw, bh) in enumerate(boxes):
        color = PALETTE[i % len(PALETTE)]
        cv2.rectangle(marked, (x, y), (x + bw, y + bh), color, 6)
        cv2.putText(marked, str(i + 1), (x + 10, y + 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, color, 5)

    panels = [thumb(marked, panel_h)]
    for i, crop in enumerate(result.crops):
        t = thumb(crop, panel_h)
        if t is None:
            continue
        cv2.rectangle(t, (0, 0), (t.shape[1] - 1, t.shape[0] - 1),
                      PALETTE[i % len(PALETTE)], 4)
        cv2.putText(t, str(i + 1), (8, 44), cv2.FONT_HERSHEY_SIMPLEX,
                    1.4, PALETTE[i % len(PALETTE)], 4)
        panels.append(t)

    sep = np.full((panel_h, 12, 3), 255, dtype=np.uint8)
    stacked = []
    for p in panels:
        stacked.extend([p, sep])
    sheet = np.hstack(stacked[:-1])

    # Header strip with the verdict.
    header = np.full((60, sheet.shape[1], 3), 255, dtype=np.uint8)
    cov = (result.crops[0].shape[0] * result.crops[0].shape[1]) / float(total)
    text = (f"{os.path.basename(path)}   regioni={len(result.crops)}   "
            f"maggiore={cov * 100:.0f}% del frame   confident={result.confident}")
    cv2.putText(header, text, (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)

    return np.vstack([header, sheet]), len(result.crops)


def main(paths):
    os.makedirs(OUT_DIR, exist_ok=True)
    pipeline = ReceiptPipeline()
    print(f"{'file':<40} {'regioni':>7}")
    print("-" * 50)
    for path in paths:
        sheet, n = build_sheet(pipeline, path)
        if sheet is None:
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(OUT_DIR, f"{name}_sheet.jpg")
        cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
        print(f"{os.path.basename(path)[:38]:<40} {n:7d}")
    print(f"\nScritti in {OUT_DIR}/")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = sorted(glob.glob("data/pictures_archived/*.jpg"))
        args += sorted(glob.glob("data/pictures_not_yet_used/*"))[:9]
    main(args)
