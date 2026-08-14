"""Regression model for hemoglobin estimation.

A thin wrapper around a scikit-learn pipeline (standardization + gradient boosting).
Kept small on purpose: the interesting engineering is in the features and the
clinical evaluation, and a strong tabular baseline should be beaten before reaching
for a deep model (roadmap W3 compares against a 1-D CNN on raw windows).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class HbRegressor:
    """Predict hemoglobin (g/dL) from a feature table."""

    def __init__(self, random_state: int = 0):
        self.pipeline = Pipeline(
            steps=[
                ("scale", StandardScaler()),
                (
                    "gbr",
                    GradientBoostingRegressor(
                        n_estimators=300,
                        max_depth=3,
                        learning_rate=0.05,
                        subsample=0.9,
                        random_state=random_state,
                    ),
                ),
            ]
        )
        self._feature_names: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "HbRegressor":
        self._feature_names = list(X.columns)
        self.pipeline.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict(X)

    def feature_importances(self) -> dict[str, float]:
        gbr: GradientBoostingRegressor = self.pipeline.named_steps["gbr"]
        names = self._feature_names or [f"f{i}" for i in range(len(gbr.feature_importances_))]
        return dict(sorted(zip(names, gbr.feature_importances_.tolist()),
                           key=lambda kv: kv[1], reverse=True))


class AnemiaClassifier:
    """Predict P(anaemic) directly, with probability calibration.

    The regressor above ranks well enough to compute an AUROC, but its raw output
    is a haemoglobin value in g/dL and cannot be read as a probability. A
    screening tool that reports "72% likely anaemic" must have that number mean
    what it says, which is what this class provides.

    **Calibration defaults to OFF, contrary to the usual advice.** Measured on
    CP-AnemiC (see `experiment.calibration_comparison`), wrapping this model in
    `CalibratedClassifierCV` made both calibration *and* discrimination worse:

        variant              Brier    ECE   AUROC   probability range
        uncalibrated         0.174  0.054   0.818   [0.01, 0.98]
        isotonic  cv=3       0.200  0.116   0.788   [0.00, 0.92]
        sigmoid   cv=3       0.213  0.169   0.789   [0.20, 0.71]

    The mechanism is visible in that last column. `CalibratedClassifierCV` fits k
    sub-models on k-1 folds each and averages their outputs; averaging pulls
    probabilities toward the centre, and with only ~380 training rows each
    sub-model is data-starved as well. The result is systematic *under*
    -confidence — the opposite of the over-confidence calibration is meant to
    cure. Pass `calibrate=True` to reproduce that comparison.
    """

    def __init__(self, random_state: int = 0, calibrate: bool = False):
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import GradientBoostingClassifier

        base = Pipeline(steps=[
            ("scale", StandardScaler()),
            ("gbc", GradientBoostingClassifier(
                n_estimators=300, max_depth=3, learning_rate=0.05,
                subsample=0.9, random_state=random_state)),
        ])
        # cv=3 inner folds: enough to calibrate without starving the base fit.
        self.model = (CalibratedClassifierCV(base, method="isotonic", cv=3)
                      if calibrate else base)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "AnemiaClassifier":
        self.model.fit(X, np.asarray(y).astype(int))
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Probability of the positive (anaemic) class."""
        return self.model.predict_proba(X)[:, 1]
