"""Tests for stage-two intermediate feature table construction."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.features.stage2_intermediate_tables import build_stage2_intermediate_tables


class Stage2IntermediateTableTests(unittest.TestCase):
    def test_builds_four_reconciled_tables(self) -> None:
        clean = pa.table(
            {
                "time": pa.array(
                    [
                        datetime(2025, 11, 18, 1),
                        datetime(2025, 11, 18, 2),
                        datetime(2025, 11, 18, 3),
                        datetime(2025, 11, 19, 1),
                        datetime(2025, 11, 19, 2),
                        datetime(2025, 11, 19, 2),
                    ],
                    type=pa.timestamp("ns"),
                ),
                "user_id": pa.array([1, 1, 1, 1, 2, 2], type=pa.int64()),
                "item_id": pa.array([10, 10, 10, 11, 10, 10], type=pa.int64()),
                "category_id": pa.array([100, 100, 100, 200, 100, 100], type=pa.int64()),
                "behavior_type": pa.array([1, 3, 4, 1, 1, 1], type=pa.uint8()),
                "behavior_name": pa.array(["pv", "cart", "buy", "pv", "pv", "pv"]),
                "behavior_date": pa.array(
                    [
                        "2025-11-18",
                        "2025-11-18",
                        "2025-11-18",
                        "2025-11-19",
                        "2025-11-19",
                        "2025-11-19",
                    ]
                ),
                "behavior_hour": pa.array([1, 2, 3, 1, 2, 2], type=pa.uint8()),
                "weekday": pa.array([1, 1, 1, 2, 2, 2], type=pa.uint8()),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            input_path = directory_path / "clean.parquet"
            output_path = directory_path / "features"
            pq.write_table(clean, input_path)

            result = build_stage2_intermediate_tables(
                input_path,
                output_directory=output_path,
            )

            self.assertEqual(result.input_rows, 6)
            self.assertEqual(
                result.output_rows,
                {
                    "user_features": 2,
                    "item_features": 2,
                    "category_features": 2,
                    "time_features": 5,
                },
            )
            user = pq.read_table(result.output_paths["user_features"])
            first_user = user.filter(pa.compute.equal(user["user_id"], 1)).to_pylist()[0]
            self.assertEqual(first_user["user_total_count"], 4)
            self.assertEqual(first_user["user_buy_count"], 1)
            self.assertEqual(first_user["user_buy_to_pv_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()

