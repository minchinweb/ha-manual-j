# Copyright (c) 2026 MinchinWeb
"""Design conditions from Open-Meteo's historical weather."""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest

from custom_components.manual_j.building import Design
from custom_components.manual_j.history import (
    archive_url,
    parse_archive,
    summarise,
    window,
)
from custom_components.manual_j.loads import design_from_summary

HOURS = 2 * 8760


def _year_of_hours():
    """Two years swinging from -30 to +30 C, the dew point 10 K below."""
    temps = [-30.0 + 60.0 * ((h // 24) % 365) / 365 for h in range(HOURS)]
    return temps, [t - 10.0 for t in temps]


def test_the_window_is_whole_years_before_this_one():
    assert window(date(2026, 11, 4)) == (date(2016, 1, 1), date(2025, 12, 31))
    assert window(date(2026, 1, 1), 2) == (date(2024, 1, 1), date(2025, 12, 31))


def test_the_url_asks_for_temperature_and_dew_point():
    url = archive_url(53.55, -113.49, date(2016, 1, 1), date(2025, 12, 31))
    parts = urlsplit(url)
    assert parts.netloc == "archive-api.open-meteo.com"
    query = parse_qs(parts.query)
    assert query["hourly"] == ["temperature_2m,dew_point_2m"]
    assert query["start_date"] == ["2016-01-01"]
    assert query["latitude"] == ["53.5500"]


def test_parse_keeps_gaps_and_drops_mismatched_dew_points():
    temps, dews = parse_archive(
        {"hourly": {"temperature_2m": [1, None, 3], "dew_point_2m": [0, 1, 2]}}
    )
    assert temps == [1.0, None, 3.0]
    assert dews == [0.0, 1.0, 2.0]
    _, dews = parse_archive({"hourly": {"temperature_2m": [1], "dew_point_2m": []}})
    assert dews == [None]
    with pytest.raises(ValueError):
        parse_archive({"hourly": {}})


def test_summarise_gives_the_design_and_humidity():
    temps, dews = _year_of_hours()
    out = summarise(temps, dews, 700.0, date(2024, 1, 1), date(2025, 12, 31))
    assert out["heat_outdoor_c"] < -29 and out["cool_outdoor_c"] > 29
    assert out["hours"] == HOURS
    assert out["cool_outdoor_w"] > 0
    assert out["humidity_hours"] > 0
    assert out["start"] == "2024-01-01"


def test_summarise_without_dew_points_has_no_humidity():
    temps, _ = _year_of_hours()
    out = summarise(temps, [None] * HOURS, 0.0, date(2024, 1, 1), date(2025, 12, 31))
    assert out["cool_outdoor_w"] is None


def test_a_summary_sets_the_design():
    temps, dews = _year_of_hours()
    out = summarise(temps, dews, 0.0, date(2024, 1, 1), date(2025, 12, 31))
    base = Design(altitude_m=650.0)
    design, info = design_from_summary(out, base, "downloaded")
    assert design.heat_outdoor_c == out["heat_outdoor_c"]
    assert design.cool_outdoor_w == out["cool_outdoor_w"]
    assert design.altitude_m == 650.0
    assert info["source"] == "downloaded"
    assert info["assumed"]["heat_outdoor_c"] == base.heat_outdoor_c
