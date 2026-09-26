"""Keep the published universe internally consistent."""
from __future__ import annotations

import csv
from pathlib import Path

ROWS = list(csv.DictReader((Path(__file__).parents[1] / "universe.csv").open(newline="")))


def test_active_identity_and_coverage() -> None:
    assert ROWS
    assert len({row["series_id"] for row in ROWS if row["series_id"]}) == sum(bool(row["series_id"]) for row in ROWS)
    assert sum(row["role"] == "target" and row["status"] == "active" for row in ROWS) == 1
    for row in ROWS:
        assert row["status"] in {"active", "candidate", "deprecated"}
        assert row["priority"] in {"P0", "P1", "P2"}
        assert all(row[key] for key in ("role", "name", "source", "collector_repo", "frequency", "pit_limit", "coverage_note"))
        if row["status"] == "active":
            assert row["series_id"] and row["latest_verified"]
        if row["status"] == "candidate":
            assert not row["series_id"]
