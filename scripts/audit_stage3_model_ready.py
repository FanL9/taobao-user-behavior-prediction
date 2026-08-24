from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path("data/modeling")
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_LIST_PATH = Path("configs/stage3_model_feature_list.txt")

SPLITS = ("train", "valid", "test")

FORBIDDEN_MODEL_COLUMNS = {
    "cutoff_time",
    "label_start",
    "label_end",
    "category_id",
    "ui_last_interaction_time",
    "ui_last_interaction_date",
    "user_first_behavior_time",
    "user_last_behavior_time",
    "sequence_recent_10_behavior_types",
}

BATCH_SIZE = 200_000


def audit_split(split, expected_features):
    path = (
        ROOT
        / split
        / f"{split}_model_ready.parquet"
    )

    pf = pq.ParquetFile(path)
    schema = pf.schema_arrow
    columns = schema.names

    expected_columns = (
        ["user_id", "item_id"]
        + expected_features
        + ["label"]
    )

    schema_ok = columns == expected_columns

    forbidden_present = sorted(
        set(columns) & FORBIDDEN_MODEL_COLUMNS
    )

    feature_columns = [
        c for c in columns
        if c not in {"user_id", "item_id", "label"}
    ]

    total_rows = 0
    positive = 0
    null_count = 0
    nan_count = 0
    inf_count = 0

    min_values = {
        col: None for col in feature_columns
    }
    max_values = {
        col: None for col in feature_columns
    }

    duplicate_key_count = 0

    key_parts = []

    for batch_no, batch in enumerate(
        pf.iter_batches(
            batch_size=BATCH_SIZE,
        ),
        start=1,
    ):
        df = batch.to_pandas()

        total_rows += len(df)

        positive += int(
            (df["label"] == 1).sum()
        )

        null_count += int(
            df[feature_columns].isna().sum().sum()
        )

        arr = df[feature_columns].to_numpy(
            dtype=np.float64,
            copy=False,
        )

        nan_count += int(
            np.isnan(arr).sum()
        )

        inf_count += int(
            np.isinf(arr).sum()
        )

        for col in feature_columns:
            values = pd.to_numeric(
                df[col],
                errors="coerce",
            )

            finite = values[
                np.isfinite(values)
            ]

            if len(finite) == 0:
                continue

            col_min = float(finite.min())
            col_max = float(finite.max())

            if min_values[col] is None:
                min_values[col] = col_min
                max_values[col] = col_max
            else:
                min_values[col] = min(
                    min_values[col],
                    col_min,
                )
                max_values[col] = max(
                    max_values[col],
                    col_max,
                )

        key_parts.append(
            df[["user_id", "item_id"]]
        )

        print(
            f"{split} batch {batch_no:02d} "
            f"| rows audited = {total_rows:,}"
        )

    keys = pd.concat(
        key_parts,
        ignore_index=True,
    )

    duplicate_key_count = int(
        keys.duplicated(
            ["user_id", "item_id"]
        ).sum()
    )

    del keys
    del key_parts

    constant_features = sorted(
        [
            col
            for col in feature_columns
            if (
                min_values[col] is not None
                and max_values[col] is not None
                and math.isclose(
                    min_values[col],
                    max_values[col],
                    rel_tol=0.0,
                    abs_tol=0.0,
                )
            )
        ]
    )

    negative = total_rows - positive
    positive_rate = (
        positive / total_rows
        if total_rows
        else 0.0
    )

    label_ok = (
        positive > 0
        and negative > 0
    )

    passed = all(
        [
            schema_ok,
            not forbidden_present,
            duplicate_key_count == 0,
            null_count == 0,
            nan_count == 0,
            inf_count == 0,
            label_ok,
            len(constant_features) == 0,
        ]
    )

    return {
        "split": split,
        "path": str(path),
        "rows": total_rows,
        "columns": len(columns),
        "model_features": len(feature_columns),
        "positive": positive,
        "negative": negative,
        "positive_rate": positive_rate,
        "schema_ok": schema_ok,
        "forbidden_columns_present": forbidden_present,
        "duplicate_primary_key_count": duplicate_key_count,
        "feature_null_count": null_count,
        "feature_nan_count": nan_count,
        "feature_inf_count": inf_count,
        "constant_features": constant_features,
        "label_ok": label_ok,
        "status": "PASS" if passed else "FAIL",
    }


