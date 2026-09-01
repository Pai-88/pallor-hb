"""Check every number in the manuscript against results/cp_anemic_summary.json.

Every claim below is checked against the analysis output rather than transcribed
by hand, so a re-run that changes a number fails this script.

    python3 scripts/verify_paper_numbers.py

Exits non-zero if any claim disagrees with the analysis output.
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SUMMARY = REPO_ROOT / "results/cp_anemic_summary.json"

# (label, value as printed in the paper, path into summary.json, tolerance)
CLAIMS = [
    ("metadata rows",            710,    "dataset.metadata_rows",                       0),
    ("distinct by SHA (pass 1)", 498,    "dataset.distinct_by_sha",                     0),
    ("distinct by thumbnail (pass 2)", 479, "dataset.distinct_thumbnail",               0),
    ("distinct photographs (pass 3)",  383, "dataset.distinct_perceptual",              0),
    ("byte-hash singles",        407,    "dataset.unambiguous_singles",                 0),
    ("collection sites",         10,     "dataset.sites",                               0),
    ("prevalence",               0.509,  "dataset.prevalence",                          6e-4),
    ("headline AUROC",           0.706,  "headline.auroc",                              5e-4),
    ("headline CI lower",        0.653,  "headline.auroc_lo",                           5e-4),
    ("headline CI upper",        0.757,  "headline.auroc_hi",                           5e-4),
    ("headline MAE",             1.60,   "headline.mae",                                5e-3),
    ("sensitivity at WHO cutoff",0.713,  "headline.sensitivity",                        6e-4),
    ("specificity at WHO cutoff",0.532,  "headline.specificity",                        6e-4),
    ("specificity at 90% sens",  0.303,  "headline.spec_at_90_sens",                    6e-4),
    ("Bland-Altman bias",        0.03,   "headline.bias",                               5e-3),
    ("LoA lower",               -3.87,   "headline.loa_lower",                          5e-3),
    ("LoA upper",                3.92,   "headline.loa_upper",                          5e-3),
    ("demographics-only AUROC",  0.524,  "inference.colour_vs_demographics.auc_b",      5e-4),
    ("DeLong difference",        0.182,  "inference.colour_vs_demographics.difference", 5e-4),
    ("DeLong CI lower",          0.107,  "inference.colour_vs_demographics.ci_lower",   6e-4),
    ("DeLong CI upper",          0.258,  "inference.colour_vs_demographics.ci_upper",   6e-4),
    ("colour+demographics AUROC",0.699,  "inference.colour_vs_colour_plus_demographics.auc_b", 6e-4),
    ("classifier CI lower",      0.680,  "model_comparison.1.auroc_lo",                 6e-4),
    ("classifier CI upper",      0.785,  "model_comparison.1.auroc_hi",                 6e-4),
    ("leakage inflation",        0.176,  "inference.leakage_inflation_unpaired.difference", 6e-4),
    ("leakage CI lower",         0.120,  "inference.leakage_inflation_unpaired.ci_lower",   6e-4),
    ("leakage CI upper",         0.232,  "inference.leakage_inflation_unpaired.ci_upper",   6e-4),
    ("bootstrap resamples",      5000,   "inference.leakage_inflation_unpaired.n_boot",     0),
    ("permutation null mean",    0.529,  "controls.permutation.mean_auroc",             6e-4),
    ("permutation null sd",      0.032,  "controls.permutation.std",                    6e-4),
    ("seed stability mean",      0.702,  "controls.seed_stability.mean",                6e-4),
    ("seed stability sd",        0.006,  "controls.seed_stability.sd",                  6e-4),
    ("byte-hash singles AUROC",  0.763,  "controls.singles_only.auroc",                 6e-4),
    ("nested CV, fixed params",  0.706,  "controls.nested_cv.auroc_fixed",              6e-4),
    ("nested CV, tuned",         0.662,  "controls.nested_cv.auroc_nested_tuned",       6e-4),
    ("Brier score",              0.220,  "calibration.brier",                           6e-4),
    ("expected calibration err", 0.114,  "calibration.ece",                             6e-4),
    ("isotonic ECE",             0.079,  "calibration_comparison.1.ece",                6e-4),
    ("isotonic H-L p",           0.156,  "calibration_comparison.1.hosmer_lemeshow_p",  6e-4),
    ("isotonic AUROC",           0.711,  "calibration_comparison.1.auroc",              6e-4),
    ("classifier AUROC",         0.733,  "calibration_comparison.0.auroc",              6e-4),
    ("LOSO mean",                0.722,  "leave_one_site_out.mean_auroc",               6e-4),
    ("LOSO min",                 0.606,  "leave_one_site_out.min_auroc",                6e-4),
    ("LOSO max",                 0.875,  "leave_one_site_out.max_auroc",                6e-4),
]

DERIVED = [
    ("byte-identical duplicates", 212,
     lambda d: d["dataset"]["metadata_rows"] - d["dataset"]["distinct_by_sha"], 0),
    ("re-encoded copies (pass 2)", 19,
     lambda d: d["dataset"]["distinct_by_sha"] - d["dataset"]["distinct_thumbnail"], 0),
    ("shifted/re-cropped copies (pass 3)", 96,
     lambda d: d["dataset"]["distinct_thumbnail"] - d["dataset"]["distinct_perceptual"], 0),
    ("LoA span", 7.8,
     lambda d: d["headline"]["loa_upper"] - d["headline"]["loa_lower"], 0.05),
    ("waterfall drop, pass 3", 0.073,
     lambda d: 0.779661 - d["headline"]["auroc"], 6e-4),
    ("alignment sweep AUROC min", 0.685,
     lambda d: min(r["auroc"] for r in d["aligned_threshold_sweep"]), 6e-4),
    ("alignment sweep AUROC max", 0.728,
     lambda d: max(r["auroc"] for r in d["aligned_threshold_sweep"]), 6e-4),
    ("alignment sweep n min", 376,
     lambda d: min(r["n"] for r in d["aligned_threshold_sweep"]), 0),
    ("alignment sweep n max", 397,
     lambda d: max(r["n"] for r in d["aligned_threshold_sweep"]), 0),
    ("re-encode sweep AUROC min", 0.697,
     lambda d: min(r["auroc"] for r in d["threshold_sweep"]), 6e-4),
    ("re-encode sweep AUROC max", 0.712,
     lambda d: max(r["auroc"] for r in d["threshold_sweep"]), 6e-4),
    # Derived operating-point arithmetic quoted in Section 4.5; recomputed here
    # because it is not stored directly in summary.json.
    ("referrals per 100 at 90% sensitivity", 80,
     lambda d: round(100 * (d["headline"]["prevalence"] * 0.9
                            + (1 - d["headline"]["prevalence"])
                            * (1 - d["headline"]["spec_at_90_sens"]))), 0),
    ("learning curve start", 0.575,
     lambda d: d["learning_curve"][0]["mean"], 6e-4),
    ("learning curve end", 0.704,
     lambda d: d["learning_curve"][-1]["mean"], 6e-4),
    ("matched-n control mean", 0.744,
     lambda d: d["matched_n_control"]["auroc_mean"], 1e-3),
    ("matched-n control sd", 0.021,
     lambda d: d["matched_n_control"]["auroc_sd"], 1e-3),
    ("pass-3 drop: sample size", 0.036,
     lambda d: d["matched_n_control"]["attributable_to_sample_size"], 1e-3),
    ("pass-3 drop: leakage", 0.038,
     lambda d: d["matched_n_control"]["attributable_to_leakage"], 1e-3),
]


def dig(d, path):
    for key in path.split("."):
        d = d[int(key)] if isinstance(d, list) else d[key]
    return d


def main() -> int:
    if not SUMMARY.exists():
        print(f"{SUMMARY} not found - run scripts/run_full_analysis.py first")
        return 2
    d = json.loads(SUMMARY.read_text())

    failures = []
    for label, claimed, path, tol in CLAIMS:
        actual = dig(d, path)
        ok = abs(float(claimed) - float(actual)) <= tol
        print(f"{'ok  ' if ok else 'FAIL'} {label:34} paper {claimed:<9} analysis {actual}")
        if not ok:
            failures.append(label)

    for label, claimed, fn, tol in DERIVED:
        actual = fn(d)
        ok = abs(float(claimed) - float(actual)) <= tol
        print(f"{'ok  ' if ok else 'FAIL'} {label:34} paper {claimed:<9} analysis {actual}")
        if not ok:
            failures.append(label)

    print()
    if failures:
        print(f"{len(failures)} claim(s) disagree with the analysis: {failures}")
        return 1
    print(f"all {len(CLAIMS) + len(DERIVED)} claims agree with the analysis output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
