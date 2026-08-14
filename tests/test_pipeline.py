"""Unit tests for features, evaluation, and the synthetic pipeline.

Run with:  python -m pytest -q   (or: python tests/test_pipeline.py)
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pallor_hb.dataset import make_synthetic_ppg, PPG_FEATURE_COLUMNS  # noqa: E402
from pallor_hb.features import (  # noqa: E402
    ppg_features_from_waveform,
    conjunctiva_color_features,
)
from pallor_hb.evaluate import regression_metrics, screening_metrics  # noqa: E402
from pallor_hb.model import HbRegressor  # noqa: E402


def test_synthetic_schema_and_ranges():
    ds = make_synthetic_ppg(n=500, seed=1)
    assert list(ds.X.columns) == PPG_FEATURE_COLUMNS
    assert len(ds) == 500
    assert ds.y.min() >= 4.0 and ds.y.max() <= 19.0
    # group structure exists for leakage-free CV
    assert len(np.unique(ds.groups)) > 1


def test_synthetic_is_reproducible():
    a = make_synthetic_ppg(n=200, seed=7)
    b = make_synthetic_ppg(n=200, seed=7)
    assert np.allclose(a.y, b.y)
    assert a.X.equals(b.X)


def test_ppg_features_from_clean_pulse():
    fs = 100.0
    t = np.arange(0, 4, 1 / fs)
    # a plausible ~1.2 Hz (72 bpm) pulse on both channels
    wave = 1.0 + 0.05 * np.sin(2 * np.pi * 1.2 * t)
    feats = ppg_features_from_waveform(red=wave, ir=wave * 1.01, fs=fs, age=30, is_female=1)
    assert set(feats) == set(PPG_FEATURE_COLUMNS)
    assert 40 <= feats["hr_bpm"] <= 210
    assert feats["perfusion_index"] >= 0
    assert 0.0 <= feats["dicrotic_ratio"] <= 1.0


def test_conjunctiva_color_features():
    from pallor_hb.dataset import CONJ_FEATURE_COLUMNS, CONJ_QC_COLUMNS

    red_patch = np.zeros((8, 8, 3))
    red_patch[..., 0] = 0.8  # strong red -> high redness
    feats = conjunctiva_color_features(red_patch, age=24, is_female=1)
    # The extractor emits the model schema plus QC columns, and nothing else.
    assert set(feats) == set(CONJ_FEATURE_COLUMNS) | set(CONJ_QC_COLUMNS)

    # A paler (less red, more uniform) patch must score lower on the pallor index
    # and on the CIELAB red-green axis.
    pale_patch = np.full((8, 8, 3), 0.6)
    pale = conjunctiva_color_features(pale_patch, age=24, is_female=1)
    assert feats["redness_index"] > pale["redness_index"]
    assert feats["lab_a"] > pale["lab_a"]


def test_alpha_mask_is_respected():
    """Transparent pixels must not contaminate colour features.

    CP-AnemiC stores the conjunctiva ROI in the alpha channel with pure black
    behind it. If the mask is ignored, mean RGB collapses toward black and the
    features encode mask area rather than tissue colour.
    """
    rgba = np.zeros((10, 10, 4))
    rgba[..., 0] = 0.8              # red everywhere in RGB
    rgba[2:5, 2:5, 3] = 1.0         # ...but only a 3x3 window is opaque tissue

    feats = conjunctiva_color_features(rgba)
    # Masked mean must equal the tissue colour, NOT the 9%-opaque whole-frame mean.
    assert feats["r_mean"] == pytest.approx(0.8, abs=1e-6)
    assert feats["roi_px"] == 9


def test_hue_mean_is_circular():
    """Hue wraps, so the mean of ~1.0 and ~0.0 must be ~0.0, not 0.5."""
    px = np.zeros((1, 4, 3))
    px[0, :2] = [1.0, 0.02, 0.0]   # hue just above 0
    px[0, 2:] = [1.0, 0.0, 0.02]   # hue just below 1
    h = conjunctiva_color_features(px)["h_mean"]
    assert min(h, 1.0 - h) < 0.02, f"circular mean failed: {h}"


def test_regression_metrics_perfect():
    y = np.array([10.0, 12.0, 14.0])
    m = regression_metrics(y, y)
    assert m.mae == 0.0 and m.rmse == 0.0
    assert abs(m.r2 - 1.0) < 1e-9
    assert m.bias == 0.0


def test_screening_confusion_counts():
    y_true = np.array([9.0, 11.0, 13.0, 8.0])   # anemic: idx 0,1,3 at cutoff 12
    y_pred = np.array([9.5, 13.0, 12.5, 7.0])   # flagged: idx 0,3
    s = screening_metrics(y_true, y_pred, cutoff=12.0)
    assert s.tp == 2 and s.fn == 1 and s.tn == 1 and s.fp == 0
    assert abs(s.sensitivity - 2 / 3) < 1e-9
    assert s.specificity == 1.0


def test_model_beats_mean_baseline():
    ds = make_synthetic_ppg(n=1500, seed=3)
    n = len(ds)
    tr, te = slice(0, int(0.8 * n)), slice(int(0.8 * n), n)
    model = HbRegressor(random_state=0).fit(ds.X.iloc[tr], ds.y[tr])
    pred = model.predict(ds.X.iloc[te])
    mae_model = np.mean(np.abs(pred - ds.y[te]))
    mae_mean = np.mean(np.abs(np.mean(ds.y[tr]) - ds.y[te]))
    # a real model must beat predicting the training mean
    assert mae_model < 0.85 * mae_mean


# --------------------------------------------------------------------------- #
# Real-data tests. Skipped when CP-AnemiC has not been downloaded, so the suite
# stays green on a fresh clone and in CI.
# --------------------------------------------------------------------------- #

_CP_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "cp-anemic", "cp-anemic")
_has_cp = os.path.isdir(_CP_ROOT)
requires_cp = pytest.mark.skipif(not _has_cp, reason="CP-AnemiC dataset not downloaded")


@requires_cp
def test_cp_anemic_dedup_is_monotonic():
    """Each stricter dedup mode must yield no more rows than the looser one."""
    from pallor_hb.dataset import load_cp_anemic

    n_none = len(load_cp_anemic(_CP_ROOT, dedup="none", verbose=False))
    n_hash = len(load_cp_anemic(_CP_ROOT, dedup="hash", verbose=False))
    n_perc = len(load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False))
    assert n_none > n_hash > n_perc, (n_none, n_hash, n_perc)


@requires_cp
def test_cp_anemic_schema_and_ranges():
    """Loaded features must match the schema and be physiologically plausible."""
    from pallor_hb.dataset import CONJ_FEATURE_COLUMNS, load_cp_anemic

    ds = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    assert list(ds.X.columns) == CONJ_FEATURE_COLUMNS
    assert not ds.X.isna().any().any(), "no feature may be NaN"
    # Conjunctiva is red tissue: mean red must exceed green and blue.
    assert ds.X.r_mean.mean() > ds.X.g_mean.mean() > 0
    assert ds.X.lab_a.mean() > 0, "CIELAB a* should be positive (reddish)"
    # Hb values must be inside a physiologically possible range.
    assert 2.0 < ds.y.min() and ds.y.max() < 20.0
    # Groups are collection sites, and there must be several for grouped CV.
    assert len(set(ds.groups)) >= 5


if __name__ == "__main__":
    # Kept at the very end so every test defined above is visible in globals();
    # placing it mid-file silently excluded later tests from this runner.
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
