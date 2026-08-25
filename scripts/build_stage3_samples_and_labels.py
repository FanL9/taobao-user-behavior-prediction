"""Official Member 2 entry point for Stage 3 tasks 1 and 3.

This replaces the former root-level ``temp.py`` and builds:

1. fixed-window purchase labels;
2. point-in-time user/item/category/time/user-item feature snapshots;
3. user sequence snapshots;
4. joined modeling samples;
5. the sample-and-label leakage audit.
"""

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.stage3_sequence_features import main as sequence_main
from src.features.stage3_snapshot_features import main as feature_main
from src.models.stage3_labels import main as label_main
from src.models.stage3_modeling_samples import main as sample_main
from src.models.stage3_samples_audit import main as audit_main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or audit Stage 3 Member 2 samples and labels."
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Audit existing local outputs without rebuilding them.",
    )
    args = parser.parse_args()

    if args.audit_only:
        if audit_main() != 0:
            raise RuntimeError("Stage 3 samples-and-labels audit failed")
        return

    label_main()
    feature_main()
    sequence_main()
    sample_main()
    if audit_main() != 0:
        raise RuntimeError("Stage 3 samples-and-labels audit failed")


if __name__ == "__main__":
    main()
