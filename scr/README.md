# Auxiliary Scripts

This directory contains optional artifact-generation utilities. They are not
required to reproduce the core data and feature pipeline.

- `build_member2_stage2_report.py`: refresh the Member 2 stage-two report.
- `build_member3_stage2_report.py`: refresh the Member 3 stage-two report.
- `build_stage2_feature_table_report.py`: refresh the initial feature-table report.
- `build_dashboard_data.py`: prepare optional dashboard datasets.
- `build_legacy_member2_csv_features.py`: regenerate the legacy supplemental
  Member 2 CSV outputs; these files are not formal wide-table inputs.

Mandatory setup, feature construction, and validation entry points remain in
`scripts/`.
