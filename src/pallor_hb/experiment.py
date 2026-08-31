"""Cross-validated experiments on the CP-AnemiC conjunctiva dataset.

The point of this module is not to squeeze out the highest number — it is to
measure how much of a reported number is real. Three things are varied
independently and reported side by side:

1. **Split strategy.** CP-AnemiC contains 327 redundant rows (710 rows,
   383 distinct photographs), so a random split trains and tests on the same pixels.
   Comparing `naive_random` against `dedup_site` quantifies that inflation
   directly rather than asserting it.
2. **Feature set.** Age and sex alone predict childhood anemia reasonably well.
   An image model that does not beat `demographics` has not shown that the
   camera contributed anything, so that ablation is run every time.
3. **Label permutation.** Shuffling the target inside the honest split must
   collapse AUROC to ~0.5. If it does not, the harness itself leaks.

A single gradient-boosted regressor predicts Hb; its continuous output doubles
as the screening score (lower predicted Hb = more likely anemic), so regression
agreement and screening discrimination describe one model, not two.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, KFold

from .dataset import (
    CONJ_FEATURE_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    WHO_ANEMIA_HB_THRESHOLD,
    Dataset,
)
from .evaluate import regression_metrics, screening_metrics
from .model import HbRegressor

# Colour-only features: everything the camera sees, with demographics removed.
COLOUR_ONLY_COLUMNS = [c for c in CONJ_FEATURE_COLUMNS if c not in DEMOGRAPHIC_COLUMNS]

FEATURE_SETS: dict[str, list[str]] = {
    "demographics": DEMOGRAPHIC_COLUMNS,
    "colour": COLOUR_ONLY_COLUMNS,
    "colour+demographics": CONJ_FEATURE_COLUMNS,
}


@dataclass
class RunResult:
    """Out-of-fold performance for one (split, feature-set) combination."""

    split: str
    features: str
    n: int
    n_folds: int
    auroc: float
    auroc_lo: float                 # bootstrap 95% CI
    auroc_hi: float
    mae: float
    rmse: float
    bias: float
    loa_lower: float
    loa_upper: float
    sensitivity: float              # at the WHO cutoff
    specificity: float
    spec_at_90_sens: float          # screening-relevant operating point
    prevalence: float
    top_features: dict[str, float] = field(default_factory=dict)

    def as_row(self) -> dict:
        """Flat dict for tabulation; importances are reported separately."""
        d = asdict(self)
        d.pop("top_features", None)
        return d


def _auroc(y_hb_true: np.ndarray, y_hb_pred: np.ndarray) -> float:
    """AUROC for 'is anemic', scoring with negated predicted Hb.

    Anemia is *low* Hb, so a higher score must mean more likely anemic; negating
    the regression output converts it into a valid ranking score without fitting
    a second model.
    """
    from sklearn.metrics import roc_auc_score

    y_true = (np.asarray(y_hb_true) < WHO_ANEMIA_HB_THRESHOLD).astype(int)
    if y_true.min() == y_true.max():
        return float("nan")
    return float(roc_auc_score(y_true, -np.asarray(y_hb_pred)))


def _bootstrap_auroc_ci(
    y_true: np.ndarray, y_pred: np.ndarray, n_boot: int = 2000, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI for AUROC.

    With n < 500 and a 50/50 class split, the sampling error on AUROC is roughly
    +/-0.05, which is the same size as many of the differences being compared —
    so reporting a point estimate alone would invite over-reading the ranking.
    """
    rng = np.random.default_rng(seed)
    n = len(y_true)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        a = _auroc(y_true[idx], y_pred[idx])
        if not np.isnan(a):
            vals.append(a)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def _spec_at_sensitivity(y_hb_true: np.ndarray, y_hb_pred: np.ndarray, target: float = 0.90) -> float:
    """Specificity achievable while holding sensitivity at or above `target`.

    Screening tolerates false positives far better than missed anemia, so the
    honest way to describe a screening model is 'how many well children does it
    needlessly refer, once it is tuned to catch 90% of anemic ones'.
    """
    from sklearn.metrics import roc_curve

    y_true = (np.asarray(y_hb_true) < WHO_ANEMIA_HB_THRESHOLD).astype(int)
    if y_true.min() == y_true.max():
        return float("nan")
    fpr, tpr, _ = roc_curve(y_true, -np.asarray(y_hb_pred))
    ok = tpr >= target
    if not ok.any():
        return float("nan")
    return float(1.0 - fpr[ok][0])


