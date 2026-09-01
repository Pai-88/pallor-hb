"""Publication-quality figures with one shared house style.

Every figure in the study is drawn through this module so that type, colour,
spacing and axis treatment are identical across them. Two deliberate choices:

- **Okabe-Ito palette.** Chosen for colourblind safety rather than aesthetics.
  Roughly 1 in 12 men has a red-green deficiency, and a clinical-screening figure
  whose "anemic" and "healthy" series are indistinguishable to part of its
  audience has failed at its only job.
- **Encoded twice, always.** Series differ in both colour *and* line style or
  marker, so the figures survive greyscale printing and photocopying.

Uncertainty is drawn wherever it exists. A bare point estimate at n = 383 invites
over-reading; a band or an error bar makes the sampling noise part of the message
rather than a footnote.
"""

from __future__ import annotations

import numpy as np

# Okabe-Ito colourblind-safe qualitative palette.
INK = "#1a1a1a"
GREY = "#8a8a8a"
GRID = "#dcdcdc"
ORANGE = "#E69F00"
SKY = "#56B4E9"
GREEN = "#009E73"
YELLOW = "#F0E442"
BLUE = "#0072B2"
VERMILLION = "#D55E00"
PURPLE = "#CC79A7"

PALETTE = [BLUE, VERMILLION, GREEN, ORANGE, PURPLE, SKY]


