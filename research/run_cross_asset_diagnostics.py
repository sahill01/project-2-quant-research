"""Generate descriptive diagnostics from saved cross-asset backtest outputs.

This script reads existing results only; it does not rerun a backtest.
Run from the project root with:
    python -m research.run_cross_asset_diagnostics
"""

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_baselines"
OUTPUT_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_diagnostics_v2"
ASSETS = ("BTCUSD", "ETHUSD", "SOLUSD")
STRATEGIES = ("buy_hold", "ema_20_50", "donchian_20")
INITIAL_CAPITAL = 50.0
TOLERANCE = 1e-7
EQUITY_COLUMNS = ("mark_to_market_equity", "net_liquidation_equity")
OUTPUT_NAMES = (
    "cross_asset_trade_diagnostics.csv",
    "cross_asset_drawdown_episodes.csv",
    "cross_asset_quarterly_diagnostics.csv",
    "cross_asset_valuation_diagnostics.csv",
    "diagnostics_manifest.json",
)


def profit_factor(pnl: pd.Series) -> float:
    wins = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else float("nan")
    return wins / losses


def load_inputs():
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(f"Missing cross-asset outputs: {INPUT_DIR}")
    summary_path = INPUT_DIR / "cross_asset_summary.csv"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Missing summary: {summary_path}")
    summary = pd.read_csv(summary_path)
    if len(summary) != len(ASSETS) * len(STRATEGIES):
        raise ValueError(f"Expected 9 cross-asset summary rows, found {len(summary)}")

    data = {}
    source_paths = [summary_path]
    for asset in ASSETS:
        for strategy in STRATEGIES:
            prefix = f"{asset}_{strategy}"
            equity_path = INPUT_DIR / f"{prefix}_equity.csv"
            trades_path = INPUT_DIR / f"{prefix}_trades.csv"
            for path in (equity_path, trades_path):
                if not path.is_file():
                    raise FileNotFoundError(path)
                source_paths.append(path)

            equity = pd.read_csv(equity_path)
            trades = pd.read_csv(trades_path)
            required_equity = {
                "timestamp", "available_at", "position", "realized_equity",
                *EQUITY_COLUMNS,
            }
            missing = required_equity - set(equity.columns)
            if missing:
                raise ValueError(f"{equity_path}: missing {sorted(missing)}")
            equity["timestamp"] = pd.to_datetime(
                equity["timestamp"], utc=True, errors="raise"
            )
            for column in ("realized_equity", *EQUITY_COLUMNS):
                equity[column] = pd.to_numeric(equity[column], errors="raise")
            numeric = equity[["realized_equity", *EQUITY_COLUMNS]].to_numpy(float)
            if not np.isfinite(numeric).all():
                raise ValueError(f"{equity_path}: non-finite equity")
            if equity["timestamp"].duplicated().any() or not equity["timestamp"].is_monotonic_increasing:
                raise ValueError(f"{equity_path}: duplicate or unordered timestamps")
            if equity["position"].isna().any() or int(equity["position"].iloc[-1]) != 0:
                raise ValueError(f"{equity_path}: invalid/final open position")

            required_trades = {
                "entry_time", "exit_time", "side", "qty", "pnl_before_fees",
                "entry_fee", "exit_fee", "total_fees", "net_pnl",
            }
            missing = required_trades - set(trades.columns)
            if missing:
                raise ValueError(f"{trades_path}: missing {sorted(missing)}")
            for column in (
                "qty", "pnl_before_fees", "entry_fee", "exit_fee",
                "total_fees", "net_pnl",
            ):
                trades[column] = pd.to_numeric(trades[column], errors="raise")
            if not trades.empty:
                if not np.isfinite(trades[[
                    "qty", "pnl_before_fees", "entry_fee", "exit_fee",
                    "total_fees", "net_pnl",
                ]].to_numpy(float)).all():
                    raise ValueError(f"{trades_path}: non-finite ledger values")
                if not np.allclose(
                    trades["entry_fee"] + trades["exit_fee"],
                    trades["total_fees"], atol=TOLERANCE, rtol=0,
                ):
                    raise ValueError(f"{trades_path}: fee totals do not reconcile")
                if not np.allclose(
                    trades["pnl_before_fees"] - trades["total_fees"],
                    trades["net_pnl"], atol=TOLERANCE, rtol=0,
                ):
                    raise ValueError(f"{trades_path}: net P&L does not reconcile")

            last = equity.iloc[-1]
            if not all(
                abs(float(last[column]) - float(last["realized_equity"])) <= TOLERANCE
                for column in EQUITY_COLUMNS
            ):
                raise ValueError(f"{equity_path}: final equity mismatch")
            summary_row = summary.loc[
                (summary["asset"] == asset)
                & (summary["strategy"] == strategy)
            ]
            if len(summary_row) != 1:
                raise ValueError(f"{asset}/{strategy}: missing/duplicate summary row")
            if not np.allclose(
                float(summary_row.iloc[0]["final_equity"]),
                float(last["realized_equity"]), atol=TOLERANCE, rtol=0,
            ):
                raise ValueError(f"{asset}/{strategy}: summary final equity mismatch")

            trades["entry_time"] = pd.to_datetime(
                trades["entry_time"], utc=True, errors="raise"
            )
            trades["exit_time"] = pd.to_datetime(
                trades["exit_time"], utc=True, errors="raise"
            )
            data[(asset, strategy)] = (equity, trades)
    return data, summary, source_paths


