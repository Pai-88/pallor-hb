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
