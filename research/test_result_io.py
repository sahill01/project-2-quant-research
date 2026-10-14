"""Synthetic checks for no-clobber result writing."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from research.backtester import save_results
import research.result_io as result_io
from research.result_io import write_csv_batch_no_clobber


def test_new_csv_batch_is_written():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "new.csv"
        write_csv_batch_no_clobber([(pd.DataFrame({"value": [1, 2]}), path)])
        saved = pd.read_csv(path)
        assert saved["value"].tolist() == [1, 2]


def test_existing_target_refuses_entire_batch_without_mutation():
    with TemporaryDirectory() as directory:
        first = Path(directory) / "first.csv"
        existing = Path(directory) / "existing.csv"
        existing.write_bytes(b"preserve these bytes\n")
        try:
            write_csv_batch_no_clobber([
                (pd.DataFrame({"value": [1]}), first),
                (pd.DataFrame({"value": [2]}), existing),
            ])
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing output target was overwritten")
        assert not first.exists()
        assert existing.read_bytes() == b"preserve these bytes\n"


def test_duplicate_targets_are_rejected_before_writing():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "duplicate.csv"
        frame = pd.DataFrame({"value": [1]})
        try:
            write_csv_batch_no_clobber([(frame, path), (frame, path)])
        except ValueError as error:
            assert "unique" in str(error)
        else:
            raise AssertionError("Duplicate output paths were accepted")
        assert not path.exists()


def test_serialization_failure_leaves_no_partial_batch_or_staging_files():
    class FailingFrame:
        def to_csv(self, *_args, **_kwargs):
            raise RuntimeError("synthetic serialization failure")

    with TemporaryDirectory() as directory:
        first = Path(directory) / "first.csv"
        second = Path(directory) / "second.csv"
        try:
            write_csv_batch_no_clobber([
                (pd.DataFrame({"value": [1]}), first),
                (FailingFrame(), second),
            ])
        except RuntimeError as error:
            assert "synthetic serialization failure" in str(error)
        else:
            raise AssertionError("Synthetic serialization failure was ignored")
        assert not first.exists()
        assert not second.exists()
        assert list(Path(directory).iterdir()) == []


def test_commit_race_rolls_back_own_files_and_preserves_concurrent_target():
    import os

    with TemporaryDirectory() as directory:
        first = Path(directory) / "first.csv"
        raced_target = Path(directory) / "raced.csv"
        original_link = os.link

        def create_race_then_fail(source, destination):
            if Path(destination) == raced_target:
                raced_target.write_bytes(b"created by concurrent writer\n")
                raise FileExistsError(str(raced_target))
            return original_link(source, destination)

        try:
            with patch.object(result_io.os, "link", side_effect=create_race_then_fail):
                write_csv_batch_no_clobber([
                    (pd.DataFrame({"value": [1]}), first),
                    (pd.DataFrame({"value": [2]}), raced_target),
                ])
        except FileExistsError:
            pass
        else:
            raise AssertionError("Commit race did not fail the CSV batch")

        assert not first.exists()
        assert raced_target.read_bytes() == b"created by concurrent writer\n"
        assert list(Path(directory).iterdir()) == [raced_target]


def test_shared_backtest_saver_preflights_equity_and_trade_outputs():
    with TemporaryDirectory() as directory:
        equity_path = Path(directory) / "sample_equity.csv"
        trades_path = Path(directory) / "sample_trades.csv"
        trades_path.write_bytes(b"existing trade output\n")
        try:
            save_results(
                pd.DataFrame({"equity": [50.0]}),
                pd.DataFrame({"pnl": []}),
                directory,
                "sample",
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("Shared backtest saver overwrote an output")
        assert not equity_path.exists()
        assert trades_path.read_bytes() == b"existing trade output\n"


def main():
    tests = [
        test_new_csv_batch_is_written,
        test_existing_target_refuses_entire_batch_without_mutation,
        test_duplicate_targets_are_rejected_before_writing,
        test_serialization_failure_leaves_no_partial_batch_or_staging_files,
        test_commit_race_rolls_back_own_files_and_preserves_concurrent_target,
        test_shared_backtest_saver_preflights_equity_and_trade_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
