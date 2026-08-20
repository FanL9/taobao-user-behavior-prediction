from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from src.data.user_behavior_cleaning_pipeline import (
    BEHAVIOR_MAPPING,
    OUTPUT_COLUMNS,
    clean_user_behavior,
    validate_clean_output,
)


HEADER = "time,user_id,item_id,item_category,behavior_type\n"


def _write_input(path: Path, rows: list[str]) -> None:
    path.write_text(HEADER + "".join(rows), encoding="utf-8")


class CleanUserBehaviorTests(unittest.TestCase):
    def test_normal_repeats_below_threshold_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "input.csv"
            output_csv = directory / "clean.csv"
            parquet_path = directory / "clean.parquet"
            report_path = directory / "report.md"

            repeated = "2025-12-01 10,1,100,9,1\n"
            rows = [repeated] * 5 + ["2025-12-01 11,2,200,8,4\n"]
            _write_input(input_csv, rows)

            result = clean_user_behavior(
                input_csv,
                output_csv,
                output_parquet=parquet_path,
                report_path=report_path,
                suspicious_repeat_threshold=60,
                chunksize=2,
                progress=False,
            )

            clean = pd.read_csv(output_csv)
            self.assertEqual(clean.columns.tolist(), OUTPUT_COLUMNS)
            self.assertEqual(len(clean), 6)
            self.assertEqual(
                int(
                    clean.duplicated(
                        ["user_id", "item_id", "behavior_type", "time"]
                    ).sum()
                ),
                4,
            )
            burst = result.report["quality"]["suspicious_repeat_bursts"]
            self.assertEqual(burst["groups"], 0)
            self.assertEqual(
                result.report["cleaning"]["removed_by_mutually_exclusive_reason"][
                    "suspicious_repeat_burst"
                ],
                0,
            )
            self.assertTrue(result.report["output_validation"]["valid"])
            self.assertEqual(
                result.report["output_validation"][
                    "repeated_clean_key_rows_preserved"
                ],
                4,
            )
            self.assertTrue(report_path.is_file())
            report_text = report_path.read_text("utf-8")
            self.assertIn("普通四元组重复不删除", report_text)
            self.assertIn("超出配置合法时间范围 | 未配置/不适用", report_text)
            self.assertEqual(pq.ParquetFile(parquet_path).metadata.num_rows, 6)

    def test_sixty_same_hour_repeats_are_flagged_and_collapsed_to_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "input.csv"
            output_csv = directory / "clean.csv"
            report_path = directory / "report.md"

            repeated = "2025-12-01 10,1,100,9,1\n"
            rows = [repeated] * 60 + ["2025-12-01 11,2,200,8,4\n"]
            _write_input(input_csv, rows)

            result = clean_user_behavior(
                input_csv,
                output_csv,
                report_path=report_path,
                suspicious_repeat_threshold=60,
                chunksize=7,
                progress=False,
            )

            clean = pd.read_csv(output_csv)
            self.assertEqual(len(clean), 2)
            burst = result.report["quality"]["suspicious_repeat_bursts"]
            self.assertEqual(burst["threshold"], 60)
            self.assertEqual(burst["groups"], 1)
            self.assertEqual(burst["rows"], 60)
            self.assertEqual(burst["rows_removed_if_collapsed_to_one"], 59)
            self.assertEqual(burst["max_group_size"], 60)
            self.assertIn(
                "异常高频组最大出现次数 | 60",
                report_path.read_text("utf-8"),
            )
            self.assertEqual(
                result.report["cleaning"]["removed_by_mutually_exclusive_reason"][
                    "suspicious_repeat_burst"
                ],
                59,
            )
            self.assertEqual(result.report["cleaning"]["removed_rows"], 59)
            self.assertTrue(result.report["output_validation"]["valid"])

    def test_time_range_filter_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "input.csv"
            output_csv = directory / "clean.csv"
            report_path = directory / "report.md"
            rows = [
                "2025-11-30 23,1,100,9,1\n",
                "2025-12-01 00,1,100,9,1\n",
                "2025-12-02 23,1,100,9,1\n",
                "2025-12-03 00,1,100,9,1\n",
            ]
            _write_input(input_csv, rows)

            result = clean_user_behavior(
                input_csv,
                output_csv,
                report_path=report_path,
                allowed_start="2025-12-01 00",
                allowed_end="2025-12-02 23",
                chunksize=2,
                progress=False,
            )

            clean = pd.read_csv(output_csv)
            self.assertEqual(len(clean), 2)
            range_check = result.report["quality"]["time_range_check"]
            self.assertTrue(range_check["configured"])
            self.assertEqual(range_check["out_of_range_time_rows"], 2)
            self.assertEqual(
                result.report["cleaning"]["removed_by_mutually_exclusive_reason"][
                    "out_of_range_time"
                ],
                2,
            )

    def test_validator_allows_normal_repeats_but_rejects_threshold_burst(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            good_csv = directory / "good.csv"
            bad_csv = directory / "bad.csv"

            base = {
                "time": "2025-12-01 10:00:00",
                "user_id": 1,
                "item_id": 100,
                "category_id": 9,
                "behavior_type": 1,
                "behavior_name": BEHAVIOR_MAPPING[1],
                "behavior_date": "2025-12-01",
                "behavior_hour": 10,
                "weekday": 0,
            }
            pd.DataFrame([base] * 5, columns=OUTPUT_COLUMNS).to_csv(
                good_csv, index=False
            )
            validation = validate_clean_output(
                good_csv,
                suspicious_repeat_threshold=60,
                chunksize=2,
            )
            self.assertTrue(validation["valid"])
            self.assertEqual(validation["repeated_clean_key_rows_preserved"], 4)

            pd.DataFrame([base] * 60, columns=OUTPUT_COLUMNS).to_csv(
                bad_csv, index=False
            )
            with self.assertRaises(ValueError):
                validate_clean_output(
                    bad_csv,
                    suspicious_repeat_threshold=60,
                    chunksize=7,
                )

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

            self.assertEqual(output.read_text(encoding="utf-8"), "existing-output\n")


if __name__ == "__main__":
    unittest.main()
