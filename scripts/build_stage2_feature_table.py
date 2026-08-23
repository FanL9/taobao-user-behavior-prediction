"""Build and validate the initial stage-two user-item feature table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.stage2_feature_table import (  # noqa: E402
    DEFAULT_FEATURE_DIRECTORY,
    DEFAULT_OUTPUT,
    build_stage2_feature_table,
)


DEFAULT_VALIDATION_OUTPUT = (
    PROJECT_ROOT / "outputs" / "stage2_feature_table_validation.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the initial user-item stage-two feature table."
    )
    parser.add_argument(
        "--feature-directory", type=Path, default=DEFAULT_FEATURE_DIRECTORY
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--validation-output", type=Path, default=DEFAULT_VALIDATION_OUTPUT
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_stage2_feature_table(
        args.feature_directory, output_path=args.output
    )
    validation = {
        **result.validation,
        "output": str(result.output_path),
        "elapsed_seconds": result.elapsed_seconds,
    }
    args.validation_output.parent.mkdir(parents=True, exist_ok=True)
    args.validation_output.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
