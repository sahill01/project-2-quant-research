"""Synthetic-only operating-characteristic stress tests for event resampling.

This module consumes generated arrays only. It does not load project candles,
event ledgers, outcomes, or research result files. See
SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md before running the simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd


MASTER_SEED = 20261020
OUTER_REPETITIONS = 300
BOOTSTRAP_DRAWS = 399
BLOCK_LENGTH = 6
SUPPORT_FLOOR = 4  # Mechanical synthetic guard, not a real-data threshold.
METHODS = ("calendar_block", "zone_cluster", "crossed_product", "iid_negative_control")


@dataclass(frozen=True)
class Scenario:
    name: str
    zones_per_cohort: int
    periods: int
    events_per_zone: int
    zone_sd: float = 0.0
    period_sd: float = 0.0
    ar1: float = 0.0
    shared_period_shock: bool = False
    unequal_zone_sizes: bool = False
    missing_rate_higher: float = 0.0
    missing_rate_lower: float = 0.0


SCENARIOS = (
    Scenario("independent_baseline", 60, 120, 1),
    Scenario("persistent_repeated_zones", 24, 96, 6, zone_sd=0.5),
    Scenario("serial_overlapping_shared_shocks", 32, 120, 5, zone_sd=0.5,
             period_sd=0.5, ar1=0.7, shared_period_shock=True),
    Scenario("unequal_concentrated_zone_sizes", 30, 100, 4, zone_sd=0.5,
             unequal_zone_sizes=True),
    Scenario("few_independent_zones", 3, 100, 12, zone_sd=0.5,
             period_sd=0.3, ar1=0.5),
    Scenario("few_calendar_periods", 30, 5, 3, zone_sd=0.3, period_sd=0.5,
             shared_period_shock=True),
    Scenario("cohort_differential_missingness", 30, 100, 4, zone_sd=0.4,
             missing_rate_higher=0.10, missing_rate_lower=0.40),
)


def _child_seed(*parts: int) -> int:
    sequence = np.random.SeedSequence([MASTER_SEED, *parts])
    return int(sequence.generate_state(1, dtype=np.uint32)[0])


def generate_dataset(scenario: Scenario, effect: float, seed: int) -> pd.DataFrame:
    """Generate one event ledger with deliberate zone/time dependence."""
    rng = np.random.default_rng(seed)
    records: list[tuple[int, int, int, float, bool]] = []
    for cohort in (0, 1):
        for zone in range(scenario.zones_per_cohort):
            if scenario.unequal_zone_sizes and zone == 0:
                count = scenario.events_per_zone * 8
            else:
                count = scenario.events_per_zone
            if scenario.periods < 6:
                period_ids = rng.integers(0, scenario.periods, count)
            else:
                period_ids = rng.integers(0, scenario.periods - 5, count)
            for period in period_ids:
                records.append((cohort, cohort * scenario.zones_per_cohort + zone,
                                int(period), 0.0, True))

    zone_ids = np.array([r[1] for r in records], dtype=int)
    cohorts = np.array([r[0] for r in records], dtype=int)
    event_periods = np.array([r[2] for r in records], dtype=int)
    zone_effects = rng.normal(0.0, scenario.zone_sd,
                              size=2 * scenario.zones_per_cohort)
    period_shocks = rng.normal(0.0, scenario.period_sd, scenario.periods)
    if scenario.ar1:
        for i in range(1, scenario.periods):
            period_shocks[i] += scenario.ar1 * period_shocks[i - 1]
    if not scenario.shared_period_shock:
        # Each zone gets a separate period path, retaining serial dependence
        # but eliminating cross-zone common shocks.
        zone_period_shocks = rng.normal(
            0.0, scenario.period_sd,
            size=(2 * scenario.zones_per_cohort, scenario.periods),
        )
        if scenario.ar1:
            for i in range(1, scenario.periods):
                zone_period_shocks[:, i] += scenario.ar1 * zone_period_shocks[:, i - 1]
    else:
        zone_period_shocks = np.broadcast_to(
            period_shocks, (2 * scenario.zones_per_cohort, scenario.periods)
        )

    values = np.empty(len(records), dtype=float)
    window_components = np.empty(len(records), dtype=float)
    for i, (cohort, zone, period) in enumerate(zip(cohorts, zone_ids, event_periods)):
        future = (np.arange(period + 1, period + 7) % scenario.periods)
        overlapping_window = float(zone_period_shocks[zone, future].mean())
        window_components[i] = overlapping_window
        values[i] = (effect if cohort == 0 else 0.0) + zone_effects[zone] + \
            overlapping_window + rng.normal(0.0, 1.0)

    keep = np.ones(len(records), dtype=bool)
    for cohort, missing_rate in ((0, scenario.missing_rate_higher),
                                 (1, scenario.missing_rate_lower)):
        indices = np.flatnonzero(cohorts == cohort)
        keep[indices] = rng.random(len(indices)) >= missing_rate
    return pd.DataFrame({
        "cohort": cohorts[keep], "zone": zone_ids[keep],
        "period": event_periods[keep], "window_component": window_components[keep],
        "outcome": values[keep],
    })


def _kish(counts: np.ndarray) -> float:
    total = float(counts.sum())
    squares = float(np.square(counts).sum())
    return 0.0 if squares == 0 else total * total / squares


def support_diagnostics(events: pd.DataFrame) -> dict[str, float | int | bool]:
    """Report raw and concentration support; not an independence estimator."""
    group_counts = []
    for cohort in (0, 1):
        group = events.loc[events.cohort == cohort]
        zone_counts = group.groupby("zone").size().to_numpy(dtype=float)
        period_counts = group.groupby("period").size().to_numpy(dtype=float)
        block_counts = (group.period // BLOCK_LENGTH).value_counts().to_numpy(dtype=float)
        group_counts.append({
            "events": len(group), "zones": len(zone_counts),
            "periods": len(period_counts), "kish_zones": _kish(zone_counts),
            "kish_periods": _kish(period_counts),
            "blocks": len(block_counts), "kish_blocks": _kish(block_counts),
        })
    supported = all(
        g["events"] > 0 and g["zones"] >= SUPPORT_FLOOR and
        g["blocks"] >= SUPPORT_FLOOR for g in group_counts
    )
    return {
        "events_higher": group_counts[0]["events"],
        "events_lower": group_counts[1]["events"],
        "zones_higher": group_counts[0]["zones"],
        "zones_lower": group_counts[1]["zones"],
        "periods_higher": group_counts[0]["periods"],
        "periods_lower": group_counts[1]["periods"],
        "blocks_higher": group_counts[0]["blocks"],
        "blocks_lower": group_counts[1]["blocks"],
        "kish_zones_higher": group_counts[0]["kish_zones"],
        "kish_zones_lower": group_counts[1]["kish_zones"],
        "kish_periods_higher": group_counts[0]["kish_periods"],
        "kish_periods_lower": group_counts[1]["kish_periods"],
        "kish_blocks_higher": group_counts[0]["kish_blocks"],
        "kish_blocks_lower": group_counts[1]["kish_blocks"],
        "support_sufficient": supported,
    }


def _weighted_contrast(events: pd.DataFrame, weights: np.ndarray) -> float:
    cohort = events.cohort.to_numpy()
    values = events.outcome.to_numpy()
    means = []
    for label in (0, 1):
        mask = cohort == label
        denominator = weights[mask].sum()
        if denominator <= 0:
            return float("nan")
        means.append(float(np.dot(weights[mask], values[mask]) / denominator))
    return means[0] - means[1]


def _bootstrap_weights(events: pd.DataFrame, method: str, rng: np.random.Generator,
                       draws: int, block_length: int = BLOCK_LENGTH) -> np.ndarray:
    n = len(events)
    cohort = events.cohort.to_numpy()
    zone = events.zone.to_numpy()
    period = events.period.to_numpy()
    weights = np.zeros((draws, n), dtype=float)
    if method == "iid_negative_control":
        for label in (0, 1):
            idx = np.flatnonzero(cohort == label)
            picks = rng.integers(0, len(idx), size=(draws, len(idx)))
            rows = np.repeat(np.arange(draws), len(idx))
            counts = np.zeros((draws, len(idx)), dtype=float)
            np.add.at(counts, (rows, picks.reshape(-1)), 1.0)
            weights[:, idx] = counts
    elif method in {"zone_cluster", "crossed_product"}:
        zone_multiplicity = np.ones((draws, n), dtype=float)
        for label in (0, 1):
            idx = np.flatnonzero(cohort == label)
            ids, inverse = np.unique(zone[idx], return_inverse=True)
            picks = rng.integers(0, len(ids), size=(draws, len(ids)))
            rows = np.repeat(np.arange(draws), len(ids))
            cluster_counts = np.zeros((draws, len(ids)), dtype=float)
            np.add.at(cluster_counts, (rows, picks.reshape(-1)), 1.0)
            zone_multiplicity[:, idx] = cluster_counts[:, inverse]
        weights = zone_multiplicity
        if method == "crossed_product":
            time_counts = _calendar_block_counts(period, draws, rng, block_length)
            weights *= time_counts[:, period]
    elif method == "calendar_block":
        time_counts = _calendar_block_counts(period, draws, rng, block_length)
        weights = time_counts[:, period]
    else:
        raise ValueError(f"Unknown bootstrap method: {method}")
    return weights


def _calendar_block_counts(periods: np.ndarray, draws: int,
                           rng: np.random.Generator,
                           block_length: int) -> np.ndarray:
    total_periods = int(periods.max()) + 1
    blocks = math.ceil(total_periods / block_length)
    starts = rng.integers(0, total_periods, size=(draws, blocks))
    offsets = np.arange(block_length)
    sampled = (starts[:, :, None] + offsets[None, None, :]) % total_periods
    sampled = sampled.reshape(draws, -1)[:, :total_periods]
    counts = np.zeros((draws, total_periods), dtype=float)
    rows = np.repeat(np.arange(draws), total_periods)
    np.add.at(counts, (rows, sampled.reshape(-1)), 1.0)
    return counts


def _interval_from_draws(estimate: float, draws_values: np.ndarray,
                         requested_draws: int) -> dict[str, float | bool | int | str | None]:
    """Summarize bootstrap draws without hiding invalid replicate counts."""
    finite = np.asarray(draws_values, dtype=float)
    finite = finite[np.isfinite(finite)]
    valid = len(finite)
    fraction = valid / requested_draws
    if valid < math.ceil(0.90 * requested_draws):
        return {"estimate": estimate, "lower": float("nan"), "upper": float("nan"),
                "width": float("nan"), "inconclusive": True,
                "inconclusive_reason": "too_many_invalid_bootstrap_draws",
                "valid_draws": valid, "valid_draw_fraction": fraction}
    lower, upper = np.quantile(finite, [0.025, 0.975])
    return {"estimate": estimate, "lower": float(lower), "upper": float(upper),
            "width": float(upper - lower), "inconclusive": False,
            "inconclusive_reason": None, "valid_draws": valid,
            "valid_draw_fraction": fraction}


def bootstrap_interval(events: pd.DataFrame, method: str, *, seed: int,
                       draws: int = BOOTSTRAP_DRAWS,
                       block_length: int = BLOCK_LENGTH) -> dict[str, float | bool | int]:
    """Return percentile interval or an explicit inconclusive support result."""
    support = support_diagnostics(events)
    estimate = _weighted_contrast(events, np.ones(len(events)))
    if not support["support_sufficient"]:
        return {"estimate": estimate, "lower": float("nan"), "upper": float("nan"),
                "width": float("nan"), "inconclusive": True,
                "inconclusive_reason": "minimum_zone_or_calendar_block_support",
                "valid_draws": 0, "valid_draw_fraction": 0.0}
    rng = np.random.default_rng(seed)
    weights = _bootstrap_weights(events, method, rng, draws, block_length)
    cohort = events.cohort.to_numpy()
    values = events.outcome.to_numpy()
    means = []
    for label in (0, 1):
        mask = cohort == label
        numerators = (weights[:, mask] * values[None, mask]).sum(axis=1)
        denominators = weights[:, mask].sum(axis=1)
        means.append(np.divide(
            numerators, denominators,
            out=np.full(draws, np.nan, dtype=float), where=denominators > 0,
        ))
    vals = means[0] - means[1]
    return _interval_from_draws(estimate, vals, draws)


def run_simulation(*, repetitions: int = OUTER_REPETITIONS,
                   bootstrap_draws: int = BOOTSTRAP_DRAWS) -> pd.DataFrame:
    """Run fixed scenarios and return Monte Carlo operating-characteristic rows."""
    rows: list[dict[str, object]] = []
    # Each method's replicate-level statistics are retained for proper Monte
    # Carlo standard errors. A scenario's true contrast is the assigned effect.
    for si, scenario in enumerate(SCENARIOS):
        for ei, effect in enumerate((0.0, 0.25)):
            per_method: dict[str, list[dict[str, object]]] = {m: [] for m in METHODS}
            supports = []
            for rep in range(repetitions):
                events = generate_dataset(scenario, effect,
                                          _child_seed(si, ei, rep, 0))
                support = support_diagnostics(events)
                supports.append(support)
                for mi, method in enumerate(METHODS):
                    result = bootstrap_interval(
                        events, method,
                        seed=_child_seed(si, ei, rep, mi + 1),
                        draws=bootstrap_draws,
                    )
                    per_method[method].append(result)
            for method in METHODS:
                valid = [r for r in per_method[method] if not r["inconclusive"]]
                estimates = np.array([float(r["estimate"]) for r in valid])
                lowers = np.array([float(r["lower"]) for r in valid])
                uppers = np.array([float(r["upper"]) for r in valid])
                widths = uppers - lowers
                covers = ((lowers <= effect) & (uppers >= effect)).astype(float)
                rejects = ((lowers > 0) | (uppers < 0)).astype(float)
                rate = lambda values: float(np.mean(values)) if len(values) else float("nan")
                mcse = lambda p: math.sqrt(p * (1.0 - p) / len(values_for_rate)) if len(values_for_rate) and np.isfinite(p) else float("nan")
                values_for_rate = covers
                coverage, coverage_se = rate(covers), mcse(rate(covers))
                values_for_rate = rejects
                rejection, rejection_se = rate(rejects), mcse(rate(rejects))
                inconclusive_rate = 1.0 - len(valid) / repetitions
                support_inconclusive_rate = float(np.mean([
                    r.get("inconclusive_reason") == "minimum_zone_or_calendar_block_support"
                    for r in per_method[method]
                ]))
                bootstrap_failure_rate = float(np.mean([
                    r.get("inconclusive_reason") == "too_many_invalid_bootstrap_draws"
                    for r in per_method[method]
                ]))
                attempted = [r for r in per_method[method]
                             if r.get("inconclusive_reason") != "minimum_zone_or_calendar_block_support"]
                valid_fractions = [float(r["valid_draw_fraction"]) for r in attempted]
                all_event_counts = [s["events_higher"] + s["events_lower"] for s in supports]
                rows.append({
                    "scenario": scenario.name,
                    "true_effect": effect,
                    "method": method,
                    "repetitions": repetitions,
                    "bootstrap_draws": bootstrap_draws,
                    "valid_repetitions": len(valid),
                    "inconclusive_rate": inconclusive_rate,
                    "support_inconclusive_rate": support_inconclusive_rate,
                    "bootstrap_failure_rate": bootstrap_failure_rate,
                    "mean_valid_bootstrap_draw_fraction": float(np.mean(valid_fractions)) if valid_fractions else float("nan"),
                    "minimum_valid_bootstrap_draw_fraction": float(np.min(valid_fractions)) if valid_fractions else float("nan"),
                    "inconclusive_mcse": math.sqrt(inconclusive_rate * (1 - inconclusive_rate) / repetitions),
                    "bias": float(np.mean(estimates - effect)) if len(estimates) else float("nan"),
                    "bias_mcse": float(np.std(estimates - effect, ddof=1) / math.sqrt(len(estimates))) if len(estimates) > 1 else float("nan"),
                    "coverage_95": coverage,
                    "coverage_mcse": coverage_se,
                    "mean_interval_width": float(np.mean(widths)) if len(widths) else float("nan"),
                    "width_mcse": float(np.std(widths, ddof=1) / math.sqrt(len(widths))) if len(widths) > 1 else float("nan"),
                    "null_false_positive_rate": rejection if effect == 0 else float("nan"),
                    "null_false_positive_mcse": rejection_se if effect == 0 else float("nan"),
                    "power": rejection if effect != 0 else float("nan"),
                    "power_mcse": rejection_se if effect != 0 else float("nan"),
                    "mean_events": float(np.mean(all_event_counts)),
                    "mean_zones_per_cohort": float(np.mean([s["zones_higher"] + s["zones_lower"] for s in supports]) / 2),
                    "mean_periods_per_cohort": float(np.mean([s["periods_higher"] + s["periods_lower"] for s in supports]) / 2),
                    "mean_kish_zones_per_cohort": float(np.mean([s["kish_zones_higher"] + s["kish_zones_lower"] for s in supports]) / 2),
                    "mean_kish_periods_per_cohort": float(np.mean([s["kish_periods_higher"] + s["kish_periods_lower"] for s in supports]) / 2),
                    "support_floor_pass_rate": float(np.mean([s["support_sufficient"] for s in supports])),
                })
    return pd.DataFrame(rows)


def report_markdown(results: pd.DataFrame, runtime_seconds: float) -> str:
    view_columns = ["scenario", "true_effect", "method", "bias", "coverage_95",
                    "coverage_mcse", "mean_interval_width",
                    "null_false_positive_rate", "null_false_positive_mcse",
                    "power", "power_mcse", "inconclusive_rate",
                    "support_inconclusive_rate", "bootstrap_failure_rate",
                    "mean_valid_bootstrap_draw_fraction",
                    "minimum_valid_bootstrap_draw_fraction",
                    "mean_kish_zones_per_cohort", "mean_kish_periods_per_cohort"]
    selected = results[view_columns]
    header = "| " + " | ".join(selected.columns) + " |"
    divider = "| " + " | ".join("---" for _ in selected.columns) + " |"
    body = "\n".join(
        "| " + " | ".join(
            f"{value:.3f}" if isinstance(value, (float, np.floating)) and np.isfinite(value)
            else str(value)
            for value in row
        ) + " |"
        for row in selected.itertuples(index=False, name=None)
    )
    table = "\n".join((header, divider, body))
    return f"""# Synthetic dependence simulation report — V3 audit correction

