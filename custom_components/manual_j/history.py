# Copyright (c) 2026 MinchinWeb
"""Design conditions from Open-Meteo's historical weather (standard library only).

When there's no outdoor sensor with a long enough record, the design
temperatures come from the last ``YEARS`` whole years of hourly weather at the
home location, from Open-Meteo's historical archive (reanalysis, no key
needed). Its dew points give the cooling design humidity too. Only the derived
values are kept (``summarise``), not the hours, so they are fetched again only
when the location or the years change.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from urllib.parse import urlencode

from .building import cooling_humidity, design_temperatures

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
YEARS = 10
SOURCE_NOTE = "Weather data by Open-Meteo.com (CC BY 4.0)"


def window(today: date, years: int = YEARS) -> tuple[date, date]:
    """The last ``years`` whole calendar years before ``today``."""
    return date(today.year - years, 1, 1), date(today.year - 1, 12, 31)


def archive_url(lat: float, lon: float, start: date, end: date) -> str:
    """Open-Meteo's archive request for hourly temperature and dew point."""
    query = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "temperature_2m,dew_point_2m",
        "timezone": "GMT",
    }
    return f"{ARCHIVE_URL}?{urlencode(query)}"


def _numbers(values: object) -> list[float | None]:
    out: list[float | None] = []
    for value in values if isinstance(values, list) else []:
        out.append(None if value is None else float(value))
    return out


def parse_archive(payload: Mapping) -> tuple[list[float | None], list[float | None]]:
    """The hourly temperatures and dew points from an archive answer, °C.

    Raises:
        ValueError: The answer has no hourly temperatures.
    """
    hourly = payload.get("hourly") or {}
    temps = _numbers(hourly.get("temperature_2m"))
    if not temps:
        raise ValueError("Open-Meteo's answer has no hourly temperatures")
    dews = _numbers(hourly.get("dew_point_2m"))
    if len(dews) != len(temps):
        dews = [None] * len(temps)
    return temps, dews


def summarise(
    temps: list[float | None],
    dews: list[float | None],
    altitude_m: float,
    start: date,
    end: date,
) -> dict:
    """The design values from the hours: what is kept between downloads.

    Returns:
        ``heat_outdoor_c``, ``heat_outdoor_99_c``, ``cool_outdoor_c``,
        ``cool_outdoor_1_c``, ``hours``, ``warnings``, the years (``start``
        and ``end``), and ``cool_outdoor_w`` (the cooling design humidity
        ratio) with ``humidity_hours``, or None for both when the dew points
        don't give one.

    Raises:
        ValueError: Too few hours for the design temperatures.
    """
    found = design_temperatures(temps)
    out = {
        "heat_outdoor_c": found["heat_c"],
        "heat_outdoor_99_c": found["heat_c_99"],
        "cool_outdoor_c": found["cool_c"],
        "cool_outdoor_1_c": found["cool_c_1"],
        "hours": found["hours"],
        "warnings": list(found["warnings"]),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "cool_outdoor_w": None,
        "humidity_hours": None,
    }
    try:
        humid = cooling_humidity(
            list(zip(temps, dews, strict=True)), found["cool_c"], altitude_m
        )
    except ValueError:
        return out
    out["cool_outdoor_w"] = humid["w"]
    out["humidity_hours"] = humid["hours"]
    out["warnings"] += humid["warnings"]
    return out
