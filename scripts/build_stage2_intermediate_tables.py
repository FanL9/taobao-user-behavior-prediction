"""Command-line entry point for the four stage-two intermediate tables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.stage2_feature_specification import DEFAULT_PARQUET_INPUT  # noqa: E402
from src.features.stage2_intermediate_tables import (  # noqa: E402
    build_stage2_intermediate_tables,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build user, item, category, and time feature Parquet tables."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_PARQUET_INPUT)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=PROJECT_ROOT / "data" / "features",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = build_stage2_intermediate_tables(
            args.input,
            output_directory=args.output_directory,
        )
        print(
            json.dumps(
                {
                    "input": str(result.input_path),
                    "input_rows": result.input_rows,
                    "outputs": {
                        name: {"path": str(result.output_paths[name]), "rows": rows}
                        for name, rows in result.output_rows.items()
                    },
                    "elapsed_seconds": result.elapsed_seconds,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as error:
        print(f"Feature table build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

