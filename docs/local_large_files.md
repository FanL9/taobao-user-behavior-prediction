# Local Large Files

The files below are not uploaded to GitHub because of their size. Each project
member must prepare or generate them locally before running the corresponding
pipeline.

| Local file | Current approximate size | Local preparation |
| --- | ---: | --- |
| `data/raw/user_behavior_processed.csv` | 469 MB | Manually place the source dataset at this path. |
| `data/raw/user_behavior_processed.parquet` | 118 MB | Run `python scripts/setup_local_database.py`. |
| `database/taobao_user_behavior.db` | 2.1 GB | Run `python scripts/setup_local_database.py`. |
| `data/processed/user_behavior_clean.parquet` | 139 MB | Run `python scripts/run_user_behavior_cleaning.py --output-parquet`. |
| `data/processed/user_behavior_clean.csv` | Not currently present; expected to be large | Run `python scripts/run_user_behavior_cleaning.py` only when CSV output is required. Parquet is the authoritative stage-two input. |
| `data/interim/item_statistics.csv` | 52 MB | Regenerate locally from the stage-one basic-analysis workflow. |
| `data/features/user_item_features.parquet` | 50 MB | Run `python scripts/build_stage2_intermediate_tables.py`. |

## Local setup order

```text
Place data/raw/user_behavior_processed.csv locally
    → python scripts/setup_local_database.py
    → python scripts/run_user_behavior_cleaning.py --output-parquet
    → python scripts/build_stage2_intermediate_tables.py
```

The final command also regenerates the smaller user, item, category, and time
feature tables. Files ignored by `.gitignore` remain local and should not be
force-added with `git add -f`.
