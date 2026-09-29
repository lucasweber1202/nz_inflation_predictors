# Methodology

Run historical mean, last value, AR(p), and AR(p) with a predictor from the same persisted time-series contract. Expand or roll the training history at each origin. Evaluate one-step predictions against an explicitly chosen target truth vintage with RMSE, MAE, bias, and directional accuracy. The sample is conditional on available vintages. Rank predictors only after real pseudo-OOS evaluation on common origins; no ranking is published here. Turning-point metrics require a declared threshold and sufficient observed turns.
