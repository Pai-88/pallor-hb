#!/usr/bin/env python3
"""Complete CP-AnemiC analysis: experiment matrix, inference, controls, figures.

The single entry point for the study. Produces everything needed to defend the
result rather than merely state it:

  * DeLong tests for the model comparisons (correlated AUROCs, same subjects)
  * an unpaired bootstrap for the leakage comparison (different row sets)
  * stability across seeds, and nested-CV evidence that hyperparameters
    were not cherry-picked
  * calibration of the screening probability (ECE, Brier, Hosmer-Lemeshow)
  * permutation importance measured out-of-fold
  * a learning curve, and a sensitivity sweep over the duplicate threshold
  * seven publication-quality figures in one shared style

Usage:
    python3 scripts/run_full_analysis.py [--root PATH] [--quick]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pallor_hb import plots  # noqa: E402
from pallor_hb import stats as st  # noqa: E402
from pallor_hb.dataset import WHO_ANEMIA_HB_THRESHOLD, load_cp_anemic  # noqa: E402
from pallor_hb.experiment import (  # noqa: E402
    FEATURE_SETS, calibration_comparison, classifier_oof_scores, learning_curve_auroc,
    leave_one_site_out, model_comparison, nested_cv_check, out_of_fold_predictions,
    permutation_control, permutation_importance_oof, repeated_cv_auroc,
    results_table, run_one, _auroc,
)

HEADLINE_FEATURES = "colour"
HEADLINE_SPLIT = "dedup_site"


def banner(msg: str) -> None:
    print(f"\n{'─' * 76}\n{msg}\n{'─' * 76}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO / "data/cp-anemic/cp-anemic"))
    ap.add_argument("--quick", action="store_true",
                    help="fewer repeats; for smoke-testing the script itself")
    args = ap.parse_args()

    out = REPO / "results"
    out.mkdir(exist_ok=True)
    t0 = time.time()
    summary: dict = {}

    # ----------------------------------------------------------------- data --
    banner("1 · DATA INTEGRITY")
    ds_naive = load_cp_anemic(args.root, dedup="none")
    ds_hash = load_cp_anemic(args.root, dedup="hash", verbose=False)
    ds = load_cp_anemic(args.root, dedup="perceptual", verbose=False)
    ds_single = load_cp_anemic(args.root, dedup="singles", verbose=False)
    print(f"  rows {len(ds_naive)} → sha-distinct {len(ds_hash)} → "
          f"pixel-distinct {len(ds)} → unambiguous singles {len(ds_single)}")
    summary["dataset"] = {
        "name": "CP-AnemiC (Mendeley m53vz6b7fx)",
        "metadata_rows": len(ds_naive), "distinct_by_sha": len(ds_hash),
        "distinct_perceptual": len(ds), "unambiguous_singles": len(ds_single),
        "sites": int(pd.Series(ds.groups).nunique()),
        "prevalence": float(ds.anemic.mean()),
        "who_threshold_g_dl": WHO_ANEMIA_HB_THRESHOLD,
    }

    # -------------------------------------------------------------- matrix --
    banner("2 · EXPERIMENT MATRIX")
    configs = [("naive_random", ds_naive), ("dedup_random", ds_hash),
               ("dedup_site", ds_hash), ("perceptual_site", ds)]
    results = []
    for split, d in configs:
        strategy = "dedup_site" if split == "perceptual_site" else split
        for fs in FEATURE_SETS:
            r = run_one(d, split=strategy, features=fs)
            r.split = split
            results.append(r)
            print(f"  {split:16s} {fs:20s} AUROC {r.auroc:.3f} "
                  f"[{r.auroc_lo:.3f}–{r.auroc_hi:.3f}]  MAE {r.mae:.2f}")
    table = results_table(results)
    table.to_csv(out / "cp_anemic_results.csv", index=False)

    def pick(split, features):
        return next(r for r in results if r.split == split and r.features == features)

    honest = pick("perceptual_site", HEADLINE_FEATURES)
    demo = pick("perceptual_site", "demographics")
    naive = pick("naive_random", HEADLINE_FEATURES)

    # Out-of-fold predictions reused throughout.
    oof = out_of_fold_predictions(ds, FEATURE_SETS[HEADLINE_FEATURES], HEADLINE_SPLIT)
    oof_demo = out_of_fold_predictions(ds, FEATURE_SETS["demographics"], HEADLINE_SPLIT)
    oof_both = out_of_fold_predictions(ds, FEATURE_SETS["colour+demographics"], HEADLINE_SPLIT)
    oof_naive = out_of_fold_predictions(ds_naive, FEATURE_SETS[HEADLINE_FEATURES], "naive_random")

    # ----------------------------------------------------------- inference --
    banner("3 · INFERENCE")
    # Paired: same subjects, correlated AUROCs -> DeLong.
    d_colour_vs_demo = st.delong_test(ds.anemic, -oof, -oof_demo)
    d_colour_vs_both = st.delong_test(ds.anemic, -oof, -oof_both)
    print(f"  colour vs demographics : Δ{d_colour_vs_demo.difference:+.3f} "
          f"[{d_colour_vs_demo.ci_lower:+.3f},{d_colour_vs_demo.ci_upper:+.3f}] "
          f"p={d_colour_vs_demo.p_value:.2e}")
    print(f"  colour vs colour+demo  : Δ{d_colour_vs_both.difference:+.3f} "
          f"[{d_colour_vs_both.ci_lower:+.3f},{d_colour_vs_both.ci_upper:+.3f}] "
          f"p={d_colour_vs_both.p_value:.3f}")

    # Unpaired: different row sets (710 with duplicates vs 479 without).
    leak = st.unpaired_auc_diff_ci(
        ds_naive.anemic, -oof_naive, ds.anemic, -oof,
        n_boot=1000 if args.quick else 5000)
    print(f"  leakage inflation      : Δ{leak['difference']:+.3f} "
          f"[{leak['ci_lower']:+.3f},{leak['ci_upper']:+.3f}] p={leak['p_value']:.2e}")

    # DeLong CI as an independent cross-check on the bootstrap CI.
    auc_d, lo_d, hi_d = st.delong_auc_ci(ds.anemic, -oof)
    print(f"  headline CI: bootstrap [{honest.auroc_lo:.3f},{honest.auroc_hi:.3f}] "
          f"vs DeLong [{lo_d:.3f},{hi_d:.3f}]")
    summary["inference"] = {
        "colour_vs_demographics": vars(d_colour_vs_demo),
        "colour_vs_colour_plus_demographics": vars(d_colour_vs_both),
        "leakage_inflation_unpaired": leak,
        "headline_ci_bootstrap": [honest.auroc_lo, honest.auroc_hi],
        "headline_ci_delong": [lo_d, hi_d],
    }

    # ------------------------------------------------------------ controls --
    banner("4 · CONTROLS")
    ctrl = permutation_control(ds, features=HEADLINE_FEATURES, split=HEADLINE_SPLIT,
                               n_repeats=3 if args.quick else 10)
    print(f"  label permutation      : AUROC {ctrl['mean_auroc']:.3f} ± {ctrl['std']:.3f} "
          f"(must be ≈0.50)")
    seeds = (0, 1, 2) if args.quick else tuple(range(10))
    stab = repeated_cv_auroc(ds, HEADLINE_FEATURES, HEADLINE_SPLIT, seeds=seeds)
    print(f"  seed stability         : {stab['mean']:.3f} ± {stab['sd']:.3f} "
          f"(range {stab['min']:.3f}–{stab['max']:.3f}, n={stab['n']})")
    singles = run_one(ds_single, split=HEADLINE_SPLIT, features=HEADLINE_FEATURES)
    print(f"  unambiguous singles    : AUROC {singles.auroc:.3f} (n={singles.n})")
    nested = nested_cv_check(ds, HEADLINE_FEATURES, HEADLINE_SPLIT)
    print(f"  nested-CV tuning       : fixed {nested['auroc_fixed']:.3f} vs "
          f"tuned {nested['auroc_nested_tuned']:.3f} (Δ{nested['difference']:+.3f})")
    summary["controls"] = {"permutation": ctrl, "seed_stability": stab,
                           "singles_only": singles.as_row(), "nested_cv": nested}

    # ------------------------------------------ model choice & calibration --
    banner("5 · MODEL COMPARISON AND CALIBRATION")
    mc = model_comparison(ds, HEADLINE_FEATURES, HEADLINE_SPLIT)
    mc.to_csv(out / "cp_anemic_model_comparison.csv", index=False)
    for r in mc.itertuples():
        extra = (f"MAE {r.mae_g_dl:.2f} g/dL, LoA width {r.loa_width_g_dl:.2f}"
                 if r.outputs_hb else "no Hb output — cannot assess agreement")
        print(f"  {r.model:19s} AUROC {r.auroc:.3f} [{r.auroc_lo:.3f}–{r.auroc_hi:.3f}]  {extra}")

    cc = calibration_comparison(ds, HEADLINE_FEATURES, HEADLINE_SPLIT)
    cc.to_csv(out / "cp_anemic_calibration_comparison.csv", index=False)
    print("  post-hoc calibration check (textbook advice fails here):")
    for r in cc.itertuples():
        print(f"    {r.variant:14s} Brier {r.brier:.3f} · ECE {r.ece:.3f} · "
              f"AUROC {r.auroc:.3f} · p∈[{r.prob_min:.2f},{r.prob_max:.2f}]")

    # The screening probability reported from here on is the uncalibrated
    # classifier, which the comparison above shows is the better-calibrated one.
    prob = classifier_oof_scores(ds, HEADLINE_FEATURES, HEADLINE_SPLIT)
    cal = st.calibration_bins(ds.anemic, prob)
    hl = st.hosmer_lemeshow(ds.anemic, prob)
    brier = st.brier_score(ds.anemic, prob)
    print(f"  chosen: Brier {brier:.3f} · ECE {cal['ece']:.3f} · "
          f"Hosmer–Lemeshow p={hl['p_value']:.3f} "
          f"({'calibrated' if hl['well_calibrated'] else 'imperfect'})")
    summary["model_comparison"] = mc.to_dict(orient="records")
    summary["calibration_comparison"] = cc.to_dict(orient="records")
    summary["calibration"] = {"brier": brier, "ece": cal["ece"], "hosmer_lemeshow": hl}

    # ------------------------------------------------------- per-site + more --
    banner("6 · GENERALISATION, IMPORTANCE, LEARNING CURVE")
    loso = leave_one_site_out(ds, features=HEADLINE_FEATURES)
    loso.to_csv(out / "cp_anemic_leave_one_site_out.csv", index=False)
    valid = loso.auroc.dropna()
    print(f"  leave-one-site-out     : mean {valid.mean():.3f} "
          f"(range {valid.min():.3f}–{valid.max():.3f}, {len(valid)} sites)")

    imp = permutation_importance_oof(ds, HEADLINE_FEATURES, HEADLINE_SPLIT,
                                     n_repeats=5 if args.quick else 20)
    imp.to_csv(out / "cp_anemic_permutation_importance.csv", index=False)
    print("  top permutation importance: " +
          ", ".join(f"{r.feature} {r.importance:+.3f}" for r in imp.head(3).itertuples()))

    lc = learning_curve_auroc(ds, HEADLINE_FEATURES, HEADLINE_SPLIT,
                              n_repeats=2 if args.quick else 5)
    lc.to_csv(out / "cp_anemic_learning_curve.csv", index=False)
    print(f"  learning curve         : {lc['mean'].iloc[0]:.3f} at {lc.fraction.iloc[0]:.0%} "
          f"→ {lc['mean'].iloc[-1]:.3f} at 100%")

    # ------------------------------------------- dedup threshold sensitivity --
    banner("7 · SENSITIVITY TO THE DUPLICATE THRESHOLD")
    thresholds = [1.0, 2.0, 3.0, 5.0] if args.quick else [0.5, 1.0, 2.0, 3.0, 4.0, 5.0]
    sweep = []
    for t in thresholds:
        d = load_cp_anemic(args.root, dedup="perceptual", verbose=False,
                           perceptual_threshold=t)
        p = out_of_fold_predictions(d, FEATURE_SETS[HEADLINE_FEATURES], HEADLINE_SPLIT)
        a = _auroc(d.y, p)
        sweep.append({"threshold": t, "n": len(d), "auroc": float(a)})
        print(f"  threshold {t:>4.1f} → n={len(d):3d}  AUROC {a:.3f}")
    pd.DataFrame(sweep).to_csv(out / "cp_anemic_threshold_sweep.csv", index=False)
    summary["threshold_sweep"] = sweep

    # ------------------------------------------------------------- figures --
    banner("8 · FIGURES")
    plots.roc_figure(
        {f"Naive split, duplicates kept — AUC {naive.auroc:.3f}": (ds_naive.y, oof_naive),
         f"Deduplicated + site-grouped — AUC {honest.auroc:.3f}": (ds.y, oof),
         f"Demographics only — AUC {demo.auroc:.3f}": (ds.y, oof_demo)},
        str(out / "fig1_roc.png"), cutoff=WHO_ANEMIA_HB_THRESHOLD,
        band_for="Deduplicated")

    plots.leakage_waterfall([
        {"label": "Random split, duplicates kept", "auroc": naive.auroc,
         "lo": naive.auroc_lo, "hi": naive.auroc_hi, "n": naive.n, "leaky": True},
        {"label": "Exact duplicates removed", "auroc": pick("dedup_random", "colour").auroc,
         "lo": pick("dedup_random", "colour").auroc_lo,
         "hi": pick("dedup_random", "colour").auroc_hi, "n": len(ds_hash)},
        {"label": "+ grouped by hospital", "auroc": pick("dedup_site", "colour").auroc,
         "lo": pick("dedup_site", "colour").auroc_lo,
         "hi": pick("dedup_site", "colour").auroc_hi, "n": len(ds_hash)},
        {"label": "+ re-encoded copies removed", "auroc": honest.auroc,
         "lo": honest.auroc_lo, "hi": honest.auroc_hi, "n": honest.n, "headline": True},
    ], str(out / "fig2_leakage.png"))

    plots.site_forest(loso, str(out / "fig3_sites.png"), pooled=honest.auroc)
    plots.calibration_figure(cal["bins"], str(out / "fig4_calibration.png"),
                             ece=cal["ece"], brier=brier)
    plots.bland_altman_figure(ds.y, oof, str(out / "fig5_bland_altman.png"))
    plots.importance_figure(list(imp.feature), list(imp.importance), list(imp.sd),
                            str(out / "fig6_importance.png"))
    plots.learning_curve_figure(list(lc.fraction), list(lc["mean"]), list(lc["sd"]),
                                str(out / "fig7_learning_curve.png"), n_total=len(ds))
    plots.threshold_sensitivity_figure([s["threshold"] for s in sweep],
                                       [s["auroc"] for s in sweep],
                                       [s["n"] for s in sweep],
                                       str(out / "fig8_threshold.png"))
    print("  wrote fig1–fig8 to results/")

    # ------------------------------------------------------------- summary --
    summary["headline"] = honest.as_row()
    summary["demographics_only"] = demo.as_row()
    summary["naive_leaky"] = naive.as_row()
    summary["leave_one_site_out"] = {
        "per_site": loso.to_dict(orient="records"),
        "mean_auroc": float(valid.mean()), "min_auroc": float(valid.min()),
        "max_auroc": float(valid.max()),
    }
    summary["permutation_importance"] = imp.to_dict(orient="records")
    summary["learning_curve"] = lc.to_dict(orient="records")
    summary["runtime_seconds"] = round(time.time() - t0, 1)

    def _json_safe(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return str(o)

    (out / "cp_anemic_summary.json").write_text(json.dumps(summary, indent=2, default=_json_safe))

    banner("HEADLINE")
    print(f"  AUROC {honest.auroc:.3f} (95% CI {honest.auroc_lo:.3f}–{honest.auroc_hi:.3f}), "
          f"n={honest.n}, {summary['dataset']['sites']} sites")
    print(f"  vs demographics    Δ{d_colour_vs_demo.difference:+.3f} (p={d_colour_vs_demo.p_value:.1e})")
    print(f"  leakage inflation  Δ{leak['difference']:+.3f} (p={leak['p_value']:.1e})")
    print(f"  sensitivity {honest.sensitivity:.3f} · specificity {honest.specificity:.3f} · "
          f"spec@90%sens {honest.spec_at_90_sens:.3f}")
    print(f"  Bland–Altman LoA {honest.loa_lower:+.2f} to {honest.loa_upper:+.2f} g/dL")
    print(f"\n  completed in {summary['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
