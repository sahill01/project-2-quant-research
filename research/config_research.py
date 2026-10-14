from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"
RESULTS_DIR = PROJECT_ROOT / "research_results"

SYMBOL = "BTCUSD"
TIMEFRAME = "4h"
DAYS_BACK = 730

INITIAL_CAPITAL = 50.0

TAKER_FEE = 0.0005
GST_ON_FEE = 0.18
EFFECTIVE_TAKER_FEE = TAKER_FEE * (1.0 + GST_ON_FEE)

SLIPPAGE_PCT = 0.0002

# Temporary baseline exposure model, NOT the future risk engine.
BASELINE_ALLOCATION = 0.95

EMA_FAST = 20
EMA_SLOW = 50
DONCHIAN_PERIOD = 20