def drawdown_episodes(asset, strategy, equity, column):
    values = equity[column].to_numpy(dtype=float)
    times = equity["timestamp"].tolist()
    peak_value = INITIAL_CAPITAL
    peak_time = times[0]
    active = None
    episodes = []

    def finish(recovery_time, recovered):
        trough_value = active["trough_equity"]
        episodes.append({
            "asset": asset,
            "strategy": strategy,
            "equity_series": column,
            "episode": len(episodes) + 1,
            "peak_time": active["peak_time"],
            "underwater_start": active["underwater_start"],
            "trough_time": active["trough_time"],
            "recovery_time": recovery_time,
            "peak_equity": active["peak_equity"],
            "trough_equity": trough_value,
            "drawdown_dollars": active["peak_equity"] - trough_value,
            "drawdown_pct": (trough_value / active["peak_equity"] - 1) * 100,
            "peak_to_trough_hours": (
                (active["trough_time"] - active["peak_time"]).total_seconds() / 3600
            ),
            "peak_to_recovery_hours": (
                (recovery_time - active["peak_time"]).total_seconds() / 3600
                if recovered else np.nan
            ),
            "underwater_duration_hours": (
                (recovery_time - active["underwater_start"]).total_seconds() / 3600
                if recovered
                else (times[-1] - active["underwater_start"]).total_seconds() / 3600
            ),
            "recovered": recovered,
        })

    for timestamp, value in zip(times, values):
        if active is None:
            if value >= peak_value:
                if value > peak_value:
                    peak_value = value
                    peak_time = timestamp
            else:
                active = {
                    "peak_equity": peak_value,
                    "peak_time": peak_time,
                    "underwater_start": timestamp,
                    "trough_time": timestamp,
                    "trough_equity": value,
                }
        else:
            if value < active["trough_equity"]:
                active["trough_time"] = timestamp
                active["trough_equity"] = value
            if value >= active["peak_equity"]:
                finish(timestamp, True)
                active = None
                peak_value = value
                peak_time = timestamp

    if active is not None:
        finish(pd.NaT, False)
    return episodes


