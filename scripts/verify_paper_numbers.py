"""Check every number in the manuscript against results/cp_anemic_summary.json.

The paper argues that unverified numbers propagate through a literature. It would
be poor form for its own numbers to rest on hand transcription, so this asserts
them mechanically instead.

    python3 scripts/verify_paper_numbers.py

Exits non-zero if any claim disagrees with the analysis output.
"""
from __future__ import annotations

import json
import pathlib
import sys

SUMMARY = pathlib.Path("results/cp_anemic_summary.json")

# (label, value as printed in the paper, path into summary.json, tolerance)
CLAIMS = [
    ("metadata rows",            710,    "dataset.metadata_rows",                       0),
    ("distinct by SHA",          498,    "dataset.distinct_by_sha",                     0),
    ("distinct at pixel level",  479,    "dataset.distinct_perceptual",                 0),
    ("unambiguous singles",      407,    "dataset.unambiguous_singles",                 0),
    ("collection sites",         10,     "dataset.sites",                               0),
    ("prevalence",               0.493,  "dataset.prevalence",                          6e-4),
    ("headline AUROC",           0.780,  "headline.auroc",                              5e-4),
    ("headline CI lower",        0.737,  "headline.auroc_lo",                           5e-4),
    ("headline CI upper",        0.818,  "headline.auroc_hi",                           5e-4),
    ("headline MAE",             1.46,   "headline.mae",                                5e-3),
    ("sensitivity at WHO cutoff",0.775,  "headline.sensitivity",                        6e-4),
    ("specificity at WHO cutoff",0.630,  "headline.specificity",                        6e-4),
    ("specificity at 90% sens",  0.362,  "headline.spec_at_90_sens",                    6e-4),
    ("Bland-Altman bias",        0.03,   "headline.bias",                               5e-3),
    ("LoA lower",               -3.65,   "headline.loa_lower",                          5e-3),
    ("LoA upper",                3.70,   "headline.loa_upper",                          5e-3),
    ("demographics-only AUROC",  0.565,  "inference.colour_vs_demographics.auc_b",      5e-4),
    ("DeLong difference",        0.215,  "inference.colour_vs_demographics.difference", 5e-4),
    ("DeLong CI lower",          0.151,  "inference.colour_vs_demographics.ci_lower",   6e-4),
    ("DeLong CI upper",          0.279,  "inference.colour_vs_demographics.ci_upper",   6e-4),
    ("colour+demographics AUROC",0.769,  "inference.colour_vs_colour_plus_demographics.auc_b", 6e-4),
    ("leakage inflation",        0.103,  "inference.leakage_inflation_unpaired.difference", 6e-4),
    ("leakage CI lower",         0.056,  "inference.leakage_inflation_unpaired.ci_lower",   6e-4),
    ("leakage CI upper",         0.152,  "inference.leakage_inflation_unpaired.ci_upper",   6e-4),
    ("bootstrap resamples",      5000,   "inference.leakage_inflation_unpaired.n_boot",     0),
    ("permutation null mean",    0.507,  "controls.permutation.mean_auroc",             6e-4),
    ("permutation null sd",      0.026,  "controls.permutation.std",                    6e-4),
    ("seed stability mean",      0.778,  "controls.seed_stability.mean",                6e-4),
    ("seed stability sd",        0.003,  "controls.seed_stability.sd",                  6e-4),
    ("singles-only AUROC",       0.763,  "controls.singles_only.auroc",                 6e-4),
    ("nested CV, fixed params",  0.780,  "controls.nested_cv.auroc_fixed",              6e-4),
    ("nested CV, tuned",         0.782,  "controls.nested_cv.auroc_nested_tuned",       6e-4),
    ("Brier score",              0.174,  "calibration.brier",                           6e-4),
    ("expected calibration err", 0.054,  "calibration.ece",                             6e-4),
    ("Hosmer-Lemeshow p",        0.021,  "calibration.hosmer_lemeshow.p_value",         6e-4),
]

DERIVED = [
    ("byte-identical duplicates", 212,
     lambda d: d["dataset"]["metadata_rows"] - d["dataset"]["distinct_by_sha"], 0),
    ("duplicates found only at pixel level", 19,
     lambda d: d["dataset"]["distinct_by_sha"] - d["dataset"]["distinct_perceptual"], 0),
    ("LoA span", 7.3,
     lambda d: d["headline"]["loa_upper"] - d["headline"]["loa_lower"], 0.05),
]


def dig(d, path):
    for key in path.split("."):
        d = d[key]
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
