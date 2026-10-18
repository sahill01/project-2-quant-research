"""Synthetic checks for time-window backtest metrics and attribution."""

import pandas as pd
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import fields

from research.experiment_metrics import (
    create_evaluation_provenance, metrics_by_temporal_split,
)
from research.experiment_protocol import (
    ExperimentConfig, TemporalSplit, TimeWindow, create_preregistration_approval,
    validate_preregistration_approval,
)
from research.hypothesis_spec import HypothesisSpec, ResearchDecisions


def synthetic_split():
    return TemporalSplit(
        train=TimeWindow("2026-01-01T01:00:00Z", "2026-01-01T03:00:00Z"),
        validation=TimeWindow("2026-01-01T03:00:00Z", "2026-01-01T05:00:00Z"),
        holdout=TimeWindow("2026-01-01T05:00:00Z", "2026-01-01T07:00:00Z"),
    )


def synthetic_ledgers():
    times = pd.date_range("2026-01-01", periods=7, freq="1h", tz="UTC")
    equity = pd.DataFrame({
        "available_at": times,
        "position": [0, 1, 1, 1, 0, 1, 0],
        "realized_equity": [50.0, 48.0, 51.0, 45.0, 55.0, 55.0, 50.0],
        "mark_to_market_equity": [50.0, 48.0, 51.0, 45.0, 55.0, 55.0, 50.0],
        "net_liquidation_equity": [50.0, 47.0, 50.0, 44.0, 55.0, 55.0, 50.0],
    })
    trades = pd.DataFrame({
        "entry_time": pd.to_datetime([
            "2026-01-01T02:30:00Z", "2026-01-01T03:30:00Z"
        ], utc=True),
        "exit_time": pd.to_datetime([
            "2026-01-01T03:30:00Z", "2026-01-01T05:30:00Z"
        ], utc=True),
        "pnl_before_fees": [5.0, -2.0],
        "entry_fee": [0.5, 0.2],
        "exit_fee": [0.5, 0.2],
        "total_fees": [1.0, 0.4],
        "net_pnl": [4.0, -2.4],
    })
    return equity, trades


_AUTO_PROVENANCE = object()


