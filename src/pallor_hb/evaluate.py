"""Clinical evaluation for a non-invasive Hb estimator.

Two layers of evaluation:
  1. Regression agreement: MAE, RMSE, R2, and Bland-Altman limits of agreement.
     Bland-Altman is the correct tool for comparing a new method against a
     reference method -- a high R2 can still hide a clinically unacceptable bias.
  2. Screening performance: sensitivity/specificity at the WHO anemia cutoff,
     because the deployed decision is binary (refer / don't refer) and we care
     most about not missing true anemics.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class RegressionMetrics:
    n: int
    mae: float
    rmse: float
    r2: float
    bias: float               # mean(pred - ref), g/dL
    loa_lower: float          # bias - 1.96*sd, g/dL
    loa_upper: float          # bias + 1.96*sd, g/dL


@dataclass
class ScreeningMetrics:
    cutoff: float
    sensitivity: float
    specificity: float
    ppv: float
    npv: float
    tp: int
    fp: int
    tn: int
    fn: int
    prevalence: float


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> RegressionMetrics:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2)) or 1e-9
    r2 = 1.0 - ss_res / ss_tot
    bias = float(np.mean(err))
    sd = float(np.std(err, ddof=1)) if err.size > 1 else 0.0
    return RegressionMetrics(
        n=int(y_true.size),
        mae=mae,
        rmse=rmse,
        r2=r2,
        bias=bias,
        loa_lower=bias - 1.96 * sd,
        loa_upper=bias + 1.96 * sd,
    )


def screening_metrics(y_true: np.ndarray, y_pred: np.ndarray, cutoff: float) -> ScreeningMetrics:
    """Binary anemia screening: positive = Hb below the cutoff."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    true_pos_class = y_true < cutoff       # truly anemic
    pred_pos_class = y_pred < cutoff       # flagged anemic

    tp = int(np.sum(true_pos_class & pred_pos_class))
    fp = int(np.sum(~true_pos_class & pred_pos_class))
    tn = int(np.sum(~true_pos_class & ~pred_pos_class))
    fn = int(np.sum(true_pos_class & ~pred_pos_class))

    sens = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    ppv = tp / (tp + fp) if (tp + fp) else float("nan")
    npv = tn / (tn + fn) if (tn + fn) else float("nan")
    prev = float(np.mean(true_pos_class))
    return ScreeningMetrics(
        cutoff=cutoff, sensitivity=sens, specificity=spec, ppv=ppv, npv=npv,
        tp=tp, fp=fp, tn=tn, fn=fn, prevalence=prev,
    )


def metrics_to_dict(reg: RegressionMetrics, scr: ScreeningMetrics) -> dict:
    return {"regression": asdict(reg), "screening": asdict(scr)}


def bland_altman_plot(y_true: np.ndarray, y_pred: np.ndarray, path: str) -> None:
    """Save a Bland-Altman plot (mean vs difference) to `path`."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mean = (y_true + y_pred) / 2
    diff = y_pred - y_true
    bias = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1)) if diff.size > 1 else 0.0

    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.scatter(mean, diff, s=10, alpha=0.4, edgecolor="none")
    ax.axhline(bias, color="C1", label=f"bias {bias:+.2f}")
    ax.axhline(bias + 1.96 * sd, color="C3", ls="--", label=f"+1.96 SD {bias + 1.96*sd:+.2f}")
    ax.axhline(bias - 1.96 * sd, color="C3", ls="--", label=f"-1.96 SD {bias - 1.96*sd:+.2f}")
    ax.set_xlabel("Mean of predicted & reference Hb (g/dL)")
    ax.set_ylabel("Predicted - reference Hb (g/dL)")
    ax.set_title("Bland-Altman: non-invasive vs reference Hb")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def pred_vs_actual_plot(y_true: np.ndarray, y_pred: np.ndarray, path: str, cutoff: float) -> None:
    """Save a predicted-vs-actual scatter with the anemia cutoff marked."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    lo = float(min(y_true.min(), y_pred.min())) - 0.5
    hi = float(max(y_true.max(), y_pred.max())) + 0.5

    fig, ax = plt.subplots(figsize=(5.2, 5))
    ax.scatter(y_true, y_pred, s=10, alpha=0.4, edgecolor="none")
    ax.plot([lo, hi], [lo, hi], color="k", lw=1, label="identity")
    ax.axvline(cutoff, color="C3", ls="--", lw=1, label=f"anemia cutoff {cutoff:g}")
    ax.axhline(cutoff, color="C3", ls="--", lw=1)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Reference Hb (g/dL)")
    ax.set_ylabel("Predicted Hb (g/dL)")
    ax.set_title("Predicted vs reference")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
