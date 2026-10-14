
from pathlib import Path

import numpy as np
import pandas as pd
from research.result_io import assert_paths_available, write_csv_batch_no_clobber


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent.parent
BASELINE_DIR = PROJECT_DIR / "research" / "results" / "baselines"
OUTPUT_DIR = PROJECT_DIR / "research" / "results" / "diagnostics"

STRATEGIES = [
    "buy_hold",
    "ema_20_50",
    "donchian_20",
]

INITIAL_CAPITAL = 50.00


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def safe_divide(numerator, denominator):
    if denominator == 0 or pd.isna(denominator):
        return np.nan
    return numerator / denominator


def profit_factor(pnl):
    winners = pnl[pnl > 0].sum()
    losers = abs(pnl[pnl < 0].sum())

    if losers == 0:
        return np.inf if winners > 0 else np.nan

    return winners / losers


def max_streak(pnl, winning=True):
    condition = pnl > 0 if winning else pnl < 0
    best = current = 0

    for is_match in condition:
        if is_match:
            current += 1
            best = max(best, current)
        else:
            current = 0

    return best


def equity_metrics(equity_path):
    path = pd.read_csv(equity_path)

    if path.empty:
        return {}

    equity = pd.to_numeric(
        path["mark_to_market_equity"], errors="raise"
    )

    if not np.isfinite(equity).all():
        raise ValueError(f"Invalid equity values in {equity_path}")

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0

    final_equity = float(equity.iloc[-1])

    return {
        "final_equity": final_equity,
        "equity_return_pct": (
            final_equity / INITIAL_CAPITAL - 1
        ) * 100,
        "max_drawdown_pct": float(drawdown.min()) * 100,
    }


# --------------------------------------------------
# TRADE-LEVEL DIAGNOSTICS
# --------------------------------------------------

def analyze_trades(strategy, trades_path, equity_path):
    trades = pd.read_csv(trades_path)

    required = {
        "entry_time", "exit_time", "side",
        "entry_price", "exit_price", "qty",
        "entry_notional", "pnl_before_fees",
        "entry_fee", "exit_fee", "total_fees", "net_pnl",
    }

    missing = required - set(trades.columns)

    if missing:
        raise ValueError(
            f"{strategy}: missing trade columns: {sorted(missing)}"
        )

    if trades.empty:
        raise ValueError(f"{strategy}: no trades found")

    numeric_columns = [
        "entry_price", "exit_price", "qty", "entry_notional",
        "pnl_before_fees", "entry_fee", "exit_fee",
        "total_fees", "net_pnl",
    ]

    for column in numeric_columns:
        trades[column] = pd.to_numeric(
            trades[column], errors="raise"
        )

    if not np.isfinite(trades[numeric_columns].to_numpy()).all():
        raise ValueError(f"{strategy}: non-finite trade values")

    trades["entry_time"] = pd.to_datetime(
        trades["entry_time"], utc=True, errors="raise"
    )
    trades["exit_time"] = pd.to_datetime(
        trades["exit_time"], utc=True, errors="raise"
    )

    if (trades["exit_time"] < trades["entry_time"]).any():
        raise ValueError(f"{strategy}: exit before entry")

    if (trades["qty"] < 0).any():
        raise ValueError(f"{strategy}: negative quantity found")

    invalid_sides = ~trades["side"].isin(["LONG", "SHORT"])
    if invalid_sides.any():
        raise ValueError(f"{strategy}: invalid trade side")

    # Reconcile the trade ledger before trusting its metrics.
    fee_difference = (
        trades["entry_fee"] + trades["exit_fee"]
        - trades["total_fees"]
    ).abs()

    pnl_difference = (
        trades["pnl_before_fees"]
        - trades["total_fees"]
        - trades["net_pnl"]
    ).abs()

    if fee_difference.max() > 1e-7:
        raise ValueError(f"{strategy}: fee accounting mismatch")

    if pnl_difference.max() > 1e-6:
        raise ValueError(f"{strategy}: net P&L accounting mismatch")

    trades = trades.sort_values(
        ["exit_time", "entry_time"]
    ).reset_index(drop=True)

    pnl = trades["net_pnl"]
    winners = pnl[pnl > 0]
    losers = pnl[pnl < 0]
    flat = pnl[pnl == 0]

    gross_pnl = float(trades["pnl_before_fees"].sum())
    total_fees = float(trades["total_fees"].sum())
    net_pnl = float(pnl.sum())

    result = {
        "strategy": strategy,
        "trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "breakeven_trades": len(flat),
        "win_rate_pct": len(winners) / len(trades) * 100,
        "gross_pnl_before_fees": gross_pnl,
        "total_fees": total_fees,
        "net_pnl": net_pnl,
        "avg_trade_net_pnl": float(pnl.mean()),
        "median_trade_net_pnl": float(pnl.median()),
        "avg_winner": float(winners.mean()) if len(winners) else np.nan,
        "median_winner": float(winners.median()) if len(winners) else np.nan,
        "avg_loser": float(losers.mean()) if len(losers) else np.nan,
        "median_loser": float(losers.median()) if len(losers) else np.nan,
        "largest_winner": float(winners.max()) if len(winners) else np.nan,
        "largest_loser": float(losers.min()) if len(losers) else np.nan,
        "profit_factor": profit_factor(pnl),
        "max_consecutive_wins": max_streak(pnl, winning=True),
        "max_consecutive_losses": max_streak(pnl, winning=False),
        "fees_pct_initial_capital": total_fees / INITIAL_CAPITAL * 100,
        "entry_notional_sum": float(trades["entry_notional"].sum()),
        "turnover_notional": float(
            trades["entry_notional"].sum()
            + (trades["exit_price"] * trades["qty"]).abs().sum()
        ),
        "fees_per_trade": total_fees / len(trades),
        "duration_median_hours": float(
            (trades["exit_time"] - trades["entry_time"])
            .dt.total_seconds().median() / 3600
        ),
        "duration_mean_hours": float(
            (trades["exit_time"] - trades["entry_time"])
            .dt.total_seconds().mean() / 3600
        ),
    }

    result.update(equity_metrics(equity_path))

    # Side-by-side long and short results.
    for side in ["LONG", "SHORT"]:
        side_trades = trades[trades["side"] == side]
        side_pnl = side_trades["net_pnl"]
        side_winners = side_pnl[side_pnl > 0]

        result[f"{side.lower()}_trades"] = len(side_trades)
        result[f"{side.lower()}_net_pnl"] = float(side_pnl.sum())
        result[f"{side.lower()}_win_rate_pct"] = (
            len(side_winners) / len(side_trades) * 100
            if len(side_trades) else np.nan
        )
        result[f"{side.lower()}_profit_factor"] = (
            profit_factor(side_pnl) if len(side_trades) else np.nan
        )

    # Trade duration buckets.
    duration_days = (
        trades["exit_time"] - trades["entry_time"]
    ).dt.total_seconds() / 86400

    duration_buckets = pd.cut(
        duration_days,
        bins=[-np.inf, 1, 3, 7, 14, 30, np.inf],
        labels=["<1d", "1-3d", "3-7d", "7-14d", "14-30d", "30d+"],
        right=False,
    )

    duration_report = (
        trades.assign(duration_bucket=duration_buckets)
        .groupby("duration_bucket", observed=False)
        .agg(
            trades=("net_pnl", "size"),
            net_pnl=("net_pnl", "sum"),
            win_rate_pct=("net_pnl", lambda x: (x > 0).mean() * 100),
        )
        .reset_index()
    )
    duration_report.insert(0, "strategy", strategy)

    # Profit concentration: top winners relative to total net P&L.
    # Values can exceed 100% when losing trades offset the winners.
    positive_trades = winners.sort_values(ascending=False)
    concentration_rows = []

    for n in [1, 3, 5, 10]:
        top_pnl = float(positive_trades.head(n).sum())

        concentration_rows.append({
            "strategy": strategy,
            "top_n": n,
            "top_winners_pnl": top_pnl,
            "total_net_pnl": net_pnl,
            "pct_of_total_net_pnl": (
                top_pnl / net_pnl * 100 if net_pnl > 0 else np.nan
            ),
            "pct_of_all_winning_pnl": (
                top_pnl / winners.sum() * 100
                if len(winners) and winners.sum() > 0 else np.nan
            ),
        })

    # Preserve a per-trade diagnostic file for deeper investigation.
    trades["duration_hours"] = (
        trades["exit_time"] - trades["entry_time"]
    ).dt.total_seconds() / 3600

    write_csv_batch_no_clobber([(
        trades, OUTPUT_DIR / f"{strategy}_trade_diagnostics.csv"
    )])

    return result, concentration_rows, duration_report


