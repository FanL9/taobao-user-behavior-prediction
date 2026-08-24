from datetime import datetime, timedelta
from pathlib import Path

from src.features.stage3_intermediate_tables import (
    build_stage3_intermediate_tables,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "user_behavior_clean.parquet"
)

OBSERVATION_START = datetime(2025, 11, 18, 0, 0, 0)

SPLIT_DATE_RANGES = {
    "train": (
        datetime(2025, 11, 18),
        datetime(2025, 12, 7),
    ),
    "valid": (
        datetime(2025, 12, 8),
        datetime(2025, 12, 14),
    ),
    "test": (
        datetime(2025, 12, 15),
        datetime(2025, 12, 17),
    ),
}


def date_range(start_date, end_date):
    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


def main():
    print("=" * 80)
    print("Stage 3 prediction-date historical feature generation")
    print(f"Input: {INPUT_PATH}")
    print("=" * 80)

    for split_name, (start_date, end_date) in SPLIT_DATE_RANGES.items():

        for prediction_date in date_range(start_date, end_date):

            cutoff_time = prediction_date.replace(
                hour=23,
                minute=59,
                second=59,
            )

            date_string = prediction_date.strftime("%Y-%m-%d")

            output_dir = (
                PROJECT_ROOT
                / "data"
                / "modeling"
                / split_name
                / "snapshots"
                / date_string
                / "features"
            )

            output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            print()
            print("=" * 80)
            print(f"Split           : {split_name}")
            print(f"Prediction date : {date_string}")
            print(f"Observation from: {OBSERVATION_START}")
            print(f"Cutoff          : {cutoff_time}")
            print(f"Output          : {output_dir}")
            print("=" * 80)

            result = build_stage3_intermediate_tables(
                input_path=INPUT_PATH,
                observation_start=OBSERVATION_START,
                cutoff_time=cutoff_time,
                output_directory=output_dir,
            )

            print(
                "Input rows       :",
                f"{result.input_rows:,}",
            )

            for name, path in result.output_paths.items():
                print(
                    f"{name:<20}: "
                    f"{result.output_rows[name]:>12,} "
                    f"rows -> {path}"
                )

    print()
    print("=" * 80)
    print("All prediction-date historical features completed.")
    print("=" * 80)


if __name__ == "__main__":
    main()
