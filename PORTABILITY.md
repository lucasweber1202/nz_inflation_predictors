# Portability

Python 3.11+ standard library powers the engine; pytest is needed only for tests. This repository imports no collector. Export time_series rows from PostgreSQL or Databricks into CSV with stable ISO dates and a collected-at timestamp; keep secrets and raw payloads outside Git. The CSV contract is read-only, with no database credential required.

Results are versioned JSON (`schema_version: 1`) with `country,target,predictor,model,pit_mode,origin,target_period,horizon,train_start,train_end,feature_cutoff,feature_window_start,feature_window_end,feature_value,truth_as_of,prediction,actual,error,previous`; summary fields are `n,rmse,mae,bias,directional_accuracy`. Inputs and origin order produce deterministic sorted rows.
