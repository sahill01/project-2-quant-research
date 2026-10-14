"""Run fixed fee/slippage sensitivity cases for saved 4h baseline strategies.

Strategy signals, allocation, execution timing and backtester are unchanged.
Each case writes summary metrics only to a separate no-clobber output folder.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
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


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"
BASELINE_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_baselines"
OUTPUT_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_cost_sensitivity_v1"
ASSETS = ("BTCUSD", "ETHUSD", "SOLUSD")
TIMEFRAME = "4h"
ALLOCATION_FRACTION = 0.95
STRATEGIES = ("buy_hold", "ema_20_50", "donchian_20")
SUMMARY_NAME = "cross_asset_cost_sensitivity.csv"
MANIFEST_NAME = "cost_sensitivity_manifest.json"
TOLERANCE = 1e-7


def cost_scenarios(base_fee: float, base_slippage: float) -> tuple[dict, ...]:
    """Return fixed diagnostic scenarios, not candidate strategy settings."""
    if not all(np.isfinite(value) and value >= 0 for value in (base_fee, base_slippage)):
        raise ValueError("Base fee and slippage must be finite and non-negative")
    return (
        {"scenario": "zero_cost", "fee_rate": 0.0, "slippage_pct": 0.0},
        {"scenario": "configured", "fee_rate": base_fee, "slippage_pct": base_slippage},
        {"scenario": "double_fee", "fee_rate": 2 * base_fee, "slippage_pct": base_slippage},
        {"scenario": "double_slippage", "fee_rate": base_fee, "slippage_pct": 2 * base_slippage},
        {"scenario": "double_both", "fee_rate": 2 * base_fee, "slippage_pct": 2 * base_slippage},
    )


def max_drawdown_pct(values: pd.Series, initial_capital: float) -> float:
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    if numeric.empty or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Cannot calculate drawdown from empty/non-finite equity")
    running_peak = pd.concat(
        [pd.Series([initial_capital]), numeric.reset_index(drop=True)],
        ignore_index=True,
    ).cummax().iloc[1:].reset_index(drop=True)
    return float((numeric.reset_index(drop=True) / running_peak - 1).min() * 100)


def signals_for(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "buy_hold": buy_and_hold_signal(frame),
        "ema_20_50": ema_crossover_signal(frame, fast=20, slow=50),
        "donchian_20": donchian_breakout_signal(frame, period=20),
    }


def evaluate_case(
    frame: pd.DataFrame,
    signal: pd.Series,
    scenario: dict,
    *,
    asset: str,
    strategy: str,
) -> dict:
    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        fee_rate=float(scenario["fee_rate"]),
        slippage_pct=float(scenario["slippage_pct"]),
        allocation_fraction=ALLOCATION_FRACTION,
    )
    equity, trades = run_backtest(frame, signal, config)
    for column in (
        "realized_equity", "mark_to_market_equity", "net_liquidation_equity"
    ):
        values = pd.to_numeric(equity[column], errors="raise").to_numpy(float)
        if not np.isfinite(values).all():
            raise ValueError(f"{asset}/{strategy}/{scenario['scenario']}: non-finite {column}")
    if int(equity["position"].iloc[-1]) != 0:
        raise ValueError(f"{asset}/{strategy}/{scenario['scenario']}: final position is open")
    if not np.allclose(
        equity.iloc[-1][["mark_to_market_equity", "net_liquidation_equity"]].to_numpy(float),
        float(equity.iloc[-1]["realized_equity"]),
        atol=TOLERANCE,
        rtol=0,
    ):
        raise ValueError(f"{asset}/{strategy}/{scenario['scenario']}: final equity does not reconcile")

    metrics = summarize(equity, trades, INITIAL_CAPITAL)
    metrics.update({
        "asset": asset,
        "strategy": strategy,
        "scenario": scenario["scenario"],
        "timeframe": TIMEFRAME,
        "candles": len(frame),
        "first_available_at": frame["available_at"].iloc[0],
        "last_available_at": frame["available_at"].iloc[-1],
        "fee_rate": config.fee_rate,
        "slippage_pct": config.slippage_pct,
        "allocation_fraction": config.allocation_fraction,
        "total_fees": float(trades["total_fees"].sum()) if not trades.empty else 0.0,
        "time_in_market_pct": float((equity["position"] != 0).mean() * 100),
        "max_drawdown_net_liquidation_pct": max_drawdown_pct(
            equity["net_liquidation_equity"], INITIAL_CAPITAL
        ),
        "final_realized_equity": float(equity["realized_equity"].iloc[-1]),
    })
    return metrics


def load_and_validate_market() -> dict[str, pd.DataFrame]:
    data = {}
    reference = None
    expected_step = pd.Timedelta(hours=4)
    expected_rows = DAYS_BACK * 24 // 4
    for asset in ASSETS:
        path = default_dataset_path(DATA_DIR, asset, TIMEFRAME, DAYS_BACK)
        frame = load_ohlcv(path, TIMEFRAME)
        if len(frame) != expected_rows:
            raise ValueError(f"{path}: expected {expected_rows} rows, got {len(frame)}")
        if not frame["timestamp"].diff().dropna().eq(expected_step).all():
            raise ValueError(f"{path}: missing/irregular 4h timestamps")
        if reference is None:
            reference = frame["timestamp"].reset_index(drop=True)
        elif not frame["timestamp"].reset_index(drop=True).equals(reference):
            raise ValueError(f"{path}: timestamp range differs from other assets")
        data[asset] = frame
    return data


def validate_configured_cost_case(summary: pd.DataFrame, baseline: pd.DataFrame) -> None:
    configured = summary.loc[summary["scenario"] == "configured"]
    if len(configured) != len(ASSETS) * len(STRATEGIES):
        raise ValueError("Configured cost scenario is missing combinations")
    for _, row in configured.iterrows():
        matches = baseline.loc[
            (baseline["asset"] == row["asset"])
            & (baseline["strategy"] == row["strategy"])
        ]
        if len(matches) != 1:
            raise ValueError(f"Missing/duplicate saved baseline for {row['asset']}/{row['strategy']}")
        original = matches.iloc[0]
        for column in (
            "final_equity", "total_return_pct", "max_drawdown_pct",
            "trades", "total_fees", "max_drawdown_net_liquidation_pct",
        ):
            if not np.isclose(float(row[column]), float(original[column]), atol=TOLERANCE, rtol=0):
                raise ValueError(
                    f"Configured case mismatch for {row['asset']}/{row['strategy']} "
                    f"metric {column}: {row[column]} != {original[column]}"
                )


def run_analysis() -> tuple[pd.DataFrame, dict[str, str]]:
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"Refusing to overwrite cost-sensitivity output: {OUTPUT_DIR}")
    baseline_path = BASELINE_DIR / "cross_asset_summary.csv"
    if not baseline_path.is_file():
        raise FileNotFoundError(f"Missing saved baseline summary: {baseline_path}")

    market_data = load_and_validate_market()
    baseline = pd.read_csv(baseline_path)
    cases = cost_scenarios(EFFECTIVE_TAKER_FEE, SLIPPAGE_PCT)
    rows = []
    for asset, frame in market_data.items():
        for strategy, signal in signals_for(frame).items():
            for scenario in cases:
                rows.append(evaluate_case(
                    frame, signal, scenario, asset=asset, strategy=strategy
                ))
    summary = pd.DataFrame(rows).sort_values(
        ["asset", "strategy", "scenario"]
    ).reset_index(drop=True)
    if len(summary) != len(ASSETS) * len(STRATEGIES) * len(cases):
        raise ValueError("Unexpected number of sensitivity cases")
    validate_configured_cost_case(summary, baseline)

    input_paths = {
        f"data/{asset}_4h": default_dataset_path(DATA_DIR, asset, TIMEFRAME, DAYS_BACK)
        for asset in ASSETS
    }
    input_paths["saved_cross_asset_summary"] = baseline_path
    hashes = {
        key: sha256(path.read_bytes()).hexdigest()
        for key, path in sorted(input_paths.items())
    }
    return summary, hashes


def main() -> None:
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"Refusing to overwrite cost-sensitivity output: {OUTPUT_DIR}")
    summary, input_hashes = run_analysis()
    output_paths = (OUTPUT_DIR / SUMMARY_NAME, OUTPUT_DIR / MANIFEST_NAME)
    existing = [str(path) for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite files: {existing}")

    source_paths = {
        "run_cross_asset_cost_sensitivity.py": Path(__file__),
        "backtester.py": Path(__file__).with_name("backtester.py"),
        "data_loader.py": Path(__file__).with_name("data_loader.py"),
        "strategies.py": Path(__file__).with_name("strategies.py"),
        "config.py": PROJECT_ROOT / "config.py",
    }
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "cost_sensitivity_descriptive_only",
        "assets": list(ASSETS),
        "strategies": list(STRATEGIES),
        "timeframe": TIMEFRAME,
        "initial_capital": INITIAL_CAPITAL,
        "allocation_fraction": ALLOCATION_FRACTION,
        "scenarios": list(cost_scenarios(EFFECTIVE_TAKER_FEE, SLIPPAGE_PCT)),
        "assumptions": [
            "Strategy signals and parameters are unchanged.",
            "Only fee rate and slippage are varied by the fixed scenarios.",
            "The existing backtester is used; cost changes can affect future equity-based quantity through existing sizing behavior.",
            "The configured scenario must reconcile to the saved cross-asset summary before writing.",
            "No strategy is selected and no predictive or future-profitability claim is made.",
        ],
        "input_sha256": input_hashes,
        "implementation_sha256": {
            name: sha256(path.read_bytes()).hexdigest()
            for name, path in sorted(source_paths.items())
        },
        "outputs": [SUMMARY_NAME],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    summary.to_csv(OUTPUT_DIR / SUMMARY_NAME, index=False)
    (OUTPUT_DIR / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(summary)} cases to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
