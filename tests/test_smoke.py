"""Adversarial smoke tests: try to break the pipeline, not to confirm it works.

Organised by failure mode rather than by module, because the failures that matter
here are not "this function raised" but "this function returned a plausible number
that was wrong". Each group encodes a specific way the study's conclusions could
be silently invalid:

1. Split integrity      — could a test row have been seen during training?
2. Feature correctness  — do the colour features measure tissue, or an artefact?
3. Numerical robustness — do degenerate inputs return garbage instead of raising?
4. Determinism          — is the published number reproducible?
5. Statistical machinery— do the tests agree with independent implementations?
6. Adversarial nulls    — does the pipeline correctly report *no* signal when
                          there is none? (the check that catches leakage)
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pallor_hb.dataset import (  # noqa: E402
    CONJ_FEATURE_COLUMNS, DEMOGRAPHIC_COLUMNS, WHO_ANEMIA_HB_THRESHOLD,
    Dataset, load_cp_anemic, _match_column, _perceptual_groups,
)
from pallor_hb.features import (  # noqa: E402
    ALPHA_ROI_THRESHOLD, conjunctiva_color_features, load_conjunctiva_roi,
)
from pallor_hb import experiment as ex  # noqa: E402
from pallor_hb import stats as st  # noqa: E402

_CP_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "cp-anemic", "cp-anemic")
requires_cp = pytest.mark.skipif(not os.path.isdir(_CP_ROOT),
                                 reason="CP-AnemiC dataset not downloaded")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _toy_dataset(n=120, n_sites=6, seed=0, signal=1.0):
    """Synthetic conjunctiva-shaped dataset with a known, tunable signal."""
    rng = np.random.default_rng(seed)
    groups = np.array([f"site_{i % n_sites}" for i in range(n)])
    hb = rng.uniform(6, 15, n)
    X = pd.DataFrame(
        {c: (rng.normal(0, 1, n) + signal * (hb - 10) / 3 if c == "redness_index"
             else rng.normal(0, 1, n))
         for c in CONJ_FEATURE_COLUMNS})
    return Dataset(X=X, y=hb, groups=groups)


def _rgba(colour=(0.8, 0.3, 0.3), size=12, opaque_slice=None, bg=0.0):
    """RGBA patch with an explicit alpha mask; background defaults to black."""
    a = np.full((size, size, 4), float(bg))
    a[..., :3] = colour
    a[..., 3] = 0.0
    sl = opaque_slice or (slice(2, size - 2), slice(2, size - 2))
    a[sl[0], sl[1], 3] = 1.0
    return a


# =========================================================================== #
# 1. Split integrity — the leakage guards
# =========================================================================== #

def test_grouped_split_never_shares_a_site():
    """No hospital may appear in both train and test under the grouped split."""
    ds = _toy_dataset()
    splitter, uses_groups = ex.make_splitter("dedup_site")
    assert uses_groups
    for tr, te in splitter.split(ds.X, ds.y, ds.groups):
        assert not (set(ds.groups[tr]) & set(ds.groups[te])), "site leaked across folds"


def test_every_row_is_tested_exactly_once():
    """Out-of-fold predictions must cover each row once — no gaps, no double use."""
    ds = _toy_dataset()
    splitter, _ = ex.make_splitter("dedup_site")
    seen = np.zeros(len(ds.y), dtype=int)
    for _, te in splitter.split(ds.X, ds.y, ds.groups):
        seen[te] += 1
    assert (seen == 1).all(), f"rows tested {sorted(set(seen))} times"


def test_train_and_test_indices_are_disjoint():
    ds = _toy_dataset()
    for strategy in ("dedup_random", "dedup_site"):
        splitter, ug = ex.make_splitter(strategy)
        args = (ds.X, ds.y, ds.groups) if ug else (ds.X, ds.y)
        for tr, te in splitter.split(*args):
            assert not set(tr) & set(te)


def test_oof_predictions_have_no_missing_values():
    ds = _toy_dataset()
    oof = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site")
    assert np.isfinite(oof).all()
    assert len(oof) == len(ds.y)


@requires_cp
def test_no_duplicate_image_survives_deduplication():
    """After perceptual dedup, every retained image must be pixel-distinct."""
    ds = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    assert ds.meta.sha.nunique() == len(ds), "byte-identical duplicates remain"


@requires_cp
def test_dedup_reduces_conflicting_labels():
    """Dedup must not increase the number of rows or lose the site column."""
    a = load_cp_anemic(_CP_ROOT, dedup="none", verbose=False)
    b = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    assert len(b) < len(a)
    assert set(b.groups) <= set(a.groups)
    assert b.meta is not None and "site" in b.meta.columns


# =========================================================================== #
# 2. Feature correctness — measuring tissue, not artefacts
# =========================================================================== #

def test_mask_selects_only_opaque_pixels():
    px = load_conjunctiva_roi(_rgba(size=12))          # 8x8 opaque window
    assert px.shape == (64, 3)
    assert np.allclose(px[:, 0], 0.8)


def test_black_background_never_contaminates_the_mean():
    """The whole-frame mean would be far darker; the masked mean must not be."""
    f = conjunctiva_color_features(_rgba(colour=(0.9, 0.2, 0.2), size=20))
    assert f["r_mean"] == pytest.approx(0.9, abs=1e-9)
    assert f["g_mean"] == pytest.approx(0.2, abs=1e-9)


def test_alpha_threshold_is_exclusive_of_soft_edges():
    """Anti-aliased boundary pixels (alpha just under the cut) must be excluded."""
    a = np.zeros((6, 6, 4))
    a[..., 0] = 1.0
    a[0, 0, 3] = (ALPHA_ROI_THRESHOLD - 1) / 255.0   # just below
    a[1, 1, 3] = ALPHA_ROI_THRESHOLD / 255.0         # exactly at
    px = load_conjunctiva_roi(a)
    assert len(px) == 1, "only the pixel at/above the threshold should be kept"


def test_redness_index_is_invariant_to_uniform_brightness():
    """Normalised redness must survive an exposure change; raw means must not."""
    base = _rgba(colour=(0.8, 0.4, 0.3))
    dim = _rgba(colour=(0.4, 0.2, 0.15))             # same hue, half brightness
    fb, fd = conjunctiva_color_features(base), conjunctiva_color_features(dim)
    assert fb["redness_index"] == pytest.approx(fd["redness_index"], abs=1e-9)
    assert fb["rg_ratio"] == pytest.approx(fd["rg_ratio"], abs=1e-6)
    assert fb["r_mean"] != pytest.approx(fd["r_mean"])   # raw mean does change


def test_pallor_moves_features_in_the_expected_direction():
    """A paler (less saturated) conjunctiva must score lower on redness and a*."""
    red = conjunctiva_color_features(_rgba(colour=(0.85, 0.25, 0.25)))
    pale = conjunctiva_color_features(_rgba(colour=(0.75, 0.60, 0.60)))
    assert red["redness_index"] > pale["redness_index"]
    assert red["lab_a"] > pale["lab_a"]
    assert red["s_mean"] > pale["s_mean"]


def test_lab_conversion_matches_reference_values():
    """CIELAB of pure sRGB white and mid-grey must hit published values."""
    white = load_conjunctiva_roi(np.ones((2, 2, 3)))
    L, a, b = __import__("pallor_hb.features", fromlist=["_srgb_to_lab_mean"])._srgb_to_lab_mean(white)
    assert L == pytest.approx(100.0, abs=0.05)
    assert a == pytest.approx(0.0, abs=0.05) and b == pytest.approx(0.0, abs=0.05)


def test_feature_extraction_is_order_independent():
    """Shuffling pixels must not change any summary statistic."""
    rng = np.random.default_rng(3)
    a = np.zeros((10, 10, 4))
    a[..., :3] = rng.uniform(0.2, 0.9, (10, 10, 3))
    a[..., 3] = 1.0
    f1 = conjunctiva_color_features(a, age=24, is_female=1)
    flat = a.reshape(-1, 4)
    f2 = conjunctiva_color_features(rng.permutation(flat).reshape(10, 10, 4),
                                    age=24, is_female=1)
    for k in f1:
        # Relative tolerance: summation order changes the last bits of means, and
        # lab_l is ~60, so an absolute 1e-9 bound would fail on float noise alone.
        assert f1[k] == pytest.approx(f2[k], rel=1e-9, abs=1e-12), k


def test_roi_px_excluded_from_model_features():
    """Mask area is annotator behaviour and must never reach the model."""
    assert "roi_px" not in CONJ_FEATURE_COLUMNS
    assert "roi_px" not in ex.COLOUR_ONLY_COLUMNS
    assert "roi_px" in conjunctiva_color_features(_rgba())


def test_colour_feature_set_excludes_demographics():
    assert not set(ex.COLOUR_ONLY_COLUMNS) & set(DEMOGRAPHIC_COLUMNS)
    assert set(ex.FEATURE_SETS["colour+demographics"]) == set(CONJ_FEATURE_COLUMNS)


# =========================================================================== #
# 3. Numerical robustness — degenerate inputs must raise, not lie
# =========================================================================== #

def test_empty_mask_raises_rather_than_returning_nan():
    a = np.zeros((8, 8, 4))
    a[..., :3] = 0.5                     # colour present but alpha all zero
    with pytest.raises(ValueError, match="zero pixels"):
        load_conjunctiva_roi(a)


def test_single_pixel_mask_still_produces_finite_features():
    a = np.zeros((8, 8, 4))
    a[..., :3] = [0.7, 0.3, 0.2]
    a[4, 4, 3] = 1.0
    f = conjunctiva_color_features(a)
    assert f["roi_px"] == 1
    # Demographics are NaN unless supplied; only the colour features must be finite.
    assert all(np.isfinite(v) for k, v in f.items() if k not in DEMOGRAPHIC_COLUMNS)


def test_pure_black_roi_does_not_divide_by_zero():
    a = np.zeros((6, 6, 4))
    a[..., 3] = 1.0                      # fully opaque, but RGB all zero
    f = conjunctiva_color_features(a)
    assert all(np.isfinite(v) for k, v in f.items() if k not in DEMOGRAPHIC_COLUMNS)


def test_saturated_white_roi_is_finite():
    a = np.ones((6, 6, 4))
    f = conjunctiva_color_features(a)
    assert all(np.isfinite(v) for k, v in f.items() if k not in DEMOGRAPHIC_COLUMNS)
    assert f["lab_l"] == pytest.approx(100.0, abs=0.1)


def test_uint8_and_float_inputs_agree():
    """0-255 arrays must be normalised identically to 0-1 arrays."""
    f_float = conjunctiva_color_features(_rgba(colour=(0.8, 0.4, 0.2)))
    a = (_rgba(colour=(0.8, 0.4, 0.2)) * 255)
    f_uint = conjunctiva_color_features(a)
    assert f_float["redness_index"] == pytest.approx(f_uint["redness_index"], abs=1e-6)


def test_rejects_malformed_shapes():
    for bad in [np.zeros((5, 5)), np.zeros((5, 5, 2)), np.zeros((5, 5, 5))]:
        with pytest.raises(ValueError):
            load_conjunctiva_roi(bad)


def test_column_matcher_prefers_whole_words():
    """'IMAGE_ID' contains the substring 'age' — it must not match the age column."""
    cols = ["IMAGE_ID", "HB_LEVEL", "Age(Months)", "GENDER", "HOSPITAL"]
    assert _match_column(cols, "age") == "Age(Months)"
    assert _match_column(cols, "hb") == "HB_LEVEL"
    assert _match_column(cols, "sex") == "GENDER"
    assert _match_column(cols, "site") == "HOSPITAL"
    assert _match_column(cols, "image") == "IMAGE_ID"


def test_column_matcher_returns_none_when_absent():
    assert _match_column(["foo", "bar"], "hb") is None


def test_unknown_split_strategy_raises():
    with pytest.raises(ValueError, match="unknown split"):
        ex.make_splitter("teleportation")


def test_unknown_dedup_mode_raises(tmp_path):
    (tmp_path / "m.csv").write_text("IMAGE_ID,HB_LEVEL\nx,10\n")
    with pytest.raises(ValueError, match="dedup must be"):
        load_cp_anemic(tmp_path, dedup="wishful", verbose=False)


def test_missing_dataset_raises_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="mendeley"):
        load_cp_anemic(tmp_path, verbose=False)


# =========================================================================== #
# 4. Determinism — the published number must be reproducible
# =========================================================================== #

def test_out_of_fold_predictions_are_deterministic():
    ds = _toy_dataset()
    a = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site", seed=0)
    b = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site", seed=0)
    assert np.array_equal(a, b)


def test_bootstrap_ci_is_seed_stable():
    rng = np.random.default_rng(0)
    y = rng.uniform(6, 15, 200)
    p = y + rng.normal(0, 1, 200)
    assert ex._bootstrap_auroc_ci(y, p, seed=0) == ex._bootstrap_auroc_ci(y, p, seed=0)


def test_perceptual_grouping_is_stable_under_row_order():
    """Group *membership* must not depend on the order files are presented in."""
    from PIL import Image
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        paths = []
        for i, shade in enumerate([200, 200, 60]):     # first two identical
            a = np.zeros((16, 16, 4), np.uint8)
            a[..., 0] = shade
            a[..., 3] = 255
            p = Path(d) / f"i{i}.png"
            Image.fromarray(a).save(p)
            paths.append(p)
        g = _perceptual_groups(paths)
        assert g[0] == g[1] and g[0] != g[2]
        gr = _perceptual_groups(list(reversed(paths)))
        # Same partition, possibly different labels.
        assert (gr[0] != gr[1]) and (gr[1] == gr[2])


# =========================================================================== #
# 5. Statistical machinery — agree with independent implementations
# =========================================================================== #

def test_delong_auc_matches_sklearn_exactly():
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 300)
    a, b = rng.normal(y, 1, 300), rng.normal(y * 0.3, 1, 300)
    r = st.delong_test(y, a, b)
    assert r.auc_a == pytest.approx(roc_auc_score(y, a), abs=1e-12)
    assert r.auc_b == pytest.approx(roc_auc_score(y, b), abs=1e-12)


def test_delong_identical_scores_give_p_one():
    rng = np.random.default_rng(2)
    y = rng.integers(0, 2, 150)
    s = rng.normal(y, 1, 150)
    r = st.delong_test(y, s, s)
    assert r.difference == pytest.approx(0.0, abs=1e-12)
    assert r.p_value == 1.0


def test_delong_is_antisymmetric():
    rng = np.random.default_rng(3)
    y = rng.integers(0, 2, 200)
    a, b = rng.normal(y, 1, 200), rng.normal(0, 1, 200)
    r1, r2 = st.delong_test(y, a, b), st.delong_test(y, b, a)
    assert r1.difference == pytest.approx(-r2.difference, abs=1e-12)
    assert abs(r1.z) == pytest.approx(abs(r2.z), abs=1e-9)


def test_delong_requires_both_classes():
    with pytest.raises(ValueError, match="both classes"):
        st.delong_test(np.ones(10, dtype=int), np.arange(10.0), np.arange(10.0))


def test_delong_rejects_non_binary_labels():
    with pytest.raises(ValueError, match="binary"):
        st.delong_test(np.array([0, 1, 2, 1]), np.arange(4.0), np.arange(4.0))


def test_delong_ci_brackets_the_difference():
    rng = np.random.default_rng(4)
    y = rng.integers(0, 2, 250)
    a, b = rng.normal(y * 1.5, 1, 250), rng.normal(y * 0.2, 1, 250)
    r = st.delong_test(y, a, b)
    assert r.ci_lower < r.difference < r.ci_upper


def test_brier_score_bounds():
    y = np.array([0, 1, 0, 1])
    assert st.brier_score(y, y.astype(float)) == 0.0            # perfect
    assert st.brier_score(y, 1.0 - y) == 1.0                    # inverted
    assert st.brier_score(y, np.full(4, 0.5)) == pytest.approx(0.25)


def test_calibration_bins_are_weighted_correctly():
    rng = np.random.default_rng(5)
    p = rng.uniform(0, 1, 500)
    y = (rng.uniform(0, 1, 500) < p).astype(int)   # perfectly calibrated by design
    c = st.calibration_bins(y, p, n_bins=10)
    assert sum(b["count"] for b in c["bins"]) == 500
    assert c["ece"] < 0.10, "well-calibrated data should have small ECE"


def test_hosmer_lemeshow_flags_miscalibration():
    rng = np.random.default_rng(6)
    p = rng.uniform(0, 1, 600)
    y_good = (rng.uniform(0, 1, 600) < p).astype(int)
    y_bad = (rng.uniform(0, 1, 600) < np.clip(p * 0.2, 0, 1)).astype(int)
    assert st.hosmer_lemeshow(y_good, p)["well_calibrated"]
    assert not st.hosmer_lemeshow(y_bad, p)["well_calibrated"]


def test_summarise_repeats_ignores_nans():
    s = st.summarise_repeats([0.8, 0.9, float("nan")])
    assert s["n"] == 2 and s["mean"] == pytest.approx(0.85)


# =========================================================================== #
# 6. Adversarial nulls — report NO signal when there is none
# =========================================================================== #

def test_shuffled_labels_collapse_to_chance():
    """The single most important guard: a leak would keep AUROC above 0.5."""
    ds = _toy_dataset(n=200, signal=2.0)
    ctrl = ex.permutation_control(ds, features="colour", split="dedup_site", n_repeats=4)
    assert 0.35 < ctrl["mean_auroc"] < 0.65, ctrl


def test_pure_noise_features_score_near_chance():
    ds = _toy_dataset(n=200, signal=0.0)     # features carry nothing
    oof = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site")
    assert 0.30 < ex._auroc(ds.y, oof) < 0.70


def test_strong_signal_is_detected():
    """The converse guard: a real signal must not be destroyed by the harness."""
    ds = _toy_dataset(n=200, signal=4.0)
    oof = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site")
    assert ex._auroc(ds.y, oof) > 0.80


def test_constant_feature_column_does_not_crash():
    ds = _toy_dataset(n=120)
    ds.X["redness_index"] = 1.0
    oof = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site")
    assert np.isfinite(oof).all()


def test_auroc_undefined_for_single_class_returns_nan():
    y = np.full(20, 13.0)                    # nobody is anaemic
    assert np.isnan(ex._auroc(y, np.arange(20.0)))


def test_spec_at_sensitivity_is_monotone_in_target():
    rng = np.random.default_rng(7)
    y = rng.uniform(6, 15, 300)
    pred = y + rng.normal(0, 1.2, 300)
    hi = ex._spec_at_sensitivity(y, pred, target=0.80)
    lo = ex._spec_at_sensitivity(y, pred, target=0.95)
    assert hi >= lo, "demanding more sensitivity cannot increase specificity"


def test_anemic_property_matches_who_threshold():
    ds = Dataset(X=pd.DataFrame({"a": [1, 2, 3]}),
                 y=np.array([10.9, 11.0, 11.1]), groups=np.array(["s"] * 3))
    assert list(ds.anemic) == [1, 0, 0]
    assert WHO_ANEMIA_HB_THRESHOLD == 11.0


# =========================================================================== #
# 7. Real-data end-to-end invariants
# =========================================================================== #

@requires_cp
def test_real_features_are_physiologically_plausible():
    ds = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    assert ds.X.r_mean.mean() > ds.X.g_mean.mean() > 0      # conjunctiva is red
    assert ds.X.lab_a.mean() > 10                           # clearly on the red axis
    assert (ds.X.redness_index > 1 / 3).mean() > 0.95       # red dominates
    assert ds.X.h_mean.between(0, 1).all()                  # hue stays in range
    assert (ds.X.roi_px if "roi_px" in ds.X else pd.Series([1])).notna().all()


@requires_cp
def test_real_dataset_has_no_missing_or_infinite_features():
    ds = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    assert np.isfinite(ds.X.to_numpy()).all()
    assert np.isfinite(ds.y).all()


@requires_cp
def test_headline_auroc_is_reproducible_and_in_range():
    """Locks the published number against silent regressions."""
    ds = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    oof = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site")
    auroc = ex._auroc(ds.y, oof)
    assert 0.74 < auroc < 0.82, f"headline AUROC moved: {auroc:.4f}"


@requires_cp
def test_image_features_beat_demographics_on_real_data():
    """The central claim: the camera contributes beyond age and sex."""
    ds = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    colour = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["colour"], "dedup_site")
    demo = ex.out_of_fold_predictions(ds, ex.FEATURE_SETS["demographics"], "dedup_site")
    r = st.delong_test(ds.anemic, -colour, -demo)
    assert r.difference > 0.10, r
    assert r.p_value < 0.001, r


@requires_cp
def test_leakage_inflation_is_positive_and_material():
    """The headline finding: the naive split really is optimistic."""
    naive = load_cp_anemic(_CP_ROOT, dedup="none", verbose=False)
    strict = load_cp_anemic(_CP_ROOT, dedup="perceptual", verbose=False)
    a = ex._auroc(naive.y, ex.out_of_fold_predictions(
        naive, ex.FEATURE_SETS["colour"], "naive_random"))
    b = ex._auroc(strict.y, ex.out_of_fold_predictions(
        strict, ex.FEATURE_SETS["colour"], "dedup_site"))
    assert a - b > 0.05, f"expected material inflation, got {a - b:.4f}"
