"""End-to-end known-answer tests for temporal alignment and fair comparisons."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.engine import (
    FeatureSpec,
    Observation,
    as_of,
    compare_common_sample,
    experiment,
    feature_at_origin,
    period_end,
)


def observation(
    series: str,
    reference: date,
    vintage: date,
    value: float,
    release: date | None = None,
) -> Observation:
    return Observation(
        series, reference, vintage, value, vintage.isoformat() + "T12:00:00", release
    )


def synthetic_monthly() -> tuple[list[Observation], list[date], list[float]]:
    values = [2, 5, 3, 7, 4, 9, 6, 8, 10]
    rows: list[Observation] = []
    targets: list[float] = []
    previous = 3.0
    for month, predictor in enumerate(values, 1):
        origin = date(2020, month, 20)
        target_date = period_end(origin, "monthly")
        previous = 1 + 0.4 * previous + 2 * predictor
        targets.append(previous)
        rows.append(
            observation("FUEL", date(2020, month, 10), date(2020, month, 10), predictor)
        )
        release = date(2020 if month < 12 else 2021, month + 1 if month < 12 else 1, 2)
        rows.append(observation("CPI", target_date, release, previous))
    # Both a future observation and a revision to an old reference must stay out.
    rows.extend(
        [
            observation("FUEL", date(2020, 8, 25), date(2020, 8, 25), 999),
            observation("FUEL", date(2020, 8, 10), date(2020, 8, 26), 999),
            observation(
                "FUEL", date(2020, 8, 27), date(2020, 8, 5), 999, date(2020, 8, 5)
            ),
        ]
    )
    return rows, [date(2020, 8, 20), date(2020, 9, 20)], targets


def test_daily_to_monthly_excludes_future_and_late_revision() -> None:
    rows, origins, _ = synthetic_monthly()
    feature, start, end = feature_at_origin(
        rows, "FUEL", origins[0], FeatureSpec("daily", "monthly", "mean")
    )
    assert (feature, start, end) == (8, date(2020, 8, 1), origins[0])
    assert ("FUEL", date(2020, 8, 27)) not in as_of(
        rows, origins[0], mode="reconstructed"
    )
    assert as_of(rows, origins[0])[("FUEL", date(2020, 8, 10))].value == 8


def test_weekly_to_monthly_and_quarterly_qtd() -> None:
    rows = [
        observation("WEEK", date(2020, 8, day), date(2020, 8, day), value)
        for day, value in ((5, 2), (12, 4), (19, 6), (26, 100))
    ]
    monthly = feature_at_origin(
        rows, "WEEK", date(2020, 8, 20), FeatureSpec("weekly", "monthly", "mean")
    )
    quarterly = feature_at_origin(
        rows, "WEEK", date(2020, 8, 20), FeatureSpec("weekly", "quarterly", "mean")
    )
    assert monthly == (4, date(2020, 8, 1), date(2020, 8, 20))
    assert quarterly == (4, date(2020, 7, 1), date(2020, 8, 20))


def test_monthly_to_quarterly_partial_and_configured_lag() -> None:
    rows = [
        observation("SPI", ref, vintage, value)
        for ref, vintage, value in (
            (date(2020, 4, 30), date(2020, 5, 5), 9),
            (date(2020, 6, 30), date(2020, 7, 5), 9),
            (date(2020, 7, 31), date(2020, 8, 15), 2),
            (date(2020, 8, 31), date(2020, 9, 5), 4),
        )
    ]
    assert feature_at_origin(
        rows, "SPI", date(2020, 8, 20), FeatureSpec("monthly", "quarterly", "mean")
    ) == (2, date(2020, 7, 1), date(2020, 8, 20))
    assert (
        feature_at_origin(
            rows,
            "SPI",
            date(2020, 8, 20),
            FeatureSpec("monthly", "quarterly", "last", lag=1),
        )[0]
        == 9
    )


def test_arx_pseudo_oos_rolling_expanding_and_common_sample() -> None:
    rows, origins, targets = synthetic_monthly()
    spec = FeatureSpec("daily", "monthly", "mean")
    kwargs = {
        "model": "arx",
        "predictor_id": "FUEL",
        "feature_spec": spec,
        "target_frequency": "monthly",
        "horizon": 0,
        "country": "AUD",
        "truth_as_of": date(2020, 10, 3),
    }
    expanding = experiment(rows, "CPI", origins, **kwargs)
    rolling = experiment(rows, "CPI", origins, window=5, **kwargs)
    assert expanding["n"] == rolling["n"] == 2
    assert abs(expanding["predictions"][0]["prediction"] - targets[7]) < 1e-5
    assert expanding["predictions"][0]["feature_value"] == 8
    assert expanding["predictions"][0]["feature_cutoff"] == "2020-08-20"
    assert expanding["predictions"][0]["target_period"] == "2020-08-31"
    assert (
        expanding["predictions"][0]["train_start"]
        < rolling["predictions"][0]["train_start"]
    )
    baseline = experiment(
        rows,
        "CPI",
        origins[1:],
        model="last",
        target_frequency="monthly",
        horizon=0,
        country="AUD",
        truth_as_of=date(2020, 10, 3),
    )
    comparison = compare_common_sample([expanding, baseline])
    assert comparison["common_n"] == 1
    assert comparison["origins"] == [
        {"origin": "2020-09-20", "target_period": "2020-09-30"}
    ]
    assert comparison == compare_common_sample([expanding, baseline])
    with pytest.raises(ValueError, match="incompatible"):
        compare_common_sample([expanding, {**baseline, "horizon": 1}])


def test_declared_target_period_does_not_skip_gap() -> None:
    rows, origins, _ = synthetic_monthly()
    rows = [
        r
        for r in rows
        if not (r.series_id == "CPI" and r.reference_date == date(2020, 8, 31))
    ]
    with pytest.raises(ValueError, match="no valid origins"):
        experiment(
            rows,
            "CPI",
            origins[:1],
            model="last",
            target_frequency="monthly",
            horizon=0,
            country="AUD",
            truth_as_of=date(2020, 10, 3),
        )


def test_unsupported_frequency_and_future_truth() -> None:
    with pytest.raises(ValueError, match="frequency mismatch"):
        FeatureSpec("quarterly", "monthly")
    rows, origins, _ = synthetic_monthly()
    with pytest.raises(ValueError, match="no valid origins"):
        experiment(
            rows,
            "CPI",
            origins[:1],
            model="last",
            target_frequency="monthly",
            horizon=0,
            country="AUD",
            truth_as_of=origins[0],
        )


def test_quarterly_arx_with_monthly_partial_feature() -> None:
    rows: list[Observation] = []
    previous = 2.0
    expected = 0.0
    origin = date(2021, 8, 20)
    for index, x in enumerate((3, 6, 4, 8, 5, 9, 7), 0):
        year, quarter = divmod(index, 4)
        start_month = quarter * 3 + 1
        y = 1 + previous * 0.3 + x * 2
        ref = period_end(date(2020 + year, start_month, 1), "quarterly")
        rows.append(
            observation(
                "SPI",
                period_end(date(2020 + year, start_month, 1), "monthly"),
                date(2020 + year, start_month + 1, 5),
                x,
            )
        )
        next_year, next_month = divmod(ref.year * 12 + ref.month, 12)
        rows.append(observation("CPI", ref, date(next_year, next_month + 1, 5), y))
        previous = y
        expected = y
    result = experiment(
        rows,
        "CPI",
        [origin],
        model="arx",
        predictor_id="SPI",
        feature_spec=FeatureSpec("monthly", "quarterly", "mean"),
        target_frequency="quarterly",
        horizon=0,
        country="NZD",
        truth_as_of=date(2021, 11, 1),
    )
    assert result["predictions"][0]["target_period"] == "2021-09-30"
    assert result["predictions"][0]["feature_window_start"] == "2021-07-01"
    assert result["predictions"][0]["feature_value"] == 7
    assert abs(result["predictions"][0]["prediction"] - expected) < 1e-5


def test_common_sample_rejects_directional_baseline_mismatch() -> None:
    rows, origins, _ = synthetic_monthly()
    args = {
        "target_frequency": "monthly",
        "horizon": 0,
        "country": "AUD",
        "truth_as_of": date(2020, 10, 3),
    }
    baseline = experiment(rows, "CPI", origins, model="last", **args)
    changed = {**baseline, "predictions": [dict(p) for p in baseline["predictions"]]}
    changed["predictions"][0]["previous"] += 1
    with pytest.raises(ValueError, match="directional baseline mismatch"):
        compare_common_sample([baseline, changed])
