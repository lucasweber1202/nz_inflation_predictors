# Portability

Python 3.11+ standard library powers the engine; pytest is needed only for tests. This repository imports no collector. Export time_series rows from PostgreSQL or Databricks into CSV with stable ISO dates and a collected-at timestamp; keep secrets and raw payloads outside Git. The CSV contract is read-only, with no database credential required.
