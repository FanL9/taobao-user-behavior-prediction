"""Build fixed historical feature snapshots for Stage 3 splits."""

from datetime import datetime
from pathlib import Path

from src.features.stage3_intermediate_tables import (
    build_stage3_intermediate_tables,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.parquet"
)

SPLIT_WINDOWS = {
    "train": (
        datetime(2025, 11, 18),
        datetime(2025, 12, 7),
        datetime(2025, 12, 8),
    ),
    "valid": (
        datetime(2025, 12, 9),
        datetime(2025, 12, 14),
        datetime(2025, 12, 15),
    ),
    "test": (
        datetime(2025, 12, 16),
        datetime(2025, 12, 17),
        datetime(2025, 12, 18),
    ),
}


def main() -> None:
    print("=" * 80)
    print("Stage 3 fixed-window historical feature generation")
    print(f"Input: {INPUT_PATH}")
    print("=" * 80)

    for split_name, (
        observation_start,
        observation_end,
        label_date,
    ) in SPLIT_WINDOWS.items():
        cutoff_time = observation_end.replace(
            hour=23,
            minute=59,
            second=59,
        )
        date_string = label_date.strftime("%Y-%m-%d")
        output_dir = (
            PROJECT_ROOT
            / "data"
            / "modeling"
            / split_name
            / "snapshots"
            / date_string
            / "features"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        print()
        print("=" * 80)
        print(f"Split           : {split_name}")
        print(f"Label date      : {date_string}")
        print(f"Observation from: {observation_start}")
        print(f"Cutoff          : {cutoff_time}")
        print(f"Output          : {output_dir}")
        print("=" * 80)

        result = build_stage3_intermediate_tables(
            input_path=INPUT_PATH,
            observation_start=observation_start,
            cutoff_time=cutoff_time,
            output_directory=output_dir,
        )

        print("Input rows       :", f"{result.input_rows:,}")
        for name, path in result.output_paths.items():
            print(
                f"{name:<20}: {result.output_rows[name]:>12,} rows -> {path}"
            )

    print()
    print("=" * 80)
    print("All fixed-window historical features completed.")
    print("=" * 80)


if __name__ == "__main__":
    main()
