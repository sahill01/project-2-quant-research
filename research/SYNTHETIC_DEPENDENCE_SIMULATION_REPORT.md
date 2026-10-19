# Synthetic dependence simulation report — V1 initial run (superseded by V2)

> **SYNTHETIC — NOT MARKET EVIDENCE.** No project OHLCV, real event ledger,
> forward return, or project outcome label was read or calculated. The
> simulation is not evidence that a candidate estimator is valid for markets.

## Fixed protocol

Design was documented before execution in
[`SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md`](SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md).
Master seed: `20261020`. Scenario/replicate/method seeds are derived
deterministically. Monte Carlo repetitions per scenario/effect cell:
`300`. Bootstrap draws per dataset:
`399`. Runtime: `139.17` seconds.
The estimand is the generated event-weighted higher-minus-lower mean contrast;
nonzero synthetic effect is 0.25. Percentages include Monte Carlo standard
errors in the CSV. The 4-zone/4-period support floor is a mechanical toy guard,
not a real-data adequacy recommendation.

## Operating characteristics by declared synthetic scenario

| scenario | true_effect | method | bias | coverage_95 | mean_interval_width | null_false_positive_rate | power | inconclusive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| independent_baseline | 0.000 | calendar_block | -0.010 | 0.920 | 0.679 | 0.080 | nan | 0.000 |
| independent_baseline | 0.000 | zone_cluster | -0.010 | 0.937 | 0.697 | 0.063 | nan | 0.000 |
| independent_baseline | 0.000 | crossed_product | -0.010 | 1.000 | 1.186 | 0.000 | nan | 0.000 |
| independent_baseline | 0.000 | iid_negative_control | -0.010 | 0.950 | 0.699 | 0.050 | nan | 0.000 |
| independent_baseline | 0.250 | calendar_block | -0.008 | 0.907 | 0.686 | nan | 0.293 | 0.000 |
| independent_baseline | 0.250 | zone_cluster | -0.008 | 0.937 | 0.705 | nan | 0.283 | 0.000 |
| independent_baseline | 0.250 | crossed_product | -0.008 | 0.993 | 1.197 | nan | 0.043 | 0.000 |
| independent_baseline | 0.250 | iid_negative_control | -0.008 | 0.930 | 0.701 | nan | 0.277 | 0.000 |
| persistent_repeated_zones | 0.000 | calendar_block | -0.013 | 0.780 | 0.478 | 0.220 | nan | 0.000 |
| persistent_repeated_zones | 0.000 | zone_cluster | -0.013 | 0.910 | 0.699 | 0.090 | nan | 0.000 |
| persistent_repeated_zones | 0.000 | crossed_product | -0.013 | 0.980 | 0.972 | 0.020 | nan | 0.000 |
| persistent_repeated_zones | 0.000 | iid_negative_control | -0.013 | 0.807 | 0.504 | 0.193 | nan | 0.000 |
| persistent_repeated_zones | 0.250 | calendar_block | 0.002 | 0.837 | 0.485 | nan | 0.527 | 0.000 |
| persistent_repeated_zones | 0.250 | zone_cluster | 0.002 | 0.957 | 0.698 | nan | 0.277 | 0.000 |
| persistent_repeated_zones | 0.250 | crossed_product | 0.002 | 1.000 | 0.979 | nan | 0.083 | 0.000 |
| persistent_repeated_zones | 0.250 | iid_negative_control | 0.002 | 0.857 | 0.505 | nan | 0.513 | 0.000 |
| serial_overlapping_shared_shocks | 0.000 | calendar_block | -0.022 | 0.860 | 0.512 | 0.140 | nan | 0.000 |
| serial_overlapping_shared_shocks | 0.000 | zone_cluster | -0.022 | 0.933 | 0.682 | 0.067 | nan | 0.000 |
| serial_overlapping_shared_shocks | 0.000 | crossed_product | -0.022 | 1.000 | 0.984 | 0.000 | nan | 0.000 |
| serial_overlapping_shared_shocks | 0.000 | iid_negative_control | -0.022 | 0.887 | 0.530 | 0.113 | nan | 0.000 |
| serial_overlapping_shared_shocks | 0.250 | calendar_block | -0.026 | 0.847 | 0.517 | nan | 0.463 | 0.000 |
| serial_overlapping_shared_shocks | 0.250 | zone_cluster | -0.026 | 0.923 | 0.676 | nan | 0.260 | 0.000 |
| serial_overlapping_shared_shocks | 0.250 | crossed_product | -0.026 | 0.987 | 0.986 | nan | 0.043 | 0.000 |
| serial_overlapping_shared_shocks | 0.250 | iid_negative_control | -0.026 | 0.847 | 0.528 | nan | 0.433 | 0.000 |
| unequal_concentrated_zone_sizes | 0.000 | calendar_block | 0.009 | 0.730 | 0.475 | 0.270 | nan | 0.000 |
| unequal_concentrated_zone_sizes | 0.000 | zone_cluster | 0.009 | 0.943 | 0.749 | 0.057 | nan | 0.000 |
| unequal_concentrated_zone_sizes | 0.000 | crossed_product | 0.009 | 0.993 | 1.018 | 0.007 | nan | 0.000 |
| unequal_concentrated_zone_sizes | 0.000 | iid_negative_control | 0.009 | 0.790 | 0.501 | 0.210 | nan | 0.000 |
| unequal_concentrated_zone_sizes | 0.250 | calendar_block | -0.009 | 0.690 | 0.482 | nan | 0.497 | 0.000 |
| unequal_concentrated_zone_sizes | 0.250 | zone_cluster | -0.009 | 0.920 | 0.740 | nan | 0.283 | 0.000 |
| unequal_concentrated_zone_sizes | 0.250 | crossed_product | -0.009 | 0.983 | 1.011 | nan | 0.103 | 0.000 |
| unequal_concentrated_zone_sizes | 0.250 | iid_negative_control | -0.009 | 0.707 | 0.499 | nan | 0.487 | 0.000 |
| few_independent_zones | 0.000 | calendar_block | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.000 | zone_cluster | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.000 | crossed_product | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.000 | iid_negative_control | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.250 | calendar_block | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.250 | zone_cluster | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.250 | crossed_product | nan | nan | nan | nan | nan | 1.000 |
| few_independent_zones | 0.250 | iid_negative_control | nan | nan | nan | nan | nan | 1.000 |
| few_calendar_periods | 0.000 | calendar_block | 0.029 | 0.000 | 0.000 | 1.000 | nan | 0.000 |
| few_calendar_periods | 0.000 | zone_cluster | 0.029 | 0.947 | 0.644 | 0.053 | nan | 0.000 |
| few_calendar_periods | 0.000 | crossed_product | 0.029 | 0.947 | 0.644 | 0.053 | nan | 0.000 |
| few_calendar_periods | 0.000 | iid_negative_control | 0.029 | 0.907 | 0.605 | 0.093 | nan | 0.000 |
| few_calendar_periods | 0.250 | calendar_block | -0.020 | 0.000 | 0.000 | nan | 1.000 | 0.000 |
| few_calendar_periods | 0.250 | zone_cluster | -0.020 | 0.927 | 0.637 | nan | 0.307 | 0.000 |
| few_calendar_periods | 0.250 | crossed_product | -0.020 | 0.913 | 0.637 | nan | 0.317 | 0.000 |
| few_calendar_periods | 0.250 | iid_negative_control | -0.020 | 0.897 | 0.598 | nan | 0.353 | 0.000 |
| cohort_differential_missingness | 0.000 | calendar_block | -0.012 | 0.907 | 0.608 | 0.093 | nan | 0.000 |
| cohort_differential_missingness | 0.000 | zone_cluster | -0.012 | 0.933 | 0.714 | 0.067 | nan | 0.000 |
| cohort_differential_missingness | 0.000 | crossed_product | -0.012 | 1.000 | 1.111 | 0.000 | nan | 0.000 |
| cohort_differential_missingness | 0.000 | iid_negative_control | -0.012 | 0.913 | 0.634 | 0.087 | nan | 0.000 |
| cohort_differential_missingness | 0.250 | calendar_block | 0.024 | 0.887 | 0.614 | nan | 0.410 | 0.000 |
| cohort_differential_missingness | 0.250 | zone_cluster | 0.024 | 0.933 | 0.708 | nan | 0.287 | 0.000 |
| cohort_differential_missingness | 0.250 | crossed_product | 0.024 | 0.993 | 1.114 | nan | 0.077 | 0.000 |
| cohort_differential_missingness | 0.250 | iid_negative_control | 0.024 | 0.897 | 0.633 | nan | 0.400 | 0.000 |

Full metrics and Monte Carlo standard errors are in
`SYNTHETIC_DEPENDENCE_SIMULATION_RESULTS.csv`.

## V1 status

This initial run is retained for auditability. Its generic four-period support floor was inadequate for the six-period moving-block bootstrap; the five-period case produced degenerate intervals. Use the separately named V2 report and results for the corrected mechanical support gate.

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

The practical policy remains blocked pending an approved sampling model,
credible dependence/block assumptions, cluster and time support criteria,
precision target, and multiplicity/decision rules. This simulation cannot
estimate those from the project data and does not resolve them.
