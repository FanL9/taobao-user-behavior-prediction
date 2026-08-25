"""Train-only feature selection for Stage 3 next-day purchase modeling."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pandas as pd


class Stage3FeatureSelector:
    """Apply frozen high-missing, low-variance and correlation rules."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = copy.deepcopy(config)
        self.selection_config = self.config["feature_selection"]
        self.fit_split = str(self.config.get("fit_split", "train"))
        self.is_fitted_ = False
        self.input_features_: list[str] = []
        self.selected_features_: list[str] = []
        self.drop_records_: list[dict[str, Any]] = []
        self.missing_rates_: dict[str, float] = {}

    @staticmethod
    def _is_binary(series: pd.Series) -> bool:
        unique = set(pd.unique(series.dropna()))
        return bool(unique) and unique.issubset({0, 1, 0.0, 1.0})

    def _record_drop(
        self,
        *,
        feature: str,
        reason: str,
        statistic: float,
        threshold: float,
        paired_feature: str | None = None,
    ) -> None:
        self.drop_records_.append(
            {
                "feature": feature,
                "reason": reason,
                "statistic": float(statistic),
                "threshold": float(threshold),
                "paired_feature": paired_feature,
                "fit_split": self.fit_split,
            }
        )

    def _drop_high_missing(self, X: pd.DataFrame, dropped: set[str]) -> None:
        config = self.selection_config["high_missing"]
        if not bool(config.get("enabled", True)):
            return
        threshold = float(config["threshold"])
        for feature in self.input_features_:
            missing_rate = float(self.missing_rates_.get(feature, 0.0))
            if missing_rate > threshold:
                dropped.add(feature)
                self._record_drop(
                    feature=feature,
                    reason="high_missing_rate",
                    statistic=missing_rate,
                    threshold=threshold,
                )

    def _drop_low_variance(self, X: pd.DataFrame, dropped: set[str]) -> None:
        config = self.selection_config["low_variance"]
        if not bool(config.get("enabled", True)):
            return
        variance_threshold = float(config["continuous_variance_threshold"])
        dominant_threshold = float(config["binary_max_dominant_frequency"])

        for feature in self.input_features_:
            if feature in dropped:
                continue
            values = pd.to_numeric(X[feature], errors="coerce")
            non_null = values.dropna()
            unique_count = int(non_null.nunique(dropna=True))
            if unique_count <= 1:
                dropped.add(feature)
                self._record_drop(
                    feature=feature,
                    reason="constant",
                    statistic=0.0,
                    threshold=variance_threshold,
                )
                continue

            if self._is_binary(non_null):
                dominant = float(non_null.value_counts(normalize=True).max())
                if dominant >= dominant_threshold:
                    dropped.add(feature)
                    self._record_drop(
                        feature=feature,
                        reason="near_constant_binary",
                        statistic=dominant,
                        threshold=dominant_threshold,
                    )
                continue

            variance = float(non_null.var(ddof=0))
            if not np.isfinite(variance) or variance <= variance_threshold:
                dropped.add(feature)
                self._record_drop(
                    feature=feature,
                    reason="low_variance",
                    statistic=variance,
                    threshold=variance_threshold,
                )

    def _priority_key(self, feature: str) -> tuple[Any, ...]:
        config = self.selection_config["high_correlation"]
        whitelist = set(config.get("whitelist", []))
        prefixes = list(config.get("preferred_feature_prefixes", []))
        prefix_rank = len(prefixes)
        for index, prefix in enumerate(prefixes):
            if feature.startswith(prefix):
                prefix_rank = index
                break
        return (
            0 if feature in whitelist else 1,
            float(self.missing_rates_.get(feature, 0.0)),
            prefix_rank,
            feature,
        )

    def _drop_high_correlation(self, X: pd.DataFrame, dropped: set[str]) -> None:
        config = self.selection_config["high_correlation"]
        if not bool(config.get("enabled", True)):
            return
        threshold = float(config["threshold"])
        method = str(config.get("method", "pearson"))
        include_binary = bool(config.get("include_binary", False))
        whitelist = set(config.get("whitelist", []))

        candidates: list[str] = []
        for feature in self.input_features_:
            if feature in dropped:
                continue
            values = pd.to_numeric(X[feature], errors="coerce")
            if values.notna().sum() < 2:
                continue
            if not include_binary and self._is_binary(values):
                continue
            candidates.append(feature)

        ordered = sorted(candidates, key=self._priority_key)
        if len(ordered) < 2:
            return
        correlations = X[ordered].corr(method=method).abs()

        for keeper_index, keeper in enumerate(ordered):
            if keeper in dropped:
                continue
            for candidate in ordered[keeper_index + 1 :]:
                if candidate in dropped:
                    continue
                if keeper in whitelist and candidate in whitelist:
                    continue
                value = correlations.at[keeper, candidate]
                if pd.isna(value) or float(value) < threshold:
                    continue
                dropped.add(candidate)
                self._record_drop(
                    feature=candidate,
                    reason="high_correlation",
                    statistic=float(value),
                    threshold=threshold,
                    paired_feature=keeper,
                )

    def fit(
        self,
        X_train: pd.DataFrame,
        *,
        raw_missing_rates: dict[str, float] | None = None,
        split_name: str | None = None,
    ) -> Stage3FeatureSelector:
        actual_split = split_name or self.fit_split
        if actual_split != self.fit_split:
            raise ValueError(
                f"Stage3FeatureSelector may only fit on {self.fit_split}; "
                f"received {actual_split}"
            )
        if self.is_fitted_:
            raise RuntimeError("Stage3FeatureSelector has already been fitted")
        if X_train.empty or not len(X_train.columns):
            raise ValueError("Feature selection requires a non-empty train matrix")

        non_numeric = [
            column
            for column in X_train.columns
            if not pd.api.types.is_numeric_dtype(X_train[column])
        ]
        if non_numeric:
            raise ValueError(f"Feature selector received non-numeric fields: {non_numeric}")

        self.input_features_ = X_train.columns.tolist()
        observed_missing = X_train.isna().mean().to_dict()
        self.missing_rates_ = {
            feature: float(
                (raw_missing_rates or {}).get(
                    feature,
                    observed_missing.get(feature, 0.0),
                )
            )
            for feature in self.input_features_
        }

        dropped: set[str] = set()
        self._drop_high_missing(X_train, dropped)
        self._drop_low_variance(X_train, dropped)
        self._drop_high_correlation(X_train, dropped)

        self.selected_features_ = [
            feature for feature in self.input_features_ if feature not in dropped
        ]
        if not self.selected_features_:
            raise RuntimeError("All Stage 3 features were removed by selection")
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not self.is_fitted_:
            raise RuntimeError("Stage3FeatureSelector must be fitted before transform")
        missing = [
            feature for feature in self.selected_features_ if feature not in X.columns
        ]
        if missing:
            raise ValueError(f"Transform matrix is missing selected features: {missing}")
        return X[self.selected_features_].copy()

    def fit_transform(
        self,
        X_train: pd.DataFrame,
        *,
        raw_missing_rates: dict[str, float] | None = None,
        split_name: str | None = None,
    ) -> pd.DataFrame:
        self.fit(
            X_train,
            raw_missing_rates=raw_missing_rates,
            split_name=split_name,
        )
        return self.transform(X_train)

    def get_selected_features(self) -> list[str]:
        if not self.is_fitted_:
            raise RuntimeError("Stage3FeatureSelector is not fitted")
        return list(self.selected_features_)

    def get_drop_records(self) -> list[dict[str, Any]]:
        if not self.is_fitted_:
            raise RuntimeError("Stage3FeatureSelector is not fitted")
        return copy.deepcopy(self.drop_records_)

    def get_state(self) -> dict[str, Any]:
        if not self.is_fitted_:
            raise RuntimeError("Stage3FeatureSelector is not fitted")
        return {
            "config_version": self.config.get("version"),
            "fit_split": self.fit_split,
            "input_features": list(self.input_features_),
            "selected_features": list(self.selected_features_),
            "missing_rates": dict(self.missing_rates_),
            "drop_records": copy.deepcopy(self.drop_records_),
        }
