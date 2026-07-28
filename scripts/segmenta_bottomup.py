"""
Bottom-up segmentation: text first, then grow to the paper edge.

Why this order (Gemini's advice, matching the hypothesis already in the plan):
starting from paper luminosity failed four times because a light receipt on a
light table has no reliable brightness step. Printed text, on the other hand, is
high contrast and easy to group. So:

  1. find text blocks           (strong signal)
  2. grow each block outwards   (local search, we already know a receipt is there)
  3. check rectangularity       (domain rule: a receipt is always a rectangle)

Step 2 is the key change: looking for the sheet edge inside a small neighbourhood
where a receipt is known to exist is a much easier problem than finding sheets in
the whole frame.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.getcwd())

# Oriented images are cached because _orient_whole_image costs 4 OCR passes per
# photo, which made every earlier experiment time out.
CACHE = "data/cache_oriented"

CASES = [
    ("07.47.51", 5), ("07.53.17", 4), ("07.57.06", 2),
    ("10.33.47", 2), ("21.12.47", 1), ("21.25.11", 1),
]


def text_blocks(img, min_area_frac=0.002):
    """
    Step 1: locate printed-text regions.

    The area floor must stay LOW. At 1% of the frame it kept only the largest
    block, which on a receipt carrying a credit-card slip is the slip itself
    (bigger, well-spaced font): the body with products and total was split into
    pieces of 0.3% and below and thrown away, leaving a crop that counted as
    "1 receipt found" while containing none of the purchase.

    Small fragments are the normal state of receipt text. Recomposing them is
    the job of growth and merging, not of a threshold applied before either.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    m = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15)))

    n, labels = cv2.connectedComponents(m)
    boxes = []
    for lab in range(1, n):
        comp = (labels == lab).astype(np.uint8) * 255
        if cv2.countNonZero(comp) < h * w * min_area_frac:
            continue
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            boxes.append(list(cv2.boundingRect(cnts[0])))
    return boxes, binary


def paper_profile(gray, box, axis, side, limit=None):
    """
    Step 2: walk outwards from a text box until the paper ends.

    We compare each new line (row or column) with the paper already inside the
    box: while we are still on the same sheet the brightness stays close to the
    sheet's own median. A drop marks the table, and that is where we stop.
    This is a LOCAL comparison, which is why it works where a global threshold
    does not.
    """
    x, y, w, h = box
    inside = gray[y:y + h, x:x + w]
    if inside.size == 0:
        return 0

    # Reference = the PAPER inside the box, not its average. The 75th percentile
    # ignores the printed text, which would otherwise drag the median down and
    # make the very first step outside look like a mismatch (observed on large
    # text blocks, which refused to grow at all).
    ref = float(np.percentile(inside, 75))
    tol = 28.0  # grey levels of tolerance before we call it 'not paper'

    # No fixed cap: growth must stop at the paper edge, not at an arbitrary
    # budget. With limit=220 most blocks were hitting the ceiling instead.
    if limit is None:
        limit = max(gray.shape)

    moved = 0
    for step in range(1, limit + 1):
        if axis == 0:  # vertical growth
            yy = y - step if side < 0 else y + h + step - 1
            if yy < 0 or yy >= gray.shape[0]:
                break
            line = gray[yy, x:x + w]
        else:          # horizontal growth
            xx = x - step if side < 0 else x + w + step - 1
            if xx < 0 or xx >= gray.shape[1]:
                break
            line = gray[y:y + h, xx]
        if line.size == 0:
            break
        # Use a high percentile: text pixels are dark, paper is the bright part.
        level = float(np.percentile(line, 75))
        if abs(level - ref) > tol:
            break
        moved = step
    return moved


def grow(img, box, max_side_frac=0.35):
    """
    Grow to the paper edge, but cap the SIDEWAYS growth.

    Domain rule: a receipt is a narrow, tall rectangle. Growing far to the left
    or right of its own text means we have walked onto the neighbouring receipt
    — which is exactly how uncapped growth turned five receipts into three.
    Vertical growth stays unbounded: that direction is where header and total
    live, and merging those back in is the whole point.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x, y, w, h = box
    side_cap = int(w * max_side_frac)

    up = paper_profile(gray, box, 0, -1)
    down = paper_profile(gray, box, 0, +1)
    left = min(paper_profile(gray, box, 1, -1), side_cap)
    right = min(paper_profile(gray, box, 1, +1), side_cap)
    nx = max(0, x - left)
    ny = max(0, y - up)
    nx2 = min(img.shape[1], x + w + right)
    ny2 = min(img.shape[0], y + h + down)
    return [nx, ny, nx2 - nx, ny2 - ny]


def iou(a, b):
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix = max(0, min(ax2, bx2) - max(a[0], b[0]))
    iy = max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


def contains(big, small, frac=0.85):
    """Is `small` essentially inside `big`?"""
    sx2, sy2 = small[0] + small[2], small[1] + small[3]
    bx2, by2 = big[0] + big[2], big[1] + big[3]
    ix = max(0, min(sx2, bx2) - max(small[0], big[0]))
    iy = max(0, min(sy2, by2) - max(small[1], big[1]))
    area = small[2] * small[3]
    return area > 0 and (ix * iy) / area >= frac


def x_overlap(a, b):
    """Fraction of the narrower box's width shared with the other."""
    ax2, bx2 = a[0] + a[2], b[0] + b[2]
    inter = max(0, min(ax2, bx2) - max(a[0], b[0]))
    return inter / float(min(a[2], b[2])) if min(a[2], b[2]) else 0.0


