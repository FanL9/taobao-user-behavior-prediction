# Feature Data Files

Most feature tables in this directory may be committed to GitHub.

`user_item_features.parquet` is intentionally excluded from Git because it is a
large table. Generate it locally together with the other stage-two feature
tables:

```bash
python scripts/build_stage2_intermediate_tables.py
```

The command requires `data/processed/user_behavior_clean.parquet` and creates:

- `user_features.parquet`
- `item_features.parquet`
- `category_features.parquet`
- `time_features.parquet`
- `user_item_features.parquet` (local only)

Do not manually edit generated Parquet files. See
`docs/local_large_files.md` for all local-only data files.
