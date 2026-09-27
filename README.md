# New Zealand inflation predictors: operational universe

`universe.csv` is the governed target/predictor catalogue, not a forecasting
model. `active` IDs are verified end to end (official source, collector run on
PostgreSQL, observations spot-checked against the source file). `candidate`
rows are explicit gaps with a blank `series_id`.

The target is the Stats NZ quarterly all-groups CPI (`STATSNZ_CPI_CPIQ_SE9A`).
`collector_statsnz_cpi` persists the official Table 8 base expenditure weights
and the CPI hierarchy and validates them against the published index before
every write (see that repository's METHODOLOGY). Current CSV backfills are not
historical point-in-time snapshots; every collector stores the collection date
as `vintage_date`.

The two RBNZ rows stay `candidate` although `collector_rbnz_nz` is implemented
and tested: RBNZ serves its statistics behind Cloudflare and admits automated
clients only from allowlisted static IPs, so no live observation has been
verified. They become `active` after the first allowlisted run passes
`RBNZ_LIVE_SMOKE=1`.

The expected sign is only an economic hypothesis and can change with lag and
regime. Sources: [Stats NZ CPI](https://www.stats.govt.nz/information-releases/consumers-price-index-june-2026-quarter/),
[Stats NZ SPI](https://www.stats.govt.nz/information-releases/selected-price-indexes-august-2026/),
[MBIE fuel](https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/energy-statistics-and-modelling/energy-statistics/weekly-fuel-price-monitoring),
[RBNZ B1](https://www.rbnz.govt.nz/statistics/series/exchange-and-interest-rates/exchange-rates-and-the-trade-weighted-index),
[RBNZ B2](https://www.rbnz.govt.nz/statistics/series/exchange-and-interest-rates/wholesale-interest-rates).
Authority: Masuko template main `723f8633bbd367ad9cca0a199e84b10fd355da36`
(`NZD` is in its `metadata.country` vocabulary). Last verified 2026-09-27.
