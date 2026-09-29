# Point in time

Strict PIT uses only `vintage_date <= origin` and `reference_date <= origin`. The first backfill is stamped with the collection date, so earlier origins have no invented historical coverage. Reconstructed PIT requires an independently verified per-row release date and is explicitly labelled `reconstructed`; current revised values can still differ from original releases. Same-day revisions collapse to the latest collected value. Target truth uses an explicit `truth_as_of`, separate from feature origin. No sub-day claims or retractions are supported.
