"""Compare saved mark-to-market and net-liquidation equity paths.

Run from the project root with:
    python -m research.compare_equity_valuations
"""

from pathlib import Path

import numpy as np
import pandas as pd
from research.result_io import assert_paths_available, write_csv_batch_no_clobber


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = PROJECT_ROOT / "research" / "results" / "baselines"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "research"
    / "results"
    / "diagnostics"
    / "equity_valuation_comparison.csv"
)
INITIAL_CAPITAL = 50.0
TOLERANCE = 1e-8
STRATEGIES = ["buy_hold", "ema_20_50", "donchian_20"]
VALUE_COLUMNS = [
    "realized_equity",
    "mark_to_market_equity",
    "net_liquidation_equity",
]


def calculate_metrics(strategy: str) -> dict:
    path = BASELINE_DIR / f"{strategy}_equity.csv"
    frame = pd.read_csv(path)

    required = {"timestamp", "available_at", "position", *VALUE_COLUMNS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{path}: no equity observations")

    for column in VALUE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    values = frame[VALUE_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{path}: non-finite equity values")

    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    available_at = pd.to_datetime(
        frame["available_at"], utc=True, errors="raise"
    )
    if len(timestamps) != len(available_at) or not timestamps.equals(available_at):
        raise ValueError(f"{path}: timestamp and available_at rows differ")
    if not timestamps.is_monotonic_increasing:
        raise ValueError(f"{path}: timestamps are not ordered")
    if frame["position"].isna().any():
        raise ValueError(f"{path}: missing position values")

    final = frame.iloc[-1]
    if int(final["position"]) != 0:
        raise ValueError(f"{path}: final position is not flat")
    final_mtm = float(final["mark_to_market_equity"])
    final_nle = float(final["net_liquidation_equity"])
    final_realized = float(final["realized_equity"])
    if not (
        abs(final_mtm - final_realized) <= TOLERANCE
        and abs(final_nle - final_realized) <= TOLERANCE
    ):
        raise ValueError(
            f"{path}: final valuation mismatch: mark={final_mtm}, "
            f"net_liquidation={final_nle}, realized={final_realized}"
        )

    open_mask = frame["position"] != 0
    if not open_mask.any():
        raise ValueError(f"{path}: no open-position observations")

    def equity_stats(column: str) -> tuple[float, float, float, float]:
        series = frame[column].astype(float)
        peaks = pd.concat(
            [pd.Series([INITIAL_CAPITAL]), series.reset_index(drop=True)],
            ignore_index=True,
        ).cummax().iloc[1:].reset_index(drop=True)
        drawdown_dollars = peaks - series.reset_index(drop=True)
        drawdown_pct = (
            series.reset_index(drop=True) / peaks - 1.0
        ) * 100.0
        final_equity = float(series.iloc[-1])
        total_return_pct = (final_equity / INITIAL_CAPITAL - 1.0) * 100.0
        return (
            final_equity,
            total_return_pct,
            float(drawdown_pct.min()),
            float(drawdown_dollars.max()),
        )

    mtm_stats = equity_stats("mark_to_market_equity")
    nle_stats = equity_stats("net_liquidation_equity")
    if abs(mtm_stats[0] - nle_stats[0]) > TOLERANCE:
        raise ValueError(
            f"{path}: final equity differs between series: "
            f"{mtm_stats[0]} vs {nle_stats[0]}"
        )
    if abs(mtm_stats[1] - nle_stats[1]) > TOLERANCE:
        raise ValueError(f"{path}: total returns differ between series")

    discount = (
        frame.loc[open_mask, "mark_to_market_equity"]
        - frame.loc[open_mask, "net_liquidation_equity"]
    )
    return {
        "strategy": strategy,
        "observations": len(frame),
        "open_observations": int(open_mask.sum()),
        "final_equity_mark_to_market": mtm_stats[0],
        "final_equity_net_liquidation": nle_stats[0],
        "total_return_pct_mark_to_market": mtm_stats[1],
        "total_return_pct_net_liquidation": nle_stats[1],
        "max_drawdown_pct_mark_to_market": mtm_stats[2],
        "max_drawdown_pct_net_liquidation": nle_stats[2],
        "max_drawdown_dollars_mark_to_market": mtm_stats[3],
        "max_drawdown_dollars_net_liquidation": nle_stats[3],
        "max_open_liquidation_discount": float(discount.max()),
        "average_open_liquidation_discount": float(discount.mean()),
        "median_open_liquidation_discount": float(discount.median()),
        "open_observations_discount_positive_pct": float(
            (discount > 0).mean() * 100.0
        ),
        "final_position": int(final["position"]),
        "final_realized_equity": final_realized,
    }


def main() -> None:
    assert_paths_available([OUTPUT_PATH])
    report = pd.DataFrame(
        [calculate_metrics(strategy) for strategy in STRATEGIES]
    )
    write_csv_batch_no_clobber([(report, OUTPUT_PATH)])

    display_columns = [
        "strategy",
        "final_equity_mark_to_market",
        "final_equity_net_liquidation",
        "total_return_pct_mark_to_market",
        "max_drawdown_pct_mark_to_market",
        "max_drawdown_pct_net_liquidation",
        "max_drawdown_dollars_mark_to_market",
        "max_drawdown_dollars_net_liquidation",
        "max_open_liquidation_discount",
        "average_open_liquidation_discount",
        "median_open_liquidation_discount",
        "open_observations_discount_positive_pct",
    ]
    print(report[display_columns].round(4).to_string(index=False))
    print(f"\nSaved comparison report: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
