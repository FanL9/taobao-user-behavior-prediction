"""Tests for Member 3 stage-two conversion features."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.features.conversion_features import build_conversion_features


class ConversionFeatureTests(unittest.TestCase):
    def test_builds_item_and_global_conversion_tables(self) -> None:
        item = pa.table(
            {
                "item_id": pa.array([10, 20], type=pa.int64()),
                "item_pv_count": pa.array([10, 0], type=pa.int64()),
                "item_fav_count": pa.array([2, 0], type=pa.int64()),
                "item_cart_count": pa.array([4, 1], type=pa.int64()),
                "item_buy_count": pa.array([1, 1], type=pa.int64()),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "item_features.parquet"
            item_output = root / "item_conversion_features.parquet"
            global_output = root / "conversion_features.parquet"
            pq.write_table(item, input_path)

            result = build_conversion_features(
                input_path,
                item_output_path=item_output,
                global_output_path=global_output,
            )

            self.assertEqual(result.item_rows, 2)
            conversion = pq.read_table(item_output).to_pylist()
            self.assertEqual(conversion[0]["conversion_pv_to_buy_rate"], 0.1)
            self.assertEqual(conversion[0]["conversion_has_full_funnel"], 1)
            self.assertEqual(conversion[1]["conversion_pv_to_buy_rate"], 0.0)
            global_row = pq.read_table(global_output).to_pylist()[0]
            self.assertEqual(global_row["pv_count"], 10)
            self.assertEqual(global_row["buy_count"], 2)
            self.assertEqual(global_row["pv_to_buy_rate"], 0.2)


if __name__ == "__main__":
    unittest.main()
