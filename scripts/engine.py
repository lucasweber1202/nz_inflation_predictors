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
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Observation:
    series_id: str
    reference_date: date
    vintage_date: date
    value: float
    collected_at: str
    release_date: date | None = None


@dataclass(frozen=True)
class FeatureSpec:
    """A governed, explicit mapping from one predictor to one target cadence."""

    predictor_frequency: str
    target_frequency: str
    aggregation: str = "last"
    transformation: str = "level"
    lag: int = 0
    availability_rule: str = "observed_as_of_origin"

    def __post_init__(self) -> None:
        allowed = {
            "monthly": {"daily", "weekly", "monthly"},
            "quarterly": {"daily", "weekly", "monthly", "quarterly"},
        }
        if self.predictor_frequency not in allowed.get(self.target_frequency, set()):
            raise ValueError(
                f"frequency mismatch: {self.predictor_frequency} -> {self.target_frequency} unsupported"
            )
        if self.aggregation not in {"last", "mean", "sum"}:
            raise ValueError("aggregation must be last, mean or sum")
        if self.transformation not in {"level", "difference", "pct_change"}:
            raise ValueError("transformation must be level, difference or pct_change")
        if self.lag < 0 or self.availability_rule not in {
            "observed_as_of_origin",
            "complete_period_only",
        }:
            raise ValueError("invalid lag or availability rule")


def read_feature_spec(
    path: Path, predictor_id: str, target_frequency: str
) -> FeatureSpec:
    with path.open(newline="", encoding="utf-8") as handle:
        matches = [r for r in csv.DictReader(handle) if r["series_id"] == predictor_id]
    if len(matches) != 1:
        raise ValueError(
            f"predictor {predictor_id!r} must have exactly one governed row"
        )
    row = matches[0]
    if row["target_frequency"] != target_frequency:
        raise ValueError("frequency mismatch between target registry and feature spec")
    if any(
        row[key] == "PENDING_RESEARCH"
        for key in ("aggregation", "transformation", "lag", "availability_rule")
    ):
        raise ValueError(f"feature spec for {predictor_id} requires research approval")
    return FeatureSpec(
        row["frequency"],
        target_frequency,
        row["aggregation"],
        row["transformation"],
        int(row["lag"]),
        row["availability_rule"],
    )


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


def period_start(day: date, frequency: str) -> date:
    if frequency == "monthly":
        return day.replace(day=1)
    if frequency == "quarterly":
        return date(day.year, 1 + 3 * ((day.month - 1) // 3), 1)
    raise ValueError(f"unsupported target frequency {frequency}")


def period_end(day: date, frequency: str) -> date:
    start = period_start(day, frequency)
    months = 1 if frequency == "monthly" else 3
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    return date(year, month + 1, 1) - timedelta(days=1)


def shift_period(day: date, count: int, frequency: str) -> date:
    from calendar import monthrange

    months = count * (1 if frequency == "monthly" else 3)
    year, index = divmod(day.year * 12 + day.month - 1 + months, 12)
    month = index + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def feature_at_origin(
    rows: list[Observation],
    series_id: str,
    origin: date,
    spec: FeatureSpec,
    *,
    mode: str = "strict",
) -> tuple[float | None, date, date]:
    """Aggregate observed rows in the configured period, bounded by the origin.

    Difference and pct_change compare equivalent partial windows one period apart.
    No observation or revision after either historical cutoff enters its feature.
    """
    cutoff = shift_period(origin, -spec.lag, spec.target_frequency)

    def aggregate(cut: date) -> tuple[float | None, date, date]:
        start = period_start(cut, spec.target_frequency)
        end = min(period_end(cut, spec.target_frequency), cut)
        if spec.availability_rule == "complete_period_only" and cut < period_end(
            cut, spec.target_frequency
        ):
            return None, start, end
        snapshot = as_of(rows, min(cut, origin), mode=mode)
        selected = [
            r
            for (sid, ref), r in snapshot.items()
            if sid == series_id and start <= ref <= end
        ]
        if not selected:
            return None, start, end
        if spec.aggregation == "last":
            value = max(selected, key=lambda r: r.reference_date).value
        elif spec.aggregation == "mean":
            value = sum(r.value for r in selected) / len(selected)
        else:
            value = sum(r.value for r in selected)
        return value, start, end

    value, start, end = aggregate(cutoff)
    if value is None or spec.transformation == "level":
        return value, start, end
    prior_cutoff = shift_period(cutoff, -1, spec.target_frequency)
    previous, _, _ = aggregate(prior_cutoff)
    if previous is None:
        return None, start, end
    if spec.transformation == "difference":
        return value - previous, start, end
    return (value / previous - 1.0) if previous != 0 else None, start, end


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
    feature_spec: FeatureSpec | None = None,
    target_frequency: str,
    horizon: int,
    country: str,
    mode: str = "strict",
    truth_as_of: date | None = None,
) -> dict:
    """Pseudo-OOS with explicit target period and historical feature cutoffs."""
    if window is not None and window < order + 2:
        raise ValueError("rolling window too short")
    if truth_as_of is None:
        raise ValueError("explicit target truth cutoff required")
    if horizon < 0:
        raise ValueError("horizon must be a nonnegative number of target periods")
    period_start(
        date(2000, 1, 1), target_frequency
    )  # validate cadence even without origins
    if model == "arx" and (predictor_id is None or feature_spec is None):
        raise ValueError("ARX requires predictor ID and governed feature spec")
    if feature_spec is not None and feature_spec.target_frequency != target_frequency:
        raise ValueError("frequency mismatch between feature spec and target")
    truth = as_of([r for r in rows if r.series_id == target_id], truth_as_of)
    truth_by_period: dict[date, float] = {}
    for (sid, ref), row in truth.items():
        period = period_end(ref, target_frequency)
        if period in truth_by_period:
            raise ValueError(f"duplicate target period {period}")
        truth_by_period[period] = row.value
    outcomes = []
    for origin in sorted(set(origins)):
        target_period = period_end(
            shift_period(origin, horizon, target_frequency), target_frequency
        )
        if target_period not in truth_by_period:
            continue  # A missing declared horizon is never silently replaced by a later period.
        snapshot = as_of(rows, origin, mode=mode)
        training = sorted(
            (period_end(d, target_frequency), r.value)
            for (sid, d), r in snapshot.items()
            if sid == target_id and period_end(d, target_frequency) < target_period
        )
        if not training:
            continue
        if window is not None:
            training = training[-window:]
        dates, values = zip(*training)
        predictor = None
        next_predictor = None
        feature_window_start = None
        feature_window_end = None
        if model == "arx":
            assert predictor_id is not None and feature_spec is not None
            predictor = []
            for period in dates:
                distance = (target_period.year - period.year) * (
                    12 if target_frequency == "monthly" else 4
                )
                distance += (target_period.month - period.month) // (
                    1 if target_frequency == "monthly" else 3
                )
                historical_origin = shift_period(origin, -distance, target_frequency)
                historical_feature, _, _ = feature_at_origin(
                    rows, predictor_id, historical_origin, feature_spec, mode=mode
                )
                predictor.append(historical_feature)
            next_predictor, feature_window_start, feature_window_end = (
                feature_at_origin(rows, predictor_id, origin, feature_spec, mode=mode)
            )
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
                "country": country,
                "target": target_id,
                "predictor": predictor_id if model == "arx" else None,
                "model": model,
                "pit_mode": mode,
                "origin": origin.isoformat(),
                "target_period": target_period.isoformat(),
                "horizon": horizon,
                "train_start": dates[0].isoformat(),
                "train_end": dates[-1].isoformat(),
                "feature_cutoff": origin.isoformat(),
                "feature_window_start": feature_window_start.isoformat()
                if feature_window_start
                else None,
                "feature_window_end": feature_window_end.isoformat()
                if feature_window_end
                else None,
                "feature_value": next_predictor,
                "truth_as_of": truth_as_of.isoformat(),
                "actual": truth_by_period[target_period],
                "prediction": estimate,
                "error": estimate - truth_by_period[target_period],
                "previous": values[-1],
            }
        )
    if not outcomes:
        raise ValueError(
            "no valid origins; check PIT, frequency alignment and minimum history"
        )
    return {
        "schema_version": 1,
        "country": country,
        "target": target_id,
        "predictor": predictor_id if model == "arx" else None,
        "model": model,
        "pit_mode": mode,
        "target_frequency": target_frequency,
        "horizon": horizon,
        "truth_as_of": truth_as_of.isoformat(),
        "n": len(outcomes),
        "scores": metrics(
            [o["actual"] for o in outcomes],
            [o["prediction"] for o in outcomes],
            [o["previous"] for o in outcomes],
        ),
        "predictions": outcomes,
    }


