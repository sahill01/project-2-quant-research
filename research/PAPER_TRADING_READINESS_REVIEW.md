# Paper-trading readiness review

Review date: 2026-10-15

## Decision

**Not ready for paper trading.** The repository supports historical research and
simulated candle-level fills. It does not currently provide a paper execution
system, current market data, operational safeguards, or approved risk limits.
This is an engineering readiness assessment, not a proposal to start paper
trading.

## Current-state evidence

| Area | Status | Evidence and remaining gap |
|---|---|---|
| Historical data validation | Partial | `research/data_loader.py` rejects empty, duplicate, malformed, non-finite and misaligned candle input and derives `available_at` from candle open plus timeframe. It does not enforce a general missing-candle or stale-data policy; weekly boundaries are exempt pending a source anchor. The 12 local files span 2024-09-28/29 through 2026-09-28. On the review date the newest candle opens are about 17 days old, so these files are not fresh inputs for paper execution. |
| Live/paper data freshness | Standalone check only | `research/data_quality.py` now checks a latest `available_at` timestamp against an explicit caller-supplied clock and maximum age. It is not wired into loading, historical downloading, or trading. `fetch_data.py` performs bounded historical HTTP downloads; no streaming/polling feed, staleness alarm, reconnect state, or paper data adapter was found. |
| Causal signal timing | Backtest evidence only | Signals are acted on at the next candle open in `research/backtester.py`; equity observations use candle availability timestamps. Existing causality and prefix-invariance suites pass. There is no tested always-on signal service or deterministic restart/replay path. |
| Simulated fills | Backtest only | `run_backtest()` models one net position with next-open fills, configured slippage and fees, reversals, and terminal liquidation. It has no order IDs, partial fills, cancel/reject states, acknowledgements, or persistent order lifecycle. |
| Risk controls | Not enforced | `research/risk_engine.py` is a standalone calculator. `research/RISK_ENGINE_ASSUMPTIONS.md` states that it is not connected to the active backtester and selects no policy defaults. No approved limits or breach actions exist. |
| Position and cash reconciliation | Synthetic backtest reference only | Accounting tests reconcile the simulated ledger, and `test_independent_accounting_reference.py` compares synthetic trade/equity ledgers to a separate scalar calculation. No independent paper broker/account ledger or restart reconciliation process exists. |
| Monitoring and recovery | Not implemented | No paper-specific structured event log, alerting, health monitor, watchdog, or failure-recovery workflow was found. |
| Predictive validation | Insufficient | Current evidence covers a 730-day descriptive baseline sample and synthetic engineering tests. There is no approved hypothesis, untouched holdout evaluation, independent framework or market-data comparison, or acceptance plan establishing a predictive effect. |
| Operational and venue constraints | Not assessed for paper adapter | No paper adapter or venue contract model exists for precision, minimum notional, funding, margin, or venue-specific order behavior. |

## Gate conditions before a paper-only proposal

1. Approve a specific falsifiable hypothesis and its time-ordered validation
   plan; preserve an untouched holdout and predeclare rejection criteria.
2. Establish adequate, venue-identified historical coverage and a declared
   gap/staleness policy; validate checksums, cadence, timestamps and source
   terms before using any extended data.
3. Build and test a paper-only data and order-state adapter with partial fill,
   cancel, rejection, timeout, reconnect and restart cases. No exchange order
   path is authorized by this assessment.
4. Define and separately approve risk limits, then test sizing, exposure,
   breach behavior and account reconciliation against an independent ledger.
5. Add structured monitoring, alerts, audit records and recovery procedures;
   exercise deterministic replay and stale-data/fault scenarios.
6. Obtain independent review that the prespecified out-of-sample evidence
   meets the agreed acceptance plan under transaction-cost and execution
   uncertainty.

Until these conditions are reviewed and satisfied, the system remains a
research/backtesting project. No strategy selection, paper activation, or live
execution is authorized here.
