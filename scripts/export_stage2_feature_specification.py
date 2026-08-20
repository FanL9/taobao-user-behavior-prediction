"""Export stage-two feature definitions without building feature values."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.stage2_feature_specification import (  # noqa: E402
    DEFAULT_DICTIONARY_OUTPUT,
    DEFAULT_SCHEMA_OUTPUT,
    export_stage2_specifications,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the stage-one clean schema and export the stage-two "
            "feature dictionary and intermediate-table schemas."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Clean Parquet or CSV. By default, prefer "
            "data/processed/user_behavior_clean.parquet and fall back to CSV."
        ),
    )
    parser.add_argument(
        "--dictionary-output",
        type=Path,
        default=DEFAULT_DICTIONARY_OUTPUT,
        help="Feature dictionary CSV output path.",
    )
    parser.add_argument(
        "--schema-output",
        type=Path,
        default=DEFAULT_SCHEMA_OUTPUT,
        help="Intermediate-table schema JSON output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dictionary_path, schema_path = export_stage2_specifications(
        input_path=args.input,
        dictionary_output=args.dictionary_output,
        schema_output=args.schema_output,
    )
    print(f"Feature dictionary: {dictionary_path}")
    print(f"Intermediate table schemas: {schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

