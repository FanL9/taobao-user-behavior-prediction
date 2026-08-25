# Feature Data Files

Most feature tables in this directory may be committed to GitHub.

`user_item_features.parquet` and `user_item_feature_table.parquet` are
intentionally excluded from Git because they are large reproducible tables.
Generate the base tables locally with:

```bash
python scripts/build_stage2_intermediate_tables.py
```

The command requires `data/processed/user_behavior_clean.parquet` and creates:

- `user_features.parquet`
- `item_features.parquet`
- `category_features.parquet`
- `time_features.parquet`
- `user_item_features.parquet` (local only)

Build the formal Member 2 sequence table separately:

```bash
python scripts/build_member2_stage2_features.py
```

The formal stage-two Member 2 outputs are `user_features.parquet`,
`time_features.parquet`, and `user_sequence_features.parquet`. The CSV files
`user_active_level.csv`, `time_feature_hourly_weekly.csv`,
`peak_hour_features.csv`, and `user_sequence_features.csv` are supplementary
legacy outputs with different field definitions; do not use them as inputs to
the final feature table. Their optional legacy generator is
`scr/build_legacy_member2_csv_features.py`.

Build and validate the formal Member 3 non-dashboard outputs:

```bash
python scripts/build_member3_stage2_features.py
```

This creates `item_conversion_features.parquet` and
`conversion_features.parquet`. Item and category popularity levels are included
in `item_features.parquet` and `category_features.parquet` by the base-table
builder.

Build the local-only initial feature table after all inputs exist:

```bash
python scripts/build_stage2_feature_table.py
```

The output is `user_item_feature_table.parquet`. It combines user, sequence,
item, category, time, user-item interaction, and item-conversion features.

Dashboard datasets are part of the stage-two assignment. Generate the four
local-only dashboard Parquet tables with:

```bash
python scr/build_dashboard_data.py
```

The expected files are documented in `docs/local_large_files.md`.

Do not manually edit generated Parquet files. See
`docs/local_large_files.md` for all local-only data files.
