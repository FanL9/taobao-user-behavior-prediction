from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from src.data.clean_user_behavior import (
    BEHAVIOR_MAPPING,
    OUTPUT_COLUMNS,
    clean_user_behavior,
    validate_clean_output,
)


FIXTURE = Path(__file__).parent / "fixtures" / "user_behavior_sample.csv"


class CleanUserBehaviorTests(unittest.TestCase):
    def test_chunked_cleaning_quality_and_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            csv_path = directory / "clean.csv"
            parquet_path = directory / "clean.parquet"
            report_path = directory / "report.json"

            result = clean_user_behavior(
                FIXTURE,
                csv_path,
                output_parquet=parquet_path,
                report_path=report_path,
                chunksize=2,
                progress=False,
            )

            clean = pd.read_csv(csv_path)
            self.assertEqual(clean.columns.tolist(), OUTPUT_COLUMNS)
            self.assertEqual(len(clean), 3)
            self.assertFalse(clean[OUTPUT_COLUMNS].isna().any().any())
            self.assertEqual(set(clean["behavior_type"]), {1, 2, 4})
            expected_names = clean["behavior_type"].map(BEHAVIOR_MAPPING)
            self.assertTrue(expected_names.eq(clean["behavior_name"]).all())
            parsed_time = pd.to_datetime(
                clean["time"],
                format="%Y-%m-%d %H:%M:%S",
                errors="coerce",
            )
            self.assertFalse(parsed_time.isna().any())
            self.assertTrue(clean["behavior_hour"].between(0, 23).all())
            self.assertEqual(
                int(
                    clean.duplicated(
                        ["user_id", "item_id", "behavior_type", "time"]
                    ).sum()
                ),
                0,
            )

            quality = result.report["quality"]
            cleaning = result.report["cleaning"]
            self.assertEqual(quality["total_rows"], 10)
            self.assertEqual(quality["fully_duplicate_rows"], 1)
            self.assertEqual(
                quality["duplicate_user_item_behavior_time_rows"], 2
            )
            self.assertEqual(quality["records_with_missing_critical_field"], 2)
            self.assertEqual(quality["invalid_behavior_type_rows"], 1)
            self.assertEqual(quality["invalid_id_rows"], 1)
            self.assertEqual(quality["unparseable_time_rows"], 2)
            self.assertEqual(cleaning["original_rows"], 10)
            self.assertEqual(cleaning["clean_rows"], 3)
            self.assertEqual(cleaning["removed_rows"], 7)
            self.assertEqual(
                sum(cleaning["removed_by_mutually_exclusive_reason"].values()),
                7,
            )
            self.assertEqual(
                cleaning["removed_by_mutually_exclusive_reason"],
                {
                    "missing_critical_field": 2,
                    "invalid_behavior_type": 1,
                    "invalid_id": 1,
                    "unparseable_time": 1,
                    "duplicate_clean_key": 2,
                },
            )

            on_disk_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk_report, result.report)
            self.assertEqual(pq.ParquetFile(parquet_path).metadata.num_rows, 3)
            parquet = pd.read_parquet(parquet_path)
            self.assertEqual(parquet.columns.tolist(), OUTPUT_COLUMNS)
            validation = validate_clean_output(
                csv_path,
                expected_rows=3,
                parquet_path=parquet_path,
                chunksize=2,
            )
            self.assertTrue(validation["valid"])
            self.assertEqual(validation["duplicate_clean_key_rows"], 0)

    def test_failure_does_not_overwrite_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            bad_input = directory / "bad.csv"
            bad_input.write_text("wrong,column\n1,2\n", encoding="utf-8")
            output = directory / "clean.csv"
            output.write_text("existing-output\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                clean_user_behavior(
                    bad_input,
                    output,
                    chunksize=2,
                    progress=False,
                )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "existing-output\n",
            )


if __name__ == "__main__":
    unittest.main()
