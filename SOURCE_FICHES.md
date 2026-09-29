# Source fiches and collection decisions

The [source registry](source_registry.csv) records publisher, page, native table/series identity, cadence, release lag, revision exposure, point-in-time quality, automation feasibility, licence status, economic channel, and owning collector. `PENDING_VERIFICATION` is a deliberate gate, not a native identifier. Candidate rows cannot enter the experiment merely because a publisher page exists.

## Verified within an existing collector

- **National rental stock index (STATSNZ_SPI_CPIM_SE9041S)**: live metadata from `collector_statsnz_spi` identifies the native monthly series and official source URL. The existing export already supplies it; no new ingestion branch is needed. Strict as-of experiments start with collected vintages, and the feature uses only observations available by the forecast origin.

## Next publisher-owned implementations

- **Demand**: Stats NZ Retail Trade Survey (quarterly). Assign to the existing Stats NZ publisher collector. Resolve native table ID, downloadable format, first reference period, release-date calendar, revisions, licence, and source-specific assertions before activating a series.
- **Costs and expectations**: MBIE QSDEP electricity retail costs: assign to collector_mbie_nz and verify workbook layout. RBNZ M14 expectations: assign to collector_rbnz_nz, contingent on live source access. Stats NZ Business Price Indexes and Labour Cost Index remain quarterly candidates under the existing Stats NZ collector.
- **Additional sources**: Electricity Authority wholesale data requires export and source-owner validation. Ministry of Transport freight information is annual and not a direct price index. Stats NZ merchandise trade reports values and volumes, not import prices.

## Acceptance gate for any candidate

Record the exact official native ID and download URL, cadence and earliest history, publication timing, revision behavior, unattended retrieval result, data format and licence. Add a parser and a known-answer source validation to the owning collector, persist the standard observation/vintage contract, and run a live smoke before marking it active. Historical publisher backfills are sensitivity data, never silently relabeled as contemporaneously observed vintages.
