# Validation and Paper-Trading Readiness Plan

## Current data constraint

Local data covers 730 days for BTCUSD, ETHUSD and SOLUSD at 15m, 1h, 4h and
1d. Existing files have regular cadence and aligned timestamps. The loader
checks UTC interval boundaries for minute/hour/day candles; weekly boundaries
remain unchecked until a source-specific week anchor is defined. It is
adequate for validating the data, feature and backtest pipelines,
but is too limited to support a broad predictive claim or representative
coverage of market regimes. There is no verified local history beyond that
span. Delta's public historical-candles API documentation specifies a
2,000-candle response limit, but does not establish retention depth. No
exchange request was made.

## Required predictive experiment design

Before feature/signal implementation, record and approve one hypothesis with:

1. A market rationale and a falsifiable expected effect.
2. Exact feature and signal formulas and their `available_at` timing.
3. Fixed entry, exit, fee, slippage and sizing assumptions matching the
   approved baseline unless an explicit change is approved.
4. A baseline comparison and failure/rejection conditions.
5. Time-ordered training and validation windows plus a later untouched
   holdout. Freeze the full configuration before the holdout is opened.
6. Multiple assets, time periods and regimes, plus cost and execution
   uncertainty sensitivity.
7. Predeclared sample-size rationale and reporting metrics. Avoid selecting
   a winner using holdout outcomes.
8. A reproducible manifest with code/data hashes, configuration, timestamps,
   test results and rejection decisions.

The existing split/manifest utilities enforce basic chronology, availability
column coverage, fingerprint matching, output no-clobber behavior, and an
explicit `APPROVED` hypothesis-status declaration before holdout freeze. The
status is a caller attestation, not independent proof of user approval. A
manifest requires the caller to provide experiment-specific source files and
hashes them alongside the core backtester, loader, strategies and protocol.
The caller must include every feature and runner file that affects the
experiment. These utilities do not decide suitable date windows, sample
sufficiency or a strategy. The manifest writer also rejects an empty input
data-file list so a configured run cannot appear reproducible without data
hashes. Configuration fingerprints use strict JSON serialization and reject
NaN and infinite values instead of encoding Python's non-standard JSON tokens.

`experiment_metrics.py` summarizes precomputed ledgers over those windows,
using the last equity observation before each window as its starting account
value and drawdown peak. It keeps closed-trade exit-time attribution separate
from fee event-time attribution. It does not load or reveal holdout data; the
caller remains responsible for using the freeze/open protocol before
calculating holdout metrics.
The holdout is omitted from the partition object's default representation to
avoid accidental disclosure through ordinary logging. Python callers can
still intentionally access the private attribute or serialize the object, so
this is not a security boundary.

The saved cross-asset regime diagnostic is only a retrospective decomposition
of account-equity changes. It assigns each interval to a trailing regime known
at the previous close and keeps an initial calibration year; it does not test
whether regime labels predict returns. Sparse regime cells and the short
sample preclude regime-performance claims.

Cost sensitivity is implemented as fixed fee/slippage scenarios around the
configured assumptions, with the unchanged strategy definitions. This is a
descriptive robustness check; the scenario values do not search for or select
lower-cost settings. Cost effects may interact with equity-based quantity
through the existing backtester behavior.

## Independent execution and accounting comparison protocol

A test-only scalar reference now checks synthetic ledgers in
`test_independent_accounting_reference.py`; no independent framework or
market-data comparison has been run. Before any future predictive evaluation,
compare the active backtester with a separately written reference
implementation. The reference must not import the production fill, fee,
position-sizing, trade-accounting, or equity-valuation helpers. Record both
implementations' source hashes and use a fresh output directory that refuses
existing targets.

Start with deterministic synthetic OHLCV fixtures covering: remaining flat;
opening and closing a long; opening and closing a short; long-to-short and
short-to-long reversals; nonzero fee and slippage; an open position valued at
an intermediate close; and final-candle liquidation. For each candle, compare
signal/decision time, execution time and price, side and quantity, entry/exit
fees, gross and net closed-trade P&L, realized equity, mark-to-market equity,
net liquidation equity, and terminal position state. Independently calculate
expected fills, fee amounts, and equity from the declared formulas instead of
using either engine's helper functions as the oracle.

Require exact matches for timestamps, sides, position states, trade counts,
and signal decisions. For price, quantity, fees, P&L and equity, require
absolute error <= 1e-9 in the synthetic fixtures; document any scale-dependent
tolerance before using wider-valued fixtures. Each discrepancy must be
reconciled to a declared convention (such as rounding) before comparison is
accepted. A framework comparison is supplementary: it must match execution
timing, fee/slippage inputs and position semantics, and differences must be
reported rather than normalized away.

Only after synthetic agreement should an independently generated trace be
compared on training/validation data for an approved hypothesis. Do not expose
the project holdout during this engineering check. A mismatch blocks later
predictive evaluation until its cause is fixed and the frozen configuration,
code hashes, test output and discrepancy report are recorded. This protocol
defines an engineering gate; it is not evidence that any strategy has
predictive value.

## Paper-trading gate

The current-state assessment is recorded in
`research/PAPER_TRADING_READINESS_REVIEW.md`. It finds the system not ready:
local candles are stale for operational use, the active engine models
simulated fills only, risk calculations are not enforced controls, and there
is no paper order lifecycle, independent reconciliation, or monitoring stack.
`research/data_quality.py` offers a synthetic-tested freshness check with
explicit caller-supplied time and age threshold; it is not integrated into an
operational feed and defines no default freshness policy.

Paper trading should not begin until independent review confirms all of the
following:

- causal, fresh data ingestion with explicit gap/staleness policy;
- deterministic signal generation and reproducible replay;
- complete order lifecycle, partial-fill, cancel/reject and restart recovery
  handling in a paper-only adapter;
- position and cash reconciliation against an independent ledger;
- separately approved risk limits and tested breach behavior;
- structured monitoring, alerting, audit logs and failure recovery;
- out-of-sample evidence that meets a prespecified acceptance plan, including
  costs, execution uncertainty and multiple-market conditions.

None of these statements authorizes exchange connectivity, live orders or
activation of the standalone risk module in the backtester. Paper-trading
transition remains an explicit approval gate.
