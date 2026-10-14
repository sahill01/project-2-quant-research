# Longer Historical Data: Availability and Decision Notes

Review date: 2026-10-15

## What is available locally

`data/raw/` contains 12 files: BTCUSD, ETHUSD and SOLUSD at 15m, 1h, 4h and
1d, each named for a 730-day range. The audited rows cover approximately
2024-09-28 through 2026-09-28 UTC, with regular cadence and aligned
timestamps. No older local candles were found.

## Option 1: Extend Delta Exchange history

The official [Delta historical OHLC candles documentation](https://docs-global.delta.exchange/)
accepts a symbol, resolution, and Unix start/end times, and caps responses at
2,000 candles. The current downloader already chunks requests, but its
configuration requests only 730 days. The documentation does not state how
far back each symbol is retained, so history older than the local range is
not verified. Confirming retention would require a deliberate, read-only
historical request; no such request was made in this review.

This path is the closest match to the current datasets because it preserves
the Delta venue and product symbols. It still requires validating returned
coverage, gaps, duplicate timestamps, timestamp boundaries, and overlap
against the existing range before any research use.

## Option 2: Public historical archives from another venue

The official [Binance Public Data repository](https://github.com/binance/binance-public-data/blob/master/README.md)
documents public daily/monthly Spot and Futures archives, lists 4h klines,
and supplies checksum files. Its [download utility documentation](https://github.com/binance/binance-public-data/blob/master/python/README.md)
uses 2020-01 as the default start date for available archive downloads, but
that is not a guarantee that each requested symbol and market has a complete
history from that date. Exact symbol, contract, listing, and date coverage
must be checked before an experiment.

Binance symbols such as BTCUSDT, ETHUSDT and SOLUSDT represent Binance Spot
or USD-M Futures markets. They are not the same instrument history as the
current Delta BTCUSD/ETHUSD/SOLUSD files. They can support a separately
identified cross-venue robustness study, but must not be concatenated with
Delta candles as if they were one continuous market series. Differences in
venue, quote asset, contract construction, funding, and execution costs need
their own declared treatment.

The archive has usage conditions: the [current Binance Vision dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md)
are version 1.0, last updated 2026-08-26, and limit the stated free
non-commercial use to specified research/backtesting activities. They
prohibit several commercial, live-execution, and compensated signal uses.
Review the current terms against the intended use before acquiring or relying
on these files. This note is an engineering prerequisite, not a legal
interpretation.

The same repository documents checksums and archive corrections, while its
issue tracker currently includes reports of missing or inconsistent candle
rows (for example [issue 475](https://github.com/binance/binance-public-data/issues/475)
and [issue 501](https://github.com/binance/binance-public-data/issues/501)).
Checksums establish file integrity, not market-data correctness; each
download still needs the project's finite-value, duplicate, alignment, gap,
range, and OHLC validation.

## Option 3: Licensed historical-data provider

A vendor could potentially provide longer, normalized multi-venue or
venue-specific data, but cost, redistribution rights, corrections policy,
contract coverage, and point-in-time provenance are unverified. Selecting or
paying for an external service is an approval gate under the project rules.
No vendor has been selected or contacted.

## Recommended acquisition sequence

1. Decide whether the objective requires Delta-only history or explicitly
   permits a separate cross-venue dataset.
2. For Delta, first verify old-date availability for the exact symbols and
   intervals without saving or merging results. Retention remains unknown.
3. For Binance archives, inspect exact directory coverage and current terms;
   verify checksums and representative daily/monthly overlap before adoption.
4. Store any acquired history under a new, venue-specific directory. Never
   overwrite the current 730-day files. Record source, contract, interval,
   UTC range, checksum, retrieval date, terms/version, and validation results.
5. Keep venues separate in analysis and manifests. Do not use acquired data in
   a predictive experiment until the hypothesis and validation plan are
   approved.

No data was downloaded or API endpoint queried. Only public documentation was
reviewed; no existing data or research output was modified for this
investigation.
