"""Fit Stage 3 preprocessing on train and transform all splits in batches."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.features.stage3_feature_selection import Stage3FeatureSelector
from src.features.stage3_preprocessing import Stage3Preprocessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "data" / "modeling"
CONFIG_PATH = PROJECT_ROOT / "configs" / "stage3_feature_config.json"
FEATURE_LIST_PATH = PROJECT_ROOT / "configs" / "stage3_model_feature_list.txt"
ARTIFACT_PATH = (
    PROJECT_ROOT / "artifacts" / "preprocessors" / "stage3_preprocessor.joblib"
)
SELECTION_REPORT_PATH = (
    PROJECT_ROOT / "reports" / "stage3_feature_selection_report.json"
)
SPLITS = ("train", "valid", "test")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def modeling_path(split: str) -> Path:
    return ROOT / split / f"{split}_modeling.parquet"


def model_ready_path(split: str) -> Path:
    return ROOT / split / f"{split}_model_ready.parquet"


def deterministic_train_sample(
    path: Path,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Keep the rows with the smallest seeded key hashes across all batches."""

    sampling = config["preprocessing"]["fit_sampling"]
    strategy = str(sampling["strategy"])
    if strategy != "deterministic_hash_top_k":
        raise ValueError(f"Unsupported fit sampling strategy: {strategy}")

    max_rows = int(sampling["max_rows"])
    batch_size = int(sampling["batch_size"])
    seed = int(config["random_seed"])
    key_columns = list(config["sample_key_columns"])
    if max_rows <= 0 or batch_size <= 0:
        raise ValueError("Fit sampling max_rows and batch_size must be positive")

    parquet = pq.ParquetFile(path)
    schema_columns = set(parquet.schema_arrow.names)
    missing_keys = [column for column in key_columns if column not in schema_columns]
    if missing_keys:
        raise ValueError(f"Train Parquet is missing sampling keys: {missing_keys}")

    sample = pd.DataFrame()
    hash_column = "__stage3_fit_hash__"
    seed_mask = np.uint64(seed)

    for batch_number, batch in enumerate(
        parquet.iter_batches(batch_size=batch_size, use_threads=True),
        start=1,
    ):
        frame = batch.to_pandas()
        hashes = pd.util.hash_pandas_object(
            frame[key_columns],
            index=False,
        ).astype("uint64")
        frame[hash_column] = hashes ^ seed_mask
        candidate = frame.nsmallest(min(max_rows, len(frame)), hash_column)
        if sample.empty:
            sample = candidate
        else:
            sample = pd.concat([sample, candidate], ignore_index=True).nsmallest(
                max_rows,
                hash_column,
            )
        print(
            f"fit sample batch {batch_number:03d} "
            f"| retained={len(sample):,}"
        )

    if sample.empty:
        raise RuntimeError("Training input is empty")
    sample = sample.sort_values(hash_column).drop(columns=[hash_column])
    sample = sample.reset_index(drop=True)
    metadata = {
        "strategy": strategy,
        "sample_size": int(len(sample)),
        "max_rows": max_rows,
        "seed": seed,
        "source_rows": int(parquet.metadata.num_rows),
        "source_path": str(path),
    }
    return sample, metadata


def fit_model_ready_pipeline(
    train_df: pd.DataFrame,
    config: dict[str, Any],
    *,
    scaling_profile: str | None = None,
    fit_metadata: dict[str, Any] | None = None,
) -> tuple[Stage3Preprocessor, Stage3FeatureSelector]:
    """Fit both stages once; this function never accepts valid/test as fit data."""

    preprocessor = Stage3Preprocessor(
        config,
        scaling_profile=scaling_profile,
    )
    preprocessor.fit(
        train_df,
        split_name=config["fit_split"],
        fit_metadata=fit_metadata,
    )
    # Feature selection sees unscaled values so low-variance thresholds retain
    # their configured meaning even when the output profile is linear.
    train_transformed = preprocessor.transform(train_df, apply_scaling=False)
    selector = Stage3FeatureSelector(config)
    selector.fit(
        train_transformed.X,
        raw_missing_rates=preprocessor.get_output_missing_rates(),
        split_name=config["fit_split"],
    )
    return preprocessor, selector


def transform_model_ready_frame(
    df: pd.DataFrame,
    preprocessor: Stage3Preprocessor,
    selector: Stage3FeatureSelector,
) -> pd.DataFrame:
    transformed = preprocessor.transform(df)
    selected = selector.transform(transformed.X)
    if transformed.y is None:
        raise ValueError("Current Stage 3 model-ready outputs require label")
    result = pd.concat(
        [
            transformed.tracking_df.reset_index(drop=True),
            selected.reset_index(drop=True),
            transformed.y.reset_index(drop=True),
        ],
        axis=1,
    )
    return result


