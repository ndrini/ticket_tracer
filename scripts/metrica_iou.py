"""
Measure segmentation quality with IoU instead of a receipt count.

Counting is binary and hides bad crops. Two real cases from this project both
scored as successes: one photo counted 2/2 with boxes covering 62% and 55% of
the frame and overlapping heavily, and one counted 1/1 where the single box WAS
the whole frame — the segmenter had not found the receipt, it had returned the
photo. IoU exposes both immediately (a full-frame box over a quarter-frame
receipt scores about 0.25).

Reported here:
  - mean IoU over matched pairs      how tight the crops are
  - precision / recall / F1 at 0.5   how many receipts found, how much rubbish
  - under-segmentation               one box swallowing two or more receipts
  - over-segmentation                one receipt broken across several boxes

The last two are counted separately because they are opposite failures and a
single score would let them cancel out. Under-segmentation is the more
dangerous of the two: it silently drops a whole purchase while still looking
like a valid crop.

mAP is deliberately not used. It averages Average Precision across object
classes, and here there is exactly one class ("receipt"), so the mean would be
over a single term. AP also needs a confidence score to rank predictions by,
which a geometric algorithm does not produce.

Usage:
    uv run python scripts/metrica_iou.py <cartella> <verita.json>
    uv run python scripts/metrica_iou.py <cartella> <verita.json> --scrivi-bozza
"""
import json
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segmenta_detector import segment  # noqa: E402

IOU_THRESHOLD = 0.5


def iou(a, b):
    """Intersection over union of two [x, y, w, h] boxes."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def covers(box, truth, frac=0.7):
    """Does `box` contain most of `truth`? Used to spot merged receipts."""
    ix = max(0, min(box[0] + box[2], truth[0] + truth[2]) - max(box[0], truth[0]))
    iy = max(0, min(box[1] + box[3], truth[1] + truth[3]) - max(box[1], truth[1]))
    area = truth[2] * truth[3]
    return area > 0 and (ix * iy) / area >= frac


def match(pred, truth, threshold=IOU_THRESHOLD):
    """
    Greedy one-to-one pairing, best IoU first.

    One-to-one matters: without it a single huge box could claim every receipt
    in the photo and score a perfect recall, which is precisely the failure
    this metric exists to catch.
    """
    pairs = sorted(
        ((iou(p, t), pi, ti) for pi, p in enumerate(pred) for ti, t in enumerate(truth)),
        reverse=True)
    used_p, used_t, matched = set(), set(), []
    for score, pi, ti in pairs:
        if score < threshold or pi in used_p or ti in used_t:
            continue
        used_p.add(pi)
        used_t.add(ti)
        matched.append((pi, ti, score))
    return matched, used_p, used_t


def evaluate(pred, truth):
    """Per-photo figures; the caller aggregates them."""
    matched, used_p, used_t = match(pred, truth)

    under = sum(1 for p in pred if sum(covers(p, t) for t in truth) >= 2)
    over = sum(1 for t in truth if sum(covers(p, t, 0.35) for p in pred) >= 2)

    return {
        "tp": len(matched),
        "fp": len(pred) - len(used_p),
        "fn": len(truth) - len(used_t),
        "ious": [m[2] for m in matched],
        "under": under,
        "over": over,
        "n_pred": len(pred),
        "n_truth": len(truth),
    }


def draft(folder, out_path):
    """
    Write the current output as a starting point for the ground truth.

    Hand-correcting a draft is faster than drawing every box, but it carries a
    real risk: boxes the algorithm got wrong become "truth" and the metric then
    certifies its own mistakes. The file must be reviewed against the contact
    sheets before it is trusted.
    """
    truth = {}
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        img = cv2.imread(os.path.join(folder, name))
        if img is None:
            continue
        boxes = sorted(segment(img), key=lambda b: b[0])
        truth[name] = [[int(v) for v in b] for b in boxes]
        print(f"  {name:<34} {len(boxes)} box")

    with open(out_path, "w") as fh:
        json.dump(truth, fh, indent=2, ensure_ascii=False)
    print(f"\nBozza in {out_path}")
    print("ATTENZIONE: e' l'output attuale, non una verita'. Va corretta a mano")
    print("confrontandola con i fogli visivi, altrimenti la metrica misura se")
    print("stessa.")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    folder, truth_path = argv[0], argv[1]

    if "--scrivi-bozza" in argv:
        draft(folder, truth_path)
        return 0

    if not os.path.exists(truth_path):
        print(f"Verita' non trovata: {truth_path}")
        print("Creane una bozza con --scrivi-bozza, poi correggila a mano.")
        return 1

    with open(truth_path) as fh:
        truth_all = json.load(fh)

    total = {"tp": 0, "fp": 0, "fn": 0, "under": 0, "over": 0}
    all_ious = []

    print(f"{'foto':<34} {'veri':>5} {'trov':>5} {'IoU med':>8} {'esito':>18}")
    print("-" * 74)
    for name in sorted(truth_all):
        path = os.path.join(folder, name)
        img = cv2.imread(path)
        if img is None:
            print(f"  {name:<32} (non leggibile)")
            continue
        pred = sorted(segment(img), key=lambda b: b[0])
        r = evaluate(pred, [list(b) for b in truth_all[name]])

        for k in total:
            total[k] += r[k]
        all_ious.extend(r["ious"])

        mean_iou = sum(r["ious"]) / len(r["ious"]) if r["ious"] else 0.0
        notes = []
        if r["fn"]:
            notes.append(f"{r['fn']} persi")
        if r["fp"]:
            notes.append(f"{r['fp']} spuri")
        if r["under"]:
            notes.append(f"{r['under']} fusi")
        if r["over"]:
            notes.append(f"{r['over']} spezzati")
        print(f"{name[:33]:<34} {r['n_truth']:5d} {r['n_pred']:5d} "
              f"{mean_iou:8.3f} {', '.join(notes) or 'OK':>18}")

    tp, fp, fn = total["tp"], total["fp"], total["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    print("-" * 74)
    print(f"IoU medio (coppie accoppiate) : {sum(all_ious) / len(all_ious) if all_ious else 0:.3f}")
    print(f"Precision  (IoU>={IOU_THRESHOLD})           : {precision:.3f}   ({tp} veri, {fp} spuri)")
    print(f"Recall     (IoU>={IOU_THRESHOLD})           : {recall:.3f}   ({tp} trovati, {fn} persi)")
    print(f"F1                            : {f1:.3f}")
    print(f"Sotto-segmentazione (fusi)    : {total['under']}")
    print(f"Sovra-segmentazione (spezzati): {total['over']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