def make_splitter(strategy: str, n_folds: int = 5):
    """Return (splitter, uses_groups) for a named split strategy."""
    if strategy in ("naive_random", "dedup_random"):
        return KFold(n_splits=n_folds, shuffle=True, random_state=0), False
    if strategy == "dedup_site":
        return GroupKFold(n_splits=n_folds), True
    raise ValueError(f"unknown split strategy {strategy!r}")


def out_of_fold_predictions(
    ds: Dataset, columns: list[str], strategy: str, n_folds: int = 5, seed: int = 0
) -> np.ndarray:
    """Cross-validated out-of-fold Hb predictions for one feature set."""
    splitter, uses_groups = make_splitter(strategy, n_folds)
    X = ds.X[columns]
    oof = np.full(len(ds.y), np.nan)
    split_args = (X, ds.y, ds.groups) if uses_groups else (X, ds.y)
    for train_idx, test_idx in splitter.split(*split_args):
        model = HbRegressor(random_state=seed).fit(X.iloc[train_idx], ds.y[train_idx])
        oof[test_idx] = model.predict(X.iloc[test_idx])
    if np.isnan(oof).any():
        raise RuntimeError("some rows never appeared in a test fold")
    return oof


def run_one(
    ds: Dataset, split: str, features: str, n_folds: int = 5, seed: int = 0
) -> RunResult:
    """Evaluate one (split, feature-set) combination end to end."""
    columns = FEATURE_SETS[features]
    oof = out_of_fold_predictions(ds, columns, split, n_folds=n_folds, seed=seed)

    reg = regression_metrics(ds.y, oof)
    scr = screening_metrics(ds.y, oof, cutoff=WHO_ANEMIA_HB_THRESHOLD)
    auroc = _auroc(ds.y, oof)
    lo, hi = _bootstrap_auroc_ci(ds.y, oof, seed=seed)

    # Feature importances from a model refit on everything — for interpretation
    # only; the reported metrics all come from the out-of-fold predictions.
    full = HbRegressor(random_state=seed).fit(ds.X[columns], ds.y)
    top = dict(list(full.feature_importances().items())[:6])

    return RunResult(
        split=split, features=features, n=len(ds.y), n_folds=n_folds,
        auroc=auroc, auroc_lo=lo, auroc_hi=hi,
        mae=reg.mae, rmse=reg.rmse, bias=reg.bias,
        loa_lower=reg.loa_lower, loa_upper=reg.loa_upper,
        sensitivity=scr.sensitivity, specificity=scr.specificity,
        spec_at_90_sens=_spec_at_sensitivity(ds.y, oof),
        prevalence=scr.prevalence, top_features=top,
    )


def permutation_control(ds: Dataset, features: str = "colour+demographics",
                        split: str = "dedup_site", n_repeats: int = 5,
                        seed: int = 0) -> dict:
    """Shuffle the target and confirm performance collapses to chance.

    This is the harness's own unit test: if a leak existed in the splitting or
    feature code, a model would still score above 0.5 on permuted labels.
    """
    rng = np.random.default_rng(seed)
    aurocs = []
    for i in range(n_repeats):
        shuffled = Dataset(X=ds.X, y=rng.permutation(ds.y), groups=ds.groups, meta=ds.meta)
        oof = out_of_fold_predictions(shuffled, FEATURE_SETS[features], split, seed=i)
        aurocs.append(_auroc(shuffled.y, oof))
    return {"mean_auroc": float(np.mean(aurocs)), "std": float(np.std(aurocs)),
            "runs": [float(a) for a in aurocs]}


