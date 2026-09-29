# Methodology

Run historical mean, last value, AR(p), and AR(p) with a predictor from the same persisted time-series contract. Expand or roll the training history at each origin. Evaluate one-step predictions against an explicitly chosen target truth vintage with RMSE, MAE, bias, and directional accuracy. The sample is conditional on available vintages. Rank predictors only after real pseudo-OOS evaluation on common origins; no ranking is published here. Turning-point metrics require a declared threshold and sufficient observed turns.

## Governed features and fair comparison

`predictor_map.csv` declares target frequency, within-period aggregation, transformation, lag in target periods and availability rule. Approved defaults use observed partial-period levels: mean for daily/weekly prices (and monthly price indexes into quarterly CPI), last for monthly rates. These are descriptive baseline features, not empirically selected transformations. Annual-to-monthly and quarterly-to-monthly mappings remain `PENDING_RESEARCH`; no implicit interpolation is permitted. Difference and percent change, or sum for a genuine flow series, require an explicit governed row. A lag of one uses the equivalent date in the previous target period.

At each forecast origin, the feature takes only observed references and vintages available by that end-of-day cutoff. Historical ARX training features are rebuilt at their own shifted historical origins; the current revised predictor history cannot stand in for what earlier forecasts knew. The target period is computed from target frequency and explicit horizon, never selected as the next row present in a file. A missing target period removes that origin from the result. Historical truth is selected separately at `truth_as_of`.

`compare_common_sample()` intersects `(origin, target_period)` across model outputs with matching country, target, frequency, horizon, PIT mode and truth vintage. It recomputes metrics on that intersection and rejects mismatched actual values. No cross-predictor ranking is published until real vintage exports yield a defensible common sample. Turning-point metric: `NOT_APPLICABLE_UNTIL_THRESHOLD_DEFINED`.
