#!/usr/bin/env python
"""
Build the oriented-image cache used by the segmentation experiments.

Why a cache: _orient_whole_image runs OCR four times per photo (once per 90°
rotation) to pick the best one. That is ~2 minutes per image, and it made every
measurement script time out — four of them were killed mid-run before this
existed. Orientation is deterministic, so it is computed once and reused.

Usage:
    uv run python scripts/prepara_cache_orientamento.py
    uv run python scripts/prepara_cache_orientamento.py foto1.jpg foto2.jpg

Images already cached are skipped, so re-running is cheap.
"""
import os
import sys

import cv2

sys.path.insert(0, os.getcwd())
from app.etl.etl_engine import ReceiptPipeline  # noqa: E402

CACHE = "data/cache_oriented"

# The reference set: photos with a human-established receipt count.
# Keys match the short names used by scripts/segmenta_bottomup.py.
DEFAULT = {
    "07.47.51": "data/pictures_not_yet_used/2025-02-20 07.47.51.jpg",
    "07.53.17": "data/pictures_not_yet_used/2025-02-20 07.53.17.jpg",
    "07.57.06": "data/pictures_archived/2025-02-20 07.57.06.jpg",
    "10.33.47": "data/pictures_not_yet_used/2025-03-15 10.33.47.jpg",
    "21.12.47": "data/pictures_not_yet_used/2025-06-24 21.12.47.jpg",
    "21.25.11": "data/pictures_not_yet_used/2025-06-29 21.25.11.jpg",
}


def cache_one(pipeline, key, path):
    out = os.path.join(CACHE, key + ".jpg")
    if os.path.exists(out):
        print(f"  gia' in cache  {key}")
        return False
    raw = cv2.imread(path)
    if raw is None:
        print(f"  NON LEGGIBILE  {key}  ({path})")
        return False
    img = pipeline._resize_safe(raw, 2000)
    img = pipeline._orient_whole_image(img, 800)
    cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"  scritto        {key}  {img.shape[1]}x{img.shape[0]}")
    return True


def main(argv):
    os.makedirs(CACHE, exist_ok=True)
    pipeline = ReceiptPipeline()

    if argv:
        targets = {os.path.splitext(os.path.basename(p))[0]: p for p in argv}
    else:
        targets = DEFAULT

    print(f"Cache orientamento in {CACHE}/\n")
    written = 0
    for key, path in targets.items():
        written += cache_one(pipeline, key, path)

    print(f"\n{written} nuove, {len(targets) - written} gia' presenti.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