def _style():
    """Apply the shared rcParams and return the pyplot module."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.dpi": 200,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "medium",
        "axes.titlelocation": "left",
        "axes.titlepad": 10,
        "axes.labelsize": 9,
        "axes.labelcolor": INK,
        "axes.edgecolor": GREY,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "grid.alpha": 0.9,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "xtick.labelcolor": INK,
        "ytick.labelcolor": INK,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "text.color": INK,
    })
    return plt


def _titles(ax, title: str, subtitle: str | None = None) -> None:
    """Bold title with an optional grey subtitle line beneath it."""
    if subtitle:
        ax.set_title(f"{title}\n", loc="left")
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=8.5,
                color=GREY, va="bottom", ha="left")
    else:
        ax.set_title(title, loc="left")


def _bootstrap_roc_band(y_true, score, n_boot=500, seed=0):
    """Pointwise 95% band for a ROC curve, interpolated on a common FPR grid."""
    from sklearn.metrics import roc_curve

    rng = np.random.default_rng(seed)
    grid = np.linspace(0, 1, 101)
    curves = []
    n = len(y_true)
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        if len(np.unique(y_true[i])) < 2:
            continue
        fpr, tpr, _ = roc_curve(y_true[i], score[i])
        curves.append(np.interp(grid, fpr, tpr))
    if not curves:
        return grid, None, None
    c = np.vstack(curves)
    return grid, np.percentile(c, 2.5, axis=0), np.percentile(c, 97.5, axis=0)


def roc_figure(curves: dict, path: str, cutoff: float, band_for: str | None = None) -> None:
    """ROC curves for several configurations, with a bootstrap band on one.

    `curves` maps label -> (reference Hb, predicted Hb). Each entry carries its
    own reference array because the leaky configuration is scored on a different
    (un-deduplicated) row set, and showing them on one axis is what makes the
    size of the leakage visible instead of merely asserted.
    """
    from sklearn.metrics import roc_curve

    plt = _style()
    fig, ax = plt.subplots(figsize=(5.4, 4.8))

    styles = [(BLUE, "--"), (VERMILLION, "-"), (GREY, ":")]
    for (label, (y_hb, pred)), (colour, ls) in zip(curves.items(), styles):
        y_bin = (np.asarray(y_hb, dtype=float) < cutoff).astype(int)
        score = -np.asarray(pred, dtype=float)      # anemia is LOW Hb
        if band_for and label.startswith(band_for):
            g, lo, hi = _bootstrap_roc_band(y_bin, score)
            if lo is not None:
                ax.fill_between(g, lo, hi, color=colour, alpha=0.15, lw=0)
        fpr, tpr, _ = roc_curve(y_bin, score)
        ax.plot(fpr, tpr, ls, color=colour, lw=2.0, label=label, solid_capstyle="round")

    ax.plot([0, 1], [0, 1], color=GREY, lw=0.9, alpha=0.7, zorder=0)
    ax.text(0.62, 0.55, "chance", color=GREY, fontsize=8, rotation=38, va="center")
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)
    ax.set_aspect("equal")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("Sensitivity")
    _titles(ax, "Anaemia screening performance",
            f"WHO threshold Hb < {cutoff:g} g/dL · shaded band = 95% bootstrap CI")
    ax.legend(loc="lower right", handlelength=2.2)
    fig.savefig(path)
    plt.close(fig)


def leakage_waterfall(rows: list[dict], path: str) -> None:
    """Horizontal AUROC intervals showing optimism removed step by step.

    A waterfall rather than a bar chart: each row is a confidence interval, so
    the reader can see immediately that the top and bottom intervals do not
    overlap while adjacent ones do.
    """
    plt = _style()
    fig, ax = plt.subplots(figsize=(6.6, 3.2))

    # Sample size belongs beside the label, not floating in the plot area: each
    # row is a different subset, and the reader needs n to read the interval.
    labels = [f"{r['label']}\n(n = {r['n']})" for r in rows]
    y = np.arange(len(rows))[::-1]
    for yi, r in zip(y, rows):
        colour = VERMILLION if r.get("headline") else (BLUE if r.get("leaky") else GREY)
        ax.plot([r["lo"], r["hi"]], [yi, yi], color=colour, lw=2.6,
                solid_capstyle="round", alpha=0.85)
        ax.plot(r["auroc"], yi, "o", color=colour, ms=7,
                markeredgecolor="white", markeredgewidth=1.1, zorder=3)
        ax.text(r["hi"] + 0.006, yi, f"{r['auroc']:.3f}", va="center",
                fontsize=8.5, color=colour, fontweight="medium")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xlabel("AUROC (95% CI)")
    ax.grid(axis="y", visible=False)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    _titles(ax, "Each step removes one source of optimism",
            "Duplicate images and shared collection sites both inflate apparent performance")
    fig.savefig(path)
    plt.close(fig)


def site_forest(loso, path: str, pooled: float | None = None) -> None:
    """Forest plot of leave-one-site-out AUROC, marker area scales with test-set size.

    Sizing by n is what stops a 0.875 on ten patients from reading as
    the strongest site on the chart.
    """
    plt = _style()
    d = loso.dropna(subset=["auroc"]).sort_values("n_test")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))

    y = np.arange(len(d))
    sizes = 26 + 210 * (d.n_test / d.n_test.max())
    ax.scatter(d.auroc, y, s=sizes, color=BLUE, alpha=0.75,
               edgecolor="white", linewidth=1.1, zorder=3)
    if pooled is not None:
        ax.axvline(pooled, color=VERMILLION, lw=1.4, ls="--", zorder=1)
        # Anchored to the lowest row so it cannot collide with the subtitle.
        ax.text(pooled + 0.006, -0.42, f"pooled {pooled:.3f}", color=VERMILLION,
                fontsize=8, va="bottom", ha="left")
    ax.axvline(0.5, color=GREY, lw=0.9, zorder=0)

    # Trim only the redundant trailing word, never mid-word.
    def _short(s: str) -> str:
        s = s.replace(" Government Hospital", " Gov. Hosp.")
        s = s.replace(" Teaching Hospital", " Teaching Hosp.")
        s = s.replace(" Municipal Hospital", " Municipal Hosp.")
        s = s.replace(" Regional Hospital", " Regional Hosp.")
        s = s.replace(" District Hospital", " District Hosp.")
        return s

    labels = [f"{_short(s)}  (n={n})" for s, n in zip(d.site, d.n_test)]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlim(0.4, 1.05)
    ax.set_xlabel("AUROC on the held-out hospital")
    ax.grid(axis="y", visible=False)
    _titles(ax, "Generalisation to an unseen hospital",
            "Trained on nine sites, tested on the tenth · marker area scales with test-set size")
    fig.savefig(path)
    plt.close(fig)


def calibration_figure(bins: list[dict], path: str, ece: float, brier: float) -> None:
    """Reliability curve with a histogram of predicted probabilities beneath."""
    plt = _style()
    fig, (ax, axh) = plt.subplots(
        2, 1, figsize=(4.9, 5.4), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12})

    mp = np.array([b["mean_pred"] for b in bins])
    ob = np.array([b["observed"] for b in bins])
    ct = np.array([b["count"] for b in bins], dtype=float)

    ax.plot([0, 1], [0, 1], color=GREY, lw=1.0, ls="--", zorder=0)
    ax.text(0.70, 0.66, "perfect", color=GREY, fontsize=8, rotation=38)
    # Binomial 95% interval per bin: with ~48 cases a bin, the observed rate is
    # itself uncertain, and without this the wiggle looks like real structure.
    err = 1.96 * np.sqrt(np.clip(ob * (1 - ob), 1e-9, None) / ct)
    ax.errorbar(mp, ob, yerr=err, fmt="none", ecolor=VERMILLION,
                elinewidth=1.0, capsize=2.5, alpha=0.55, zorder=2)
    ax.plot(mp, ob, "-o", color=VERMILLION, lw=1.8, ms=6,
            markeredgecolor="white", markeredgewidth=1.1, zorder=3)
    ax.set_ylabel("Observed anaemia rate")
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlim(-0.03, 1.03)
    _titles(ax, "Calibration of predicted anaemia risk",
            f"Equal-count bins · ECE {ece:.3f} · Brier {brier:.3f} · bars = 95% binomial CI")

    # Equal-count bins have unequal widths, so a fixed bar width would overlap.
    widths = np.diff(np.concatenate([[mp[0]], (mp[1:] + mp[:-1]) / 2, [mp[-1]]]))
    widths = np.maximum(widths, 0.012)
    axh.bar(mp, ct, width=widths, color=BLUE, alpha=0.55, edgecolor="none")
    axh.set_xlabel("Predicted probability of anaemia")
    axh.set_ylabel("Count")
    axh.grid(axis="x", visible=False)
    fig.savefig(path)
    plt.close(fig)


def bland_altman_figure(y_true, y_pred, path: str) -> None:
    """Bland-Altman with limits of agreement and a fitted proportional-bias line.

    The regression of difference on mean is drawn because the failure mode here
    is not constant bias but *proportional* bias — the model shrinks toward the
    population mean, over-predicting anaemic children and under-predicting
    healthy ones. A flat mean-bias line alone would hide that.
    """
    plt = _style()
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mean = (y_true + y_pred) / 2
    diff = y_pred - y_true
    bias = float(diff.mean())
    sd = float(diff.std(ddof=1))
    lo, hi = bias - 1.96 * sd, bias + 1.96 * sd

    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    ax.scatter(mean, diff, s=13, color=BLUE, alpha=0.40, edgecolor="none", zorder=2)

    # Labels sit just ABOVE each line rather than centred on it — centring puts
    # the rule straight through the glyphs and makes the numbers unreadable.
    x_label = mean.max() + 0.25
    for val, colour, label in [(bias, VERMILLION, f"bias {bias:+.2f}"),
                               (hi, GREY, f"+1.96 SD  {hi:+.2f}"),
                               (lo, GREY, f"−1.96 SD  {lo:+.2f}")]:
        ax.axhline(val, color=colour, lw=1.3,
                   ls="-" if colour == VERMILLION else "--", zorder=3)
        ax.text(x_label, val + 0.12, label, va="bottom", ha="left",
                fontsize=8, color=colour)

    slope, intercept = np.polyfit(mean, diff, 1)
    xs = np.linspace(mean.min(), mean.max(), 50)
    ax.plot(xs, slope * xs + intercept, color=VERMILLION, lw=1.4, ls=":",
            zorder=4, label=f"proportional bias (slope {slope:+.2f})")

    ax.set_xlabel("Mean of predicted and reference Hb (g/dL)")
    ax.set_ylabel("Predicted − reference Hb (g/dL)")
    ax.set_xlim(mean.min() - 0.3, mean.max() + 2.6)
    _titles(ax, "Agreement with laboratory haemoglobin",
            f"Limits of agreement span {hi - lo:.1f} g/dL — too wide to report a Hb value")
    ax.legend(loc="lower left", handlelength=2.2)
    fig.savefig(path)
    plt.close(fig)


# Human-readable axis labels. Raw identifiers are fine in code and wrong in a
# figure a reader meets without the source beside them.
FEATURE_LABELS = {
    "r_mean": "Red (mean)",
    "g_mean": "Green (mean)",
    "b_mean": "Blue (mean)",
    "h_mean": "Hue (circular mean)",
    "h_concentration": "Hue concentration",
    "s_mean": "Saturation (mean)",
    "lab_l": "CIELAB L*  (lightness)",
    "lab_a": "CIELAB a*  (red–green)",
    "lab_b": "CIELAB b*  (blue–yellow)",
    "redness_index": "Redness index  r/(r+g+b)",
    "redness_p10": "Redness, 10th percentile",
    "rg_ratio": "Red / green ratio",
    "age": "Age (months)",
    "is_female": "Sex (female)",
}


def importance_figure(names, means, stds, path: str) -> None:
    """Permutation importance with error bars over repeats."""
    plt = _style()
    order = np.argsort(means)
    names = [FEATURE_LABELS.get(names[i], names[i]) for i in order]
    means = np.asarray(means)[order]
    stds = np.asarray(stds)[order]

    fig, ax = plt.subplots(figsize=(5.4, 0.34 * len(names) + 1.5))
    y = np.arange(len(names))
    ax.barh(y, means, xerr=stds, color=BLUE, alpha=0.8, height=0.68,
            error_kw={"ecolor": GREY, "elinewidth": 1.0, "capsize": 2.5})
    ax.axvline(0, color=GREY, lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8.5)
    ax.set_xlabel("Drop in AUROC when the feature is shuffled")
    ax.grid(axis="y", visible=False)
    _titles(ax, "Which colour features carry the signal",
            "Permutation importance on held-out folds · bars = ±1 SD over repeats")
    fig.savefig(path)
    plt.close(fig)


def learning_curve_figure(fractions, means, stds, path: str, n_total: int) -> None:
    """AUROC against training-set size, to show whether more data would help."""
    plt = _style()
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    n = np.asarray(fractions) * n_total
    means = np.asarray(means)
    stds = np.asarray(stds)

    ax.fill_between(n, means - stds, means + stds, color=BLUE, alpha=0.16, lw=0)
    ax.plot(n, means, "-o", color=BLUE, lw=1.9, ms=5.5,
            markeredgecolor="white", markeredgewidth=1.0)
    ax.axhline(0.5, color=GREY, lw=0.9, ls=":")
    ax.set_xlabel("Training images")
    ax.set_ylabel("AUROC on held-out sites")

    # State what this particular curve shows rather than how to read one in
    # general: a rising tail and a flat tail have opposite implications.
    tail_gain = float(means[-1] - means[-2]) if len(means) > 1 else 0.0
    verdict = ("still rising at full size — more images would likely help"
               if tail_gain > 0.005 else
               "flat at full size — more images alone would not help")
    _titles(ax, "Does more data help?",
            f"Shaded band = ±1 SD across repeats · {verdict}")
    fig.savefig(path)
    plt.close(fig)


def threshold_sensitivity_figure(thresholds, aurocs, ns, path: str) -> None:
    """Headline AUROC as a function of the duplicate-merging threshold.

    Guards against the obvious criticism that the reported result was produced by
    a conveniently chosen cutoff: if the curve is flat across the plausible range,
    the conclusion does not depend on the choice.
    """
    plt = _style()
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    ax.plot(thresholds, aurocs, "-o", color=VERMILLION, lw=1.9, ms=5.5,
            markeredgecolor="white", markeredgewidth=1.0, zorder=3)
    for t, a, n in zip(thresholds, aurocs, ns):
        ax.annotate(f"n={n}", (t, a), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=7.5, color=GREY)
    ax.set_xlabel("Duplicate-merging threshold (mean absolute pixel difference)")
    ax.set_ylabel("AUROC")
    ax.set_ylim(min(aurocs) - 0.05, max(aurocs) + 0.05)
    _titles(ax, "The conclusion does not hinge on the merging threshold",
            "Headline AUROC across the plausible range of the duplicate cutoff")
    fig.savefig(path)
    plt.close(fig)