def leave_one_site_out(ds: Dataset, features: str = "colour", seed: int = 0) -> pd.DataFrame:
    """Train on nine hospitals, test on the tenth, for every hospital in turn.

    This is the closest thing to external validation available inside a single
    dataset: each held-out site has its own camera, lighting, operator and local
    anemia prevalence. Per-site AUROC also exposes whether one large site is
    carrying the pooled number.

    Sites whose held-out fold contains only one class yield an undefined AUROC and
    are reported as NaN rather than silently dropped, since a site with 87%
    prevalence is itself a finding about the dataset.
    """
    columns = FEATURE_SETS[features]
    rows = []
    for site in sorted(set(ds.groups)):
        test = ds.groups == site
        train = ~test
        if train.sum() < 20 or test.sum() < 5:
            rows.append({"site": site, "n_test": int(test.sum()), "auroc": float("nan"),
                         "mae": float("nan"), "prevalence": float("nan"),
                         "note": "too few samples"})
            continue
        model = HbRegressor(random_state=seed).fit(ds.X[columns][train], ds.y[train])
        pred = model.predict(ds.X[columns][test])
        y_true = ds.y[test]
        rows.append({
            "site": site,
            "n_test": int(test.sum()),
            "auroc": _auroc(y_true, pred),
            "mae": float(np.mean(np.abs(pred - y_true))),
            "prevalence": float((y_true < WHO_ANEMIA_HB_THRESHOLD).mean()),
            "note": "",
        })
    return pd.DataFrame(rows).sort_values("n_test", ascending=False).reset_index(drop=True)


def results_table(results: list[RunResult]) -> pd.DataFrame:
    """Tidy dataframe of all runs, ordered for reading."""
    df = pd.DataFrame([r.as_row() for r in results])
    order = {"naive_random": 0, "dedup_random": 1, "dedup_site": 2}
    fs_order = {"demographics": 0, "colour": 1, "colour+demographics": 2}
    return (df.assign(_s=df.split.map(order), _f=df.features.map(fs_order))
              .sort_values(["_s", "_f"]).drop(columns=["_s", "_f"]).reset_index(drop=True))


# --------------------------------------------------------------------------- #
# Rigour additions: stability, calibration, importance, learning curve
# --------------------------------------------------------------------------- #

def repeated_cv_auroc(
    ds: Dataset, features: str = "colour", split: str = "dedup_site",
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
) -> dict:
    """AUROC across many random seeds, to separate signal from fold-assignment luck.

    Note that `GroupKFold` is deterministic — it partitions by group size, not at
    random — so under the site-grouped split the *folds* are identical across
    seeds and only the model's own randomness (subsampling) varies. That is
    reported honestly rather than dressed up as split variability: it is a
    measure of model stability, and the site-grouped fold structure is fixed by
    the data, not chosen.
    """
    from .stats import summarise_repeats

    vals = []
    for s in seeds:
        oof = out_of_fold_predictions(ds, FEATURE_SETS[features], split, seed=s)
        vals.append(_auroc(ds.y, oof))
    out = summarise_repeats(vals)
    out["values"] = [float(v) for v in vals]
    return out


def out_of_fold_probabilities(
    ds: Dataset, features: str = "colour", split: str = "dedup_site", seed: int = 0
) -> np.ndarray:
    """Cross-validated calibrated P(anaemic), for calibration assessment."""
    from .model import AnemiaClassifier

    splitter, uses_groups = make_splitter(split)
    X = ds.X[FEATURE_SETS[features]]
    y = ds.anemic
    prob = np.full(len(y), np.nan)
    args = (X, y, ds.groups) if uses_groups else (X, y)
    for tr, te in splitter.split(*args):
        clf = AnemiaClassifier(random_state=seed).fit(X.iloc[tr], y[tr])
        prob[te] = clf.predict_proba(X.iloc[te])
    if np.isnan(prob).any():
        raise RuntimeError("some rows never appeared in a test fold")
    return prob


