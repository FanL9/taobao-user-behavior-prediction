import copy
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.stage3_preprocessing import Stage3Preprocessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config():
    return json.loads(
        (PROJECT_ROOT / "configs" / "stage3_feature_config.json").read_text(
            encoding="utf-8-sig"
        )
    )


def make_frame(periods, scores, counts, labels=None):
    size = len(periods)
    prediction_date = pd.Timestamp("2025-01-01")
    return pd.DataFrame(
        {
            "user_id": range(1, size + 1),
            "item_id": range(101, 101 + size),
            "category_id": range(201, 201 + size),
            "prediction_date": [prediction_date] * size,
            "cutoff_time": [pd.Timestamp("2025-01-01 23:59:59")] * size,
            "label_start": [pd.Timestamp("2025-01-02")] * size,
            "label_end": [pd.Timestamp("2025-01-02 23:59:59")] * size,
            "label": labels if labels is not None else [0, 1] * (size // 2),
            "event_count": counts,
            "score": scores,
            "binary_flag": [0, 1] * (size // 2),
            "time_period": periods,
            "weekday": [0, 1, 2, 3][:size],
            "sequence_recent_10_behavior_types": ["1|3", "1|4"]
            * (size // 2),
            "user_activity_level": ["high", "low"] * (size // 2),
            "item_popularity_level": ["high", "low"] * (size // 2),
            "category_popularity_level": ["popular", "long_tail"]
            * (size // 2),
            "time_is_peak_hour": [0, 1] * (size // 2),
        }
    )


class Stage3PreprocessingTests(unittest.TestCase):
    def test_train_fitted_missing_unknown_clipping_and_roles(self) -> None:
        config = load_config()
        config["preprocessing"]["outlier"].update(
            {"strategy": "clip", "lower_quantile": 0.25, "upper_quantile": 0.75}
        )
        train = make_frame(
            ["morning", "afternoon", None, "night"],
            [1.0, 2.0, np.nan, 100.0],
            [1.0, np.nan, 3.0, 4.0],
        )
        valid = make_frame(
            ["dawn", None, "morning", "night"],
            [np.nan, 1000.0, 2.0, 3.0],
            [np.nan, 1000.0, 2.0, 3.0],
        )

        preprocessor = Stage3Preprocessor(config, scaling_profile="tree")
        train_result = preprocessor.fit_transform(train, split_name="train")
        state_before = copy.deepcopy(preprocessor.get_state())
        valid_result = preprocessor.transform(valid)

        self.assertEqual(
            valid_result.tracking_df.columns.tolist(),
            config["tracking_columns"],
        )
        for forbidden in config["tracking_columns"] + ["label"]:
            self.assertNotIn(forbidden, valid_result.X.columns)
        self.assertNotIn("time_is_peak_hour", valid_result.X.columns)
        self.assertNotIn("user_activity_level__high", valid_result.X.columns)
        self.assertEqual(train_result.X.columns.tolist(), valid_result.X.columns.tolist())
        self.assertEqual(len(valid_result.X), len(valid))
        self.assertEqual(preprocessor.get_state(), state_before)
        self.assertEqual(preprocessor.numeric_fill_values_["event_count"], 0.0)
        self.assertEqual(preprocessor.numeric_fill_values_["score"], 2.0)
        self.assertEqual(float(valid_result.X.loc[0, "score"]), 2.0)
        self.assertLessEqual(
            float(valid_result.X["score"].max()),
            preprocessor.clip_bounds_["score"][1],
        )
        unknown_column = "time_period____UNKNOWN__"
        self.assertIn(unknown_column, valid_result.X.columns)
        self.assertEqual(float(valid_result.X.loc[0, unknown_column]), 1.0)

        with self.assertRaises(ValueError):
            Stage3Preprocessor(config).fit(train, split_name="valid")

    def test_linear_profile_scales_continuous_but_not_binary(self) -> None:
        config = load_config()
        train = make_frame(
            ["morning", "afternoon", "evening", "night"],
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
        )
        linear = Stage3Preprocessor(config, scaling_profile="linear")
        result = linear.fit_transform(train)
        self.assertAlmostEqual(float(result.X["score"].mean()), 0.0, places=7)
        self.assertEqual(result.X["binary_flag"].tolist(), [0.0, 1.0, 0.0, 1.0])
        self.assertNotIn("binary_flag", linear.scaled_columns_)

    def test_target_like_extra_column_is_rejected(self) -> None:
        config = load_config()
        train = make_frame(
            ["morning", "afternoon", "evening", "night"],
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
        )
        train["future_purchase_label"] = [0, 1, 0, 1]
        with self.assertRaises(ValueError):
            Stage3Preprocessor(config).fit(train)


if __name__ == "__main__":
    unittest.main()
