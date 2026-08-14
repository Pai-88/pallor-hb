"""Inferential statistics for comparing screening models.

The bootstrap intervals reported elsewhere describe one model at a time. They are
the wrong tool for comparing two models on the *same* subjects: those AUROCs are
correlated, so overlapping marginal intervals do not imply a non-significant
difference, and treating them as independent throws away the pairing that makes
the comparison powerful.

This module therefore provides:

- **DeLong's test** for two correlated ROC curves (same subjects, two scores),
  which is the standard exact-variance method and needs no resampling.
- **An unpaired bootstrap** for the leakage comparison, where the two AUROCs come
  from genuinely different row sets (710 rows with duplicates vs 479 without) and
  so cannot be paired.
- **Calibration** measures, because a screening tool that outputs a probability
  must be judged on whether that probability is truthful, not only on ranking.

Reference: DeLong, DeLong & Clarke-Pearson (1988), Biometrics 44(3):837-845.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


# --------------------------------------------------------------------------- #
# DeLong's method
# --------------------------------------------------------------------------- #

def _midrank(x: np.ndarray) -> np.ndarray:
    """Mid-ranks of `x`, averaging ranks within ties (as DeLong requires)."""
    order = np.argsort(x)
    z = x[order]
    n = len(x)
    t = np.zeros(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j < n and z[j] == z[i]:
            j += 1
        t[i:j] = 0.5 * (i + j - 1) + 1
        i = j
    out = np.empty(n, dtype=float)
    out[order] = t
    return out


def _fast_delong(scores: np.ndarray, n_pos: int) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised DeLong AUCs and covariance matrix.

    Args:
        scores: (k, n) array of k score vectors, columns ordered positives-first.
        n_pos: number of positive cases (the leading columns).

    Returns:
        (aucs, covariance) with shapes (k,) and (k, k).
    """
    m, k = n_pos, scores.shape[0]
    n = scores.shape[1] - m
    pos, neg = scores[:, :m], scores[:, m:]

    tx = np.stack([_midrank(pos[r]) for r in range(k)])
    ty = np.stack([_midrank(neg[r]) for r in range(k)])
    tz = np.stack([_midrank(scores[r]) for r in range(k)])

    aucs = tz[:, :m].sum(axis=1) / m / n - (m + 1.0) / 2.0 / n
    # Structural components: v01 over positives, v10 over negatives.
    v01 = (tz[:, :m] - tx) / n
    v10 = 1.0 - (tz[:, m:] - ty) / m
    sx = np.atleast_2d(np.cov(v01))
    sy = np.atleast_2d(np.cov(v10))
    return aucs, sx / m + sy / n


@dataclass
class DelongResult:
    auc_a: float
    auc_b: float
    difference: float          # auc_a - auc_b
    ci_lower: float            # 95% CI on the difference
    ci_upper: float
    z: float
    p_value: float
    n: int
    n_positive: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def delong_test(y_true: np.ndarray, score_a: np.ndarray, score_b: np.ndarray) -> DelongResult:
    """Compare two correlated AUROCs measured on the same subjects.

    Args:
        y_true: binary labels (1 = positive/anemic).
        score_a, score_b: scores where higher means more likely positive.

    Returns:
        DelongResult with the AUC difference, its 95% CI, and a two-sided p-value.
    """
    y_true = np.asarray(y_true).astype(int)
    a = np.asarray(score_a, dtype=float)
    b = np.asarray(score_b, dtype=float)
    if not (len(y_true) == len(a) == len(b)):
        raise ValueError("y_true, score_a and score_b must have equal length")
    if set(np.unique(y_true)) - {0, 1}:
        raise ValueError("y_true must be binary 0/1")
    if y_true.min() == y_true.max():
        raise ValueError("need both classes present")

    order = np.argsort(-y_true, kind="mergesort")   # positives first, stable
    scores = np.stack([a[order], b[order]])
    n_pos = int(y_true.sum())

    aucs, cov = _fast_delong(scores, n_pos)
    diff = float(aucs[0] - aucs[1])
    # Var(A-B) = Var(A) + Var(B) - 2Cov(A,B)
    var = float(cov[0, 0] + cov[1, 1] - 2 * cov[0, 1])
    se = float(np.sqrt(max(var, 0.0)))
    if se == 0:
        z, p = 0.0, 1.0
    else:
        z = diff / se
        p = float(2 * stats.norm.sf(abs(z)))
    return DelongResult(
        auc_a=float(aucs[0]), auc_b=float(aucs[1]), difference=diff,
        ci_lower=diff - 1.96 * se, ci_upper=diff + 1.96 * se,
        z=float(z), p_value=p, n=len(y_true), n_positive=n_pos,
    )


def delong_auc_ci(y_true: np.ndarray, score: np.ndarray, alpha: float = 0.05) -> tuple[float, float, float]:
    """Analytic (AUC, lower, upper) confidence interval via DeLong's variance.

    Reported alongside the bootstrap interval as a cross-check: the two use
    entirely different machinery, so close agreement is evidence that neither is
    an artefact of the resampling scheme.
    """
    y_true = np.asarray(y_true).astype(int)
    s = np.asarray(score, dtype=float)
    order = np.argsort(-y_true, kind="mergesort")
    aucs, cov = _fast_delong(np.stack([s[order]]), int(y_true.sum()))
    auc = float(aucs[0])
    se = float(np.sqrt(max(float(cov[0, 0]), 0.0)))
    z = stats.norm.ppf(1 - alpha / 2)
    return auc, float(np.clip(auc - z * se, 0, 1)), float(np.clip(auc + z * se, 0, 1))


