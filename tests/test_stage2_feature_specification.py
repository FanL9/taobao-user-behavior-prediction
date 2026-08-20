"""Tests for the stage-two feature specification metadata."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.features.stage2_feature_specification import (
    FEATURE_DEFINITIONS,
    REQUIRED_INPUT_COLUMNS,
    TABLE_DEFINITIONS,
    export_feature_dictionary,
    export_table_schemas,
    validate_clean_input_schema,
)


class Stage2FeatureSpecificationTests(unittest.TestCase):
    def test_all_primary_keys_are_defined(self) -> None:
        fields = {
            table.table_name: {
                feature.feature_name
                for feature in FEATURE_DEFINITIONS
                if feature.table_name == table.table_name
            }
            for table in TABLE_DEFINITIONS
        }
        for table in TABLE_DEFINITIONS:
            self.assertTrue(set(table.primary_key).issubset(fields[table.table_name]))

    def test_csv_header_is_accepted_without_reading_data_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "clean.csv"
            input_path.write_text(
                ",".join(REQUIRED_INPUT_COLUMNS) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                validate_clean_input_schema(input_path),
                REQUIRED_INPUT_COLUMNS,
            )

    def test_exports_dictionary_and_four_table_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dictionary_path = Path(directory) / "dictionary.csv"
            schema_path = Path(directory) / "schemas.json"
            export_feature_dictionary(dictionary_path)
            export_table_schemas(schema_path)

            with dictionary_path.open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            payload = json.loads(schema_path.read_text(encoding="utf-8"))

            self.assertEqual(len(rows), len(FEATURE_DEFINITIONS))
            self.assertEqual(len(payload["tables"]), 4)


if __name__ == "__main__":
    unittest.main()

