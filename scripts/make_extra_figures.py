"""Two additional figures for the paper, from the same out-of-fold predictions.

Reuses the exact headline configuration in run_full_analysis.py — perceptual
deduplication, site-grouped folds, colour features — so anything drawn here is
the same model the headline AUROC describes, not a refit.

    python3 scripts/make_extra_figures.py

Writes results/fig9_operating_point.png and results/fig10_pred_vs_actual.png.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from pallor_hb.dataset import WHO_ANEMIA_HB_THRESHOLD, load_cp_anemic
from pallor_hb.experiment import (FEATURE_SETS, classifier_oof_scores,
                                  out_of_fold_predictions)
from pallor_hb import plots

HEADLINE_FEATURES = "colour"
HEADLINE_SPLIT = "dedup_site"


def operating_point_figure(y_true, score, path):
    """Sensitivity and specificity against every achievable decision threshold.

    The paper argues that AUROC is not the number that decides deployability.
    This is that argument as a picture: it shows what a screening programme
    actually has to trade, and marks the two operating points quoted in the
    text — the WHO cutoff, and the threshold tuned to 90 % sensitivity.
    """
    plt = plots._style()
    order = np.argsort(score)
    thresholds = np.unique(score[order])

    sens, spec = [], []
    for t in thresholds:
        pred = score >= t
        tp = np.sum(pred & y_true)
        fn = np.sum(~pred & y_true)
        tn = np.sum(~pred & ~y_true)
        fp = np.sum(pred & ~y_true)
        sens.append(tp / (tp + fn) if (tp + fn) else np.nan)
        spec.append(tn / (tn + fp) if (tn + fp) else np.nan)
    sens, spec = np.asarray(sens), np.asarray(spec)

    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ax.plot(thresholds, sens, color=plots.BLUE, lw=2.0, label="Sensitivity")
    ax.plot(thresholds, spec, color=plots.VERMILLION, lw=2.0, label="Specificity")

    # the operating point actually used in the paper: score >= 0 is the WHO cutoff
    # because score is the negated Hb prediction relative to the threshold
    idx_who = int(np.argmin(np.abs(thresholds)))
    ax.axvline(thresholds[idx_who], color="0.45", ls="--", lw=1.0)
    ax.annotate(f"WHO cutoff\nsens {sens[idx_who]:.2f} / spec {spec[idx_who]:.2f}",
                xy=(thresholds[idx_who], 0.12), xytext=(6, 0),
                textcoords="offset points", fontsize=8, color="0.30")

    # the 90 %-sensitivity point quoted in the text
    ok = np.where(sens >= 0.90)[0]
    if len(ok):
        i90 = ok[-1]
        ax.plot([thresholds[i90]], [spec[i90]], "o", color=plots.VERMILLION, ms=7,
                zorder=5)
        ax.annotate(f"at 90 % sensitivity,\nspecificity is only {spec[i90]:.2f}",
                    xy=(thresholds[i90], spec[i90]),
                    xytext=(-118, -46), textcoords="offset points",
                    fontsize=8.5, color=plots.VERMILLION, zorder=6,
                    arrowprops=dict(arrowstyle="->", color=plots.VERMILLION, lw=1.0))

    ax.set_xlabel("Decision threshold on the screening score")
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, loc="center right", fontsize=9)
    plots._titles(ax, "What a screening programme actually trades",
                  "Raising sensitivity costs specificity far faster than AUROC suggests")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return sens, spec


def pred_vs_actual_figure(y_true, y_pred, path):
    """Predicted against measured haemoglobin, with the identity line.

    Bland-Altman shows the same shrinkage as a bias term; this shows it
    directly. Points collapsing toward the horizontal is the model regressing
    to the population mean, which is what makes it unusable as a meter.
    """
    plt = plots._style()
    fig, ax = plt.subplots(figsize=(5.6, 5.2))

    anemic = y_true < WHO_ANEMIA_HB_THRESHOLD
    ax.scatter(y_true[~anemic], y_pred[~anemic], s=16, alpha=0.55,
               color=plots.BLUE, edgecolor="none", label="Not anaemic")
    ax.scatter(y_true[anemic], y_pred[anemic], s=16, alpha=0.55,
               color=plots.VERMILLION, edgecolor="none", label="Anaemic")

    lo = float(min(y_true.min(), y_pred.min())) - 0.4
    hi = float(max(y_true.max(), y_pred.max())) + 0.4
    ax.plot([lo, hi], [lo, hi], color="0.35", ls="--", lw=1.0, label="Perfect agreement")

    slope, intercept = np.polyfit(y_true, y_pred, 1)
    xs = np.array([lo, hi])
    ax.plot(xs, slope * xs + intercept, color=plots.GREEN, lw=1.8,
            label=f"Fit (slope {slope:.2f})")

    ax.axvline(WHO_ANEMIA_HB_THRESHOLD, color="0.75", lw=0.8)
    ax.axhline(WHO_ANEMIA_HB_THRESHOLD, color="0.75", lw=0.8)
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Laboratory haemoglobin (g/dL)")
    ax.set_ylabel("Predicted haemoglobin (g/dL)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    plots._titles(ax, "The model shrinks toward the population mean",
                  "A fitted slope well below 1 is why this is a screen, not a meter")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return slope


def decision_curve_figure(y_true, prob, path):
    """Net benefit against threshold probability (Vickers & Elkin, 2006).

    AUROC says how well the model ranks; it says nothing about whether acting
    on it beats the obvious alternatives. In a setting where the realistic
    comparators are "refer every child" and "refer none", that is the question
    that decides deployment.

        NB(p_t) = TP/N - (FP/N) * p_t/(1 - p_t)

    p_t is the probability at which a clinician would consider referral
    worthwhile; the odds term is how many false referrals one missed case is
    worth. A model is useful only where its curve sits above BOTH comparators.
    """
    plt = plots._style()
    pts = np.linspace(0.01, 0.75, 300)
    n = len(y_true)
    prev = y_true.mean()

    nb_model, nb_all = [], []
    for pt in pts:
        pred = prob >= pt
        tp = np.sum(pred & y_true)
        fp = np.sum(pred & ~y_true)
        w = pt / (1.0 - pt)
        nb_model.append(tp / n - (fp / n) * w)
        nb_all.append(prev - (1.0 - prev) * w)
    nb_model, nb_all = np.asarray(nb_model), np.asarray(nb_all)

    fig, ax = plt.subplots(figsize=(7.0, 4.3))
    ax.plot(pts, nb_model, color=plots.BLUE, lw=2.2, label="Colour model", zorder=4)
    ax.plot(pts, nb_all, color=plots.VERMILLION, lw=1.6, ls="--", label="Refer every child")
    ax.axhline(0.0, color="0.45", lw=1.2, ls=":", label="Refer none")

    # The region that matters is the CONTIGUOUS run in which the model beats both
    # comparators, taken from the right-hand end. Reporting min-to-max of a
    # non-contiguous mask would claim benefit at low p_t where "refer everyone"
    # is in fact the better strategy.
    better = nb_model > np.maximum(nb_all, 0.0)
    cross = None
    for i in range(len(pts) - 1, 0, -1):
        if not better[i - 1] and better[i]:
            cross = pts[i]
            break
    if cross is not None:
        ax.axvspan(cross, pts[-1], color=plots.BLUE, alpha=0.08, zorder=0)
        ax.axvline(cross, color=plots.BLUE, lw=1.0, ls=":")
        ax.annotate(f"below $p_t \\approx {cross:.2f}$,\nrefer everyone",
                    xy=(cross, 0.0), xytext=(-6, 26),
                    textcoords="offset points", ha="right", va="bottom",
                    fontsize=8.5, color="0.30")
        ax.annotate("model adds net benefit here",
                    xy=((cross + pts[-1]) / 2, ax.get_ylim()[1] * 0.72),
                    ha="center", fontsize=8.5, color=plots.BLUE)

    ax.set_xlabel("Threshold probability $p_t$")
    ax.set_ylabel("Net benefit")
    ax.set_xlim(0, 0.75)
    ax.set_ylim(min(-0.05, nb_model.min()), max(nb_model.max(), prev) * 1.15)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    plots._titles(ax, "Is acting on the model better than the alternatives?",
                  "Net benefit versus referring everyone or no one")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return pts, nb_model, nb_all


def feature_correlation_figure(X, names, path):
    """Pairwise correlation between the twelve colour features.

    The importance section argues that a low permutation score means "redundant
    given the others" rather than "uninformative". That argument only holds if
    the features really are collinear, which is an evidential claim and is
    therefore shown rather than asserted.
    """
    plt = plots._style()
    C = np.corrcoef(np.asarray(X, dtype=float).T)
    k = len(names)

    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    im = ax.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(k)); ax.set_yticks(range(k))
    ax.set_xticklabels(names, rotation=55, ha="right", fontsize=7.5)
    ax.set_yticklabels(names, fontsize=7.5)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for i in range(k):
        for j in range(k):
            if abs(C[i, j]) >= 0.75 and i != j:
                ax.text(j, i, f"{C[i, j]:.2f}", ha="center", va="center",
                        fontsize=6.0, color="white" if abs(C[i, j]) > 0.88 else "0.15")

    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("Pearson correlation", fontsize=8.5)
    cb.outline.set_visible(False)
    plots._titles(ax, "The colour features are highly collinear",
                  "Values shown where |r| >= 0.75; importance is shared, not absent")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)

    off = C[~np.eye(k, dtype=bool)]
    return float(np.abs(off).mean()), float(np.abs(off).max())


def main() -> int:
    root = pathlib.Path("data/cp-anemic")
    out = pathlib.Path("results"); out.mkdir(exist_ok=True)

    ds = load_cp_anemic(root, dedup="perceptual", verbose=False)
    oof = out_of_fold_predictions(ds, FEATURE_SETS[HEADLINE_FEATURES], HEADLINE_SPLIT)

    y_true = np.asarray(ds.y, dtype=float)
    y_pred = np.asarray(oof, dtype=float)
    anemic = np.asarray(ds.anemic, dtype=bool)
    score = -y_pred + WHO_ANEMIA_HB_THRESHOLD   # higher score = more likely anaemic

    print(f"n = {len(y_true)}  prevalence = {anemic.mean():.3f}")

    sens, spec = operating_point_figure(anemic, score, out / "fig9_operating_point.png")
    slope = pred_vs_actual_figure(y_true, y_pred, out / "fig10_pred_vs_actual.png")

    names = list(FEATURE_SETS[HEADLINE_FEATURES])
    pretty = [n.replace("_", " ") for n in names]
    mean_r, max_r = feature_correlation_figure(ds.X[names].values if hasattr(ds.X, "columns")
                                               else ds.X, pretty,
                                               out / "fig12_feature_correlation.png")
    print(f"feature collinearity: mean |r| = {mean_r:.2f}, max |r| = {max_r:.2f}")

    prob = np.asarray(classifier_oof_scores(ds, HEADLINE_FEATURES, HEADLINE_SPLIT), dtype=float)
    pts, nb_m, nb_a = decision_curve_figure(anemic, prob, out / "fig11_decision_curve.png")
    better = nb_m > np.maximum(nb_a, 0.0)
    cross = next((pts[i] for i in range(len(pts) - 1, 0, -1)
                  if not better[i - 1] and better[i]), None)
    print(f"DCA: model beats both comparators above p_t = {cross:.3f}"
          if cross is not None else "DCA: model never beats both comparators")

    at_who = score >= 0
    tp = np.sum(at_who & anemic); fn = np.sum(~at_who & anemic)
    tn = np.sum(~at_who & ~anemic); fp = np.sum(at_who & ~anemic)
    print(f"WHO cutoff: sensitivity {tp/(tp+fn):.3f}  specificity {tn/(tn+fp):.3f}")
    print(f"pred-vs-actual fitted slope: {slope:.3f}")
    print("wrote fig9, fig10, fig11, fig12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
