from __future__ import annotations

from typing import Iterable

import pandas as pd


def add_available_at(
    df: pd.DataFrame,
    timeframe: str,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Add the timestamp at which each candle becomes fully known.

    Example:
        4h candle timestamp = 08:00
        available_at = 12:00

    This prevents higher-timeframe information from being used
    before that candle has actually closed.
    """

    result = df.copy()

    if timestamp_col not in result.columns:
        raise ValueError(f"Missing required column: {timestamp_col}")

    timeframe_map = {
        "1m": pd.Timedelta(minutes=1),
        "5m": pd.Timedelta(minutes=5),
        "15m": pd.Timedelta(minutes=15),
        "30m": pd.Timedelta(minutes=30),
        "1h": pd.Timedelta(hours=1),
        "2h": pd.Timedelta(hours=2),
        "4h": pd.Timedelta(hours=4),
        "6h": pd.Timedelta(hours=6),
        "12h": pd.Timedelta(hours=12),
        "1d": pd.Timedelta(days=1),
    }

    if timeframe not in timeframe_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    result["available_at"] = (
        pd.to_datetime(result[timestamp_col], utc=True)
        + timeframe_map[timeframe]
    )

    return result


def causal_asof_join(
    decisions: pd.DataFrame,
    features: pd.DataFrame,
    decision_time_col: str = "decision_time",
    feature_time_col: str = "available_at",
    feature_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """
    Join features to decision timestamps using only information
    that was available at the decision time.

    The most recent feature whose `available_at` <= decision time
    is selected.

    This is the core mechanism for causal multi-timeframe joins.
    """

    if decision_time_col not in decisions.columns:
        raise ValueError(
            f"Missing decision time column: {decision_time_col}"
        )

    if feature_time_col not in features.columns:
        raise ValueError(
            f"Missing feature time column: {feature_time_col}"
        )

    left = decisions.copy()
    right = features.copy()

    left[decision_time_col] = pd.to_datetime(
        left[decision_time_col],
        utc=True,
        errors="coerce",
    )

    right[feature_time_col] = pd.to_datetime(
        right[feature_time_col],
        utc=True,
        errors="coerce",
    )
    if left[decision_time_col].isna().any():
        raise ValueError("Decision timestamps must be valid")
    if right[feature_time_col].isna().any():
        raise ValueError("Feature availability timestamps must be valid")
    if right[feature_time_col].duplicated().any():
        raise ValueError("Feature availability timestamps must be unique")

    if feature_columns is None:
        excluded = {
            feature_time_col,
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        feature_columns = [
            col for col in right.columns
            if col not in excluded
        ]

    feature_columns = list(feature_columns)
    if len(set(feature_columns)) != len(feature_columns):
        raise ValueError("Feature columns must be unique")
    if feature_time_col in feature_columns:
        raise ValueError("Feature columns must not repeat the availability column")
    missing_features = set(feature_columns) - set(right.columns)
    if missing_features:
        raise ValueError(f"Missing feature columns: {sorted(missing_features)}")

    right = right[[feature_time_col] + feature_columns].copy()

    order_column = "__causal_asof_input_order"
    existing_columns = set(left.columns) | set(right.columns)
    while order_column in existing_columns:
        order_column += "_"
    left[order_column] = range(len(left))
    right = right.sort_values(feature_time_col, kind="stable")
    left = left.sort_values([decision_time_col, order_column], kind="stable")

    result = pd.merge_asof(
        left,
        right,
        left_on=decision_time_col,
        right_on=feature_time_col,
        direction="backward",
        allow_exact_matches=True,
    )

    matched = result[feature_time_col].notna()
    if (result.loc[matched, feature_time_col] > result.loc[matched, decision_time_col]).any():
        raise RuntimeError("As-of join selected a feature before its availability")

    return (
        result.sort_values(order_column, kind="stable")
        .drop(columns=order_column)
        .reset_index(drop=True)
    )
