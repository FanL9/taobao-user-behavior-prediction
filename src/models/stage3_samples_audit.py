"""Audit Stage 3 Member 2 samples and purchase labels."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.stage3_labels import SPLIT_WINDOWS


ROOT = Path("data/modeling")
JSON_OUTPUT = Path("reports/stage3_samples_and_labels_audit.json")
MARKDOWN_OUTPUT = Path("reports/stage3_samples_and_labels_audit.md")

REQUIRED_FEATURE_GROUPS = {
    "user_item": "ui_pv_count",
    "user_behavior": "user_total_count",
    "user_activity": "user_activity_level",
    "time": "time_total_count",
    "sequence": "sequence_recent_10_behavior_types",
    "item": "item_total_count",
    "category": "category_total_count",
    "item_conversion": "conversion_pv_count",
}

RAW_TIME_COLUMNS = (
    "ui_last_interaction_time",
    "user_first_behavior_time",
    "user_last_behavior_time",
)


def _encoded_keys(table) -> np.ndarray:
    users = table["user_id"].combine_chunks().to_numpy().astype(np.uint64)
    items = table["item_id"].combine_chunks().to_numpy().astype(np.uint64)
    if (users >= 2**32).any() or (items >= 2**32).any():
        raise RuntimeError("user_id or item_id exceeds the audit key encoding")
    return (users << np.uint64(32)) | items


def _metadata_null_count(parquet_file: pq.ParquetFile) -> tuple[int, bool]:
    total = 0
    complete = True
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        row_group = parquet_file.metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            statistics = row_group.column(column_index).statistics
            if statistics is None or not statistics.has_null_count:
                complete = False
                continue
            total += statistics.null_count
    return total, complete


def _column_max(parquet_file: pq.ParquetFile, column_name: str):
    column_index = parquet_file.schema_arrow.names.index(column_name)
    maxima = []
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        statistics = parquet_file.metadata.row_group(row_group_index).column(
            column_index
        ).statistics
        if statistics is None or not statistics.has_min_max:
            return None
        maxima.append(statistics.max)
    return max(maxima)


def audit_split(split: str, window: dict[str, pd.Timestamp]) -> dict:
    label_path = ROOT / f"{split}_labels.parquet"
    modeling_path = ROOT / split / f"{split}_modeling.parquet"
    if not label_path.exists():
        raise FileNotFoundError(label_path)
    if not modeling_path.exists():
        raise FileNotFoundError(modeling_path)

    label_pf = pq.ParquetFile(label_path)
    model_pf = pq.ParquetFile(modeling_path)
    required_label_columns = {
        "user_id",
        "item_id",
        "prediction_date",
        "cutoff_time",
        "label_start",
        "label_end",
        "label",
    }
    missing_label_columns = sorted(
        required_label_columns - set(label_pf.schema_arrow.names)
    )

    label_table = pq.read_table(
        label_path,
        columns=["user_id", "item_id", "prediction_date", "label"],
    )
    model_table = pq.read_table(
        modeling_path,
        columns=["user_id", "item_id", "prediction_date", "label"],
    )
    label_keys = _encoded_keys(label_table)
    model_keys = _encoded_keys(model_table)
    duplicate_label_keys = len(label_keys) - len(np.unique(label_keys))
    duplicate_model_keys = len(model_keys) - len(np.unique(model_keys))
    keys_and_labels_match = (
        np.array_equal(label_keys, model_keys)
        and np.array_equal(
            label_table["label"].combine_chunks().to_numpy(),
            model_table["label"].combine_chunks().to_numpy(),
        )
    )

    label_values = sorted(
        value.as_py()
        for value in pc.unique(label_table["label"].combine_chunks())
    )
    prediction_dates = sorted(
        str(value.as_py().date())
        for value in pc.unique(
            label_table["prediction_date"].combine_chunks()
        )
    )

    model_columns = set(model_pf.schema_arrow.names)
    feature_groups = {
        group: column in model_columns
        for group, column in REQUIRED_FEATURE_GROUPS.items()
    }
    model_null_count, model_null_count_complete = _metadata_null_count(model_pf)
    cutoff = window["feature_end"].normalize() + pd.Timedelta(
        hours=23, minutes=59, seconds=59
    )
    time_column_maxima = {
        column: str(_column_max(model_pf, column))
        for column in RAW_TIME_COLUMNS
    }
    future_time_columns = []
    for column, maximum in time_column_maxima.items():
        if maximum == "None" or pd.Timestamp(maximum) > cutoff:
            future_time_columns.append(column)

    positives = int(pc.sum(label_table["label"]).as_py())
    rows = label_pf.metadata.num_rows
    failures = []
    if missing_label_columns:
        failures.append(f"missing label columns: {missing_label_columns}")
    if label_values != [0, 1]:
        failures.append(f"invalid label values: {label_values}")
    if prediction_dates != [str(window["label_date"].date())]:
        failures.append(f"invalid prediction_date values: {prediction_dates}")
    if duplicate_label_keys:
        failures.append(f"duplicate label keys: {duplicate_label_keys}")
    if duplicate_model_keys:
        failures.append(f"duplicate modeling keys: {duplicate_model_keys}")
    if not keys_and_labels_match:
        failures.append("modeling keys or labels do not match label table")
    missing_groups = [name for name, present in feature_groups.items() if not present]
    if missing_groups:
        failures.append(f"missing feature groups: {missing_groups}")
    if "conversion_scope" in model_columns:
        failures.append("global conversion_scope was joined into modeling data")
    if model_null_count_complete and model_null_count:
        failures.append(f"modeling null values: {model_null_count}")
    if future_time_columns:
        failures.append(f"future raw time columns: {future_time_columns}")

    return {
        "split": split,
        "feature_start": str(window["feature_start"].date()),
        "feature_end": str(window["feature_end"].date()),
        "label_date": str(window["label_date"].date()),
        "rows": rows,
        "positive": positives,
        "negative": rows - positives,
        "positive_rate": positives / rows,
        "label_values": label_values,
        "duplicate_label_keys": duplicate_label_keys,
        "duplicate_modeling_keys": duplicate_model_keys,
        "keys_and_labels_match": keys_and_labels_match,
        "feature_groups": feature_groups,
        "global_conversion_joined": "conversion_scope" in model_columns,
        "modeling_columns": model_pf.metadata.num_columns,
        "modeling_null_count": model_null_count,
        "modeling_null_count_complete": model_null_count_complete,
        "raw_time_maxima": time_column_maxima,
        "future_raw_time_columns": future_time_columns,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def _render_markdown(report: dict) -> str:
    lines = [
        "# Member 2 阶段三建模样本与标签审计",
        "",
        f"**总体状态：{report['overall_status']}**",
        "",
        "## 时间切分与样本标签",
        "",
        "| 数据集 | 特征基准日 | 标签日 | 样本数 | 正样本 | 负样本 | 正样本率 | 状态 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for split in report["splits"]:
        lines.append(
            f"| {split['split']} | {split['feature_start']}—{split['feature_end']} "
            f"| {split['label_date']} | {split['rows']:,} | "
            f"{split['positive']:,} | {split['negative']:,} | "
            f"{split['positive_rate']:.6%} | {split['status']} |"
        )

    lines.extend(
        [
            "",
            "## 检查结论",
            "",
            "- 每个数据集内 `user_id + item_id` 唯一，标签表保留 `prediction_date` 追踪标签日。",
            "- 标签只包含 0/1，建模样本的主键和标签与对应标签表完全一致。",
            "- 用户、活跃度、时间、序列、商品、类目、用户—商品及商品粒度转化链路特征均已关联。",
            "- 未将全局单行 `conversion_scope` 漏斗表拼入建模样本。",
            "- 原始时间字段最大值均未超过各数据集特征截止日，未发现标签日或未来行为进入特征。",
            "",
            "## 标签日新出现购买对",
            "",
            "候选集仅包含对应特征基准日范围内出现过的用户—商品对；标签日首次出现的购买对不进入候选集。",
            "",
            "| 数据集 | 标签日全部购买对 | 被排除的新购买对 |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in report["label_summary"]:
        lines.append(
            f"| {row['dataset']} | {int(row['label_purchase_pairs']):,} | "
            f"{int(row['excluded_new_purchase_pairs']):,} |"
        )
    lines.extend(
        [
            "",
            "该排除规则属于候选集口径，不是错标；后续报告和模型适用范围必须明确说明模型不覆盖标签日首次出现的用户—商品对。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    split_reports = [
        audit_split(split, window) for split, window in SPLIT_WINDOWS.items()
    ]
    summary_path = ROOT / "purchase_label_summary.csv"
    label_summary = pd.read_csv(summary_path).to_dict(orient="records")
    failures = [
        f"{split['split']}: {failure}"
        for split in split_reports
        for failure in split["failures"]
    ]
    report = {
        "overall_status": "PASS" if not failures else "FAIL",
        "splits": split_reports,
        "label_summary": label_summary,
        "failures": failures,
    }

    JSON_OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    MARKDOWN_OUTPUT.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
