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
- [ ] Prefix-invariance test
- [ ] Multi-timeframe causal join test
- [ ] Train/validation/locked-holdout split
- [ ] Intrabar stop/target ordering
- [ ] Contract/tick/minimum-size constraints
- [ ] Funding/liquidation model

## Phase 3
- [ ] Swing Engine
- [ ] Market Structure Engine
- [ ] Simple structural hypotheses
- [ ] Incremental feature testing

## Phase 4
- [ ] Support/resistance lifecycle
- [ ] Pattern Engine
- [ ] Evidence objects
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
