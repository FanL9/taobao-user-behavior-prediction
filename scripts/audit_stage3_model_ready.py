"""Audit train-fitted Stage 3 next-day model-ready outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "data" / "modeling"
REPORT_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "configs" / "stage3_feature_config.json"
FEATURE_LIST_PATH = PROJECT_ROOT / "configs" / "stage3_model_feature_list.txt"
ARTIFACT_PATH = (
    PROJECT_ROOT / "artifacts" / "preprocessors" / "stage3_preprocessor.joblib"
)
SPLITS = ("train", "valid", "test")
BATCH_SIZE = 200_000


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def audit_label_window(split: str, config: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / f"{split}_labels.parquet"
    parquet = pq.ParquetFile(path)
    bad_rows = 0
    checked_rows = 0
    start_days = int(config["label_definition"]["label_start_offset_days"])
    end_days = int(config["label_definition"]["label_end_offset_days"])

    columns = ["prediction_date", "cutoff_time", "label_start", "label_end"]
    for batch in parquet.iter_batches(columns=columns, batch_size=BATCH_SIZE):
        frame = batch.to_pandas()
        prediction_date = pd.to_datetime(frame["prediction_date"]).dt.normalize()
        expected_cutoff = prediction_date - pd.Timedelta(seconds=1)
        expected_start = prediction_date + pd.Timedelta(days=start_days)
        expected_end = prediction_date + pd.Timedelta(days=end_days) - pd.Timedelta(
            seconds=1
        )
        valid = (
            pd.to_datetime(frame["cutoff_time"]).eq(expected_cutoff)
            & pd.to_datetime(frame["label_start"]).eq(expected_start)
            & pd.to_datetime(frame["label_end"]).eq(expected_end)
        )
        bad_rows += int((~valid).sum())
        checked_rows += len(frame)
    return {
        "rows_checked": checked_rows,
        "invalid_label_window_rows": bad_rows,
        "status": "PASS" if bad_rows == 0 else "FAIL",
    }


def audit_split(
    split: str,
    expected_features: list[str],
    config: dict[str, Any],
    feature_source_map: dict[str, str],
) -> dict[str, Any]:
    path = ROOT / split / f"{split}_model_ready.parquet"
    parquet = pq.ParquetFile(path)
    columns = parquet.schema_arrow.names
    tracking = list(config["tracking_columns"])
    target = str(config["target_column"])
    expected_columns = tracking + expected_features + [target]
    schema_ok = columns == expected_columns

    patterns = [re.compile(value) for value in config["leakage_name_patterns"]]
    forbidden = set(config["forbidden_feature_columns"])
    forbidden_features = sorted(
        feature
        for feature in expected_features
        if feature in forbidden
        or feature_source_map.get(feature) in forbidden
        or any(pattern.search(feature) for pattern in patterns)
    )

    total_rows = 0
    positive = 0
    null_count = 0
    nan_count = 0
    inf_count = 0
    duplicate_key_count = 0
    key_order_ok = True
    previous_key: tuple[Any, ...] | None = None
    sort_key = ["prediction_date", "user_id", "item_id"]

    for batch_number, batch in enumerate(
        parquet.iter_batches(batch_size=BATCH_SIZE),
        start=1,
    ):
        frame = batch.to_pandas()
        total_rows += len(frame)
        positive += int((frame[target] == 1).sum())
        features = frame[expected_features]
        null_count += int(features.isna().sum().sum())
        values = features.to_numpy(dtype=np.float64, copy=False)
        nan_count += int(np.isnan(values).sum())
        inf_count += int(np.isinf(values).sum())

        keys = frame[sort_key]
        duplicate_key_count += int(keys.duplicated().sum())
        key_tuples = list(keys.itertuples(index=False, name=None))
        if key_tuples:
            if previous_key is not None:
                if key_tuples[0] == previous_key:
                    duplicate_key_count += 1
                if key_tuples[0] < previous_key:
                    key_order_ok = False
            if any(left > right for left, right in zip(key_tuples, key_tuples[1:])):
                key_order_ok = False
            previous_key = key_tuples[-1]
        print(f"{split} batch {batch_number:03d} | rows={total_rows:,}")

    negative = total_rows - positive
    label_ok = positive > 0 and negative > 0
    passed = all(
        [
            schema_ok,
            not forbidden_features,
            duplicate_key_count == 0,
            key_order_ok,
            null_count == 0,
            nan_count == 0,
            inf_count == 0,
            label_ok,
        ]
    )
    return {
        "split": split,
        "path": str(path),
        "rows": total_rows,
        "columns": len(columns),
        "model_features": len(expected_features),
        "positive": positive,
        "negative": negative,
        "positive_rate": positive / total_rows if total_rows else 0.0,
        "schema_ok": schema_ok,
        "forbidden_features": forbidden_features,
        "duplicate_primary_key_count": duplicate_key_count,
        "key_order_ok": key_order_ok,
        "feature_null_count": null_count,
        "feature_nan_count": nan_count,
        "feature_inf_count": inf_count,
        "label_ok": label_ok,
        "status": "PASS" if passed else "FAIL",
    }


def main() -> None:
    config = load_config()
    expected_features = [
        line
        for line in FEATURE_LIST_PATH.read_text(encoding="utf-8").splitlines()
        if line
    ]
    artifact = joblib.load(ARTIFACT_PATH)
    preprocessor_state = artifact["preprocessor_state"]
    selector_state = artifact["selector_state"]
    artifact_fit_ok = (
        preprocessor_state.get("fit_split") == "train"
        and selector_state.get("fit_split") == "train"
        and selector_state.get("selected_features") == expected_features
    )

    label_windows = {
        split: audit_label_window(split, config) for split in SPLITS
    }
    feature_source_map = preprocessor_state.get("feature_source_map", {})
    results = [
        audit_split(split, expected_features, config, feature_source_map)
        for split in SPLITS
    ]
    schemas = [
        pq.ParquetFile(ROOT / split / f"{split}_model_ready.parquet").schema_arrow
        for split in SPLITS
    ]
    schema_consistency = all(schema.equals(schemas[0]) for schema in schemas[1:])
    overall_pass = (
        artifact_fit_ok
        and schema_consistency
        and all(value["status"] == "PASS" for value in label_windows.values())
        and all(result["status"] == "PASS" for result in results)
    )

    payload = {
        "overall_status": "PASS" if overall_pass else "FAIL",
        "prediction_target": "next-calendar-day user-item purchase",
        "artifact_fit_split_is_train": artifact_fit_ok,
        "schema_consistency": schema_consistency,
        "tracking_columns": config["tracking_columns"],
        "feature_count": len(expected_features),
        "label_windows": label_windows,
        "splits": results,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "stage3_model_ready_audit.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown = [
        "# Stage 3 Model-Ready Data Audit",
        "",
        f"Overall status: **{payload['overall_status']}**",
        "",
        "- Prediction target: purchase on the next calendar day",
        f"- Preprocessor and selector fitted on train only: {artifact_fit_ok}",
        f"- Train/valid/test schema consistent: {schema_consistency}",
        f"- Model feature count: {len(expected_features)}",
        "- Tracking columns are retained but excluded from X: "
        + ", ".join(f"`{column}`" for column in config["tracking_columns"]),
        "",
        "| Split | Rows | Positive Rate | Label Window | Status |",
        "|---|---:|---:|---|---|",
    ]
    for result in results:
        window_status = label_windows[result["split"]]["status"]
        markdown.append(
            f"| {result['split']} | {result['rows']:,} "
            f"| {result['positive_rate']:.6%} | {window_status} "
            f"| {result['status']} |"
        )
    markdown.extend(["", "## Selected features", ""])
    markdown.extend(f"- `{feature}`" for feature in expected_features)
    markdown_path = REPORT_DIR / "stage3_model_ready_audit.md"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")

    print("Schema consistency:", schema_consistency)
    print("Artifact fit split is train:", artifact_fit_ok)
    print("Overall status:", payload["overall_status"])
    print("JSON report:", json_path)
    print("Markdown report:", markdown_path)
    if not overall_pass:
        raise SystemExit("AUDIT FAILED - do not train models yet.")


if __name__ == "__main__":
    main()
