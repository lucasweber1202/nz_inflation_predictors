"""Standalone end-of-day inflation research on persisted collector CSV contracts.

The module is copied into each country repository. It never imports a collector.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Observation:
    series_id: str
    reference_date: date
    vintage_date: date
    value: float
    collected_at: str
    release_date: date | None = None


def read_contract(path: Path) -> list[Observation]:
    """Read exported time_series; optional release_date requires verified provenance."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        value = float(row["value"])
        if not math.isfinite(value):
            raise ValueError("nonfinite observation")
        result.append(
            Observation(
                row["series_id"],
                date.fromisoformat(row["reference_date"]),
                date.fromisoformat(row["vintage_date"]),
                value,
                row["collected_at"],
                date.fromisoformat(row["release_date"])
                if row.get("release_date")
                else None,
            )
        )
    if len({(r.series_id, r.reference_date, r.vintage_date) for r in result}) != len(
        result
    ):
        raise ValueError("duplicate collector vintage")
    return result


def as_of(
    rows: list[Observation], origin: date, *, mode: str = "strict"
) -> dict[tuple[str, date], Observation]:
    """End-of-day vintage cut; reconstruction needs an independently verified release date."""
    if mode not in {"strict", "reconstructed"}:
        raise ValueError("unknown PIT mode")
    chosen: dict[tuple[str, date], Observation] = {}
    for row in rows:
        if row.reference_date > origin:
            continue
        if mode == "strict":
            if row.vintage_date > origin:
                continue
        elif row.release_date is None or row.release_date > origin:
            continue
        key = (row.series_id, row.reference_date)
        previous = chosen.get(key)
        if previous is None or (row.vintage_date, row.collected_at) > (
            previous.vintage_date,
            previous.collected_at,
        ):
            chosen[key] = row
    return chosen


def month_end(day: date) -> date:
    from calendar import monthrange

    return day.replace(day=monthrange(day.year, day.month)[1])


def align_monthly(
    rows: dict[tuple[str, date], Observation],
    series_id: str,
    *,
    aggregation: str = "last",
) -> dict[date, float]:
    """Align only observed values; no forward filling across release boundaries."""
    grouped: dict[date, list[Observation]] = defaultdict(list)
    for (key, _), row in rows.items():
        if key == series_id:
            grouped[month_end(row.reference_date)].append(row)
    if aggregation not in {"last", "mean"}:
        raise ValueError("aggregation must be last or mean")
    return {
        month: (
            sum(r.value for r in items) / len(items)
            if aggregation == "mean"
            else max(items, key=lambda r: r.reference_date).value
        )
        for month, items in grouped.items()
    }


