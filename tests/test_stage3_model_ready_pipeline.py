import json
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_stage3_model_ready import (
    fit_model_ready_pipeline,
    transform_model_ready_frame,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config():
    return json.loads(
        (PROJECT_ROOT / "configs" / "stage3_feature_config.json").read_text(
            encoding="utf-8-sig"
        )
    )


def frame_for_split(split, periods):
    size = len(periods)
    prediction_date = {
        "train": "2025-11-20",
        "valid": "2025-12-10",
        "test": "2025-12-16",
    }[split]
    prediction_date = pd.Timestamp(prediction_date)
    return pd.DataFrame(
        {
            "user_id": range(1, size + 1),
            "item_id": range(101, 101 + size),
            "category_id": range(201, 201 + size),
            "prediction_date": [prediction_date] * size,
            "cutoff_time": [prediction_date + pd.Timedelta(hours=23, minutes=59, seconds=59)] * size,
            "label_start": [prediction_date + pd.Timedelta(days=1)] * size,
            "label_end": [prediction_date + pd.Timedelta(days=1, hours=23, minutes=59, seconds=59)] * size,
            "label": [0, 1, 0, 1, 0, 1, 0, 1][:size],
            "ui_pv_count": [1, 3, 2, 8, 5, 13, 7, 21][:size],
            "score": [0.5, 2.0, 1.5, 5.0, 3.0, 8.0, 4.5, 13.0][:size],
            "time_period": periods,
            "weekday": list(range(size)),
            "sequence_recent_10_behavior_types": [
                "1|3", "1|4", "2|3", "1|2|4"
            ] * (size // 4),
            "user_activity_level": ["low", "high"] * (size // 2),
            "item_popularity_level": ["low", "high"] * (size // 2),
            "category_popularity_level": ["long_tail", "popular"] * (size // 2),
            "time_is_peak_hour": [0, 1] * (size // 2),
        }
    )


class Stage3ModelReadyPipelineTests(unittest.TestCase):
    def test_train_fit_then_three_frozen_transforms(self) -> None:
        config = load_config()
        train = frame_for_split(
            "train",
            ["morning", "afternoon", "evening", "night"] * 2,
        )
        valid = frame_for_split(
            "valid",
            ["dawn", "afternoon", "evening", "night"] * 2,
        )
        test = frame_for_split(
            "test",
            ["late_night", "afternoon", "evening", "night"] * 2,
        )

        preprocessor, selector = fit_model_ready_pipeline(
            train,
            config,
            fit_metadata={"strategy": "unit_test", "sample_size": len(train)},
        )
        outputs = [
            transform_model_ready_frame(frame, preprocessor, selector)
            for frame in (train, valid, test)
        ]

        schemas = [output.columns.tolist() for output in outputs]
        self.assertEqual(schemas[0], schemas[1])
        self.assertEqual(schemas[0], schemas[2])
        self.assertEqual(
            schemas[0][: len(config["tracking_columns"])],
            config["tracking_columns"],
        )
        self.assertEqual(schemas[0][-1], config["target_column"])
        selected = selector.get_selected_features()
        forbidden = set(config["tracking_columns"] + [config["target_column"]])
        self.assertFalse(forbidden.intersection(selected))
        self.assertEqual(preprocessor.get_state()["fit_split"], "train")
        self.assertEqual(selector.get_state()["fit_split"], "train")
        for output, source in zip(outputs, (train, valid, test)):
            self.assertEqual(len(output), len(source))
            self.assertEqual(output["label"].tolist(), source["label"].tolist())


if __name__ == "__main__":
    unittest.main()