def permutation_importance_oof(
    ds: Dataset, features: str = "colour", split: str = "dedup_site",
    n_repeats: int = 20, seed: int = 0,
) -> pd.DataFrame:
    """Permutation importance measured on held-out folds.

    Impurity-based importances (the model's own `feature_importances_`) are
    computed on training data and are biased toward high-cardinality continuous
    features, so they are unsuitable for a claim about what actually drives
    out-of-sample performance. Permuting a column in the *test* fold and
    measuring the AUROC drop answers that question directly.

    Correlated features share credit, so a low score here means "redundant given
    the others", not "irrelevant" — several of these colour features are near
    -duplicates of one another by construction.
    """
    splitter, uses_groups = make_splitter(split)
    columns = FEATURE_SETS[features]
    X = ds.X[columns]
    rng = np.random.default_rng(seed)
    drops = {c: [] for c in columns}

    args = (X, ds.y, ds.groups) if uses_groups else (X, ds.y)
    for tr, te in splitter.split(*args):
        model = HbRegressor(random_state=seed).fit(X.iloc[tr], ds.y[tr])
        base = _auroc(ds.y[te], model.predict(X.iloc[te]))
        if np.isnan(base):
            continue
        for c in columns:
            for _ in range(n_repeats):
                Xp = X.iloc[te].copy()
                Xp[c] = rng.permutation(Xp[c].to_numpy())
                a = _auroc(ds.y[te], model.predict(Xp))
                if not np.isnan(a):
                    drops[c].append(base - a)

    return (pd.DataFrame([{"feature": c,
                           "importance": float(np.mean(v)) if v else 0.0,
                           "sd": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0}
                          for c, v in drops.items()])
            .sort_values("importance", ascending=False).reset_index(drop=True))


def learning_curve_auroc(
    ds: Dataset, features: str = "colour", split: str = "dedup_site",
    fractions: tuple[float, ...] = (0.25, 0.4, 0.55, 0.7, 0.85, 1.0),
    n_repeats: int = 5, seed: int = 0,
) -> pd.DataFrame:
    """AUROC as a function of training-set size, subsampling the training folds.

    Only the *training* portion is subsampled; every point is still evaluated on
    the full held-out fold, so the curve isolates the effect of training size
    rather than confounding it with test-set noise.
    """
    from .stats import summarise_repeats

    splitter, uses_groups = make_splitter(split)
    columns = FEATURE_SETS[features]
    X = ds.X[columns]
    rows = []
    for frac in fractions:
        vals = []
        for rep in range(n_repeats):
            rng = np.random.default_rng(seed + rep)
            oof = np.full(len(ds.y), np.nan)
            args = (X, ds.y, ds.groups) if uses_groups else (X, ds.y)
            for tr, te in splitter.split(*args):
                k = max(20, int(round(frac * len(tr))))
                sub = rng.choice(tr, size=min(k, len(tr)), replace=False)
                model = HbRegressor(random_state=rep).fit(X.iloc[sub], ds.y[sub])
                oof[te] = model.predict(X.iloc[te])
            vals.append(_auroc(ds.y, oof))
        s = summarise_repeats(vals)
        rows.append({"fraction": frac, "mean": s["mean"], "sd": s["sd"]})
    return pd.DataFrame(rows)


def nested_cv_check(
    ds: Dataset, features: str = "colour", split: str = "dedup_site", seed: int = 0
) -> dict:
    """Compare the fixed a-priori hyperparameters against nested-CV tuning.

    The headline model uses hyperparameters that were never tuned on this data,
    which is the cleanest defence against selection bias. This check exists to
    show that the choice was not merely lucky: tuning inside each training fold
    (so the test fold never influences selection) should land in the same place.
    A tuned score much *higher* than the fixed one would mean the reported result
    is pessimistic; much lower would suggest the fixed settings were overfitted
    to this dataset by prior inspection.
    """
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import GridSearchCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    splitter, uses_groups = make_splitter(split)
    X = ds.X[FEATURE_SETS[features]]
    grid = {"gbr__max_depth": [2, 3, 4], "gbr__learning_rate": [0.02, 0.05, 0.1]}

    oof = np.full(len(ds.y), np.nan)
    chosen = []
    args = (X, ds.y, ds.groups) if uses_groups else (X, ds.y)
    for tr, te in splitter.split(*args):
        pipe = Pipeline([("scale", StandardScaler()),
                         ("gbr", GradientBoostingRegressor(
                             n_estimators=300, subsample=0.9, random_state=seed))])
        gs = GridSearchCV(pipe, grid, cv=3, scoring="neg_mean_absolute_error", n_jobs=-1)
        gs.fit(X.iloc[tr], ds.y[tr])
        chosen.append(gs.best_params_)
        oof[te] = gs.predict(X.iloc[te])

    fixed = _auroc(ds.y, out_of_fold_predictions(ds, FEATURE_SETS[features], split, seed=seed))
    tuned = _auroc(ds.y, oof)
    return {"auroc_fixed": float(fixed), "auroc_nested_tuned": float(tuned),
            "difference": float(tuned - fixed),
            "selected_params": [{k: v for k, v in p.items()} for p in chosen]}