def trade_diagnostics(data):
    rows = []
    for (asset, strategy), (_, trades) in data.items():
        if not trades.empty:
            duration = (
                trades["exit_time"] - trades["entry_time"]
            ).dt.total_seconds() / 3600
            trades = trades.assign(duration_hours=duration)
        else:
            trades = trades.assign(duration_hours=pd.Series(dtype=float))

        for side in ("LONG", "SHORT"):
            side_trades = trades.loc[trades["side"] == side]
            net = side_trades["net_pnl"]
            winners = net[net > 0].sort_values(ascending=False)
            winner_total = float(winners.sum())
            row = {
                "asset": asset,
                "strategy": strategy,
                "side": side,
                "trades": len(side_trades),
                "gross_pnl_before_fees": float(side_trades["pnl_before_fees"].sum()),
                "entry_fees": float(side_trades["entry_fee"].sum()),
                "exit_fees": float(side_trades["exit_fee"].sum()),
                "total_fees": float(side_trades["total_fees"].sum()),
                "net_pnl": float(net.sum()),
                "win_rate_pct": float((net > 0).mean() * 100) if len(net) else np.nan,
                "profit_factor": profit_factor(net) if len(net) else np.nan,
                "avg_trade_net_pnl": float(net.mean()) if len(net) else np.nan,
                "median_trade_net_pnl": float(net.median()) if len(net) else np.nan,
                "mean_duration_hours": float(side_trades["duration_hours"].mean()) if len(net) else np.nan,
                "median_duration_hours": float(side_trades["duration_hours"].median()) if len(net) else np.nan,
                "top_1_winner_pct_of_winning_pnl": float(winners.head(1).sum() / winner_total * 100) if winner_total else np.nan,
                "top_3_winners_pct_of_winning_pnl": float(winners.head(3).sum() / winner_total * 100) if winner_total else np.nan,
                "top_5_winners_pct_of_winning_pnl": float(winners.head(5).sum() / winner_total * 100) if winner_total else np.nan,
            }
            rows.append(row)
    return pd.DataFrame(rows)


def quarterly_diagnostics(data):
    rows = []
    for (asset, strategy), (equity, trades) in data.items():
        equity = equity.copy()
        equity["quarter"] = (
            equity["timestamp"].dt.tz_localize(None).dt.to_period("Q").astype(str)
        )
        if not trades.empty:
            trades = trades.copy()
            trades["quarter"] = (
                trades["exit_time"].dt.tz_localize(None).dt.to_period("Q").astype(str)
            )
        else:
            trades = trades.assign(quarter=pd.Series(dtype=str))

        previous_equity = {
            "mark_to_market_equity": INITIAL_CAPITAL,
            "net_liquidation_equity": INITIAL_CAPITAL,
        }
        running_peaks = dict(previous_equity)
        for quarter, period in equity.groupby("quarter", sort=True):
            series = period.set_index("timestamp")
            quarter_trades = trades.loc[trades["quarter"] == quarter]
            pnl = quarter_trades["net_pnl"]
            quarter_rows = {
                "asset": asset,
                "strategy": strategy,
                "quarter_utc": quarter,
                "start_equity_mark_to_market": previous_equity["mark_to_market_equity"],
                "start_equity_net_liquidation": previous_equity["net_liquidation_equity"],
                "end_equity_mark_to_market": float(series["mark_to_market_equity"].iloc[-1]),
                "end_equity_net_liquidation": float(series["net_liquidation_equity"].iloc[-1]),
                "return_mark_to_market_pct": np.nan,
                "return_net_liquidation_pct": np.nan,
                "max_drawdown_mark_to_market_pct": np.nan,
                "max_drawdown_net_liquidation_pct": np.nan,
                "closed_trades": len(quarter_trades),
                "closed_trade_net_pnl": float(pnl.sum()),
                "entry_fees_at_exit_quarter": float(quarter_trades["entry_fee"].sum()),
                "exit_fees_at_exit_quarter": float(quarter_trades["exit_fee"].sum()),
                "total_fees_at_exit_quarter": float(quarter_trades["total_fees"].sum()),
                "closed_trade_win_rate_pct": float((pnl > 0).mean() * 100) if len(pnl) else np.nan,
                "closed_trade_profit_factor": profit_factor(pnl) if len(pnl) else np.nan,
                "trade_attribution_note": "Closed-trade P&L and both trade fees are grouped by exit quarter; equity returns use account equity.",
            }
            for column, return_key, dd_key in (
                ("mark_to_market_equity", "return_mark_to_market_pct", "max_drawdown_mark_to_market_pct"),
                ("net_liquidation_equity", "return_net_liquidation_pct", "max_drawdown_net_liquidation_pct"),
            ):
                values = series[column].astype(float)
                previous_value = previous_equity[column]
                quarter_rows[return_key] = (
                    (float(values.iloc[-1]) / previous_value - 1) * 100
                    if previous_value else np.nan
                )
                peaks = pd.concat(
                    [pd.Series([running_peaks[column]]), values.reset_index(drop=True)],
                    ignore_index=True,
                ).cummax().iloc[1:].reset_index(drop=True)
                quarter_rows[dd_key] = float(
                    ((values.reset_index(drop=True) / peaks - 1).min()) * 100
                )
                running_peaks[column] = max(
                    running_peaks[column], float(values.max())
                )
                previous_equity[column] = float(values.iloc[-1])

            rows.append(quarter_rows)
    return pd.DataFrame(rows)


