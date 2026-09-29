"""Known-answer and leakage tests for the standalone research engine."""

from datetime import date
from pathlib import Path

from scripts.engine import (
    Observation,
    align_monthly,
    as_of,
    experiment,
    forecast,
    metrics,
    read_contract,
)


def row(
    day: int,
    vintage: int,
    value: float,
    series: str = "TARGET",
    release: int | None = None,
) -> Observation:
    return Observation(
        series,
        date(2020, 1, day),
        date(2020, 1, vintage),
        value,
        f"2020-01-{vintage:02d}T12:00:00",
        date(2020, 1, release) if release else None,
    )


def test_strict_pit_and_release_cutoffs() -> None:
    rows = [
        row(1, 3, 1.0, release=2),
        row(1, 7, 2.0, release=7),
        row(6, 6, 3.0, release=6),
        row(1, 9, 4.0, release=9),
    ]
    strict = as_of(rows, date(2020, 1, 5))
    assert strict[("TARGET", date(2020, 1, 1))].value == 1.0
    assert len(strict) == 1
    assert as_of([row(1, 9, 8, release=8)], date(2020, 1, 5), mode="strict") == {}
    assert as_of([row(1, 9, 8, release=2)], date(2020, 1, 5), mode="reconstructed")
    assert not as_of([row(1, 9, 8, release=8)], date(2020, 1, 5), mode="reconstructed")


def test_models_and_metrics() -> None:
    history = [float(i) for i in range(12)]
    assert forecast(history, "mean") == 5.5
    assert forecast(history, "last") == 11
    assert abs(forecast(history, "ar") - 12) < 1e-5
    assert (
        abs(forecast(history, "arx", predictor=history, next_predictor=12) - 12) < 1e-5
    )
    result = metrics([2, 4], [3, 2], [1, 3])
    assert result == {
        "rmse": (2.5) ** 0.5,
        "mae": 1.5,
        "bias": -0.5,
        "directional_accuracy": 0.5,
    }


def test_alignment_and_known_answer_experiment() -> None:
    origin = date(2020, 1, 5)
    rows = [
        Observation("TARGET", date(2019, 12, 31), origin, 10, "2020-01-05T12:00:00"),
        Observation(
            "TARGET", date(2020, 1, 31), date(2020, 2, 2), 12, "2020-02-02T12:00:00"
        ),
    ]
    assert align_monthly(as_of(rows, origin), "TARGET") == {date(2019, 12, 31): 10}
    kwargs = {
        "truth_as_of": date(2020, 2, 3),
        "target_frequency": "monthly",
        "horizon": 0,
        "country": "AUD",
    }
    outcome = experiment(rows, "TARGET", [origin], **kwargs)
    assert outcome["n"] == 1
    assert outcome["scores"]["mae"] == 2
    assert outcome == experiment(rows, "TARGET", [origin], **kwargs)
    try:
        experiment(
            rows,
            "TARGET",
            [origin],
            target_frequency="monthly",
            horizon=0,
            country="AUD",
            truth_as_of=origin,
        )
        assert False, "target truth cannot be available before release"
    except ValueError:
        pass


def test_contract_rejects_duplicate_vintage(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    header = "series_id,reference_date,vintage_date,value,collected_at\n"
    entry = "X,2020-01-01,2020-01-02,1,2020-01-02T12:00:00\n"
    path.write_text(header + entry + entry)
    try:
        read_contract(path)
        assert False, "duplicate was accepted"
    except ValueError:
        pass
