"""Run unchanged baseline strategies across BTC, ETH, and SOL.

Run from the project root with:
    python -m research.run_cross_asset_baselines

All inputs are validated before any backtest runs. Output paths are isolated
from the BTC baseline and diagnostics directories, and existing targets are
never overwritten.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    DAYS_BACK,
    EFFECTIVE_TAKER_FEE,
    INITIAL_CAPITAL,
    SLIPPAGE_PCT,
)
from research.backtester import BacktestConfig, run_backtest, summarize
from research.data_loader import default_dataset_path, load_ohlcv
from research.strategies import (
    buy_and_hold_signal,
    donchian_breakout_signal,
    ema_crossover_signal,
)
from research.result_io import write_csv_batch_no_clobber


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_baselines"
BASELINE_DIR = PROJECT_ROOT / "research" / "results" / "baselines"
DIAGNOSTICS_DIR = PROJECT_ROOT / "research" / "results" / "diagnostics"
ASSETS = ("BTCUSD", "ETHUSD", "SOLUSD")
TIMEFRAME = "4h"
ALLOCATION_FRACTION = 0.95
STRATEGY_NAMES = ("buy_hold", "ema_20_50", "donchian_20")
TOLERANCE = 1e-8


def target_names() -> list[str]:
    names = [
        f"{asset}_{strategy}_{kind}.csv"
        for asset in ASSETS
        for strategy in STRATEGY_NAMES
        for kind in ("equity", "trades")
    ]
    names.append("cross_asset_summary.csv")
    return names


def validate_output_location() -> None:
    output = OUTPUT_DIR.resolve()
    protected = {BASELINE_DIR.resolve(), DIAGNOSTICS_DIR.resolve()}
    if output in protected or any(parent in protected for parent in output.parents):
        raise ValueError(f"Unsafe output directory: {output}")
    existing = [name for name in target_names() if (OUTPUT_DIR / name).exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing cross-asset outputs: "
            + ", ".join(existing)
        )


def load_and_validate_datasets() -> dict[str, pd.DataFrame]:
    datasets = {}
    expected_delta = pd.Timedelta(hours=4)
    expected_count = DAYS_BACK * 24 // 4

    for asset in ASSETS:
        path = default_dataset_path(DATA_DIR, asset, TIMEFRAME, DAYS_BACK)
        frame = load_ohlcv(path, TIMEFRAME)
        if len(frame) != expected_count:
            raise ValueError(
                f"{path}: expected {expected_count} 4h candles for "
                f"{DAYS_BACK} days, found {len(frame)}"
            )
        steps = frame["timestamp"].diff().dropna()
        if not steps.eq(expected_delta).all():
            raise ValueError(f"{path}: timestamps contain missing/irregular 4h bars")
        observed_duration = (
            frame["available_at"].iloc[-1] - frame["timestamp"].iloc[0]
        )
        if observed_duration != pd.Timedelta(days=DAYS_BACK):
            raise ValueError(
                f"{path}: observed range is {observed_duration}, expected "
                f"{DAYS_BACK} days"
            )
        datasets[asset] = frame

    reference = datasets[ASSETS[0]]["timestamp"].reset_index(drop=True)
    for asset in ASSETS[1:]:
        timestamps = datasets[asset]["timestamp"].reset_index(drop=True)
        if not timestamps.equals(reference):
            raise ValueError(
                f"{asset}: candle timestamps differ from {ASSETS[0]}"
            )
    return datasets


def max_drawdown_pct(values: pd.Series, initial_capital: float) -> float:
    values = pd.to_numeric(values, errors="raise").astype(float)
    if values.empty or not np.isfinite(values.to_numpy()).all():
        raise ValueError("Cannot calculate drawdown from empty/non-finite equity")
    running_peak = pd.concat(
        [pd.Series([initial_capital]), values.reset_index(drop=True)],
        ignore_index=True,
    ).cummax().iloc[1:].reset_index(drop=True)
    drawdown = values.reset_index(drop=True) / running_peak - 1.0
    return float(drawdown.min() * 100.0)


def signals_for(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "buy_hold": buy_and_hold_signal(frame),
        "ema_20_50": ema_crossover_signal(frame, fast=20, slow=50),
        "donchian_20": donchian_breakout_signal(frame, period=20),
    }


def run_experiment(datasets: dict[str, pd.DataFrame]):
    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        fee_rate=EFFECTIVE_TAKER_FEE,
        slippage_pct=SLIPPAGE_PCT,
        allocation_fraction=ALLOCATION_FRACTION,
    )
    outputs = {}
    summaries = []

    for asset, frame in datasets.items():
        for strategy, signal in signals_for(frame).items():
            equity, trades = run_backtest(frame, signal, config)
            metrics = summarize(equity, trades, config.initial_capital)
            metrics.update({
                "asset": asset,
                "strategy": strategy,
                "timeframe": TIMEFRAME,
                "history_days": DAYS_BACK,
                "first_candle_timestamp": frame["timestamp"].iloc[0],
                "last_candle_timestamp": frame["timestamp"].iloc[-1],
                "last_available_at": frame["available_at"].iloc[-1],
                "candles": len(frame),
                "fee_rate": config.fee_rate,
                "slippage_pct": config.slippage_pct,
                "allocation_fraction": config.allocation_fraction,
                "total_fees": (
                    float(trades["total_fees"].sum())
                    if not trades.empty else 0.0
                ),
                "time_in_market_pct": float(
                    (equity["position"] != 0).mean() * 100
                ),
                "max_drawdown_net_liquidation_pct": max_drawdown_pct(
                    equity["net_liquidation_equity"],
                    config.initial_capital,
                ),
            })
            outputs[(asset, strategy)] = (equity, trades)
            summaries.append(metrics)
            print(
                f"Completed {asset} {strategy}: "
                f"{len(frame)} candles, {len(trades)} trades"
            )

    return outputs, pd.DataFrame(summaries)


def validate_outputs(outputs, summary: pd.DataFrame) -> None:
    if len(outputs) != len(ASSETS) * len(STRATEGY_NAMES):
        raise ValueError(f"Expected 9 combinations, found {len(outputs)}")
    if len(summary) != 9:
        raise ValueError(f"Expected 9 summary rows, found {len(summary)}")

    for (asset, strategy), (equity, trades) in outputs.items():
        for column in (
            "realized_equity",
            "mark_to_market_equity",
            "net_liquidation_equity",
        ):
            values = pd.to_numeric(equity[column], errors="raise").to_numpy(float)
            if not np.isfinite(values).all():
                raise ValueError(f"{asset} {strategy}: non-finite {column}")
        if int(equity["position"].iloc[-1]) != 0:
            raise ValueError(f"{asset} {strategy}: final position is not flat")
        final = equity.iloc[-1]
        if not (
            abs(final["realized_equity"] - final["mark_to_market_equity"]) <= TOLERANCE
            and abs(final["realized_equity"] - final["net_liquidation_equity"]) <= TOLERANCE
        ):
            raise ValueError(f"{asset} {strategy}: final equity values disagree")
        row = summary.loc[
            (summary["asset"] == asset) & (summary["strategy"] == strategy)
        ].iloc[0]
        if int(row["trades"]) != len(trades):
            raise ValueError(f"{asset} {strategy}: summary trade count mismatch")
        fees = float(trades["total_fees"].sum()) if not trades.empty else 0.0
        if abs(float(row["total_fees"]) - fees) > TOLERANCE:
            raise ValueError(f"{asset} {strategy}: summary fee mismatch")


def write_outputs(outputs, summary: pd.DataFrame) -> None:
    validate_output_location()
    csv_outputs = []
    for (asset, strategy), (equity, trades) in outputs.items():
        prefix = f"{asset}_{strategy}"
        csv_outputs.extend([
            (equity, OUTPUT_DIR / f"{prefix}_equity.csv"),
            (trades, OUTPUT_DIR / f"{prefix}_trades.csv"),
        ])
    csv_outputs.append((summary, OUTPUT_DIR / "cross_asset_summary.csv"))
    write_csv_batch_no_clobber(csv_outputs)

    expected_files = set(target_names())
    actual_files = {path.name for path in OUTPUT_DIR.glob("*.csv")}
    if actual_files != expected_files:
        raise ValueError(
            f"Output file set mismatch: missing={sorted(expected_files - actual_files)}, "
            f"unexpected={sorted(actual_files - expected_files)}"
        )

    for (asset, strategy), _ in outputs.items():
        prefix = f"{asset}_{strategy}"
        equity = pd.read_csv(OUTPUT_DIR / f"{prefix}_equity.csv")
        trades = pd.read_csv(OUTPUT_DIR / f"{prefix}_trades.csv")
        if len(equity) != int(
            summary.loc[
                (summary["asset"] == asset) & (summary["strategy"] == strategy),
                "candles",
            ].iloc[0]
        ):
            raise ValueError(f"{prefix}: saved equity row count mismatch")
        if int(equity["position"].iloc[-1]) != 0:
            raise ValueError(f"{prefix}: saved final position is not flat")
        if len(trades) != int(
            summary.loc[
                (summary["asset"] == asset) & (summary["strategy"] == strategy),
                "trades",
            ].iloc[0]
        ):
            raise ValueError(f"{prefix}: saved trade count mismatch")


def main() -> None:
    # Check overwrite safety before loading data or running any backtest.
    validate_output_location()
    datasets = load_and_validate_datasets()
    outputs, summary = run_experiment(datasets)
    validate_outputs(outputs, summary)
    write_outputs(outputs, summary)

    display = [
        "asset", "strategy", "final_equity", "total_return_pct",
        "max_drawdown_pct", "max_drawdown_net_liquidation_pct", "trades",
        "win_rate_pct", "profit_factor", "total_fees", "time_in_market_pct",
    ]
    print("\nCROSS-ASSET BASELINE SUMMARY")
    print(summary[display].round(4).to_string(index=False))
    print(f"\nSaved validated outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
