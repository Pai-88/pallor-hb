"""Unit tests for features, evaluation, and the synthetic pipeline.

Run with:  python -m pytest -q   (or: python tests/test_pipeline.py)
"""

from __future__ import annotations

import os
import sys

import numpy as np

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
    patch = np.zeros((8, 8, 3))
    patch[..., 0] = 0.8  # strong red -> high redness
    feats = conjunctiva_color_features(patch)
    assert feats["redness_index"] > 0.2
    assert feats["r_over_g"] > 1.0


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


if __name__ == "__main__":
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
