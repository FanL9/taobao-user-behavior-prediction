"""Build conversion funnel features for stage two."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "user_behavior_clean.parquet"
)

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "features"
    / "conversion_features.parquet"
)


BEHAVIOR_MAPPING = {
    1: "pv",
    2: "fav",
    3: "cart",
    4: "buy",
}


def safe_rate(numerator, denominator):
    if denominator == 0:
        return 0.0

    return numerator / denominator


def build_conversion_features(
    input_path=DEFAULT_INPUT,
    output_path=DEFAULT_OUTPUT,
):

    table = pq.read_table(
        input_path,
        columns=[
            "behavior_type",
        ],
    )

    counts = {
        "pv_count": 0,
        "fav_count": 0,
        "cart_count": 0,
        "buy_count": 0,
    }

    for value in table["behavior_type"].to_pylist():

        name = BEHAVIOR_MAPPING[value]

        counts[f"{name}_count"] += 1


    result = pa.table(
        {
            "pv_count": [
                counts["pv_count"]
            ],

            "fav_count": [
                counts["fav_count"]
            ],

            "cart_count": [
                counts["cart_count"]
            ],

            "buy_count": [
                counts["buy_count"]
            ],

            "pv_to_fav_rate": [
                safe_rate(
                    counts["fav_count"],
                    counts["pv_count"]
                )
            ],

            "pv_to_cart_rate": [
                safe_rate(
                    counts["cart_count"],
                    counts["pv_count"]
                )
            ],

            "pv_to_buy_rate": [
                safe_rate(
                    counts["buy_count"],
                    counts["pv_count"]
                )
            ],

            "fav_to_buy_rate": [
                safe_rate(
                    counts["buy_count"],
                    counts["fav_count"]
                )
            ],

            "cart_to_buy_rate": [
                safe_rate(
                    counts["buy_count"],
                    counts["cart_count"]
                )
            ],
        }
    )


    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    pq.write_table(
        result,
        output_path,
        compression="snappy",
    )

    return output_path


if __name__ == "__main__":

    output = build_conversion_features()

    print(
        f"created: {output}"
    )