# --------------------------------------------------
# RUN ALL BASELINES
# --------------------------------------------------

def main():
    assert_paths_available([
        *(OUTPUT_DIR / f"{strategy}_trade_diagnostics.csv" for strategy in STRATEGIES),
        OUTPUT_DIR / "diagnostic_summary.csv",
        OUTPUT_DIR / "profit_concentration.csv",
        OUTPUT_DIR / "trade_duration.csv",
    ])

    summaries = []
    concentration = []
    durations = []

    for strategy in STRATEGIES:
        trades_path = BASELINE_DIR / f"{strategy}_trades.csv"
        equity_path = BASELINE_DIR / f"{strategy}_equity.csv"

        if not trades_path.exists() or not equity_path.exists():
            raise FileNotFoundError(
                f"Missing baseline files for {strategy}"
            )

        summary, concentration_rows, duration_report = analyze_trades(
            strategy, trades_path, equity_path
        )

        summaries.append(summary)
        concentration.extend(concentration_rows)
        durations.append(duration_report)

    summary_df = pd.DataFrame(summaries)
    concentration_df = pd.DataFrame(concentration)
    duration_df = pd.concat(durations, ignore_index=True)

    write_csv_batch_no_clobber([
        (summary_df, OUTPUT_DIR / "diagnostic_summary.csv"),
        (concentration_df, OUTPUT_DIR / "profit_concentration.csv"),
        (duration_df, OUTPUT_DIR / "trade_duration.csv"),
    ])

    print("\n" + "=" * 76)
    print("PROJECT 2 — BASELINE DIAGNOSTICS")
    print("=" * 76)

    display_columns = [
        "strategy", "trades", "win_rate_pct",
        "gross_pnl_before_fees", "total_fees", "net_pnl",
        "profit_factor", "max_drawdown_pct",
        "long_net_pnl", "short_net_pnl",
    ]

    print(summary_df[display_columns].round(4).to_string(index=False))

    print("\nPROFIT CONCENTRATION")
    print(
        concentration_df[
            ["strategy", "top_n", "top_winners_pnl",
             "pct_of_total_net_pnl", "pct_of_all_winning_pnl"]
        ].round(2).to_string(index=False)
    )

    print("\nSaved reports to:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