def compare_common_sample(experiments: list[dict]) -> dict:
    """Recompute metrics only over identical origin/target pairs and truth values."""
    if len(experiments) < 2:
        raise ValueError("at least two experiment outputs required")
    fields = (
        "country",
        "target",
        "target_frequency",
        "horizon",
        "truth_as_of",
        "pit_mode",
    )
    if any(
        tuple(e[key] for key in fields) != tuple(experiments[0][key] for key in fields)
        for e in experiments[1:]
    ):
        raise ValueError("incompatible target, horizon, PIT or truth vintage")
    indexed = [
        {(p["origin"], p["target_period"]): p for p in e["predictions"]}
        for e in experiments
    ]
    common = sorted(set.intersection(*(set(x) for x in indexed)))
    if not common:
        raise ValueError("no common forecast origins")
    for key in common:
        if len({(x[key]["actual"], x[key]["previous"]) for x in indexed}) != 1:
            raise ValueError(
                "target truth or directional baseline mismatch on common origin"
            )
    return {
        "schema_version": 1,
        "common_n": len(common),
        "origins": [{"origin": a, "target_period": b} for a, b in common],
        "models": [
            {
                "model": e["model"],
                "predictor": e["predictor"],
                "scores": metrics(
                    [x[k]["actual"] for k in common],
                    [x[k]["prediction"] for k in common],
                    [x[k]["previous"] for k in common],
                ),
            }
            for e, x in zip(experiments, indexed)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a PIT-aware pseudo-OOS experiment on exported collector rows"
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--country", required=True, choices=("AUD", "NZD"))
    parser.add_argument(
        "--target-registry", type=Path, default=Path("target_registry.csv")
    )
    parser.add_argument("--predictor-map", type=Path, default=Path("predictor_map.csv"))
    parser.add_argument(
        "--horizon",
        type=int,
        required=True,
        help="0=current target period, 1=next period",
    )
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
    with args.target_registry.open(newline="", encoding="utf-8") as handle:
        targets = [
            row for row in csv.DictReader(handle) if row["series_id"] == args.target
        ]
    if len(targets) != 1 or targets[0]["status"] != "active":
        parser.error("target must be exactly one active row in target registry")
    target_frequency = targets[0]["frequency"]
    spec = (
        read_feature_spec(args.predictor_map, args.predictor, target_frequency)
        if args.model == "arx" and args.predictor
        else None
    )
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
                feature_spec=spec,
                target_frequency=target_frequency,
                horizon=args.horizon,
                country=args.country,
                mode=args.pit_mode,
                truth_as_of=args.truth_as_of,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
