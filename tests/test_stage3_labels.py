import pandas as pd

from src.models.stage3_labels import SPLIT_WINDOWS, build_split
from src.features.stage3_snapshot_features import (
    SPLIT_WINDOWS as INTERMEDIATE_WINDOWS,
)
from src.models.stage3_modeling_samples import SPLIT_DATE_RANGES
from src.features.stage3_sequence_features import (
    SPLIT_WINDOWS as SEQUENCE_WINDOWS,
)


def test_stage3_split_windows_match_fixed_project_definition():
    expected = {
        "train": ("2025-11-18", "2025-12-07", "2025-12-08"),
        "valid": ("2025-12-09", "2025-12-14", "2025-12-15"),
        "test": ("2025-12-16", "2025-12-17", "2025-12-18"),
    }

    actual = {
        name: (
            str(window["feature_start"].date()),
            str(window["feature_end"].date()),
            str(window["label_date"].date()),
        )
        for name, window in SPLIT_WINDOWS.items()
    }

    assert actual == expected

    intermediate = {
        name: tuple(str(value.date()) for value in values)
        for name, values in INTERMEDIATE_WINDOWS.items()
    }
    sequence = {
        name: tuple(str(value.date()) for value in values)
        for name, values in SEQUENCE_WINDOWS.items()
    }
    modeling_dates = {
        name: tuple(str(value.date()) for value in values)
        for name, values in SPLIT_DATE_RANGES.items()
    }

    assert intermediate == expected
    assert sequence == expected
    assert modeling_dates == {
        "train": ("2025-12-08", "2025-12-08"),
        "valid": ("2025-12-15", "2025-12-15"),
        "test": ("2025-12-18", "2025-12-18"),
    }


def test_build_split_uses_only_window_candidates_and_one_label_day():
    behavior = pd.DataFrame(
        {
            "time": pd.to_datetime(
                [
                    "2025-11-17 23:00:00",
                    "2025-11-18 10:00:00",
                    "2025-12-07 23:00:00",
                    "2025-12-08 08:00:00",
                    "2025-12-08 09:00:00",
                    "2025-12-09 00:00:00",
                ]
            ),
            "user_id": [9, 1, 2, 1, 3, 2],
            "item_id": [90, 10, 20, 10, 30, 20],
            "behavior_type": [1, 1, 1, 4, 4, 4],
        }
    )

    labels = build_split(
        behavior,
        "train",
        pd.Timestamp("2025-11-18"),
        pd.Timestamp("2025-12-07"),
        pd.Timestamp("2025-12-08"),
    )

    assert set(map(tuple, labels[["user_id", "item_id"]].to_numpy())) == {
        (1, 10),
        (2, 20),
    }
    assert labels.set_index(["user_id", "item_id"])["label"].to_dict() == {
        (1, 10): 1,
        (2, 20): 0,
    }
    assert labels["prediction_date"].unique().tolist() == [
        pd.Timestamp("2025-12-08")
    ]


def test_build_split_rejects_nonadjacent_label_day():
    behavior = pd.DataFrame(
        columns=["time", "user_id", "item_id", "behavior_type"]
    )
    behavior["time"] = pd.to_datetime(behavior["time"])

    try:
        build_split(
            behavior,
            "train",
            pd.Timestamp("2025-11-18"),
            pd.Timestamp("2025-12-07"),
            pd.Timestamp("2025-12-09"),
        )
    except ValueError as exc:
        assert "must immediately follow" in str(exc)
    else:
        raise AssertionError("Expected a ValueError for a nonadjacent label day")
