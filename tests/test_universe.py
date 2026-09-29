"""Keep the published universe internally consistent."""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
ROWS = list(csv.DictReader((ROOT / "universe.csv").open(newline="")))
COLLECTOR_PREFIX = {
    "collector_statsnz_cpi": "STATSNZ_CPI_",
    "collector_statsnz_spi": "STATSNZ_SPI_",
    "collector_mbie_nz": "MBIE_",
    "collector_rbnz_nz": "RBNZ_",
}
OBSOLETE_AUTHORITIES = (
    "8e4613b36c2808a7de234934a81bb26f7a22d367",
    "723f8633bbd367ad9cca0a199e84b10fd355da36",
)
STALE_PHRASES = (
    "vocabulary pending",
    "pending upstream pr",
    "awaits upstream template",
)


def test_active_identity_and_coverage() -> None:
    assert ROWS
    assert len({row["series_id"] for row in ROWS if row["series_id"]}) == sum(
        bool(row["series_id"]) for row in ROWS
    )
    assert (
        sum(row["role"] == "target" and row["status"] == "active" for row in ROWS) == 1
    )
    for row in ROWS:
        assert row["role"] in {"target", "predictor"}, row
        assert row["status"] in {"active", "candidate", "deprecated"}
        assert row["priority"] in {"P0", "P1", "P2"}
        assert all(
            row[key]
            for key in (
                "role",
                "name",
                "source",
                "collector_repo",
                "frequency",
                "pit_limit",
                "coverage_note",
            )
        )
        if row["status"] == "active":
            assert row["series_id"] and row["latest_verified"] and row["history_start"]
            assert row["series_id"].startswith(COLLECTOR_PREFIX[row["collector_repo"]])
            assert re.fullmatch(
                r"\d{4}-\d{2}", row["latest_verified"]
            ) and re.fullmatch(r"\d{4}-\d{2}", row["history_start"])
            assert row["history_start"] <= row["latest_verified"]
        if row["status"] == "candidate":
            assert not row["series_id"]


def test_authority_is_current() -> None:
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).split()
    for path in tracked:
        if path == "tests/test_universe.py":
            continue
        text = (ROOT / path).read_text(encoding="utf-8").lower()
        assert not any(sha in text for sha in OBSOLETE_AUTHORITIES), path
        assert not any(phrase in text for phrase in STALE_PHRASES), path
