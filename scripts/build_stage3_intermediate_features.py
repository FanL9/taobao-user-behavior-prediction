from datetime import datetime
from pathlib import Path

from src.features.stage3_intermediate_tables import (
    build_stage3_intermediate_tables,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.parquet"

SPLITS = {
    "train": datetime(2025, 11, 27, 23, 59, 59),
    "valid": datetime(2025, 12, 4, 23, 59, 59),
    "test": datetime(2025, 12, 11, 23, 59, 59),
}

OBSERVATION_START = datetime(2025, 11, 18, 0, 0, 0)


def main():
    print("=" * 70)
    print("Stage 3 leakage-safe feature generation")
    print(f"Input: {INPUT_PATH}")
    print("=" * 70)

    for split_name, cutoff_time in SPLITS.items():
        output_dir = (
            PROJECT_ROOT
            / "data"
            / "modeling"
            / split_name
            / "features"
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        print()
        print("=" * 70)
        print(f"Building split : {split_name}")
        print(f"Observation    : {OBSERVATION_START}")
        print(f"Cutoff         : {cutoff_time}")
        print(f"Output         : {output_dir}")
        print("=" * 70)

        result = build_stage3_intermediate_tables(
            input_path=INPUT_PATH,
            observation_start=OBSERVATION_START,
            cutoff_time=cutoff_time,
            output_directory=output_dir,
        )

        print(f"Input rows     : {result.input_rows:,}")
        print(f"Elapsed        : {result.elapsed_seconds:.3f} sec")

        for name, path in result.output_paths.items():
            rows = result.output_rows[name]
            print(f"{name:<20}: {rows:>12,} rows -> {path}")

    print()
    print("=" * 70)
    print("All Stage 3 intermediate feature tables completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