def merge_overlapping(boxes, thr=0.30, x_thr=0.55, gap_frac=0.05):
    """
    Recompose the fragments of one receipt.

    Three ways two boxes belong together, applied repeatedly until nothing
    changes (one pass is not enough: a receipt can arrive in four pieces, and
    merging A+B may only then bring the union close enough to C):

      1. one is contained in the other (credit-card slip inside its receipt)
      2. they overlap substantially (IoU)
      3. they sit in the same vertical column and are close vertically — this
         is the header/body/total case, where the pieces do not overlap at all
         but clearly belong to the same sheet
    """
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out = []
        for b in sorted(boxes, key=lambda z: z[2] * z[3], reverse=True):
            hit = False
            for i, o in enumerate(out):
                if contains(o, b):
                    hit = True
                    break

                gap = max(b[1], o[1]) - min(b[1] + b[3], o[1] + o[3])
                same_column = x_overlap(b, o) >= x_thr
                near = gap <= gap_frac * max(b[3], o[3])

                if iou(b, o) >= thr or (same_column and near):
                    x1, y1 = min(b[0], o[0]), min(b[1], o[1])
                    x2 = max(b[0] + b[2], o[0] + o[2])
                    y2 = max(b[1] + b[3], o[1] + o[3])
                    out[i] = [x1, y1, x2 - x1, y2 - y1]
                    hit = True
                    changed = True
                    break
            if not hit:
                out.append(list(b))
        boxes = out
    return boxes


def ink_ok(binary, box, min_lines=3, min_breaks=8.0):
    """
    Does this region actually contain printed text?

    Counting horizontal ink runs is not enough: wood grain on the table also
    produces long horizontal streaks and used to pass as a receipt. What
    distinguishes writing is that a text line is BROKEN — words separated by
    spaces — while a wood vein runs continuously across the region.

    So we also require the average text line to break into several pieces.
    Measured on the region that exposed the problem: the receipt averages 26.7
    ink runs per row, the wood strip only 4.7. The threshold sits between them.
    """
    x, y, w, h = box
    patch = binary[y:y + h, x:x + w]
    if patch.size == 0 or w < 8:
        return False
    if (patch > 0).mean() < 0.02:
        return False

    rows = (patch > 0).sum(axis=1) / float(w)
    active = rows > 0.05

    lines, prev = 0, False
    line_rows = []
    for idx, a in enumerate(active):
        if a and not prev:
            lines += 1
        if a:
            line_rows.append(idx)
        prev = a
    if lines < min_lines or not line_rows:
        return False

    # Average number of ink runs per text row: words, not one long streak.
    breaks = []
    for idx in line_rows[::max(1, len(line_rows) // 40)]:
        row = patch[idx] > 0
        runs, prev_px = 0, False
        for px in row:
            if px and not prev_px:
                runs += 1
            prev_px = px
        breaks.append(runs)
    return bool(breaks) and (sum(breaks) / len(breaks)) >= min_breaks


def segment(img):
    boxes, binary = text_blocks(img)
    grown = [grow(img, b) for b in boxes]
    merged = merge_overlapping(grown)
    return [b for b in merged if ink_ok(binary, b)], boxes


OUT_DIR = "exports/bottomup"
PALETTE = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 200),
           (255, 0, 255), (0, 128, 255), (128, 0, 255), (0, 255, 128)]


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
    cv2.putText(header, title, (12, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return np.vstack([header, sheet])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"{'foto':<12} {'reali':>5} {'testo':>6} {'dopo crescita':>14}")
    print("-" * 46)
    exact = below = 0
    for key, truth in CASES:
        img = cv2.imread(os.path.join(CACHE, key + ".jpg"))
        if img is None:
            print(f"{key:<12} {truth:5d}   (non in cache)")
            continue
        final, raw = segment(img)
        n = len(final)
        print(f"{key:<12} {truth:5d} {len(raw):6d} {n:14d}")
        if n == truth:
            exact += 1
        if n < truth:
            below += 1

        final.sort(key=lambda b: b[0])
        esito = "OK" if n == truth else ("sotto-conta" if n < truth else "sovra-conta")
        title = f"{key}   reali={truth}   trovati={n}   {esito}"
        cv2.imwrite(os.path.join(OUT_DIR, f"{key}_bottomup.jpg"),
                    contact_sheet(img, final, title),
                    [cv2.IMWRITE_JPEG_QUALITY, 80])

    print()
    print(f"esatti: {exact}/{len(CASES)}   sotto-conta: {below}")
    print(f"\nFogli visivi in {OUT_DIR}/")


if __name__ == "__main__":
    main()