def write_model_ready_split(
    split: str,
    preprocessor: Stage3Preprocessor,
    selector: Stage3FeatureSelector,
    *,
    batch_size: int,
) -> pa.Schema:
    input_path = modeling_path(split)
    output_path = model_ready_path(split)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parquet = pq.ParquetFile(input_path)

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}.",
        suffix=".parquet.tmp",
        dir=output_path.parent,
        delete=False,
    )
    handle.close()
    temporary = Path(handle.name)
    writer: pq.ParquetWriter | None = None
    expected_schema: pa.Schema | None = None
    total_rows = 0

    try:
        for batch_number, batch in enumerate(
            parquet.iter_batches(batch_size=batch_size, use_threads=True),
            start=1,
        ):
            frame = batch.to_pandas()
            transformed = transform_model_ready_frame(
                frame,
                preprocessor,
                selector,
            )
            table = pa.Table.from_pandas(transformed, preserve_index=False)
            if expected_schema is None:
                expected_schema = table.schema
                writer = pq.ParquetWriter(
                    temporary,
                    expected_schema,
                    compression="snappy",
                    use_dictionary=True,
                )
            elif not table.schema.equals(expected_schema):
                raise RuntimeError(f"{split}: schema changed between batches")
            if writer is None:
                raise RuntimeError("Parquet writer was not initialized")
            writer.write_table(table, row_group_size=100_000)
            total_rows += len(transformed)
            print(
                f"{split} batch {batch_number:03d} "
                f"| rows={total_rows:,}"
            )

        if writer is not None:
            writer.close()
            writer = None
        if expected_schema is None:
            raise RuntimeError(f"{split}: no rows were transformed")
        written = pq.ParquetFile(temporary)
        try:
            if written.metadata.num_rows != parquet.metadata.num_rows:
                raise RuntimeError(f"{split}: output row count does not match input")
        finally:
            written.close()

        temporary.replace(output_path)
        print(f"{split} saved: {output_path}")
        return expected_schema
    except Exception:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
        raise


def _write_artifact(
    preprocessor: Stage3Preprocessor,
    selector: Stage3FeatureSelector,
    config: dict[str, Any],
) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{ARTIFACT_PATH.stem}.",
        suffix=".joblib.tmp",
        dir=ARTIFACT_PATH.parent,
        delete=False,
    )
    handle.close()
    temporary = Path(handle.name)
    try:
        joblib.dump(
            {
                "config": config,
                "preprocessor": preprocessor,
                "selector": selector,
                "preprocessor_state": preprocessor.get_state(),
                "selector_state": selector.get_state(),
            },
            temporary,
        )
        temporary.replace(ARTIFACT_PATH)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_manifests(selector: Stage3FeatureSelector) -> None:
    selected = selector.get_selected_features()
    FEATURE_LIST_PATH.write_text(
        "\n".join(selected) + "\n",
        encoding="utf-8",
    )
    SELECTION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SELECTION_REPORT_PATH.write_text(
        json.dumps(
            {
                "fit_split": selector.fit_split,
                "selected_feature_count": len(selected),
                "selected_features": selected,
                "drop_records": selector.get_drop_records(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    config = load_config()
    if config.get("fit_split") != "train":
        raise ValueError("Stage 3 preprocessing fit_split must be train")

    train_sample, sample_metadata = deterministic_train_sample(
        modeling_path("train"),
        config,
    )
    preprocessor, selector = fit_model_ready_pipeline(
        train_sample,
        config,
        scaling_profile=config["preprocessing"]["scaling"]["default_profile"],
        fit_metadata=sample_metadata,
    )
    del train_sample

    batch_size = int(config["preprocessing"]["fit_sampling"]["batch_size"])
    schemas: dict[str, pa.Schema] = {}
    for split in SPLITS:
        schemas[split] = write_model_ready_split(
            split,
            preprocessor,
            selector,
            batch_size=batch_size,
        )

    reference = schemas["train"]
    inconsistent = [
        split for split in SPLITS if not schemas[split].equals(reference)
    ]
    if inconsistent:
        raise RuntimeError(
            "Train/valid/test model-ready schemas differ: "
            f"{inconsistent}"
        )
    _write_artifact(preprocessor, selector, config)
    _write_manifests(selector)
    print("Stage 3 train-fitted preprocessing completed successfully.")


if __name__ == "__main__":
    main()