def solve(
    matrix: list[list[float]], target: list[float], ridge: float = 1e-8
) -> list[float]:
    """Small deterministic normal-equations solver with regularized slope terms."""
    n = len(matrix[0])
    a = [
        [
            sum(row[i] * row[j] for row in matrix) + (ridge if i == j and i else 0.0)
            for j in range(n)
        ]
        + [sum(row[i] * y for row, y in zip(matrix, target))]
        for i in range(n)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda j: abs(a[j][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-12:
            raise ValueError("singular model")
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for j in range(n):
            if j != col:
                scale = a[j][col]
                a[j] = [v - scale * u for v, u in zip(a[j], a[col])]
    return [row[-1] for row in a]


def forecast(
    history: list[float],
    model: str,
    *,
    order: int = 1,
    predictor: list[float | None] | None = None,
    next_predictor: float | None = None,
) -> float:
    """One-step mean, last value, AR(p), or AR(p) with known-at-origin predictor."""
    if not history or order < 1:
        raise ValueError("insufficient history")
    if model == "mean":
        return sum(history) / len(history)
    if model == "last":
        return history[-1]
    if model not in {"ar", "arx"} or len(history) <= order + 1:
        raise ValueError("insufficient AR training history")
    if model == "arx" and (
        predictor is None or len(predictor) != len(history) or next_predictor is None
    ):
        raise ValueError("ARX requires aligned, available predictor")
    matrix, target = [], []
    for i in range(order, len(history)):
        extra: list[float] = []
        if model == "arx":
            assert predictor is not None
            predictor_value = predictor[i]
            if predictor_value is None:
                continue
            extra = [predictor_value]
        matrix.append([1.0] + [history[i - lag] for lag in range(1, order + 1)] + extra)
        target.append(history[i])
    if len(matrix) < order + 2:
        raise ValueError("insufficient complete model rows")
    coefficients = solve(matrix, target)
    extra_future: list[float] = []
    if model == "arx":
        assert next_predictor is not None
        extra_future = [next_predictor]
    features = [1.0] + [history[-lag] for lag in range(1, order + 1)] + extra_future
    return sum(a * b for a, b in zip(coefficients, features))


def metrics(
    actual: list[float], predicted: list[float], previous: list[float]
) -> dict[str, float]:
    if not actual or len(actual) != len(predicted) or len(actual) != len(previous):
        raise ValueError("unequal or empty metric vectors")
    errors = [p - y for y, p in zip(actual, predicted)]
    return {
        "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)),
        "mae": sum(abs(e) for e in errors) / len(errors),
        "bias": sum(errors) / len(errors),
        "directional_accuracy": sum(
            (y > prev) == (p > prev) for y, p, prev in zip(actual, predicted, previous)
        )
        / len(actual),
    }


def experiment(
    rows: list[Observation],
    target_id: str,
    origins: list[date],
    *,
    model: str = "last",
    order: int = 1,
    window: int | None = None,
    predictor_id: str | None = None,
    mode: str = "strict",
    truth_as_of: date | None = None,
) -> dict:
    """Pseudo-OOS: origin features are as-of, and target truth has its own vintage cutoff.

    For each origin, predict the next target reference period present in the truth
    contract. Backfilled rows stamped after origin cannot train a strict PIT model.
    """
    if window is not None and window < order + 2:
        raise ValueError("rolling window too short")
    if truth_as_of is None:
        raise ValueError("explicit target truth cutoff required")
    truth = as_of([r for r in rows if r.series_id == target_id], truth_as_of)
    outcomes = []
    for origin in sorted(set(origins)):
        snapshot = as_of(rows, origin, mode=mode)
        training = sorted(
            (d, r.value)
            for (sid, d), r in snapshot.items()
            if sid == target_id and d <= origin
        )
        future = sorted(
            (d, r.value)
            for (sid, d), r in truth.items()
            if sid == target_id and d > origin
        )
        if not training or not future:
            continue
        if window is not None:
            training = training[-window:]
        dates, values = zip(*training)
        predictor = None
        next_predictor = None
        if predictor_id is not None:
            predictors = {
                d: r.value for (sid, d), r in snapshot.items() if sid == predictor_id
            }
            predictor = [predictors.get(d) for d in dates]
            next_predictor = predictors.get(future[0][0])
        try:
            estimate = forecast(
                list(values),
                model,
                order=order,
                predictor=predictor,
                next_predictor=next_predictor,
            )
        except ValueError:
            continue
        outcomes.append(
            {
                "origin": origin.isoformat(),
                "target_date": future[0][0].isoformat(),
                "actual": future[0][1],
                "predicted": estimate,
                "previous": values[-1],
            }
        )
    if not outcomes:
        raise ValueError(
            "no valid origins; check PIT, frequency alignment and minimum history"
        )
    return {
        "model": model,
        "pit_mode": mode,
        "truth_as_of": truth_as_of.isoformat(),
        "n": len(outcomes),
        "scores": metrics(
            [o["actual"] for o in outcomes],
            [o["predicted"] for o in outcomes],
            [o["previous"] for o in outcomes],
        ),
        "predictions": outcomes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a PIT-aware pseudo-OOS experiment on exported collector rows"
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--origins", type=Path, required=True, help="one ISO date per line"
    )
    parser.add_argument("--truth-as-of", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--model", choices=("mean", "last", "ar", "arx"), default="last"
    )
    parser.add_argument("--order", type=int, default=1)
    parser.add_argument("--window", type=int)
    parser.add_argument("--predictor")
    parser.add_argument(
        "--pit-mode", choices=("strict", "reconstructed"), default="strict"
    )
    args = parser.parse_args()
    dates = [
        date.fromisoformat(line.strip())
        for line in args.origins.read_text().splitlines()
        if line.strip()
    ]
    print(
        json.dumps(
            experiment(
                read_contract(args.csv),
                args.target,
                dates,
                model=args.model,
                order=args.order,
                window=args.window,
                predictor_id=args.predictor,
                mode=args.pit_mode,
                truth_as_of=args.truth_as_of,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
