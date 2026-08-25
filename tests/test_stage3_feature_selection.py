import copy
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.stage3_feature_selection import Stage3FeatureSelector


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def selection_config():
    config = json.loads(
        (PROJECT_ROOT / "configs" / "stage3_feature_config.json").read_text(
            encoding="utf-8-sig"
        )
    )
    config["feature_selection"]["high_missing"]["threshold"] = 0.5
    config["feature_selection"]["low_variance"].update(
        {
            "continuous_variance_threshold": 0.0001,
            "binary_max_dominant_frequency": 0.95,
        }
    )
    config["feature_selection"]["high_correlation"]["threshold"] = 0.99
    return config


class Stage3FeatureSelectionTests(unittest.TestCase):
    def test_all_rules_records_and_deterministic_tie_break(self) -> None:
        base = np.arange(1, 21, dtype=float)
        X = pd.DataFrame(
            {
                "conversion_pv_count": base,
                "item_pv_count": base,
                "high_missing": [1.0] + [np.nan] * 19,
                "constant": [3.0] * 20,
                "near_binary": [0.0] * 19 + [1.0],
                "low_variance": 1.0 + base / 100000.0,
                "useful": [1, 0, 3, 2, 5, 4, 7, 6, 9, 8] * 2,
            }
        )
        selector = Stage3FeatureSelector(selection_config())
        transformed = selector.fit_transform(X)

        selected = selector.get_selected_features()
        self.assertIn("item_pv_count", selected)
        self.assertNotIn("conversion_pv_count", selected)
        self.assertIn("useful", selected)
        self.assertEqual(transformed.columns.tolist(), selected)
        reasons = {
            record["feature"]: record for record in selector.get_drop_records()
        }
        self.assertEqual(reasons["high_missing"]["reason"], "high_missing_rate")
        self.assertEqual(reasons["constant"]["reason"], "constant")
        self.assertEqual(reasons["near_binary"]["reason"], "near_constant_binary")
        self.assertEqual(reasons["low_variance"]["reason"], "low_variance")
        self.assertEqual(
            reasons["conversion_pv_count"]["paired_feature"],
            "item_pv_count",
        )
        for record in reasons.values():
            self.assertEqual(record["fit_split"], "train")
            self.assertIn("statistic", record)
            self.assertIn("threshold", record)

        state_before = copy.deepcopy(selector.get_state())
        valid = X.copy()
        valid["conversion_pv_count"] = valid["conversion_pv_count"].iloc[::-1].values
        valid_transformed = selector.transform(valid)
        self.assertEqual(valid_transformed.columns.tolist(), selected)
        self.assertEqual(selector.get_state(), state_before)

        with self.assertRaises(ValueError):
            Stage3FeatureSelector(selection_config()).fit(X, split_name="test")


if __name__ == "__main__":
    unittest.main()
