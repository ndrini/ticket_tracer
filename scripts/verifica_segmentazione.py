"""
Run the detector-based segmentation over a folder and write one contact sheet
per photo, for human inspection.

Separate from segmenta_detector.py because that script measures against the six
reference photos with known counts. This one has no ground truth: it exists so
that receipts never seen during development can be judged by eye, which is the
only check that catches crops that are counted right but cut wrong.

Usage:
    uv run python scripts/verifica_segmentazione.py <cartella_immagini> [uscita]
"""
import os
import sys

import cv2

sys.path.insert(0, os.getcwd())
from segmenta_detector import contact_sheet, segment  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    src = argv[0]
    out_dir = argv[1] if len(argv) > 1 else "exports/verifica"
    os.makedirs(out_dir, exist_ok=True)

    names = sorted(f for f in os.listdir(src)
                   if f.lower().endswith((".jpg", ".jpeg", ".png")))
    print(f"{len(names)} immagini da {src}/\n")

    total = 0
    for name in names:
        img = cv2.imread(os.path.join(src, name))
        if img is None:
            print(f"  NON LEGGIBILE  {name}")
            continue
        boxes = sorted(segment(img), key=lambda b: b[0])
        total += len(boxes)
        print(f"  {name:<34} {len(boxes)} scontrini")

        key = os.path.splitext(name)[0]
        title = f"{key}   trovati={len(boxes)}"
        cv2.imwrite(os.path.join(out_dir, f"{key}_seg.jpg"),
                    contact_sheet(img, boxes, title),
                    [cv2.IMWRITE_JPEG_QUALITY, 80])

    print(f"\n{total} scontrini in {len(names)} foto.")
    print(f"Fogli visivi in {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
