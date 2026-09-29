from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_registries() -> None:
    universe = load("universe.csv")
    sources = load("source_registry.csv")
    targets = load("target_registry.csv")
    predictors = load("predictor_map.csv")
    assert len(targets) == 1 and targets[0]["status"] == "active"
    assert targets[0]["series_id"] == next(
        r["series_id"] for r in universe if r["role"] == "target"
    )
    assert len(predictors) == sum(r["role"] == "predictor" for r in universe)
    assert len({r["series_id"] for r in predictors if r["series_id"]}) == sum(
        bool(r["series_id"]) for r in predictors
    )
    assert all(
        r["series_table_id"] == "PENDING_VERIFICATION"
        for r in sources
        if r["status"] == "candidate"
        and not any(u["source"] == r["dataset"] and u["series_id"] for u in universe)
    )
    assert all(r["source_url"].startswith("https://") for r in sources)
    assert not any(
        "collector_" in line
        for line in (ROOT / "scripts/engine.py").read_text().splitlines()
        if line.startswith(("import ", "from "))
    )
