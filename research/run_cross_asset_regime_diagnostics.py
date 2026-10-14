"""Describe saved cross-asset equity changes by causal market regime.

This reads existing 4h OHLCV and baseline equity CSVs only. Regime labels are
computed from information available at a candle close, then applied to the
following close-to-close equity change. It does not generate or test signals.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import DAYS_BACK
from research.data_loader import default_dataset_path, load_ohlcv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"
INPUT_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_baselines"
OUTPUT_DIR = PROJECT_ROOT / "research" / "results" / "cross_asset_regime_diagnostics_v1"
ASSETS = ("BTCUSD", "ETHUSD", "SOLUSD")
STRATEGIES = ("buy_hold", "ema_20_50", "donchian_20")
EQUITY_COLUMNS = ("mark_to_market_equity", "net_liquidation_equity")
TREND_LOOKBACK_DAYS = 90
VOLATILITY_LOOKBACK_DAYS = 30
VOLATILITY_CALIBRATION_DAYS = 365
INTERVALS_PER_DAY = 6  # 4h candles
INITIAL_CAPITAL = 50.0
TOLERANCE = 1e-8
OUTPUT_NAME = "regime_equity_contributions.csv"
MANIFEST_NAME = "regime_diagnostics_manifest.json"


def build_regimes(
    market: pd.DataFrame,
    *,
    trend_lookback_days: int = TREND_LOOKBACK_DAYS,
    volatility_lookback_days: int = VOLATILITY_LOOKBACK_DAYS,
    calibration_days: int = VOLATILITY_CALIBRATION_DAYS,
) -> tuple[pd.DataFrame, float, pd.Timestamp]:
    """Build causal trend/volatility labels at each candle's available_at."""
    if market.empty:
        raise ValueError("Cannot classify an empty market dataset")
    if min(trend_lookback_days, volatility_lookback_days, calibration_days) <= 0:
        raise ValueError("Regime lookback and calibration periods must be positive")
    if not {"available_at", "close"}.issubset(market.columns):
        raise ValueError("Market data must contain available_at and close")

    available_at = pd.to_datetime(market["available_at"], utc=True, errors="raise")
    close = pd.to_numeric(market["close"], errors="raise").astype(float)
    if available_at.isna().any() or not available_at.is_monotonic_increasing:
        raise ValueError("Market availability timestamps must be valid and ordered")
    if available_at.duplicated().any() or not np.isfinite(close.to_numpy()).all():
        raise ValueError("Market timestamps must be unique and closes finite")
    if (close <= 0).any():
        raise ValueError("Market close prices must be positive")

    trend_bars = trend_lookback_days * INTERVALS_PER_DAY
    volatility_bars = volatility_lookback_days * INTERVALS_PER_DAY
    trailing_return = close.div(close.shift(trend_bars)).sub(1.0)
    log_returns = np.log(close).diff()
    annualization = np.sqrt(INTERVALS_PER_DAY * 365)
    realized_volatility = (
        log_returns.rolling(volatility_bars, min_periods=volatility_bars)
        .std(ddof=1)
        .mul(annualization)
    )

    calibration_end = available_at.iloc[0] + pd.Timedelta(days=calibration_days)
    calibration_volatility = realized_volatility.loc[
        available_at <= calibration_end
    ].dropna()
    if calibration_volatility.empty:
        raise ValueError(
            "Insufficient observations to calibrate volatility threshold"
        )
    volatility_threshold = float(calibration_volatility.median())

    labels = []
    for timestamp, momentum, volatility in zip(
        available_at, trailing_return, realized_volatility
    ):
        if timestamp <= calibration_end:
            labels.append("CALIBRATION")
        elif not np.isfinite(momentum) or not np.isfinite(volatility):
            labels.append("UNCLASSIFIED")
        else:
            trend = "UP" if momentum > 0 else "DOWN_OR_FLAT"
            vol = "HIGH_VOL" if volatility > volatility_threshold else "LOW_VOL"
            labels.append(f"{trend}_{vol}")

    regimes = pd.DataFrame({
        "available_at": available_at,
        "trailing_return": trailing_return,
        "annualized_realized_volatility": realized_volatility,
        "regime": labels,
    })
    return regimes, volatility_threshold, calibration_end


