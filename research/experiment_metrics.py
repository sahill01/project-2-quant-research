"""Period metrics for precomputed, availability-timestamped backtest ledgers.

Metrics use a continuous account: each window starts from the last observed
equity before its UTC start, and drawdown peaks are seeded with that value.
Closed-trade P&L is attributed by exit time; entry and exit fees are separately
counted at their respective execution times. This module does not load data,
open holdout partitions, execute strategies, or choose a strategy.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.experiment_protocol import TemporalSplit, TimeWindow
from research.experiment_protocol import (
    ExperimentConfig,
    PreregistrationApproval,
    _approval_record_fingerprint,
    _split_fingerprint,
    dataframe_fingerprint,
    validate_preregistration_approval,
)
from research.hypothesis_spec import HypothesisSpec


EQUITY_COLUMNS = (
    "realized_equity",
    "mark_to_market_equity",
    "net_liquidation_equity",
)


@dataclass(frozen=True)
class EvaluationProvenance:
    """Content binding for ledgers evaluated under one approved specification.

    This detects stale or substituted frames after the provenance record is
    made. It cannot prove that a caller originally derived those frames from
    the approved source files; that remains the caller's responsibility.
    """

    approval_sha256: str
    specification_sha256: str
    split_sha256: str
    equity_sha256: str
    trades_sha256: str
    timestamp_col: str


def create_evaluation_provenance(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    split: TemporalSplit,
    *,
    timestamp_col: str,
    config: ExperimentConfig,
    hypothesis: HypothesisSpec,
    approval: PreregistrationApproval,
) -> EvaluationProvenance:
    """Bind the supplied ledger contents to the currently approved spec."""
    validate_preregistration_approval(config, hypothesis, approval)
    split.validate()
    if _split_fingerprint(split, timestamp_col) != _split_fingerprint(config.split, timestamp_col):
        raise PermissionError("Evaluation windows do not match the approved configuration")
    return EvaluationProvenance(
        approval_sha256=_approval_record_fingerprint(approval),
        specification_sha256=approval.specification_sha256,
        split_sha256=_split_fingerprint(split, timestamp_col),
        equity_sha256=dataframe_fingerprint(equity),
        trades_sha256=dataframe_fingerprint(trades),
        timestamp_col=timestamp_col,
    )


def _validated_equity(equity: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
    required = {timestamp_col, "position", *EQUITY_COLUMNS}
    missing = required - set(equity.columns)
    if missing:
        raise ValueError(f"Equity data missing columns: {sorted(missing)}")
    frame = equity.copy()
    frame[timestamp_col] = pd.to_datetime(
        frame[timestamp_col], utc=True, errors="raise"
    )
    if frame[timestamp_col].isna().any() or frame[timestamp_col].duplicated().any():
        raise ValueError("Equity timestamps must be valid and unique")
    if not frame[timestamp_col].is_monotonic_increasing:
        raise ValueError("Equity timestamps must be ordered")
    for column in EQUITY_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    if not np.isfinite(frame[list(EQUITY_COLUMNS)].to_numpy()).all():
        raise ValueError("Equity values must be finite")
    if frame["position"].isna().any() or not frame["position"].isin((-1, 0, 1)).all():
        raise ValueError("Positions must be discrete values in {-1, 0, 1}")
    return frame


def _validated_trades(trades: pd.DataFrame) -> pd.DataFrame:
    required = {
        "entry_time", "exit_time", "pnl_before_fees", "net_pnl",
        "entry_fee", "exit_fee", "total_fees",
    }
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"Trade data missing columns: {sorted(missing)}")
    frame = trades.copy()
    for column in ("entry_time", "exit_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
        if frame[column].isna().any():
            raise ValueError(f"Trade {column} contains invalid timestamps")
    if (frame["exit_time"] < frame["entry_time"]).any():
        raise ValueError("Trade exit times must not precede entry times")
    numeric_columns = (
        "pnl_before_fees", "net_pnl", "entry_fee", "exit_fee", "total_fees"
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    if len(frame) and not np.isfinite(frame[list(numeric_columns)].to_numpy()).all():
        raise ValueError("Trade ledger contains non-finite values")
    if len(frame) and not np.allclose(
        frame["entry_fee"] + frame["exit_fee"],
        frame["total_fees"],
        atol=1e-8,
        rtol=0,
    ):
        raise ValueError("Trade fee totals do not reconcile")
    if len(frame) and not np.allclose(
        frame["pnl_before_fees"] - frame["total_fees"],
        frame["net_pnl"],
        atol=1e-8,
        rtol=0,
    ):
        raise ValueError("Trade net P&L does not reconcile")
    return frame


def _period_metrics(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    window: TimeWindow,
    *,
    period_name: str,
    timestamp_col: str,
) -> dict:
    start, end = window.parsed()
    if timestamp_col not in equity:
        raise ValueError(f"Missing equity timestamp column: {timestamp_col}")
    frame = _validated_equity(equity, timestamp_col)
    ledger = _validated_trades(trades)
    before = frame.loc[frame[timestamp_col] < start]
    in_window = frame.loc[(frame[timestamp_col] >= start) & (frame[timestamp_col] < end)]
    if before.empty:
        raise ValueError(f"No equity observation before {period_name} starts")
    if in_window.empty:
        raise ValueError(f"No equity observations in {period_name} window")

    start_observation = before.iloc[-1]
    final_observation = in_window.iloc[-1]
    result = {
        "period": period_name,
        "window_start_utc": start.isoformat(),
        "window_end_utc_exclusive": end.isoformat(),
        "equity_observations": len(in_window),
        "period_start_available_at": start_observation[timestamp_col].isoformat(),
        "period_end_available_at": final_observation[timestamp_col].isoformat(),
        "time_in_market_pct": float((in_window["position"] != 0).mean() * 100),
    }

    for column in EQUITY_COLUMNS:
        starting_equity = float(start_observation[column])
        ending_equity = float(final_observation[column])
        if starting_equity <= 0:
            raise ValueError(
                f"Cannot calculate percentage return from non-positive "
                f"starting {column}: {starting_equity}"
            )
        path = np.concatenate((
            np.asarray([starting_equity]),
            in_window[column].to_numpy(dtype=float),
        ))
        peaks = np.maximum.accumulate(path)
        drawdowns_dollars = path - peaks
        drawdowns_pct = np.divide(
            path,
            peaks,
            out=np.ones_like(path),
            where=peaks != 0,
        ) - 1.0
        prefix = column.removesuffix("_equity")
        result[f"starting_equity_{prefix}"] = starting_equity
        result[f"ending_equity_{prefix}"] = ending_equity
        result[f"total_return_pct_{prefix}"] = (
            (ending_equity / starting_equity - 1.0) * 100
        )
        result[f"max_drawdown_pct_{prefix}"] = float(drawdowns_pct.min() * 100)
        result[f"max_drawdown_dollars_{prefix}"] = float(drawdowns_dollars.min())

    closed_mask = (ledger["exit_time"] >= start) & (ledger["exit_time"] < end)
    entries_mask = (ledger["entry_time"] >= start) & (ledger["entry_time"] < end)
    exits_mask = (ledger["exit_time"] >= start) & (ledger["exit_time"] < end)
    closed = ledger.loc[closed_mask]
    entry_events = ledger.loc[entries_mask]
    exit_events = ledger.loc[exits_mask]
    wins = closed.loc[closed["net_pnl"] > 0, "net_pnl"]
    losses = closed.loc[closed["net_pnl"] < 0, "net_pnl"]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    result.update({
        "closed_trades_by_exit_time": len(closed),
        "closed_trade_gross_pnl_by_exit_time": float(closed["pnl_before_fees"].sum()),
        "closed_trade_net_pnl_by_exit_time": float(closed["net_pnl"].sum()),
        "closed_trade_entry_fees_by_exit_time": float(closed["entry_fee"].sum()),
        "closed_trade_exit_fees_by_exit_time": float(closed["exit_fee"].sum()),
        "win_rate_pct_by_exit_time": (
            float((closed["net_pnl"] > 0).mean() * 100) if len(closed) else 0.0
        ),
        "profit_factor_by_exit_time": (
            gross_profit / gross_loss if gross_loss else (math.inf if gross_profit else 0.0)
        ),
        "entry_fees_paid_by_entry_time": float(entry_events["entry_fee"].sum()),
        "exit_fees_paid_by_exit_time": float(exit_events["exit_fee"].sum()),
        "fee_attribution_note": (
            "Closed-trade P&L/fee fields are grouped by exit time; event fee fields "
            "are grouped by their execution time. Do not add both fee views."
        ),
    })
    return result


def metrics_by_temporal_split(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    split: TemporalSplit,
    *,
    timestamp_col: str = "available_at",
    config: ExperimentConfig,
    hypothesis: HypothesisSpec,
    approval: PreregistrationApproval,
    provenance: EvaluationProvenance,
) -> pd.DataFrame:
    """Calculate train/validation/holdout metrics for supplied ledgers.

    The ledger content must match a provenance record bound to the current
    approval and split. The record detects later substitution or mutation;
    the caller remains responsible for deriving the ledger from the approved
    inputs. This is an accidental-use safeguard, not a security boundary.
    """
    if split.holdout is None:
        raise ValueError("A holdout window is required")
    validate_preregistration_approval(config, hypothesis, approval)
    split.validate()
    if _split_fingerprint(split, timestamp_col) != _split_fingerprint(config.split, timestamp_col):
        raise PermissionError("Evaluation windows do not match the approved configuration")
    if not isinstance(provenance, EvaluationProvenance):
        raise PermissionError("A matching evaluation provenance record is required")
    expected_binding = (
        _approval_record_fingerprint(approval), approval.specification_sha256,
        _split_fingerprint(split, timestamp_col), dataframe_fingerprint(equity),
        dataframe_fingerprint(trades), timestamp_col,
    )
    actual_binding = (
        provenance.approval_sha256, provenance.specification_sha256,
        provenance.split_sha256, provenance.equity_sha256,
        provenance.trades_sha256, provenance.timestamp_col,
    )
    if actual_binding != expected_binding:
        raise PermissionError("Evaluation provenance is stale or does not match supplied ledgers")
    periods = (
        ("train", split.train),
        ("validation", split.validation),
        ("holdout", split.holdout),
    )
    rows = [
        _period_metrics(
            equity,
            trades,
            window,
            period_name=name,
            timestamp_col=timestamp_col,
        )
        for name, window in periods
    ]
    return pd.DataFrame(rows)
