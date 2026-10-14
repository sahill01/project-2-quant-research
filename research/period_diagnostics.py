
from pathlib import Path

import numpy as np
import pandas as pd
from research.result_io import assert_paths_available, write_csv_batch_no_clobber


PROJECT_DIR = Path(__file__).resolve().parent.parent
BASELINE_DIR = PROJECT_DIR / "research" / "results" / "baselines"
OUTPUT_DIR = PROJECT_DIR / "research" / "results" / "diagnostics"

STRATEGIES = ["buy_hold", "ema_20_50", "donchian_20"]
INITIAL_CAPITAL = 50.0


def profit_factor(pnl):
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl < 0].sum()

    if gross_loss == 0:
        return np.inf if gross_profit > 0 else np.nan

    return gross_profit / gross_loss


def analyze_quarter(strategy):
    equity_path = BASELINE_DIR / f"{strategy}_equity.csv"
    trades_path = BASELINE_DIR / f"{strategy}_trades.csv"

    equity = pd.read_csv(equity_path)
    trades = pd.read_csv(trades_path)

    equity["timestamp"] = pd.to_datetime(
        equity["timestamp"], utc=True, errors="raise"
    )
    equity["mark_to_market_equity"] = pd.to_numeric(
        equity["mark_to_market_equity"], errors="raise"
    )

    trades["entry_time"] = pd.to_datetime(
        trades["entry_time"], utc=True, errors="raise"
    )
    trades["exit_time"] = pd.to_datetime(
        trades["exit_time"], utc=True, errors="raise"
    )
    trades["net_pnl"] = pd.to_numeric(trades["net_pnl"], errors="raise")
    trades["total_fees"] = pd.to_numeric(
        trades["total_fees"], errors="raise"
    )

    # Use UTC calendar quarters. Attribute trade P&L and fees to
    # the quarter in which each trade closes.
    equity["quarter"] = equity["timestamp"].dt.to_period("Q").astype(str)
    trades["quarter"] = trades["exit_time"].dt.to_period("Q").astype(str)

    rows = []

    for quarter, period_equity in equity.groupby("quarter", sort=True):
        period_equity = period_equity.sort_values("timestamp")
        values = period_equity["mark_to_market_equity"]

        start_equity = (
            float(equity.loc[
                equity["timestamp"] < period_equity["timestamp"].iloc[0],
                "mark_to_market_equity",
            ].iloc[-1])
            if (equity["timestamp"] < period_equity["timestamp"].iloc[0]).any()
            else INITIAL_CAPITAL
        )

        end_equity = float(values.iloc[-1])
        period_return_pct = (
            (end_equity / start_equity) - 1
        ) * 100 if start_equity != 0 else np.nan

        # Drawdown relative to the equity peak entering this quarter.
        previous = equity.loc[
            equity["timestamp"] < period_equity["timestamp"].iloc[0],
            "mark_to_market_equity",
        ]
        prior_peak = (
            float(previous.cummax().iloc[-1])
            if not previous.empty
            else float(values.iloc[0])
        )

        running_peak = pd.concat(
            [pd.Series([prior_peak]), values.reset_index(drop=True)],
            ignore_index=True,
        ).cummax()

        period_values = values.reset_index(drop=True)
        period_drawdown = period_values.to_numpy() / running_peak.iloc[1:].to_numpy() - 1
        max_drawdown_pct = float(np.min(period_drawdown)) * 100

        quarter_trades = trades[trades["quarter"] == quarter]
        pnl = quarter_trades["net_pnl"]

        rows.append({
            "strategy": strategy,
            "quarter": quarter,
            "start_equity": start_equity,
            "end_equity": end_equity,
            "return_pct": period_return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "trades_closed": len(quarter_trades),
            "win_rate_pct": (
                (pnl > 0).mean() * 100 if len(pnl) else np.nan
            ),
            "profit_factor": profit_factor(pnl),
            "net_pnl_closed_trades": float(pnl.sum()),
            "fees_on_closed_trades": float(
                quarter_trades["total_fees"].sum()
            ),
        })

    return rows


def main():
    output_path = OUTPUT_DIR / "quarterly_diagnostics.csv"
    assert_paths_available([output_path])
    all_rows = []

    for strategy in STRATEGIES:
        equity_path = BASELINE_DIR / f"{strategy}_equity.csv"
        trades_path = BASELINE_DIR / f"{strategy}_trades.csv"

        if not equity_path.exists() or not trades_path.exists():
            raise FileNotFoundError(
                f"Missing baseline CSVs for {strategy}"
            )

        all_rows.extend(analyze_quarter(strategy))

    report = pd.DataFrame(all_rows)

    write_csv_batch_no_clobber([(report, output_path)])

    print("\n" + "=" * 88)
    print("PROJECT 2 — QUARTERLY DIAGNOSTICS (UTC)")
    print("=" * 88)
    print(report.round(3).to_string(index=False))
    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
