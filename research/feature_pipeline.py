"""Causally aligned assembly of descriptive feature layers."""

from dataclasses import dataclass

import pandas as pd

from .candlestick_patterns import detect_candlestick_patterns
from .chart_patterns import detect_double_top_bottom
from .structure_features import confirmed_market_structure
from .support_resistance import confirmed_swing_zones


EVENT_COLUMNS = [
    "event_id",
    "feature_layer",
    "event_type",
    "event_time",
    "available_at",
    "pivot_time",
    "formation_time",
    "payload",
]
ZONE_STATE_COLUMNS = [
    "timestamp",
    "available_at",
    "zone_id",
    "zone_type",
    "lower_bound",
    "upper_bound",
    "pivot_time",
    "created_at",
    "state",
    "touch_count",
]
_LAYER_ORDER = {"structure": 0, "candlestick": 1, "chart_pattern": 2, "zone": 3}


@dataclass(frozen=True)
class FeatureDataset:
    """Separate candle-aligned values, event records, and zone snapshots."""

    candle_features: pd.DataFrame
    events: pd.DataFrame
    zone_states: pd.DataFrame


def assemble_feature_dataset(
    candles: pd.DataFrame,
    *,
    timeframe: str,
    left_bars: int,
    right_bars: int,
    zone_width_fraction: float,
    price_tolerance_fraction: float,
    min_separation_bars: int,
    max_separation_bars: int,
) -> FeatureDataset:
    """Assemble existing descriptive APIs without propagating future events.

    ``candle_features`` remains one row per input candle. ``events`` is a
    long-form ledger with an explicit candle-level time contract:

    * ``event_time`` is the open timestamp of the candle anchoring the event.
      For swing structure and zone lifecycle rows this is the confirmation or
      lifecycle candle, not the earlier pivot candle. For chart shapes it is
      the formation candle.
    * ``available_at`` is when the required candle information is complete:
      that candle's close for single-candle and lifecycle events, or the
      confirmation candle's close for swing-confirmed shapes.
    * ``pivot_time`` identifies the originating swing candle where relevant.
    * ``formation_time`` identifies candlestick/chart geometry only; it is
      null for swing-structure and zone-lifecycle events.

    OHLC lifecycle events have candle-level precision only; this API does not
    infer an intrabar touch/break time. The original layer output is retained
    in ``payload``. ``zone_states`` has a row for each observed close and each
    zone already created by then. Broken zones remain in later snapshots.
    With C observed candles and Z accumulated zones, snapshot rows are
    O(C*Z); at most two zones can be created per candle, so the worst case is
    O(C**2). Missing candles are not synthesized.
    """
    structure = confirmed_market_structure(
        candles,
        timeframe=timeframe,
        left_bars=left_bars,
        right_bars=right_bars,
    )
    candle_features = structure.copy()
    candle_features.insert(0, "timestamp", pd.to_datetime(candles["timestamp"], utc=True))

    candle_events = detect_candlestick_patterns(candles, timeframe=timeframe)
    chart_events = detect_double_top_bottom(
        candles,
        timeframe=timeframe,
        left_bars=left_bars,
        right_bars=right_bars,
        price_tolerance_fraction=price_tolerance_fraction,
        min_separation_bars=min_separation_bars,
        max_separation_bars=max_separation_bars,
    )
    zone_events = confirmed_swing_zones(
        candles,
        timeframe=timeframe,
        left_bars=left_bars,
        right_bars=right_bars,
        zone_width_fraction=zone_width_fraction,
    )

    opens = pd.to_datetime(candles["timestamp"], utc=True).reset_index(drop=True)
    available = pd.to_datetime(candles["available_at"], utc=True).reset_index(drop=True)
    open_by_close = dict(zip(available.tolist(), opens.tolist()))
    records = []

    for pos in range(len(structure)):
        for side, value_column, time_column, label_column in (
            ("high", "swing_high_price", "swing_high_pivot_time", "swing_high_structure"),
            ("low", "swing_low_price", "swing_low_pivot_time", "swing_low_structure"),
        ):
            value = structure[value_column].iloc[pos]
            if pd.isna(value):
                continue
            pivot_time = structure[time_column].iloc[pos]
            available_at = structure["available_at"].iloc[pos]
            label = structure[label_column].iloc[pos]
            payload = structure.iloc[pos].to_dict()
            records.append({
                "event_id": f"structure:{side}:{pivot_time.isoformat()}:{available_at.isoformat()}",
                "feature_layer": "structure",
                "event_type": label,
                "event_time": opens.iloc[pos],
                "available_at": available_at,
                "pivot_time": pivot_time,
                "formation_time": pd.NaT,
                "payload": payload,
            })

    for _, row in candle_events.iterrows():
        source_time = row["candle_time"]
        records.append({
            "event_id": f"candlestick:{row['pattern_id']}:{source_time.isoformat()}",
            "feature_layer": "candlestick",
            "event_type": row["pattern_id"],
            "event_time": source_time,
            "available_at": row["available_at"],
            "pivot_time": pd.NaT,
            "formation_time": source_time,
            "payload": row.to_dict(),
        })

    for _, row in chart_events.iterrows():
        records.append({
            "event_id": f"chart_pattern:{row['pattern_id']}",
            "feature_layer": "chart_pattern",
            "event_type": row["pattern_type"],
            "event_time": row["formation_time"],
            "available_at": row["available_at"],
            "pivot_time": row["second_pivot_time"],
            "formation_time": row["formation_time"],
            "payload": row.to_dict(),
        })

    for _, row in zone_events.iterrows():
        close_time = row["event_time"]
        source_time = open_by_close.get(close_time)
        if source_time is None:
            raise ValueError("Zone event availability does not match an input candle close")
        records.append({
            "event_id": f"zone:{row['zone_id']}:{row['event']}:{close_time.isoformat()}",
            "feature_layer": "zone",
            "event_type": row["event"],
            "event_time": source_time,
            "available_at": close_time,
            "pivot_time": row["pivot_time"],
            "formation_time": pd.NaT,
            "payload": row.to_dict(),
        })

    events = pd.DataFrame(records, columns=EVENT_COLUMNS)
    if not events.empty:
        if events["event_id"].duplicated().any():
            raise ValueError("Feature event identities must be unique")
        events["_layer_order"] = events["feature_layer"].map(_LAYER_ORDER)
        events = events.sort_values(
            ["available_at", "_layer_order", "event_id"], kind="stable"
        ).drop(columns="_layer_order").reset_index(drop=True)

    zone_records = []
    zone_updates = zone_events.sort_values(
        ["event_time", "zone_id", "event"], kind="stable"
    ) if not zone_events.empty else zone_events
    update_pos = 0
    zone_by_id = {}
    for pos, close_time in enumerate(available):
        while update_pos < len(zone_updates) and zone_updates.iloc[update_pos]["event_time"] <= close_time:
            update = zone_updates.iloc[update_pos]
            zone_by_id[update["zone_id"]] = update
            update_pos += 1
        for zone_id in sorted(zone_by_id):
            zone = zone_by_id[zone_id]
            zone_records.append({
                "timestamp": opens.iloc[pos],
                "available_at": close_time,
                "zone_id": zone_id,
                "zone_type": zone["zone_type"],
                "lower_bound": zone["lower_bound"],
                "upper_bound": zone["upper_bound"],
                "pivot_time": zone["pivot_time"],
                "created_at": zone["created_at"],
                "state": zone["state"],
                "touch_count": zone["touch_count"],
            })

    zone_states = pd.DataFrame(zone_records, columns=ZONE_STATE_COLUMNS)
    return FeatureDataset(candle_features, events, zone_states)
