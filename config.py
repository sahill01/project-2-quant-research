"""
Project 2 — Quantitative Trading Research Bot

Central configuration for the research engine.

IMPORTANT:
- No API keys are required for the current research phase.
- Execution credentials will be added much later.
"""

# ============================================================
# DATA SOURCE
# ============================================================

DATA_SOURCE = "delta"

# Future data sources — NOT IMPLEMENTED YET
# DATA_SOURCE = "tradingview"
# DATA_SOURCE = "other_exchange"


# ============================================================
# MARKET UNIVERSE
# ============================================================

# Start small while testing the pipeline.
# We will later build an automatic instrument scanner.

SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
]

# Future:
# SYMBOLS = "AUTO"


# ============================================================
# TIMEFRAMES
# ============================================================

TIMEFRAMES = [
    "15m",
    "1h",
    "4h",
    "1d",
]


# ============================================================
# HISTORICAL DATA
# ============================================================

DAYS_BACK = 730


# ============================================================
# ACCOUNT / RISK
# ============================================================

INITIAL_CAPITAL = 50.00

# Maximum planned loss if the stop is hit.
RISK_PER_TRADE = 0.01       # 1%

# Maximum combined planned risk from simultaneously open trades.
MAX_PORTFOLIO_RISK = 0.02   # 2%


# ============================================================
# TRADING COST ASSUMPTIONS
# ============================================================

# Conservative initial assumption:
# Delta futures/perpetual taker fee = 0.05%
# GST on trading fee = 18%
#
# Effective fee:
# 0.0005 * 1.18 = 0.00059 = 0.059%

TAKER_FEE = 0.0005
GST_ON_FEE = 0.18

EFFECTIVE_TAKER_FEE = TAKER_FEE * (1 + GST_ON_FEE)

# Initial slippage assumption.
# We will eventually make this instrument/liquidity dependent.
SLIPPAGE_PCT = 0.0002


# ============================================================
# BACKTESTING
# ============================================================

# Headline account value uses realized equity.
USE_REALIZED_EQUITY = True

# Keep mark-to-market equity separately for drawdown analysis.
TRACK_UNREALIZED_EQUITY = True


# ============================================================
# FUTURE COMPONENTS
# ============================================================

# These are intentionally not active yet.

ENABLE_FUNDING = False
ENABLE_OPEN_INTEREST = False
ENABLE_MARK_PRICE = False

# Future execution layer:
# EXECUTION_MODE = "backtest"
# EXECUTION_MODE = "testnet"
# EXECUTION_MODE = "live"