def attribute_equity_changes(
    equity: pd.DataFrame,
    regimes: pd.DataFrame,
    *,
    asset: str,
    strategy: str,
    volatility_threshold: float,
    calibration_end: pd.Timestamp,
) -> list[dict]:
    """Assign each equity delta to the regime known before its interval."""
    required_equity = {"timestamp", "position", *EQUITY_COLUMNS}
    missing = required_equity - set(equity.columns)
    if missing:
        raise ValueError(f"Equity data missing columns: {sorted(missing)}")
    if len(equity) != len(regimes):
        raise ValueError("Market and equity rows are not one-to-one")

    equity = equity.copy()
    equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True, errors="raise")
    if not equity["timestamp"].reset_index(drop=True).equals(
        regimes["available_at"].reset_index(drop=True)
    ):
        raise ValueError("Market availability and equity timestamps do not align")
    if equity["timestamp"].duplicated().any() or not equity["timestamp"].is_monotonic_increasing:
        raise ValueError("Equity timestamps must be unique and ordered")

    for column in EQUITY_COLUMNS:
        equity[column] = pd.to_numeric(equity[column], errors="raise")
    values = equity[list(EQUITY_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Equity values must be finite")
    if equity["position"].isna().any() or not equity["position"].isin((-1, 0, 1)).all():
        raise ValueError("Equity positions must be discrete values in {-1, 0, 1}")
    if int(equity["position"].iloc[-1]) != 0:
        raise ValueError("Final position must be flat")
    if not np.allclose(
        equity.iloc[-1][list(EQUITY_COLUMNS)].to_numpy(dtype=float),
        float(equity.iloc[-1].get("realized_equity", np.nan)),
        atol=TOLERANCE,
        rtol=0,
    ):
        raise ValueError("Final valuation series do not match realized equity")

    contributions: dict[tuple[str, str], dict] = {}
    for index in range(1, len(equity)):
        # Regime at t-1 is known at the prior candle close and labels the
        # account-equity change through t. This avoids using current-bar data.
        regime = str(regimes.iloc[index - 1]["regime"])
        previous = equity.iloc[index - 1]
        current = equity.iloc[index]
        for column in EQUITY_COLUMNS:
            key = (column, regime)
            row = contributions.setdefault(key, {
                "asset": asset,
                "strategy": strategy,
                "equity_series": column,
                "regime": regime,
                "intervals": 0,
                "equity_pnl_dollars": 0.0,
                "positive_intervals": 0,
                "in_market_intervals": 0,
                "volatility_threshold_annualized": volatility_threshold,
                "calibration_end_utc": calibration_end.isoformat(),
                "regime_timing": "previous candle close labels next close-to-close equity change",
            })
            delta = float(current[column] - previous[column])
            row["intervals"] += 1
            row["equity_pnl_dollars"] += delta
            row["positive_intervals"] += int(delta > 0)
            row["in_market_intervals"] += int(int(previous["position"]) != 0)

    rows = []
    for row in contributions.values():
        count = row["intervals"]
        row["pnl_contribution_pct_initial_capital"] = (
            row["equity_pnl_dollars"] / INITIAL_CAPITAL * 100
        )
        row["positive_intervals_pct"] = row["positive_intervals"] / count * 100
        row["time_in_market_pct"] = row["in_market_intervals"] / count * 100
        del row["positive_intervals"]
        del row["in_market_intervals"]
        rows.append(row)

    for column in EQUITY_COLUMNS:
        attributed = sum(
            row["equity_pnl_dollars"] for row in rows
            if row["equity_series"] == column
        )
        observed = float(equity[column].iloc[-1] - equity[column].iloc[0])
        if not np.isclose(attributed, observed, atol=TOLERANCE, rtol=0):
            raise ValueError(
                f"{column} regime contributions do not reconcile: "
                f"{attributed} != {observed}"
            )
    return rows


def _read_equity_path(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "timestamp", "position", "realized_equity", *EQUITY_COLUMNS,
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame


def run_analysis() -> tuple[pd.DataFrame, dict[str, str]]:
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(f"Missing saved cross-asset results: {INPUT_DIR}")
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"Refusing to overwrite regime output directory: {OUTPUT_DIR}")

    rows = []
    input_paths: dict[str, Path] = {}
    for asset in ASSETS:
        market_path = default_dataset_path(DATA_DIR, asset, "4h", DAYS_BACK)
        market = load_ohlcv(market_path, "4h")
        steps = market["timestamp"].diff().dropna()
        if not steps.eq(pd.Timedelta(hours=4)).all():
            raise ValueError(f"{market_path}: missing or irregular 4h candles")
        regimes, vol_threshold, calibration_end = build_regimes(market)
        input_paths[f"data/{asset}_4h"] = market_path

        for strategy in STRATEGIES:
            prefix = f"{asset}_{strategy}"
            equity_path = INPUT_DIR / f"{prefix}_equity.csv"
            equity = _read_equity_path(equity_path)
            result = attribute_equity_changes(
                equity,
                regimes,
                asset=asset,
                strategy=strategy,
                volatility_threshold=vol_threshold,
                calibration_end=calibration_end,
            )
            rows.extend(result)
            input_paths[f"equity/{prefix}"] = equity_path

    summary = pd.DataFrame(rows).sort_values(
        ["asset", "strategy", "equity_series", "regime"]
    ).reset_index(drop=True)
    hashes = {
        key: sha256(path.read_bytes()).hexdigest()
        for key, path in sorted(input_paths.items())
    }
    return summary, hashes


def main() -> None:
    summary, input_hashes = run_analysis()
    output_paths = [OUTPUT_DIR / OUTPUT_NAME, OUTPUT_DIR / MANIFEST_NAME]
    existing = [str(path) for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite files: {existing}")

    source_paths = {
        "run_cross_asset_regime_diagnostics.py": Path(__file__),
        "data_loader.py": Path(__file__).with_name("data_loader.py"),
    }
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "descriptive_only",
        "assets": list(ASSETS),
        "strategies": list(STRATEGIES),
        "timeframe": "4h",
        "regime_definition": {
            "trend": "90-day trailing close return; UP if positive, otherwise DOWN_OR_FLAT",
            "volatility": "30-day rolling standard deviation of 4h log returns, annualized by sqrt(6*365)",
            "volatility_threshold": "per-asset median of available rolling volatility through the first 365 days",
            "initial_period": "CALIBRATION; equity intervals attributed using the preceding close label",
            "equity_attribution": "close-to-close equity change labeled by regime available at the preceding candle close",
            "limitations": "Retrospective attribution only; not a signal, strategy test, or predictive claim.",
        },
        "input_sha256": input_hashes,
        "implementation_sha256": {
            name: sha256(path.read_bytes()).hexdigest()
            for name, path in source_paths.items()
        },
        "outputs": [OUTPUT_NAME],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    summary.to_csv(OUTPUT_DIR / OUTPUT_NAME, index=False)
    (OUTPUT_DIR / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(summary)} regime attribution rows to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
