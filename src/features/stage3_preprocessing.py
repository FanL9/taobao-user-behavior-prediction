"""Train-fitted preprocessing for Stage 3 next-day purchase samples."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass(frozen=True)
class Stage3TransformResult:
    """Logical output parts kept separate to prevent role leakage."""

    tracking_df: pd.DataFrame
    X: pd.DataFrame
    y: pd.Series | None


class Stage3Preprocessor:
    """Fit preprocessing rules on train and apply frozen rules elsewhere."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        scaling_profile: str | None = None,
    ) -> None:
        self.config = copy.deepcopy(config)
        scaling = self.config["preprocessing"]["scaling"]
        self.scaling_profile = scaling_profile or scaling["default_profile"]
        if self.scaling_profile not in scaling["profiles"]:
            raise ValueError(f"Unknown scaling profile: {self.scaling_profile}")

        self.fit_split = str(self.config.get("fit_split", "train"))
        self.tracking_columns = list(self.config["tracking_columns"])
        self.sample_key_columns = list(self.config["sample_key_columns"])
        self.target_column = str(self.config["target_column"])
        self.metadata_columns = list(self.config["metadata_columns"])
        self.categorical_columns = list(self.config["categorical_columns"])
        self.sequence_columns = list(self.config["sequence_columns"])
        self.forbidden_feature_columns = set(
            self.config["forbidden_feature_columns"]
        )
        self.leakage_patterns = [
            re.compile(pattern)
            for pattern in self.config.get("leakage_name_patterns", [])
        ]

        self.is_fitted_ = False
        self.raw_feature_columns_: list[str] = []
        self.numeric_columns_: list[str] = []
        self.active_categorical_columns_: list[str] = []
        self.active_sequence_columns_: list[str] = []
        self.numeric_fill_values_: dict[str, float] = {}
        self.numeric_output_dtypes_: dict[str, str] = {}
        self.raw_missing_rates_: dict[str, float] = {}
        self.output_missing_rates_: dict[str, float] = {}
        self.feature_source_map_: dict[str, str] = {}
        self.categorical_levels_: dict[str, list[str]] = {}
        self.binary_numeric_columns_: set[str] = set()
        self.clip_bounds_: dict[str, tuple[float, float]] = {}
        self.scaled_columns_: list[str] = []
        self.feature_names_out_: list[str] = []
        self.fit_metadata_: dict[str, Any] = {}
        self.encoder_: OneHotEncoder | None = None
        self.scaler_: StandardScaler | None = None

    def _required_columns(self, *, require_target: bool) -> list[str]:
        required = list(dict.fromkeys(self.tracking_columns + self.metadata_columns))
        if require_target:
            required.append(self.target_column)
        return required

    def _validate_required_columns(
        self,
        df: pd.DataFrame,
        *,
        require_target: bool,
    ) -> None:
        missing = [
            column
            for column in self._required_columns(require_target=require_target)
            if column not in df.columns
        ]
        if missing:
            raise ValueError(f"Stage 3 input is missing required columns: {missing}")

        required_non_null = list(self.tracking_columns)
        if require_target:
            required_non_null.append(self.target_column)
        null_columns = [
            column for column in required_non_null if df[column].isna().any()
        ]
        if null_columns:
            raise ValueError(
                "Stage 3 tracking/target columns contain null values: "
                f"{null_columns}"
            )

    def _matches_leakage_pattern(self, column: str) -> bool:
        return any(pattern.search(column) for pattern in self.leakage_patterns)

    def _candidate_feature_columns(self, df: pd.DataFrame) -> list[str]:
        role_columns = (
            set(self.tracking_columns)
            | set(self.metadata_columns)
            | {self.target_column}
            | self.forbidden_feature_columns
        )
        candidates = [column for column in df.columns if column not in role_columns]
        suspicious = [
            column for column in candidates if self._matches_leakage_pattern(column)
        ]
        if suspicious:
            raise ValueError(
                "Potential target leakage columns were found in raw features: "
                f"{suspicious}"
            )
        return candidates

    @staticmethod
    def _is_binary(values: pd.Series) -> bool:
        unique = set(pd.unique(values.dropna()))
        return bool(unique) and unique.issubset({0, 1, 0.0, 1.0})

    def _is_count_feature(self, column: str) -> bool:
        patterns = self.config["preprocessing"]["missing"].get(
            "count_name_patterns", []
        )
        return any(re.search(pattern, column) for pattern in patterns)

    def _fit_numeric(self, train_df: pd.DataFrame) -> None:
        missing_config = self.config["preprocessing"]["missing"]
        count_fill = float(missing_config.get("count_fill_value", 0.0))

        for column in self.numeric_columns_:
            values = pd.to_numeric(train_df[column], errors="coerce").replace(
                [np.inf, -np.inf], np.nan
            )
            self.raw_missing_rates_[column] = float(values.isna().mean())
            if self._is_count_feature(column):
                fill_value = count_fill
            else:
                median = values.median(skipna=True)
                fill_value = 0.0 if pd.isna(median) else float(median)
            self.numeric_fill_values_[column] = fill_value

            filled = values.fillna(fill_value)
            if self._is_binary(filled):
                self.binary_numeric_columns_.add(column)

        outlier = self.config["preprocessing"]["outlier"]
        strategy = str(outlier.get("strategy", "disabled"))
        if strategy not in {"disabled", "clip"}:
            raise ValueError(f"Unsupported outlier strategy: {strategy}")
        if strategy == "disabled":
            pass
        else:
            lower_q = float(outlier["lower_quantile"])
            upper_q = float(outlier["upper_quantile"])
            if not 0.0 <= lower_q < upper_q <= 1.0:
                raise ValueError(
                    "Outlier quantiles must satisfy 0 <= lower < upper <= 1"
                )

            exclude_binary = bool(outlier.get("exclude_binary", True))
            for column in self.numeric_columns_:
                if exclude_binary and column in self.binary_numeric_columns_:
                    continue
                values = (
                    pd.to_numeric(train_df[column], errors="coerce")
                    .replace([np.inf, -np.inf], np.nan)
                    .fillna(self.numeric_fill_values_[column])
                )
                lower = float(values.quantile(lower_q))
                upper = float(values.quantile(upper_q))
                self.clip_bounds_[column] = (lower, upper)

        for column in self.numeric_columns_:
            values = (
                pd.to_numeric(train_df[column], errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
                .fillna(self.numeric_fill_values_[column])
            )
            if column in self.clip_bounds_:
                lower, upper = self.clip_bounds_[column]
                values = values.clip(lower=lower, upper=upper)
            if column in self.binary_numeric_columns_:
                self.numeric_output_dtypes_[column] = "uint8"
            elif self._is_count_feature(column) and np.allclose(
                values.to_numpy(dtype=np.float64),
                np.round(values.to_numpy(dtype=np.float64)),
            ):
                self.numeric_output_dtypes_[column] = "int64"
            else:
                self.numeric_output_dtypes_[column] = "float64"

    def _fit_categories(self, train_df: pd.DataFrame) -> None:
        categorical_config = self.config["preprocessing"]["categorical"]
        unknown = str(categorical_config.get("unknown_value", "__UNKNOWN__"))

        category_arrays: list[list[str]] = []
        for column in self.active_categorical_columns_:
            values = train_df[column].fillna(unknown).astype(str)
            levels = sorted(set(values.tolist()) - {unknown}) + [unknown]
            self.categorical_levels_[column] = levels
            self.raw_missing_rates_[column] = float(train_df[column].isna().mean())
            category_arrays.append(levels)

        if category_arrays:
            self.encoder_ = OneHotEncoder(
                categories=category_arrays,
                handle_unknown="ignore",
                sparse_output=False,
                dtype=np.uint8,
            )
            fit_values = self._prepare_categories(train_df)
            self.encoder_.fit(fit_values)

    def _prepare_categories(self, df: pd.DataFrame) -> pd.DataFrame:
        unknown = str(
            self.config["preprocessing"]["categorical"].get(
                "unknown_value", "__UNKNOWN__"
            )
        )
        prepared: dict[str, pd.Series] = {}
        for column in self.active_categorical_columns_:
            values = df[column].fillna(unknown).astype(str)
            known = set(self.categorical_levels_[column])
            prepared[column] = values.where(values.isin(known), unknown)
        return pd.DataFrame(prepared, index=df.index)

    @staticmethod
    def _parse_sequence(value: Any, length: int) -> list[int]:
        if value is None or (not isinstance(value, (list, tuple, np.ndarray)) and pd.isna(value)):
            return [0] * length
        if isinstance(value, (list, tuple, np.ndarray)):
            parts = value
        else:
            parts = str(value).split("|")
        sequence: list[int] = []
        for part in parts:
            text = str(part).strip()
            if text in {"1", "2", "3", "4"}:
                sequence.append(int(text))
        sequence = sequence[-length:]
        return [0] * (length - len(sequence)) + sequence

    def _sequence_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        length = int(self.config["sequence_length"])
        behavior_values = list(self.config["sequence_behavior_values"])
        output: dict[str, np.ndarray] = {}

        for sequence_column in self.active_sequence_columns_:
            sequences = df[sequence_column].map(
                lambda value: self._parse_sequence(value, length)
            )
            matrix = np.asarray(sequences.tolist(), dtype=np.uint8)
            use_legacy_names = len(self.active_sequence_columns_) == 1
            prefix = "seq" if use_legacy_names else sequence_column
            for index in range(length):
                output[f"{prefix}_pos_{index + 1}"] = matrix[:, index]
            for behavior in behavior_values:
                output[f"{prefix}_count_behavior_{behavior}"] = (
                    matrix == behavior
                ).sum(axis=1).astype(np.uint8)
            output[f"{prefix}_distinct_behavior_count"] = np.asarray(
                [len(set(row[row > 0])) for row in matrix],
                dtype=np.uint8,
            )

        return pd.DataFrame(output, index=df.index)

    def _numeric_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        output: dict[str, pd.Series] = {}
        for column in self.numeric_columns_:
            values = (
                pd.to_numeric(df[column], errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
                .fillna(self.numeric_fill_values_[column])
            )
            if column in self.clip_bounds_:
                lower, upper = self.clip_bounds_[column]
                values = values.clip(lower=lower, upper=upper)
            output_dtype = self.numeric_output_dtypes_[column]
            if output_dtype == "uint8" and not self._is_binary(values):
                raise ValueError(
                    f"Binary train feature {column} contains non-binary values "
                    "during transform"
                )
            if output_dtype == "int64" and not np.allclose(
                values.to_numpy(dtype=np.float64),
                np.round(values.to_numpy(dtype=np.float64)),
            ):
                raise ValueError(
                    f"Integral count feature {column} contains fractional values"
                )
            output[column] = values.astype(output_dtype)
        return pd.DataFrame(output, index=df.index)

    def _categorical_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.active_categorical_columns_:
            return pd.DataFrame(index=df.index)
        if self.encoder_ is None:
            raise RuntimeError("Categorical encoder is not fitted")

        prepared = self._prepare_categories(df)
        matrix = self.encoder_.transform(prepared)
        names = [
            f"{column}__{level}"
            for column in self.active_categorical_columns_
            for level in self.categorical_levels_[column]
        ]
        return pd.DataFrame(matrix, columns=names, index=df.index)

    def _transform_features(
        self,
        df: pd.DataFrame,
        *,
        apply_scaling: bool,
    ) -> pd.DataFrame:
        numeric = self._numeric_frame(df)
        categorical = self._categorical_frame(df)
        sequence = self._sequence_frame(df)
        X = pd.concat([numeric, categorical, sequence], axis=1)

        if apply_scaling and self.scaler_ is not None and self.scaled_columns_:
            scaled = self.scaler_.transform(X[self.scaled_columns_])
            for index, column in enumerate(self.scaled_columns_):
                X[column] = scaled[:, index]
        return X.reset_index(drop=True)

    def _build_feature_metadata(self) -> None:
        self.feature_source_map_ = {
            column: column for column in self.numeric_columns_
        }
        for column in self.active_categorical_columns_:
            for level in self.categorical_levels_[column]:
                self.feature_source_map_[f"{column}__{level}"] = column
        for sequence_column in self.active_sequence_columns_:
            for feature in self.feature_names_out_:
                if feature.startswith("seq_"):
                    self.feature_source_map_[feature] = sequence_column

        self.output_missing_rates_ = {
            feature: self.raw_missing_rates_.get(source, 0.0)
            for feature, source in self.feature_source_map_.items()
        }

    def fit(
        self,
        train_df: pd.DataFrame,
        *,
        split_name: str | None = None,
        fit_metadata: dict[str, Any] | None = None,
    ) -> Stage3Preprocessor:
        actual_split = split_name or self.fit_split
        if actual_split != self.fit_split:
            raise ValueError(
                f"Stage3Preprocessor may only fit on {self.fit_split}; "
                f"received {actual_split}"
            )
        if self.is_fitted_:
            raise RuntimeError("Stage3Preprocessor has already been fitted")

        self._validate_required_columns(train_df, require_target=True)
        if train_df.empty:
            raise ValueError("Stage 3 preprocessing requires non-empty train data")
        candidates = self._candidate_feature_columns(train_df)
        self.raw_feature_columns_ = list(candidates)
        self.active_categorical_columns_ = [
            column for column in self.categorical_columns if column in candidates
        ]
        self.active_sequence_columns_ = [
            column for column in self.sequence_columns if column in candidates
        ]
        special = set(self.active_categorical_columns_) | set(
            self.active_sequence_columns_
        )
        self.numeric_columns_ = [
            column for column in candidates if column not in special
        ]

        datetime_features = [
            column
            for column in self.numeric_columns_
            if pd.api.types.is_datetime64_any_dtype(train_df[column])
        ]
        if datetime_features:
            raise ValueError(
                "Unclassified raw datetime fields cannot enter Stage 3 X: "
                f"{datetime_features}"
            )
        non_numeric = [
            column
            for column in self.numeric_columns_
            if pd.to_numeric(train_df[column], errors="coerce").isna().all()
            and train_df[column].notna().any()
        ]
        if non_numeric:
            raise ValueError(f"Unclassified non-numeric Stage 3 features: {non_numeric}")

        for column in self.active_sequence_columns_:
            self.raw_missing_rates_[column] = float(train_df[column].isna().mean())
        self._fit_numeric(train_df)
        self._fit_categories(train_df)

        unscaled = self._transform_features(train_df, apply_scaling=False)
        self.feature_names_out_ = unscaled.columns.tolist()

        scaling = self.config["preprocessing"]["scaling"]["profiles"][
            self.scaling_profile
        ]
        strategy = str(scaling.get("strategy", "none"))
        if strategy not in {"none", "standard"}:
            raise ValueError(f"Unsupported scaling strategy: {strategy}")
        if strategy == "standard":
            exclude_binary = bool(scaling.get("exclude_binary", True))
            self.scaled_columns_ = [
                column
                for column in self.numeric_columns_
                if not (exclude_binary and column in self.binary_numeric_columns_)
            ]
            if self.scaled_columns_:
                self.scaler_ = StandardScaler()
                self.scaler_.fit(unscaled[self.scaled_columns_])

        self.fit_metadata_ = copy.deepcopy(fit_metadata or {})
        self.fit_metadata_["fit_split"] = self.fit_split
        self.fit_metadata_["fit_rows"] = int(len(train_df))
        self.is_fitted_ = True
        self._build_feature_metadata()
        return self

    def transform(
        self,
        df: pd.DataFrame,
        *,
        apply_scaling: bool = True,
    ) -> Stage3TransformResult:
        if not self.is_fitted_:
            raise RuntimeError("Stage3Preprocessor must be fitted before transform")
        self._validate_required_columns(
            df,
            require_target=self.target_column in df.columns,
        )
        self._candidate_feature_columns(df)
        missing_features = [
            column for column in self.raw_feature_columns_ if column not in df.columns
        ]
        if missing_features:
            raise ValueError(
                "Transform input is missing train-fitted raw features: "
                f"{missing_features}"
            )

        tracking = df[self.tracking_columns].copy().reset_index(drop=True)
        X = self._transform_features(df, apply_scaling=apply_scaling)
        X = X[self.feature_names_out_]
        y = None
        if self.target_column in df.columns:
            y = df[self.target_column].copy().reset_index(drop=True)
            y.name = self.target_column
        return Stage3TransformResult(tracking_df=tracking, X=X, y=y)

    def fit_transform(
        self,
        train_df: pd.DataFrame,
        *,
        split_name: str | None = None,
        fit_metadata: dict[str, Any] | None = None,
    ) -> Stage3TransformResult:
        self.fit(
            train_df,
            split_name=split_name,
            fit_metadata=fit_metadata,
        )
        return self.transform(train_df)

    def get_feature_names_out(self) -> list[str]:
        if not self.is_fitted_:
            raise RuntimeError("Stage3Preprocessor is not fitted")
        return list(self.feature_names_out_)

    def get_output_missing_rates(self) -> dict[str, float]:
        if not self.is_fitted_:
            raise RuntimeError("Stage3Preprocessor is not fitted")
        return dict(self.output_missing_rates_)

    def get_state(self) -> dict[str, Any]:
        if not self.is_fitted_:
            raise RuntimeError("Stage3Preprocessor is not fitted")
        return {
            "config_version": self.config.get("version"),
            "fit_split": self.fit_split,
            "scaling_profile": self.scaling_profile,
            "fit_metadata": copy.deepcopy(self.fit_metadata_),
            "tracking_columns": list(self.tracking_columns),
            "target_column": self.target_column,
            "raw_feature_columns": list(self.raw_feature_columns_),
            "numeric_columns": list(self.numeric_columns_),
            "categorical_levels": copy.deepcopy(self.categorical_levels_),
            "numeric_fill_values": dict(self.numeric_fill_values_),
            "numeric_output_dtypes": dict(self.numeric_output_dtypes_),
            "raw_missing_rates": dict(self.raw_missing_rates_),
            "clip_bounds": {
                column: [lower, upper]
                for column, (lower, upper) in self.clip_bounds_.items()
            },
            "scaled_columns": list(self.scaled_columns_),
            "feature_names_out": list(self.feature_names_out_),
            "feature_source_map": dict(self.feature_source_map_),
        }
