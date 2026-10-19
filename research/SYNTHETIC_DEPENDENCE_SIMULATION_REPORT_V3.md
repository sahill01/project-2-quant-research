# Synthetic dependence simulation report — V3 audit correction

> **SYNTHETIC — NOT MARKET EVIDENCE.** No project OHLCV, real event ledger,
> forward return, or project outcome label was read or calculated. The
> simulation is not evidence that a candidate estimator is valid for markets.

## Fixed protocol

Design was documented before execution in
[`SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md`](SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md).
Master seed: `20261020`. Scenario/replicate/method seeds are derived
deterministically. Monte Carlo repetitions per scenario/effect cell:
`300`. Bootstrap draws per dataset:
`399`. Runtime: `151.85` seconds.
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

| scenario | true_effect | method | bias | coverage_95 | coverage_mcse | mean_interval_width | null_false_positive_rate | null_false_positive_mcse | power | power_mcse | inconclusive_rate | support_inconclusive_rate | bootstrap_failure_rate | mean_valid_bootstrap_draw_fraction | minimum_valid_bootstrap_draw_fraction | mean_kish_zones_per_cohort | mean_kish_periods_per_cohort |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| independent_baseline | 0.000 | calendar_block | -0.010 | 0.920 | 0.016 | 0.679 | 0.080 | 0.016 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.778 |
| independent_baseline | 0.000 | zone_cluster | -0.010 | 0.937 | 0.014 | 0.697 | 0.063 | 0.014 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.778 |
| independent_baseline | 0.000 | crossed_product | -0.010 | 1.000 | 0.000 | 1.186 | 0.000 | 0.000 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.778 |
| independent_baseline | 0.000 | iid_negative_control | -0.010 | 0.950 | 0.013 | 0.699 | 0.050 | 0.013 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.778 |
| independent_baseline | 0.250 | calendar_block | -0.008 | 0.907 | 0.017 | 0.686 | nan | nan | 0.293 | 0.026 | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.998 |
| independent_baseline | 0.250 | zone_cluster | -0.008 | 0.937 | 0.014 | 0.705 | nan | nan | 0.283 | 0.026 | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.998 |
| independent_baseline | 0.250 | crossed_product | -0.008 | 0.993 | 0.005 | 1.197 | nan | nan | 0.043 | 0.012 | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.998 |
| independent_baseline | 0.250 | iid_negative_control | -0.008 | 0.930 | 0.015 | 0.701 | nan | nan | 0.277 | 0.026 | 0 | 0 | 0 | 1.000 | 1.000 | 60.000 | 39.998 |
| persistent_repeated_zones | 0.000 | calendar_block | -0.013 | 0.780 | 0.024 | 0.478 | 0.220 | 0.024 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.999 |
| persistent_repeated_zones | 0.000 | zone_cluster | -0.013 | 0.910 | 0.017 | 0.699 | 0.090 | 0.017 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.999 |
| persistent_repeated_zones | 0.000 | crossed_product | -0.013 | 0.980 | 0.008 | 0.972 | 0.020 | 0.008 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.999 |
| persistent_repeated_zones | 0.000 | iid_negative_control | -0.013 | 0.807 | 0.023 | 0.504 | 0.193 | 0.023 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.999 |
| persistent_repeated_zones | 0.250 | calendar_block | 0.002 | 0.837 | 0.021 | 0.485 | nan | nan | 0.527 | 0.029 | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.928 |
| persistent_repeated_zones | 0.250 | zone_cluster | 0.002 | 0.957 | 0.012 | 0.698 | nan | nan | 0.277 | 0.026 | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.928 |
| persistent_repeated_zones | 0.250 | crossed_product | 0.002 | 1.000 | 0.000 | 0.979 | nan | nan | 0.083 | 0.016 | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.928 |
| persistent_repeated_zones | 0.250 | iid_negative_control | 0.002 | 0.857 | 0.020 | 0.505 | nan | nan | 0.513 | 0.029 | 0 | 0 | 0 | 1.000 | 1.000 | 24.000 | 55.928 |
| serial_overlapping_shared_shocks | 0.000 | calendar_block | -0.022 | 0.860 | 0.020 | 0.512 | 0.140 | 0.020 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.259 |
| serial_overlapping_shared_shocks | 0.000 | zone_cluster | -0.022 | 0.933 | 0.014 | 0.682 | 0.067 | 0.014 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.259 |
| serial_overlapping_shared_shocks | 0.000 | crossed_product | -0.022 | 1.000 | 0.000 | 0.984 | 0.000 | 0.000 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.259 |
| serial_overlapping_shared_shocks | 0.000 | iid_negative_control | -0.022 | 0.887 | 0.018 | 0.530 | 0.113 | 0.018 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.259 |
| serial_overlapping_shared_shocks | 0.250 | calendar_block | -0.026 | 0.847 | 0.021 | 0.517 | nan | nan | 0.463 | 0.029 | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.028 |
| serial_overlapping_shared_shocks | 0.250 | zone_cluster | -0.026 | 0.923 | 0.015 | 0.676 | nan | nan | 0.260 | 0.025 | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.028 |
| serial_overlapping_shared_shocks | 0.250 | crossed_product | -0.026 | 0.987 | 0.007 | 0.986 | nan | nan | 0.043 | 0.012 | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.028 |
| serial_overlapping_shared_shocks | 0.250 | iid_negative_control | -0.026 | 0.847 | 0.021 | 0.528 | nan | nan | 0.433 | 0.029 | 0 | 0 | 0 | 1.000 | 1.000 | 32.000 | 67.028 |
| unequal_concentrated_zone_sizes | 0.000 | calendar_block | 0.009 | 0.730 | 0.026 | 0.475 | 0.270 | 0.026 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.238 |
| unequal_concentrated_zone_sizes | 0.000 | zone_cluster | 0.009 | 0.943 | 0.013 | 0.749 | 0.057 | 0.013 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.238 |
| unequal_concentrated_zone_sizes | 0.000 | crossed_product | 0.009 | 0.993 | 0.005 | 1.018 | 0.007 | 0.005 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.238 |
| unequal_concentrated_zone_sizes | 0.000 | iid_negative_control | 0.009 | 0.790 | 0.024 | 0.501 | 0.210 | 0.024 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.238 |
| unequal_concentrated_zone_sizes | 0.250 | calendar_block | -0.009 | 0.690 | 0.027 | 0.482 | nan | nan | 0.497 | 0.029 | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.388 |
| unequal_concentrated_zone_sizes | 0.250 | zone_cluster | -0.009 | 0.920 | 0.016 | 0.740 | nan | nan | 0.283 | 0.026 | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.388 |
| unequal_concentrated_zone_sizes | 0.250 | crossed_product | -0.009 | 0.983 | 0.007 | 1.011 | nan | nan | 0.103 | 0.018 | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.388 |
| unequal_concentrated_zone_sizes | 0.250 | iid_negative_control | -0.009 | 0.707 | 0.026 | 0.499 | nan | nan | 0.487 | 0.029 | 0 | 0 | 0 | 1.000 | 1.000 | 14.720 | 58.388 |
| few_independent_zones | 0.000 | calendar_block | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.610 |
| few_independent_zones | 0.000 | zone_cluster | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.610 |
| few_independent_zones | 0.000 | crossed_product | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.610 |
| few_independent_zones | 0.000 | iid_negative_control | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.610 |
| few_independent_zones | 0.250 | calendar_block | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.772 |
| few_independent_zones | 0.250 | zone_cluster | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.772 |
| few_independent_zones | 0.250 | crossed_product | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.772 |
| few_independent_zones | 0.250 | iid_negative_control | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 3.000 | 26.772 |
| few_calendar_periods | 0.000 | calendar_block | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.793 |
| few_calendar_periods | 0.000 | zone_cluster | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.793 |
| few_calendar_periods | 0.000 | crossed_product | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.793 |
| few_calendar_periods | 0.000 | iid_negative_control | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.793 |
| few_calendar_periods | 0.250 | calendar_block | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.789 |
| few_calendar_periods | 0.250 | zone_cluster | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.789 |
| few_calendar_periods | 0.250 | crossed_product | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.789 |
| few_calendar_periods | 0.250 | iid_negative_control | nan | nan | nan | nan | nan | nan | nan | nan | 1 | 1 | 0 | nan | nan | 30.000 | 4.789 |
| cohort_differential_missingness | 0.000 | calendar_block | -0.012 | 0.907 | 0.017 | 0.608 | 0.093 | 0.017 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 27.522 | 46.333 |
| cohort_differential_missingness | 0.000 | zone_cluster | -0.012 | 0.933 | 0.014 | 0.714 | 0.067 | 0.014 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 27.522 | 46.333 |
| cohort_differential_missingness | 0.000 | crossed_product | -0.012 | 1.000 | 0.000 | 1.111 | 0.000 | 0.000 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 27.522 | 46.333 |
| cohort_differential_missingness | 0.000 | iid_negative_control | -0.012 | 0.913 | 0.016 | 0.634 | 0.087 | 0.016 | nan | nan | 0 | 0 | 0 | 1.000 | 1.000 | 27.522 | 46.333 |
| cohort_differential_missingness | 0.250 | calendar_block | 0.024 | 0.887 | 0.018 | 0.614 | nan | nan | 0.410 | 0.028 | 0 | 0 | 0 | 1.000 | 1.000 | 27.501 | 46.427 |
| cohort_differential_missingness | 0.250 | zone_cluster | 0.024 | 0.933 | 0.014 | 0.708 | nan | nan | 0.287 | 0.026 | 0 | 0 | 0 | 1.000 | 1.000 | 27.501 | 46.427 |
| cohort_differential_missingness | 0.250 | crossed_product | 0.024 | 0.993 | 0.005 | 1.114 | nan | nan | 0.077 | 0.015 | 0 | 0 | 0 | 1.000 | 1.000 | 27.501 | 46.427 |
| cohort_differential_missingness | 0.250 | iid_negative_control | 0.024 | 0.897 | 0.018 | 0.633 | nan | nan | 0.400 | 0.028 | 0 | 0 | 0 | 1.000 | 1.000 | 27.501 | 46.427 |

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
