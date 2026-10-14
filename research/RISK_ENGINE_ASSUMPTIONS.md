# Standalone risk calculator assumptions

`risk_engine.py` contains arithmetic helpers only. It is not imported by or
connected to the active backtester. No risk fraction, stop policy, leverage,
portfolio limit, or exchange rule is selected by this module.

- The caller supplies the side, entry reference, stop reference, fee rate,
  slippage percentage, account equity, and all risk limits.
- Long entry is an adverse buy fill; long stop exit is an adverse sell fill.
  Short entry is an adverse sell fill; short stop exit is an adverse buy fill.
- Planned risk per unit includes the entry-to-stop loss plus the fee on each
  slipped fill notional.
- Quantity is rounded down only when the caller provides a positive quantity
  step. Exchange tick sizes, contract multipliers, funding, liquidation fees,
  minimum notional, and margin rules need a venue-specific adapter.
- Sizing validates the finite, positive risk per unit and entry fill even
  when a `PlannedTradeRisk` is constructed directly instead of returned by
  `plan_trade_risk`.
- `drawdown_limit_reached` reports a condition only; it does not close a trade.
- Risk inputs are caller-owned policy choices. These helpers do not imply that
  a future live or paper system enforces those choices.
