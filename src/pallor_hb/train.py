"""End-to-end train + evaluate entry point.

    python -m pallor_hb.train --modality ppg --n 2000 --seed 0

Trains the Hb regressor with subject-level (group) cross-validation so the
reported error is leakage-free, then refits on a train split and writes metrics
and plots to results/.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
from sklearn.model_selection import GroupShuffleSplit, GroupKFold

from . import WHO_ANEMIA_CUTOFFS
from .dataset import make_synthetic_ppg
from .model import HbRegressor
from .evaluate import (
    regression_metrics,
    screening_metrics,
    metrics_to_dict,
    bland_altman_plot,
    pred_vs_actual_plot,
)


def _cv_mae(ds, seed: int, n_splits: int = 5) -> float:
    """Leakage-free CV MAE using subject-level folds."""
    n_groups = len(np.unique(ds.groups))
    n_splits = min(n_splits, n_groups)
    gkf = GroupKFold(n_splits=n_splits)
    maes = []
    for tr, te in gkf.split(ds.X, ds.y, ds.groups):
        model = HbRegressor(random_state=seed).fit(ds.X.iloc[tr], ds.y[tr])
        pred = model.predict(ds.X.iloc[te])
        maes.append(float(np.mean(np.abs(pred - ds.y[te]))))
    return float(np.mean(maes))


def main() -> None:
    ap = argparse.ArgumentParser(description="Train + evaluate the PallorHb Hb estimator.")
    ap.add_argument("--modality", choices=["ppg"], default="ppg",
                    help="feature modality (only synthetic PPG is wired up in this scaffold)")
    ap.add_argument("--n", type=int, default=2000, help="synthetic sample count")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--population", choices=list(WHO_ANEMIA_CUTOFFS), default="women_nonpreg",
                    help="which WHO cutoff to evaluate screening against")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "..", "..", "results"))
    args = ap.parse_args()

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    cutoff = WHO_ANEMIA_CUTOFFS[args.population]

    print(f"[data] synthetic {args.modality} dataset: n={args.n} seed={args.seed}")
    ds = make_synthetic_ppg(n=args.n, seed=args.seed)

    # Leakage-free cross-validated error.
    cv_mae = _cv_mae(ds, seed=args.seed)
    print(f"[cv]   subject-level 5-fold MAE = {cv_mae:.3f} g/dL")

    # Held-out split (by subject) for the reported metrics + plots.
    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=args.seed)
    tr, te = next(gss.split(ds.X, ds.y, ds.groups))
    model = HbRegressor(random_state=args.seed).fit(ds.X.iloc[tr], ds.y[tr])
    y_pred = model.predict(ds.X.iloc[te])
    y_true = ds.y[te]

    reg = regression_metrics(y_true, y_pred)
    scr = screening_metrics(y_true, y_pred, cutoff=cutoff)

    print(f"[test] MAE={reg.mae:.3f}  RMSE={reg.rmse:.3f}  R2={reg.r2:.3f}")
    print(f"[test] Bland-Altman bias={reg.bias:+.3f}  LoA=[{reg.loa_lower:+.2f}, {reg.loa_upper:+.2f}] g/dL")
    print(f"[scr]  cutoff={cutoff:g} ({args.population})  "
          f"sensitivity={scr.sensitivity:.3f}  specificity={scr.specificity:.3f}  "
          f"prevalence={scr.prevalence:.2f}")
    print("[imp]  top features: " + ", ".join(f"{k}={v:.2f}"
          for k, v in list(model.feature_importances().items())[:4]))

    ba_path = os.path.join(outdir, "bland_altman.png")
    pv_path = os.path.join(outdir, "pred_vs_actual.png")
    bland_altman_plot(y_true, y_pred, ba_path)
    pred_vs_actual_plot(y_true, y_pred, pv_path, cutoff=cutoff)

    payload = metrics_to_dict(reg, scr)
    payload["cv_mae_gdl"] = cv_mae
    payload["modality"] = args.modality
    payload["population"] = args.population
    payload["n"] = args.n
    payload["seed"] = args.seed
    payload["feature_importances"] = model.feature_importances()
    payload["note"] = "SYNTHETIC DATA — placeholder pending real dataset integration (roadmap W2)."
    metrics_path = os.path.join(outdir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[out]  wrote {metrics_path}")
    print(f"[out]  wrote {ba_path}")
    print(f"[out]  wrote {pv_path}")


if __name__ == "__main__":
    main()