> **SYNTHETIC — NOT MARKET EVIDENCE.** No project OHLCV, real event ledger,
> forward return, or project outcome label was read or calculated. The
> simulation is not evidence that a candidate estimator is valid for markets.

## Fixed protocol

Design was documented before execution in
[`SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md`](SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md).
Master seed: `{MASTER_SEED}`. Scenario/replicate/method seeds are derived
deterministically. Monte Carlo repetitions per scenario/effect cell:
`{int(results.repetitions.iloc[0])}`. Bootstrap draws per dataset:
`{int(results.bootstrap_draws.iloc[0])}`. Runtime: `{runtime_seconds:.2f}` seconds.
The estimand is the generated event-weighted higher-minus-lower mean contrast;
nonzero synthetic effect is 0.25. Rates are shown with Monte Carlo standard
errors in the table and full metrics are in the CSV. The
4-zone/4-occupied-six-period-block support floor is a
mechanical toy guard, not a real-data adequacy recommendation. V1 exposed an
inadequate generic period-count floor: five periods passed despite yielding a
degenerate six-period block bootstrap. V1 outputs are retained unchanged; V2
adds a method-aligned support guard and uses separate output names.

Null false-positive rate and alternative power use a two-sided percentile
interval-excludes-zero rule. This is an operating-characteristic diagnostic,
not the proposed directional decision rule for SUPPORT_TOUCH_001.