def valuation_diagnostics(data):
    rows = []
    for (asset, strategy), (equity, _) in data.items():
        open_rows = equity.loc[equity["position"] != 0]
        discount = (
            open_rows["mark_to_market_equity"]
            - open_rows["net_liquidation_equity"]
        )
        row = {
            "asset": asset,
            "strategy": strategy,
            "observations": len(equity),
            "open_observations": len(open_rows),
            "max_open_liquidation_discount": float(discount.max()) if len(discount) else np.nan,
            "mean_open_liquidation_discount": float(discount.mean()) if len(discount) else np.nan,
            "median_open_liquidation_discount": float(discount.median()) if len(discount) else np.nan,
            "positive_discount_observations_pct": float((discount > 0).mean() * 100) if len(discount) else np.nan,
        }
        for column in EQUITY_COLUMNS:
            series = equity[column].astype(float)
            peaks = pd.concat(
                [pd.Series([INITIAL_CAPITAL]), series.reset_index(drop=True)],
                ignore_index=True,
            ).cummax().iloc[1:].reset_index(drop=True)
            dd_pct = series.reset_index(drop=True) / peaks - 1.0
            dd_dollars = peaks - series.reset_index(drop=True)
            row[f"max_drawdown_pct_{column}"] = float(dd_pct.min() * 100)
            row[f"max_drawdown_dollars_{column}"] = float(dd_dollars.max())
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"Refusing to overwrite existing diagnostics: {OUTPUT_DIR}")
    data, _, source_paths = load_inputs()

    trades = trade_diagnostics(data)
    episodes = []
    for (asset, strategy), (equity, _) in data.items():
        for column in EQUITY_COLUMNS:
            episodes.extend(drawdown_episodes(asset, strategy, equity, column))
    drawdowns = pd.DataFrame(episodes)
    quarters = quarterly_diagnostics(data)
    valuations = valuation_diagnostics(data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    trades.to_csv(OUTPUT_DIR / OUTPUT_NAMES[0], index=False)
    drawdowns.to_csv(OUTPUT_DIR / OUTPUT_NAMES[1], index=False)
    quarters.to_csv(OUTPUT_DIR / OUTPUT_NAMES[2], index=False)
    valuations.to_csv(OUTPUT_DIR / OUTPUT_NAMES[3], index=False)
    manifest = {
        "description": "Version 2 descriptive diagnostics from saved 730-day cross-asset baseline outputs; no backtest rerun.",
        "initial_capital": INITIAL_CAPITAL,
        "assets": list(ASSETS),
        "strategies": list(STRATEGIES),
        "inputs": {
            str(path.relative_to(PROJECT_ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
        "quarterly_attribution": "Equity returns use account equity; closed-trade net P&L and all trade fees are grouped by exit quarter.",
        "drawdown_convention": "Running peak includes initial capital; one underwater episode spans peak loss through recovery, or ends unrecovered at final observation.",
        "limitations": [
            "Quarterly results use calendar quarters, not market regimes.",
            "Exit-quarter trade attribution places entry fees in the exit quarter for closed-trade reporting.",
            "These descriptive diagnostics do not establish predictive value or future profitability.",
        ],
    }
    (OUTPUT_DIR / OUTPUT_NAMES[4]).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    expected = set(OUTPUT_NAMES)
    actual = {path.name for path in OUTPUT_DIR.iterdir() if path.is_file()}
    if actual != expected:
        raise ValueError(f"Diagnostic output set mismatch: {actual ^ expected}")
    print(f"Wrote {len(actual)} diagnostic files to {OUTPUT_DIR}")
    print("Trade rows:", len(trades), "drawdown episodes:", len(drawdowns), "quarter rows:", len(quarters))


if __name__ == "__main__":
    main()
