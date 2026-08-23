"""Tests for the initial stage-two user-item feature table."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.features.conversion_features import build_conversion_features
from src.features.stage2_feature_table import build_stage2_feature_table
from src.features.stage2_intermediate_tables import build_stage2_intermediate_tables


class Stage2FeatureTableTests(unittest.TestCase):
    def test_integrates_all_feature_groups(self) -> None:
        clean = pa.table(
            {
                "time": pa.array(
                    [
                        datetime(2025, 11, 18, 1),
                        datetime(2025, 11, 18, 2),
                        datetime(2025, 11, 18, 3),
                        datetime(2025, 11, 19, 2),
                    ],
                    type=pa.timestamp("ns"),
                ),
                "user_id": pa.array([1, 1, 1, 2], type=pa.int64()),
                "item_id": pa.array([10, 10, 10, 20], type=pa.int64()),
                "category_id": pa.array([100, 100, 100, 200], type=pa.int64()),
                "behavior_type": pa.array([1, 3, 4, 1], type=pa.uint8()),
                "behavior_name": pa.array(["pv", "cart", "buy", "pv"]),
                "behavior_date": pa.array(
                    ["2025-11-18", "2025-11-18", "2025-11-18", "2025-11-19"]
                ),
                "behavior_hour": pa.array([1, 2, 3, 2], type=pa.uint8()),
                "weekday": pa.array([1, 1, 1, 2], type=pa.uint8()),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean_path = root / "clean.parquet"
            features = root / "features"
            pq.write_table(clean, clean_path)
            build_stage2_intermediate_tables(clean_path, output_directory=features)

            sequence = pa.table(
                {
                    "user_id": pa.array([1, 2], type=pa.int64()),
                    "sequence_recent_10_behavior_types": pa.array(
                        [[1, 3, 4], [1]], type=pa.list_(pa.int64())
                    ),
                    "sequence_avg_behavior_gap_hours": pa.array(
                        [1.0, 0.0], type=pa.float64()
                    ),
                    "sequence_has_pv_cart": pa.array([1, 0], type=pa.uint8()),
                    "sequence_has_pv_fav": pa.array([0, 0], type=pa.uint8()),
                    "sequence_has_pv_buy": pa.array([1, 0], type=pa.uint8()),
                    "sequence_has_pv_cart_buy": pa.array([1, 0], type=pa.uint8()),
                }
            )
            pq.write_table(sequence, features / "user_sequence_features.parquet")
            build_conversion_features(
                features / "item_features.parquet",
                item_output_path=features / "item_conversion_features.parquet",
                global_output_path=features / "conversion_features.parquet",
            )

            output = features / "user_item_feature_table.parquet"
            result = build_stage2_feature_table(features, output_path=output)
            self.assertEqual(result.rows, 2)
            self.assertEqual(result.validation["status"], "PASS")
            wide = pq.read_table(output)
            self.assertIn("user_total_count", wide.column_names)
            self.assertIn("sequence_has_pv_cart_buy", wide.column_names)
            self.assertIn("item_popularity_level", wide.column_names)
            self.assertIn("category_popularity_level", wide.column_names)
            self.assertIn("time_is_peak_hour", wide.column_names)
            self.assertIn("conversion_cart_to_buy_rate", wide.column_names)
            self.assertEqual(
                wide["sequence_recent_10_behavior_types"].to_pylist()[0], "1|3|4"
            )


if __name__ == "__main__":
    unittest.main()
