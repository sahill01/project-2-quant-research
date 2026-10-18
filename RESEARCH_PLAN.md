# Research Plan — v1

## Non-negotiable
- No live trading.
- No optimization before integrity tests.
- Never tune against the locked holdout.
- Record hypotheses before testing.
- Record failed experiments.
- Adding future data must not change past decisions.
- Include costs in reported results.

## Phase 1
- [x] Research layer separated from old bot
- [x] `available_at`
- [x] Thin event-driven backtester
- [x] Fee + slippage
- [x] Buy-and-hold baseline
- [x] EMA long/short baseline
- [x] Donchian long/short baseline

## Phase 2
- [x] Prefix-invariance test
- [ ] Multi-timeframe causal join test
- [x] Chronological train/validation/holdout partition primitive (evaluation remains gated)
- [ ] Intrabar stop/target ordering
- [ ] Contract/tick/minimum-size constraints
- [ ] Funding/liquidation model

## Phase 3
- [x] Causal swing-point detection with configurable confirmation windows
- [x] Confirmed same-side market-structure labels (HH/LH/HL/LL; equal and initial events explicit)
- [x] Objective close-available candlestick geometry events
- [ ] Simple structural hypotheses
- [ ] Incremental feature testing

## Phase 4
- [x] Causal support/resistance zone lifecycle features (descriptive only)
- [x] Causal double-top/double-bottom geometry events
- [x] Reproducible experiment specification, provenance manifest and local approval record
- [ ] Dynamic scoring only after evidence supports it

## Phase 5
- [ ] Risk Engine
- [ ] Portfolio exposure
- [ ] Correlation/concentration
- [ ] Walk-forward testing
- [ ] Paper trading

## Phase 6
- [ ] Testnet execution
- [ ] Live execution only after research validation
