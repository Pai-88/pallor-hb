#!/usr/bin/env python3
"""Pass 3: find same-photograph pairs that survive hash + thumbnail dedup.

Shifted or re-cropped copies of one photograph carry different bytes (defeats
SHA-256) and different ROI bounding boxes (defeats the bbox-normalised 32x32
thumbnail). This pass catches them by aligning full-resolution canvases under
small translations and comparing pixels inside the joint conjunctiva mask.

Candidate generation uses TWO independent, generous prefilters (union):
  A. bbox-thumbnail MAD < 20      (catches near-aligned crops)
  B. ROI colour-histogram distance (translation-invariant, catches the rest)
Every candidate is then verified at full resolution: best masked mean-abs-diff
over integer shifts up to +/-30 px (coarse stride-3 search, then +/-2 refine),
recorded both raw and after mean-brightness compensation.

Output: results/pass3_pairs.csv with one row per candidate pair and its
verified distances, for threshold selection and visual inspection.
"""
from __future__ import annotations

import sys
import pathlib
import numpy as np
import pandas as pd
from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from pallor_hb.dataset import _roi_thumbnail  # noqa: E402

ROOT = REPO / "data/cp-anemic/cp-anemic"
PKG = pathlib.Path.home() / "Documents/pallor_meeting_prep/asare_package"
OUT = REPO / "results/pass3_pairs.csv"

THUMB_CUTOFF = 20.0
HIST_CUTOFF = 0.10          # L1 distance between normalised 3x32-bin ROI histograms
MAX_SHIFT = 30
MIN_OVERLAP_FRAC = 0.60     # joint mask must cover >=60% of the smaller ROI


def canvas_and_mask(path):
    a = np.array(Image.open(path).convert("RGBA")).astype(np.float32)
    return a[:, :, :3], a[:, :, 3] >= 128


def roi_hist(rgb, mask):
    h = [np.histogram(rgb[:, :, c][mask], bins=32, range=(0, 256))[0] for c in range(3)]
    h = np.concatenate(h).astype(np.float64)
    return h / h.sum()


def aligned_diff(A, ma, B, mb, max_shift=MAX_SHIFT):
    """Best masked mean-abs-diff over integer shifts (coarse stride 3, refine +/-2)."""
    smaller_roi = min(ma.sum(), mb.sum())

    def diff_at(dy, dx, compensate):
        ay0, by0 = max(0, dy), max(0, -dy)
        ax0, bx0 = max(0, dx), max(0, -dx)
        h = min(A.shape[0] - ay0, B.shape[0] - by0)
        w = min(A.shape[1] - ax0, B.shape[1] - bx0)
        if h < 20 or w < 20:
            return np.inf
        mm = ma[ay0:ay0 + h, ax0:ax0 + w] & mb[by0:by0 + h, bx0:bx0 + w]
        if mm.sum() < MIN_OVERLAP_FRAC * smaller_roi:
            return np.inf
        sa = A[ay0:ay0 + h, ax0:ax0 + w][mm]
        sb = B[by0:by0 + h, bx0:bx0 + w][mm]
        if compensate:
            sa = sa - sa.mean(axis=0, keepdims=True)
            sb = sb - sb.mean(axis=0, keepdims=True)
        return float(np.abs(sa - sb).mean())

    best = {}
    for compensate in (False, True):
        coarse = [(diff_at(dy, dx, compensate), dy, dx)
                  for dy in range(-max_shift, max_shift + 1, 3)
                  for dx in range(-max_shift, max_shift + 1, 3)]
        d0, dy0, dx0 = min(coarse)
        fine = [(diff_at(dy, dx, compensate), dy, dx)
                for dy in range(dy0 - 2, dy0 + 3)
                for dx in range(dx0 - 2, dx0 + 3)]
        d1, dy1, dx1 = min(fine)
        best[compensate] = (min(d0, d1), dy1, dx1)
    return best


def main():
    per = pd.read_csv(PKG / "cp_anemic_duplicate_groups.csv")
    paths = {p.name: p for p in ROOT.rglob("Image_*.png")}
    reps = per.drop_duplicates("group_id", keep="first").reset_index(drop=True)
    n = len(reps)
    print(f"{n} pass-2 group representatives")

    print("loading canvases + signatures ...", flush=True)
    canv, masks, hists = [], [], []
    for f in reps["filename"]:
        rgb, m = canvas_and_mask(paths[f])
        canv.append(rgb); masks.append(m); hists.append(roi_hist(rgb, m))
    hists = np.stack(hists)
    thumbs = np.stack([_roi_thumbnail(paths[f]) for f in reps["filename"]])

    cands = set()
    for i in range(n - 1):
        tm = np.abs(thumbs[i + 1:] - thumbs[i]).mean(axis=1)
        hd = np.abs(hists[i + 1:] - hists[i]).sum(axis=1)
        for off in np.where((tm < THUMB_CUTOFF) | (hd < HIST_CUTOFF))[0]:
            cands.add((i, i + 1 + int(off)))
    cands = sorted(cands)
    print(f"candidates (thumbnail<{THUMB_CUTOFF} OR histogram<{HIST_CUTOFF}): {len(cands)}", flush=True)

    rows = []
    for k, (i, j) in enumerate(cands):
        b = aligned_diff(canv[i], masks[i], canv[j], masks[j])
        (d_raw, dy, dx), (d_comp, _, _) = b[False], b[True]
        rows.append({
            "file_a": reps["filename"].iat[i], "file_b": reps["filename"].iat[j],
            "group_a": int(reps["group_id"].iat[i]), "group_b": int(reps["group_id"].iat[j]),
            "site_a": reps["site"].iat[i], "site_b": reps["site"].iat[j],
            "hb_a": float(reps["hb_g_dl"].iat[i]), "hb_b": float(reps["hb_g_dl"].iat[j]),
            "aligned_diff": round(d_raw, 4), "aligned_diff_meancomp": round(d_comp, 4),
            "shift_dy": dy, "shift_dx": dx,
        })
        if (k + 1) % 200 == 0:
            print(f"  {k + 1}/{len(cands)} verified", flush=True)

    df = pd.DataFrame(rows).sort_values("aligned_diff")
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT} ({len(df)} pairs)")
    print("\ndistance distribution (raw aligned diff):")
    for lo, hi in [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 10), (10, 1e9)]:
        c = int(((df.aligned_diff >= lo) & (df.aligned_diff < hi)).sum())
        print(f"  [{lo:>4}, {hi if hi < 1e9 else 'inf':>4}): {c}")
    print("\nsmallest 5 diffs at/above 3.0 (gap check):",
          df[df.aligned_diff >= 3.0].aligned_diff.head(5).tolist())
    print("largest 5 diffs below 3.0:",
          df[df.aligned_diff < 3.0].aligned_diff.tail(5).tolist())


if __name__ == "__main__":
    main()
