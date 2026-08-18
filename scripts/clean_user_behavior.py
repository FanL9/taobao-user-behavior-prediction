"""Command-line entry point for standard user-behavior cleaning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.clean_user_behavior import clean_user_behavior  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "user_behavior_processed.csv"
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.csv"
)
DEFAULT_OUTPUT_PARQUET = (
    PROJECT_ROOT / "data" / "processed" / "user_behavior_clean.parquet"
)
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "user_behavior_cleaning_report.json"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run chunked quality checks and standard cleaning."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument(
        "--output-parquet",
        type=Path,
        nargs="?",
        const=DEFAULT_OUTPUT_PARQUET,
        default=None,
        help=(
            "Also write Parquet. With no path, uses "
            "data/processed/user_behavior_clean.parquet."
        ),
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = clean_user_behavior(
            _resolve(args.input),
            _resolve(args.output_csv),
            output_parquet=(
                _resolve(args.output_parquet)
                if args.output_parquet is not None
                else None
            ),
            report_path=_resolve(args.report),
            chunksize=args.chunksize,
            encoding=args.encoding,
            progress=not args.quiet,
        )
        summary = {
            "original_rows": result.report["cleaning"]["original_rows"],
            "clean_rows": result.report["cleaning"]["clean_rows"],
            "removed_rows": result.report["cleaning"]["removed_rows"],
            "removal_ratio_percent": result.report["cleaning"][
                "removal_ratio_percent"
            ],
            "csv": str(result.csv_path),
            "parquet": str(result.parquet_path) if result.parquet_path else None,
            "report": str(result.report_path) if result.report_path else None,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"Cleaning failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
