"""Dataset loading and synthetic data generation.

Real data is integrated in Week 2 of the roadmap. Until then, `make_synthetic_ppg`
produces a physiologically-motivated synthetic dataset so the whole pipeline
(features -> model -> clinical evaluation) is runnable and testable from day one.

No patient data is ever committed to this repo; see data/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# Feature columns produced for the PPG modality. Kept in one place so the
# synthetic generator, real loaders, and the model all agree on the schema.
PPG_FEATURE_COLUMNS = [
    "red_ir_ratio",       # ratio of red/IR AC-DC (classic pulse-oximetry style feature)
    "perfusion_index",    # AC/DC amplitude, a signal-quality + physiology proxy
    "systolic_amp",       # normalized systolic peak amplitude
    "dicrotic_ratio",     # dicrotic notch height / systolic height (vascular tone)
    "pulse_area",         # area under one normalized pulse
    "rise_time",          # foot-to-peak time (s)
    "hr_bpm",             # heart rate
    "age",                # demographic covariate
    "is_female",          # demographic covariate (0/1)
]


@dataclass
class Dataset:
    """A simple (features, target, groups) bundle."""

    X: pd.DataFrame
    y: np.ndarray          # reference hemoglobin, g/dL
    groups: np.ndarray     # subject id, for leakage-free CV

    def __len__(self) -> int:
        return len(self.y)


def make_synthetic_ppg(n: int = 2000, seed: int = 0, n_subjects: int | None = None) -> Dataset:
    """Generate a synthetic (PPG-feature, Hb) dataset.

    The generative model is deliberately *simple but not linear*: hemoglobin is
    driven by a few features through monotone-ish relationships plus interaction
    and noise, so a linear model underfits and a gradient-boosted model has
    something real to learn. This is a stand-in for real data, NOT a claim about
    true PPG physiology.

    Args:
        n: number of samples.
        seed: RNG seed.
        n_subjects: number of distinct subjects (for group-aware CV). Defaults to n//4.
    """
    rng = np.random.default_rng(seed)
    if n_subjects is None:
        n_subjects = max(2, n // 4)

    groups = rng.integers(0, n_subjects, size=n)
    # Per-subject random offset so repeated samples from one subject correlate.
    subject_offset = rng.normal(0, 0.6, size=n_subjects)[groups]

    age = rng.uniform(5, 80, size=n)
    is_female = rng.integers(0, 2, size=n).astype(float)

    # Latent physiology.
    perfusion_index = np.clip(rng.gamma(2.0, 0.9, size=n), 0.05, 8.0)
    hr_bpm = np.clip(rng.normal(78, 14, size=n), 45, 150)
    red_ir_ratio = np.clip(rng.normal(0.9, 0.15, size=n), 0.4, 1.6)
    dicrotic_ratio = np.clip(rng.normal(0.35, 0.1, size=n), 0.05, 0.8)
    rise_time = np.clip(rng.normal(0.16, 0.03, size=n), 0.08, 0.3)
    systolic_amp = np.clip(rng.normal(1.0, 0.12, size=n), 0.5, 1.6)
    pulse_area = np.clip(systolic_amp * (0.55 + 0.4 * dicrotic_ratio)
                         + rng.normal(0, 0.05, size=n), 0.2, 1.6)

    # Hemoglobin as a nonlinear function of features + demographics + subject effect.
    hb = (
        13.5
        - 3.2 * (red_ir_ratio - 0.9)          # higher red/IR ratio -> lower Hb
        + 0.9 * np.log(perfusion_index)        # better perfusion -> slightly higher signal Hb
        - 1.1 * is_female                       # sex difference in reference ranges
        - 0.015 * (age - 40)                    # mild age trend
        + 2.0 * (dicrotic_ratio - 0.35)         # vascular-tone interaction
        - 1.5 * (systolic_amp - 1.0) * red_ir_ratio  # interaction term
        + subject_offset
        + rng.normal(0, 0.7, size=n)            # irreducible noise (~0.7 g/dL)
    )
    hb = np.clip(hb, 4.0, 19.0)

    X = pd.DataFrame(
        {
            "red_ir_ratio": red_ir_ratio,
            "perfusion_index": perfusion_index,
            "systolic_amp": systolic_amp,
            "dicrotic_ratio": dicrotic_ratio,
            "pulse_area": pulse_area,
            "rise_time": rise_time,
            "hr_bpm": hr_bpm,
            "age": age,
            "is_female": is_female,
        },
        columns=PPG_FEATURE_COLUMNS,
    )
    return Dataset(X=X, y=hb.astype(float), groups=groups)