## Operating characteristics by declared synthetic scenario

{table}

Full metrics and Monte Carlo standard errors are in
`SYNTHETIC_DEPENDENCE_SIMULATION_RESULTS_V3.csv`.

## Interpretation

These results describe only the stated generators and finite resampling
algorithms. Calendar blocks can retain local shared shocks and overlapping
windows but omit persistent zone effects spanning blocks. Zone resampling
preserves repeated touches within zones but misses shared calendar shocks.
Product weights attempt both dimensions but do not prove validity under
crossed dependence or serial dependence. IID resampling is a deliberately
misspecified negative control. Few zones/periods trigger `inconclusive` by
the declared mechanical support guard. Cohort-specific missingness can alter
the observed-case estimand. No candidate is selected as an approved method;
no synthetic adequacy threshold is transferred to SUPPORT_TOUCH_001.

V3 preserves the V2 DGP, seeds, repetitions, resampling algorithms, and
adequacy floor. It adds valid-bootstrap-draw fractions and separates support
inconclusives from bootstrap-failure inconclusives; it does not retune an
estimator. The reported valid-draw fraction makes bootstrap exclusions auditable. A
replicate becomes inconclusive if fewer than 90% of its requested bootstrap
draws are finite; support-floor and bootstrap-failure inconclusives are
reported separately. The practical policy remains blocked pending an approved sampling model,
credible dependence/block assumptions, cluster and time support criteria,
precision target, and multiplicity/decision rules. This simulation cannot
estimate those from the project data and does not resolve them.
"""


def write_no_clobber(path: Path, content: str | bytes) -> None:
    mode = "xb"
    payload = content.encode("utf-8") if isinstance(content, str) else content
    with path.open(mode) as handle:
        handle.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=OUTER_REPETITIONS)
    parser.add_argument("--bootstrap-draws", type=int, default=BOOTSTRAP_DRAWS)
    args = parser.parse_args()
    started = time.perf_counter()
    results = run_simulation(repetitions=args.repetitions,
                             bootstrap_draws=args.bootstrap_draws)
    elapsed = time.perf_counter() - started
    report_path = Path(__file__).with_name("SYNTHETIC_DEPENDENCE_SIMULATION_REPORT_V3.md")
    results_path = Path(__file__).with_name("SYNTHETIC_DEPENDENCE_SIMULATION_RESULTS_V3.csv")
    # Refuse both outputs before writing either one.
    if report_path.exists() or results_path.exists():
        raise FileExistsError("Refusing to overwrite an existing synthetic simulation artifact")
    write_no_clobber(results_path, results.to_csv(index=False, float_format="%.8g"))
    write_no_clobber(report_path, report_markdown(results, elapsed))
    print(f"wrote {results_path}")
    print(f"wrote {report_path}")
    print(f"runtime_seconds={elapsed:.2f}; rows={len(results)}")


if __name__ == "__main__":
    main()
