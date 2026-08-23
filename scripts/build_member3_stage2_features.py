"""Command-line entry point for Member 3 stage-two conversion features."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.conversion_features import (  # noqa: E402
    DEFAULT_GLOBAL_OUTPUT,
    DEFAULT_INPUT,
    DEFAULT_ITEM_OUTPUT,
    build_conversion_features,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build item-level and global stage-two conversion features."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--item-output", type=Path, default=DEFAULT_ITEM_OUTPUT)
    parser.add_argument("--global-output", type=Path, default=DEFAULT_GLOBAL_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_conversion_features(
        args.input,
        item_output_path=args.item_output,
        global_output_path=args.global_output,
    )
    print(
        json.dumps(
            {
                "input": str(result.input_path),
                "item_output": str(result.item_output_path),
                "item_rows": result.item_rows,
                "global_output": str(result.global_output_path),
                "global_rows": result.global_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