# --------------------------------------------------------------------------- #
# Unpaired comparison (different row sets)
# --------------------------------------------------------------------------- #

def unpaired_auc_diff_ci(
    y_a: np.ndarray, score_a: np.ndarray,
    y_b: np.ndarray, score_b: np.ndarray,
    n_boot: int = 5000, seed: int = 0,
) -> dict:
    """Bootstrap CI for the AUROC difference between two *different* datasets.

    Used for the leakage comparison, where one AUROC is measured on 710 rows
    containing duplicates and the other on 479 distinct images. The samples are
    not paired and not even the same size, so DeLong does not apply; each side is
    resampled independently and the difference accumulated.
    """
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(seed)
    y_a, score_a = np.asarray(y_a).astype(int), np.asarray(score_a, dtype=float)
    y_b, score_b = np.asarray(y_b).astype(int), np.asarray(score_b, dtype=float)

    obs = float(roc_auc_score(y_a, score_a) - roc_auc_score(y_b, score_b))
    diffs = []
    for _ in range(n_boot):
        ia = rng.integers(0, len(y_a), len(y_a))
        ib = rng.integers(0, len(y_b), len(y_b))
        if len(np.unique(y_a[ia])) < 2 or len(np.unique(y_b[ib])) < 2:
            continue
        diffs.append(roc_auc_score(y_a[ia], score_a[ia]) - roc_auc_score(y_b[ib], score_b[ib]))
    d = np.asarray(diffs)
    # Two-sided bootstrap p-value: proportion of resamples on the far side of 0.
    p = float(2 * min((d <= 0).mean(), (d >= 0).mean())) if len(d) else float("nan")
    return {
        "difference": obs,
        "ci_lower": float(np.percentile(d, 2.5)),
        "ci_upper": float(np.percentile(d, 97.5)),
        "p_value": min(p, 1.0),
        "n_boot": int(len(d)),
    }


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #

def brier_score(y_true: np.ndarray, prob: np.ndarray) -> float:
    """Mean squared error of predicted probabilities (lower is better)."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(prob, dtype=float)
    return float(np.mean((p - y) ** 2))


def calibration_bins(y_true: np.ndarray, prob: np.ndarray, n_bins: int = 10) -> dict:
    """Reliability-curve data using equal-count (quantile) bins.

    Equal-width bins are the common default but leave near-empty extreme bins
    whose noisy means dominate the visual impression of miscalibration; equal
    -count bins give every plotted point the same sample size.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(prob, dtype=float)
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append({"mean_pred": float(p[m].mean()),
                     "observed": float(y[m].mean()),
                     "count": int(m.sum())})
    mean_pred = np.array([r["mean_pred"] for r in rows])
    observed = np.array([r["observed"] for r in rows])
    counts = np.array([r["count"] for r in rows], dtype=float)
    # Expected calibration error: sample-weighted |predicted - observed|.
    ece = float(np.sum(counts / counts.sum() * np.abs(mean_pred - observed)))
    return {"bins": rows, "ece": ece}


def hosmer_lemeshow(y_true: np.ndarray, prob: np.ndarray, n_bins: int = 10) -> dict:
    """Hosmer-Lemeshow goodness-of-fit test for calibration.

    A *large* p-value is the good outcome here: it means observed and predicted
    event counts do not differ detectably. This is the reverse of the usual
    reading of a p-value and is easy to report backwards.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(prob, dtype=float), 1e-9, 1 - 1e-9)
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    chi2, groups = 0.0, 0
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() == 0:
            continue
        obs1, exp1 = y[m].sum(), p[m].sum()
        obs0, exp0 = m.sum() - obs1, m.sum() - exp1
        if exp1 > 0:
            chi2 += (obs1 - exp1) ** 2 / exp1
        if exp0 > 0:
            chi2 += (obs0 - exp0) ** 2 / exp0
        groups += 1
    dof = max(groups - 2, 1)
    return {"chi2": float(chi2), "dof": int(dof),
            "p_value": float(stats.chi2.sf(chi2, dof)),
            "well_calibrated": bool(stats.chi2.sf(chi2, dof) > 0.05)}


# --------------------------------------------------------------------------- #
# Stability across resampling
# --------------------------------------------------------------------------- #

def summarise_repeats(values: list[float]) -> dict:
    """Mean, sd and range of a metric across repeated runs.

    A single cross-validation number hides how much of it is fold-assignment
    luck. Reporting the spread across seeds shows whether a difference between
    configurations survives that noise.
    """
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"mean": float("nan"), "sd": float("nan"),
                "min": float("nan"), "max": float("nan"), "n": 0}
    return {"mean": float(v.mean()), "sd": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "min": float(v.min()), "max": float(v.max()), "n": int(v.size)}
