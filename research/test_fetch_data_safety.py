"""Mocked tests for downloader completeness and no-overwrite guarantees."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import fetch_data


class Response:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return {"success": True, "result": self._rows}


def candle(timestamp: int, close: float = 100.0):
    return {
        "time": timestamp,
        "open": 100.0,
        "high": max(101.0, close),
        "low": min(99.0, close),
        "close": close,
        "volume": 1.0,
    }


def test_empty_chunk_fails_instead_of_returning_partial_history():
    original_get = fetch_data.requests.get
    original_time = fetch_data.time.time
    fetch_data.requests.get = lambda *args, **kwargs: Response([])
    fetch_data.time.time = lambda: 1_800_000_000
    try:
        try:
            fetch_data.fetch_candles("SYN", "4h", 1)
        except RuntimeError as error:
            assert "refusing partial history" in str(error)
        else:
            raise AssertionError("Empty response was accepted as complete history")
    finally:
        fetch_data.requests.get = original_get
        fetch_data.time.time = original_time


def test_invalid_resolutions_fail_before_any_http_request():
    original_get = fetch_data.requests.get
    original_time = fetch_data.time.time
    calls = []
    fetch_data.requests.get = lambda *args, **kwargs: calls.append((args, kwargs))
    fetch_data.time.time = lambda: 1_800_000_000
    try:
        for resolution in ("0h", "-1h", "", "999999999999999999999999w"):
            try:
                fetch_data.fetch_candles("SYN", resolution, 1)
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"Invalid resolution {resolution!r} was accepted"
                )
        assert calls == []
    finally:
        fetch_data.requests.get = original_get
        fetch_data.time.time = original_time


def test_duplicate_candles_are_rejected_not_deduplicated():
    original_get = fetch_data.requests.get
    original_time = fetch_data.time.time
    timestamp = 1_799_985_600
    fetch_data.requests.get = lambda *args, **kwargs: Response([
        candle(timestamp, 100.0), candle(timestamp, 99.0)
    ])
    fetch_data.time.time = lambda: 1_800_000_000
    try:
        try:
            fetch_data.fetch_candles("SYN", "4h", 1)
        except ValueError as error:
            assert "Duplicate candle timestamps" in str(error)
        else:
            raise AssertionError("Duplicate candles were silently deduplicated")
    finally:
        fetch_data.requests.get = original_get
        fetch_data.time.time = original_time


def test_candle_outside_requested_chunk_is_rejected():
    original_get = fetch_data.requests.get
    original_time = fetch_data.time.time
    original_sleep = fetch_data.time.sleep
    fetch_data.requests.get = lambda *args, **kwargs: Response([
        candle(1_800_003_600)
    ])
    fetch_data.time.time = lambda: 1_800_000_000
    fetch_data.time.sleep = lambda _: None
    try:
        try:
            fetch_data.fetch_candles("SYN", "4h", 1)
        except ValueError as error:
            assert "outside requested chunk" in str(error)
        else:
            raise AssertionError("Out-of-range candle was accepted")
    finally:
        fetch_data.requests.get = original_get
        fetch_data.time.time = original_time
        fetch_data.time.sleep = original_sleep


def test_misaligned_candle_inside_requested_range_is_rejected():
    original_get = fetch_data.requests.get
    original_time = fetch_data.time.time
    original_sleep = fetch_data.time.sleep
    fetch_data.requests.get = lambda *args, **kwargs: Response([
        candle(1_799_996_400)
    ])
    fetch_data.time.time = lambda: 1_800_000_000
    fetch_data.time.sleep = lambda _: None
    try:
        try:
            fetch_data.fetch_candles("SYN", "4h", 1)
        except ValueError as error:
            assert "not aligned to UTC 4h" in str(error)
        else:
            raise AssertionError("Misaligned candle was accepted")
    finally:
        fetch_data.requests.get = original_get
        fetch_data.time.time = original_time
        fetch_data.time.sleep = original_sleep


def test_save_dataset_refuses_overwrite_and_preserves_existing_bytes():
    original_dir = fetch_data.OUTPUT_DIR
    original_days = fetch_data.DAYS_BACK
    with TemporaryDirectory() as directory:
        fetch_data.OUTPUT_DIR = directory
        fetch_data.DAYS_BACK = 1
        path = Path(directory) / "SYN_4h_1d.csv"
        path.write_text("keep me\n", encoding="utf-8")
        try:
            try:
                fetch_data.save_dataset(pd.DataFrame(), "SYN", "4h")
            except FileExistsError:
                pass
            else:
                raise AssertionError("Existing dataset was overwritten")
            assert path.read_text(encoding="utf-8") == "keep me\n"
        finally:
            fetch_data.OUTPUT_DIR = original_dir
            fetch_data.DAYS_BACK = original_days


def main():
    tests = [
        test_empty_chunk_fails_instead_of_returning_partial_history,
        test_invalid_resolutions_fail_before_any_http_request,
        test_duplicate_candles_are_rejected_not_deduplicated,
        test_candle_outside_requested_chunk_is_rejected,
        test_misaligned_candle_inside_requested_range_is_rejected,
        test_save_dataset_refuses_overwrite_and_preserves_existing_bytes,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