def classifier_oof_scores(
    ds: Dataset, features: str = "colour", split: str = "dedup_site",
    seed: int = 0, calibrate: bool = False,
) -> np.ndarray:
    """Out-of-fold P(anaemic) from a classifier trained on the binary target."""
    from .model import AnemiaClassifier

    splitter, uses_groups = make_splitter(split)
    X = ds.X[FEATURE_SETS[features]]
    y = ds.anemic
    prob = np.full(len(y), np.nan)
    args = (X, y, ds.groups) if uses_groups else (X, y)
    for tr, te in splitter.split(*args):
        clf = AnemiaClassifier(random_state=seed, calibrate=calibrate).fit(X.iloc[tr], y[tr])
        prob[te] = clf.predict_proba(X.iloc[te])
    if np.isnan(prob).any():
        raise RuntimeError("some rows never appeared in a test fold")
    return prob


def model_comparison(
    ds: Dataset, features: str = "colour", split: str = "dedup_site", seed: int = 0
) -> pd.DataFrame:
    """Compare the Hb regressor against a direct binary classifier.

    Both are legitimate ways to produce a screening score and they answer
    different questions, so both are reported rather than the better one being
    quietly adopted:

    - the **regressor** estimates haemoglobin, which is what makes Bland-Altman
      agreement and the "not a haemoglobin meter" conclusion available at all;
    - the **classifier** optimises the binary decision directly and discriminates
      better, but yields no Hb value and so cannot be checked for agreement.

    Reporting the pair also prevents the comparison itself from becoming a hidden
    model-selection step performed on the test metric.
    """
    from sklearn.metrics import roc_auc_score

    y_bin = ds.anemic
    rows = []

    reg_oof = out_of_fold_predictions(ds, FEATURE_SETS[features], split, seed=seed)
    lo, hi = _bootstrap_auroc_ci(ds.y, reg_oof, seed=seed)
    reg = regression_metrics(ds.y, reg_oof)
    rows.append({"model": "Hb regressor", "auroc": _auroc(ds.y, reg_oof),
                 "auroc_lo": lo, "auroc_hi": hi, "mae_g_dl": reg.mae,
                 "loa_width_g_dl": reg.loa_upper - reg.loa_lower,
                 "outputs_hb": True})

    clf_oof = classifier_oof_scores(ds, features, split, seed=seed)
    # Bootstrap the classifier's AUROC on the same footing as the regressor's.
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(2000):
        i = rng.integers(0, len(y_bin), len(y_bin))
        if len(np.unique(y_bin[i])) > 1:
            vals.append(roc_auc_score(y_bin[i], clf_oof[i]))
    rows.append({"model": "binary classifier", "auroc": float(roc_auc_score(y_bin, clf_oof)),
                 "auroc_lo": float(np.percentile(vals, 2.5)),
                 "auroc_hi": float(np.percentile(vals, 97.5)),
                 "mae_g_dl": float("nan"), "loa_width_g_dl": float("nan"),
                 "outputs_hb": False})
    return pd.DataFrame(rows)


def calibration_comparison(
    ds: Dataset, features: str = "colour", split: str = "dedup_site", seed: int = 0
) -> pd.DataFrame:
    """Measure whether post-hoc calibration actually helps on this dataset.

    Included because the textbook answer ("always calibrate a boosted model") is
    wrong here, and a claim that surprising should ship with the evidence that
    produced it rather than as an assertion in a docstring.
    """
    from sklearn.metrics import roc_auc_score

    from .stats import brier_score, calibration_bins, hosmer_lemeshow

    y = ds.anemic
    rows = []
    for label, calibrate in [("uncalibrated", False), ("isotonic cv=3", True)]:
        p = classifier_oof_scores(ds, features, split, seed=seed, calibrate=calibrate)
        cal = calibration_bins(y, p)
        rows.append({
            "variant": label, "brier": brier_score(y, p), "ece": cal["ece"],
            "hosmer_lemeshow_p": hosmer_lemeshow(y, p)["p_value"],
            "auroc": float(roc_auc_score(y, p)),
            "prob_min": float(p.min()), "prob_max": float(p.max()),
        })
    return pd.DataFrame(rows)