def authorized_report(
    equity, trades, experiment_split, *, provenance_source=_AUTO_PROVENANCE,
    trades_provenance_source=_AUTO_PROVENANCE, approval_variant=False,
    metric_split=None, stale_source=False,
):
    decisions = ResearchDecisions(**{
        item.name: "synthetic protocol fixture" for item in fields(ResearchDecisions)
    })
    hypothesis = HypothesisSpec(
        hypothesis_id="HYP-METRICS-SYN", title="Synthetic metrics gate",
        market_rationale="Test-only", feature_definition="Test-only",
        signal_definition="No signal", information_available_at="available_at before decision",
        entry_and_exit_assumptions="Test-only", expected_effect="No predictive assertion",
        failure_conditions=("Test-only",), baseline_comparison="Test-only",
        sample_size_and_validation="Test-only", confounders=("Test-only",),
        transaction_cost_assumptions="Test-only", approval_status="APPROVED",
        decisions=decisions,
    )
    config = ExperimentConfig(
        experiment_id="SYN-METRICS-001", version=1,
        hypothesis_id=hypothesis.hypothesis_id, hypothesis_version=1,
        hypothesis_approval_status="APPROVED", strategy="synthetic", assets=("SYN",),
        timeframe="1h", feature_pipeline_version="synthetic-v1", parameters={"fixture": True},
        cost_model_version="synthetic-cost-v1",
        execution={"fixture": "no trading"}, split=experiment_split,
    )
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        data.write_text("available_at,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
        source_file = root / "source.py"
        source_file.write_text("SYNTHETIC = True\n", encoding="utf-8")
        approval = create_preregistration_approval(
            config, hypothesis, {"synthetic": data}, {"fixture.py": source_file},
            approver="synthetic test", approved_at_utc="2026-01-01T00:00:00Z",
            approval_note="Test gate only",
        )
        equity_source = equity if provenance_source is _AUTO_PROVENANCE else provenance_source
        trades_source = (
            trades if trades_provenance_source is _AUTO_PROVENANCE
            else trades_provenance_source
        )
        provenance = create_evaluation_provenance(
            equity_source, trades_source, experiment_split, timestamp_col="available_at",
            config=config, hypothesis=hypothesis, approval=approval,
        ) if equity_source is not None else None
        if stale_source:
            source_file.write_text("SYNTHETIC = False\n", encoding="utf-8")
        selected_approval = approval
        if approval_variant:
            alternate_data = root / "alternate_data.csv"
            alternate_data.write_text(
                "available_at,value\n2026-01-01T00:00:00Z,2\n", encoding="utf-8"
            )
            selected_approval = create_preregistration_approval(
                config, hypothesis, {"synthetic": alternate_data}, {"fixture.py": source_file},
                approver="synthetic test", approved_at_utc="2026-01-01T00:00:00Z",
                approval_note="Different synthetic run",
            )
        return metrics_by_temporal_split(
            equity, trades, metric_split or experiment_split, config=config,
            hypothesis=hypothesis, approval=selected_approval, provenance=provenance,
        )


def test_period_returns_and_drawdowns_use_prior_equity_as_start_peak():
    equity, trades = synthetic_ledgers()
    report = authorized_report(equity, trades, synthetic_split())
    train = report.loc[report.period == "train"].iloc[0]
    validation = report.loc[report.period == "validation"].iloc[0]
    holdout = report.loc[report.period == "holdout"].iloc[0]

    assert train.starting_equity_mark_to_market == 50.0
    assert train.ending_equity_mark_to_market == 51.0
    assert abs(train.max_drawdown_pct_mark_to_market + 4.0) < 1e-10
    assert abs(train.max_drawdown_dollars_mark_to_market + 2.0) < 1e-10
    assert abs(validation.total_return_pct_mark_to_market - (55 / 51 - 1) * 100) < 1e-10
    assert abs(validation.max_drawdown_pct_mark_to_market - (45 / 51 - 1) * 100) < 1e-10
    assert abs(validation.max_drawdown_dollars_mark_to_market + 6.0) < 1e-10
    assert holdout.total_return_pct_mark_to_market < 0
    assert abs(holdout.max_drawdown_dollars_mark_to_market + 5.0) < 1e-10


def test_closed_trade_pnl_and_entry_exit_fee_event_attribution_are_separate():
    equity, trades = synthetic_ledgers()
    report = authorized_report(equity, trades, synthetic_split())
    train = report.loc[report.period == "train"].iloc[0]
    validation = report.loc[report.period == "validation"].iloc[0]
    holdout = report.loc[report.period == "holdout"].iloc[0]

    assert train.closed_trades_by_exit_time == 0
    assert train.closed_trade_net_pnl_by_exit_time == 0.0
    assert train.entry_fees_paid_by_entry_time == 0.5
    assert validation.closed_trades_by_exit_time == 1
    assert validation.closed_trade_net_pnl_by_exit_time == 4.0
    assert validation.closed_trade_entry_fees_by_exit_time == 0.5
    assert validation.closed_trade_exit_fees_by_exit_time == 0.5
    assert validation.entry_fees_paid_by_entry_time == 0.2
    assert validation.exit_fees_paid_by_exit_time == 0.5
    assert holdout.closed_trades_by_exit_time == 1
    assert holdout.closed_trade_net_pnl_by_exit_time == -2.4
    assert holdout.entry_fees_paid_by_entry_time == 0.0
    assert holdout.exit_fees_paid_by_exit_time == 0.2


def test_invalid_trade_accounting_and_missing_period_observation_fail():
    equity, trades = synthetic_ledgers()
    bad_trades = trades.copy()
    bad_trades.loc[0, "total_fees"] = 2.0
    try:
        authorized_report(equity, bad_trades, synthetic_split())
    except ValueError as error:
        assert "fee totals" in str(error)
    else:
        raise AssertionError("Invalid fee accounting was accepted")

    empty_period_split = TemporalSplit(
        train=TimeWindow("2026-01-01T00:30:00Z", "2026-01-01T00:45:00Z"),
        validation=synthetic_split().validation,
        holdout=synthetic_split().holdout,
    )
    try:
        authorized_report(equity, trades, empty_period_split)
    except ValueError as error:
        assert "No equity observations" in str(error)
    else:
        raise AssertionError("A split window with no equity rows was accepted")

    zero_start = equity.copy()
    zero_start.loc[0, "mark_to_market_equity"] = 0.0
    zero_start.loc[1, "mark_to_market_equity"] = 0.0
    try:
        authorized_report(zero_start, trades, synthetic_split())
    except ValueError as error:
        assert "non-positive starting" in str(error)
    else:
        raise AssertionError("Percentage return from zero starting equity was accepted")

    reversed_trade = trades.copy()
    reversed_trade.loc[0, "exit_time"] = pd.Timestamp("2026-01-01T01:30:00Z")
    try:
        authorized_report(equity, reversed_trade, synthetic_split())
    except ValueError as error:
        assert "precede entry" in str(error)
    else:
        raise AssertionError("Trade exit before entry was accepted")


def test_holdout_metrics_require_current_preregistration_approval():
    decisions = ResearchDecisions(**{
        item.name: "synthetic test decision" for item in fields(ResearchDecisions)
    })
    hypothesis = HypothesisSpec(
        hypothesis_id="HYP-GATE-SYN", title="Synthetic gate", market_rationale="test",
        feature_definition="test", signal_definition="none",
        information_available_at="available_at before decision", entry_and_exit_assumptions="test",
        expected_effect="no claim", failure_conditions=("test",), baseline_comparison="test",
        sample_size_and_validation="test", confounders=("test",), transaction_cost_assumptions="test",
        approval_status="APPROVED", decisions=decisions,
    )
    config = ExperimentConfig(
        experiment_id="SYN-GATE-001", version=1, hypothesis_id=hypothesis.hypothesis_id,
        strategy="synthetic", assets=("SYN",), timeframe="1h", parameters={},
        execution={"fixture": "test"}, split=synthetic_split(),
        hypothesis_approval_status="APPROVED", feature_pipeline_version="synthetic-v1",
        cost_model_version="synthetic-cost-v1",
    )
    try:
        validate_preregistration_approval(config, hypothesis, None)
    except PermissionError:
        pass
    else:
        raise AssertionError("Missing approval was accepted for holdout metrics")


def test_holdout_metrics_reject_missing_or_substituted_ledger_provenance():
    equity, trades = synthetic_ledgers()
    try:
        authorized_report(equity, trades, synthetic_split(), provenance_source=None)
    except PermissionError as error:
        assert "provenance" in str(error).lower()
    else:
        raise AssertionError("Missing evaluation provenance was accepted")

    substituted = equity.copy()
    substituted.loc[0, "realized_equity"] = 999.0
    try:
        authorized_report(equity, trades, synthetic_split(), provenance_source=substituted)
    except PermissionError as error:
        assert "provenance" in str(error).lower()
    else:
        raise AssertionError("Provenance for another equity ledger was accepted")

    substituted_trades = trades.copy()
    substituted_trades.loc[0, "net_pnl"] += 0.25
    try:
        authorized_report(
            equity, trades, synthetic_split(),
            trades_provenance_source=substituted_trades,
        )
    except PermissionError as error:
        assert "provenance" in str(error).lower()
    else:
        raise AssertionError("Provenance for another trade ledger was accepted")

    try:
        authorized_report(equity, trades, synthetic_split(), stale_source=True)
    except PermissionError as error:
        assert "approval" in str(error).lower() or "provenance" in str(error).lower()
    else:
        raise AssertionError("Metrics accepted provenance after the approved source became stale")

    try:
        authorized_report(equity, trades, synthetic_split(), approval_variant=True)
    except PermissionError as error:
        assert "provenance" in str(error).lower()
    else:
        raise AssertionError("Provenance from another approved run was accepted")

    different_split = TemporalSplit(
        train=TimeWindow("2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z"),
        validation=synthetic_split().validation,
        holdout=synthetic_split().holdout,
    )
    try:
        authorized_report(equity, trades, synthetic_split(), metric_split=different_split)
    except PermissionError as error:
        assert "configuration" in str(error).lower()
    else:
        raise AssertionError("Metrics over unapproved window boundaries were accepted")


def main():
    tests = [
        test_period_returns_and_drawdowns_use_prior_equity_as_start_peak,
        test_closed_trade_pnl_and_entry_exit_fee_event_attribution_are_separate,
        test_invalid_trade_accounting_and_missing_period_observation_fail,
        test_holdout_metrics_require_current_preregistration_approval,
        test_holdout_metrics_reject_missing_or_substituted_ledger_provenance,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