def main():
    expected_features = (
        FEATURE_LIST_PATH
        .read_text(encoding="utf-8")
        .splitlines()
    )

    print("=" * 90)
    print("STAGE 3 FINAL MODEL-READY AUDIT")
    print("=" * 90)

    results = []

    for split in SPLITS:
        result = audit_split(
            split,
            expected_features,
        )

        results.append(result)

        print()
        print(
            split,
            "| status =", result["status"],
            "| rows =", f'{result["rows"]:,}',
            "| positive rate =",
            f'{result["positive_rate"]:.6%}',
        )
        print()

    schema_reference = pq.ParquetFile(
        ROOT
        / "train"
        / "train_model_ready.parquet"
    ).schema_arrow

    schema_consistency = True

    for split in ("valid", "test"):
        other = pq.ParquetFile(
            ROOT
            / split
            / f"{split}_model_ready.parquet"
        ).schema_arrow

        if not schema_reference.equals(other):
            schema_consistency = False

    overall_pass = (
        schema_consistency
        and all(
            r["status"] == "PASS"
            for r in results
        )
    )

    json_path = (
        REPORT_DIR
        / "stage3_model_ready_audit.json"
    )

    json_path.write_text(
        json.dumps(
            {
                "overall_status":
                    "PASS" if overall_pass else "FAIL",
                "schema_consistency":
                    schema_consistency,
                "feature_count":
                    len(expected_features),
                "splits":
                    results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    md = []

    md.append(
        "# Stage 3 Model-Ready Data Audit"
    )
    md.append("")
    md.append(
        f"Overall status: "
        f"**{'PASS' if overall_pass else 'FAIL'}**"
    )
    md.append("")
    md.append(
        f"- Model feature count: "
        f"{len(expected_features)}"
    )
    md.append(
        f"- Train/valid/test schema consistent: "
        f"{schema_consistency}"
    )
    md.append(
        "- Prediction target: "
        "historically interacted user-item pair "
        "purchases the item within the next 7 days"
    )
    md.append(
        "- Raw identifier and future-window metadata "
        "are excluded from model features."
    )
    md.append("")

    md.append(
        "| Split | Rows | Positive | Negative | "
        "Positive Rate | Duplicate Keys | "
        "Null/NaN/Inf | Status |"
    )

    md.append(
        "|---|---:|---:|---:|---:|---:|---:|---|"
    )

    for r in results:
        bad_values = (
            r["feature_null_count"]
            + r["feature_nan_count"]
            + r["feature_inf_count"]
        )

        md.append(
            f'| {r["split"]} '
            f'| {r["rows"]:,} '
            f'| {r["positive"]:,} '
            f'| {r["negative"]:,} '
            f'| {r["positive_rate"]:.6%} '
            f'| {r["duplicate_primary_key_count"]:,} '
            f'| {bad_values:,} '
            f'| {r["status"]} |'
        )

    md.append("")
    md.append("## Leakage controls")
    md.append("")
    md.append(
        "- Features are calculated only from behavior "
        "at or before each split cutoff."
    )
    md.append(
        "- Future 7-day label-window timestamps are "
        "not model features."
    )
    md.append(
        "- `user_id` and `item_id` are retained only "
        "as sample keys."
    )
    md.append(
        "- Raw `category_id` is excluded from the "
        "traditional-model feature matrix."
    )
    md.append(
        "- Raw datetime fields are excluded; "
        "engineered historical time features remain."
    )
    md.append("")
    md.append("## Final feature list")
    md.append("")

    for feature in expected_features:
        md.append(f"- `{feature}`")

    report_path = (
        REPORT_DIR
        / "stage3_model_ready_audit.md"
    )

    report_path.write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("=" * 90)
    print(
        "Schema consistency:",
        schema_consistency,
    )
    print(
        "Overall status:",
        "PASS" if overall_pass else "FAIL",
    )
    print(
        "JSON report:",
        json_path,
    )
    print(
        "Markdown report:",
        report_path,
    )

    if not overall_pass:
        raise SystemExit(
            "AUDIT FAILED - do not train models yet."
        )


if __name__ == "__main__":
    main()
