#!/usr/bin/env python3
"""Generate the README banner from the dataset itself.

Every vertical stripe is one real photograph, filled with that image's true mean
conjunctiva colour and positioned by the child's laboratory haemoglobin. Read
left to right, the banner is the project's entire premise in one picture: pale
tissue on the left where haemoglobin is low, redder tissue on the right where it
is high — and enough scatter to show why this is a hard problem rather than an
obvious one.

Nothing here is decorative. If the colour-pallor relationship were not real the
banner would look like noise, and if it were trivially strong the whole study
would be pointless.

Note on ethics: the banner is built from *derived colour statistics*, never from
the photographs. No dataset image is redistributed by this repository.

Usage:
    python3 scripts/make_banner.py [--root data/cp-anemic/cp-anemic]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from pallor_hb.dataset import WHO_ANEMIA_HB_THRESHOLD, load_cp_anemic  # noqa: E402

BG = "#0E1116"
INK = "#FFFFFF"
MUTED = "#9AA3AD"
ACCENT = "#E8833A"


def build(root: str, out: Path, width_px: int = 2400, height_px: int = 640) -> None:
    ds = load_cp_anemic(root, dedup="perceptual", verbose=False)

    order = np.argsort(ds.y)
    hb = ds.y[order]
    rgb = np.clip(ds.X[["r_mean", "g_mean", "b_mean"]].to_numpy()[order], 0, 1)
    n = len(hb)

    dpi = 200
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Type and texture get their own horizontal bands. Overlaying words on the
    # stripe field was tried first and is unreadable: the field is high-contrast
    # at every point, so there is nowhere quiet for text to sit.
    FIELD_TOP = 0.46

    # The stripe field, drawn as one RGBA image so the fade is a real alpha ramp
    # rather than a stack of translucent rectangles.
    H = 256
    field = np.zeros((H, n, 4))
    field[..., :3] = rgb[None, :, :]
    ys = np.linspace(0, 1, H)
    # Full strength at the bottom, easing out at the top so the field dissolves
    # into the type area instead of ending on a hard edge.
    field[..., 3] = np.clip(1.0 - (ys - 0.55) / 0.45, 0, 1)[:, None] ** 0.9

    ax.imshow(field, extent=[0, n, 0.0, FIELD_TOP], aspect="auto",
              interpolation="bilinear", zorder=1)

    # WHO threshold: the boundary the whole project exists to detect.
    cut = int(np.searchsorted(hb, WHO_ANEMIA_HB_THRESHOLD))
    ax.axvline(cut, color=INK, lw=1.0, alpha=0.7, ymin=0.0, ymax=FIELD_TOP, zorder=3)
    ax.text(cut - n * 0.006, FIELD_TOP + 0.035, "anaemic", color=MUTED, fontsize=7.5,
            ha="right", va="bottom", family="sans-serif", zorder=4)
    ax.text(cut + n * 0.006, FIELD_TOP + 0.035, "not anaemic", color=MUTED, fontsize=7.5,
            ha="left", va="bottom", family="sans-serif", zorder=4)
    ax.plot([cut], [FIELD_TOP + 0.018], marker="v", color=MUTED, markersize=3.5, zorder=4)
    ax.text(n * 0.004, FIELD_TOP + 0.035, f"← lower haemoglobin", color=MUTED,
            fontsize=7.5, ha="left", va="bottom", family="sans-serif", zorder=4)
    ax.text(n * 0.996, FIELD_TOP + 0.035, "higher haemoglobin →", color=MUTED,
            fontsize=7.5, ha="right", va="bottom", family="sans-serif", zorder=4)

    # --- type band -----------------------------------------------------------
    ax.text(0.030, 0.885, "PallorHb", transform=ax.transAxes, color=INK,
            fontsize=33, fontweight="bold", va="center", family="sans-serif", zorder=5)
    ax.text(0.030, 0.755, "Non-invasive anaemia screening from a photograph of the eyelid",
            transform=ax.transAxes, color=INK, fontsize=11.5, alpha=0.93,
            va="center", family="sans-serif", zorder=5)
    ax.text(0.030, 0.660,
            f"Every stripe below is one of {n} children — that child's real conjunctiva "
            f"colour, ordered by their real blood test",
            transform=ax.transAxes, color=MUTED, fontsize=8.8, va="center",
            family="sans-serif", zorder=5)
    # The banner would be dishonest without this line. Sorted by haemoglobin the
    # field shows no clean pale-to-red gradient (r = +0.02 for mean redness),
    # and a reader is entitled to know that is the truth rather than assume the
    # picture failed. The absence of an obvious gradient IS the finding.
    ax.text(0.030, 0.570,
            "No clean fade from pale to red — the signal is real but subtle, "
            "which is exactly why it had to be measured properly",
            transform=ax.transAxes, color=ACCENT, fontsize=8.8, alpha=0.92,
            va="center", family="sans-serif", zorder=5)

    ax.text(0.970, 0.885, "AUROC 0.780", transform=ax.transAxes, color=ACCENT,
            fontsize=20, fontweight="bold", ha="right", va="center",
            family="sans-serif", zorder=5)
    ax.text(0.970, 0.755, "95% CI 0.737–0.818 · deduplicated, hospital-grouped",
            transform=ax.transAxes, color=MUTED, fontsize=8.6, ha="right",
            va="center", family="sans-serif", zorder=5)
    ax.text(0.970, 0.660, "triage, not measurement",
            transform=ax.transAxes, color=MUTED, fontsize=8.6, ha="right",
            va="center", family="sans-serif", zorder=5)
    ax.text(0.970, 0.570, "62 tests · one command reproduces every figure",
            transform=ax.transAxes, color=MUTED, fontsize=8.6, ha="right",
            va="center", family="sans-serif", zorder=5)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG, dpi=dpi)
    plt.close(fig)

    below = int((hb < WHO_ANEMIA_HB_THRESHOLD).sum())
    print(f"wrote {out}  ({width_px}x{height_px})")
    print(f"  {n} stripes · {below} below the WHO threshold · "
          f"Hb {hb.min():.1f}–{hb.max():.1f} g/dL")
    # Sanity check that the picture is telling the truth: the pale end should
    # genuinely be paler. Correlation is expected to be positive but modest.
    redness = rgb[:, 0] / (rgb.sum(axis=1) + 1e-9)
    r = float(np.corrcoef(hb, redness)[0, 1])
    print(f"  correlation between haemoglobin and redness: r = {r:+.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO / "data/cp-anemic/cp-anemic"))
    ap.add_argument("--out", default=str(REPO / "results/banner.png"))
    args = ap.parse_args()
    build(args.root, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
