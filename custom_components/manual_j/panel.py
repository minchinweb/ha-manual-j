# Copyright (c) 2026 MinchinWeb
"""The HVAC design tab and its websocket command (needs Home Assistant).

The page (``frontend/index.html``) is served at ``/manual_j_static/`` and
shown as a tab on House Structure's Thermal Lab page; it loads House
Structure's ``tab.js`` for the connection and theme. It asks
``manual_j/loads`` for the numbers, which are worked out on each request from
what House Structure publishes at that moment, so they follow its changes.
The slow part, the recorder's two years of hourly outdoor means, is kept until
the hour changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import logging
from pathlib import Path

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
import voluptuous as vol

from . import structure
from .building import HOURS_PER_YEAR, Design
from .constants import (
    DOMAIN,
    FITTED,
    OUTDOOR_ENTITY,
    STATIC_URL,
    STRUCTURE_DOMAIN,
    TAB_ORDER,
    TAB_TITLE,
)
from .house_model import nominal_from_settings
from .loads import HUMIDITY_NOTE, assemble_all, design_from_record, equipment_from

_LOGGER = logging.getLogger(__name__)

FRONTEND = Path(__file__).parent / "frontend"
LOADS_HOURS = 2 * HOURS_PER_YEAR  # the record the design temperatures come from
_STARTED = f"{DOMAIN}_panel"
_OUTDOOR = f"{DOMAIN}_outdoor"  # the hourly record, until the hour changes


def _version() -> str:
    """A short hash of the page, to bust caches when it changes."""
    return hashlib.sha256((FRONTEND / "index.html").read_bytes()).hexdigest()[:10]


async def async_register(hass: HomeAssistant) -> None:
    """Serve the page and add the command, once."""
    if hass.data.get(_STARTED):
        return
    hass.data[_STARTED] = True
    websocket_api.async_register_command(hass, ws_loads)
    if hass.http is not None:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND), cache_headers=True)]
        )


async def tab(hass: HomeAssistant) -> dict:
    """The HVAC design tab, for House Structure's Thermal Lab page."""
    version = await hass.async_add_executor_job(_version)
    return {
        "title": TAB_TITLE,
        "url": f"{STATIC_URL}/index.html?v={version}",
        "order": TAB_ORDER,
    }


def _settings(hass: HomeAssistant) -> dict:
    """The config entry's settings (empty if it isn't set up)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        return dict(entry.data)
    return {}


def _stamp(value) -> datetime:
    """A statistics row's start, as an aware time (epoch seconds or a datetime)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromtimestamp(float(value), UTC)


async def hourly_outdoor(
    hass: HomeAssistant, entity_id: str, end: datetime
) -> list[float | None]:
    """The outdoor temperature's hourly means over ``LOADS_HOURS`` (None if missing)."""
    start = end - timedelta(hours=LOADS_HOURS)
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        {entity_id},
        "hour",
        None,
        {"mean"},
    )
    values: list[float | None] = [None] * LOADS_HOURS
    for row in found.get(entity_id, []):
        index = int((_stamp(row["start"]) - start).total_seconds() // 3600)
        if 0 <= index < LOADS_HOURS and row.get("mean") is not None:
            values[index] = float(row["mean"])
    return values


async def _cached_hourly_outdoor(
    hass: HomeAssistant, entity_id: str, end: datetime
) -> list[float | None]:
    """``hourly_outdoor``, reused until the hour (or the sensor) changes.

    The window ends on the hour, so the record only changes hourly; the
    recorder query is the slow part of the tab, and this skips it on refreshes.
    """
    key = (entity_id, end)
    cached = hass.data.get(_OUTDOOR)
    if cached is not None and cached[0] == key:
        return list(cached[1])
    values = await hourly_outdoor(hass, entity_id, end)
    hass.data[_OUTDOOR] = (key, values)
    return list(values)


@websocket_api.websocket_command({vol.Required("type"): "manual_j/loads"})
@websocket_api.async_response
async def ws_loads(hass: HomeAssistant, connection, msg: dict) -> None:
    """The Manual J, S and D results, set against the recorded and fitted values."""
    summary = hass.data.get(STRUCTURE_DOMAIN)
    rooms = structure.rooms(summary)
    if not rooms:
        connection.send_result(
            msg["id"],
            {"available": False, "reason": "House Structure has no rooms yet."},
        )
        return
    settings = _settings(hass)
    hourly: list[float | None] = [None] * LOADS_HOURS
    notes: list[str] = []
    if settings.get(OUTDOOR_ENTITY):
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        try:
            hourly = await _cached_hourly_outdoor(hass, settings[OUTDOOR_ENTITY], end)
        except Exception:  # the design then stays the assumed one
            _LOGGER.debug("No hourly outdoor record", exc_info=True)
    else:
        notes.append(
            "No outdoor temperature sensor is set, so the design temperatures are "
            "the assumed ones. Choose one on Manual J's Reconfigure form."
        )
    design, info = design_from_record(hourly, Design())
    areas = ar.async_get(hass)
    names = {}
    for area_id in rooms:
        area = areas.async_get_area(area_id)
        if area is not None:
            names[area_id] = area.name
    furnace, ac, furnace_area_id, equipment_notes = equipment_from(
        structure.equipment(summary)
    )
    nominal, envelope_note = nominal_from_settings(settings)
    furnace_area = areas.async_get_area(furnace_area_id) if furnace_area_id else None
    rates = structure.fitted_rates(hass.data.get(FITTED))
    try:
        result = assemble_all(
            rooms,
            names,
            rates,
            nominal,
            design,
            buildings=structure.buildings(summary, settings.get("buildings")),
            furnace=furnace,
            ac=ac,
            design_info=info,
            extra_warnings=[*notes, envelope_note, HUMIDITY_NOTE, *equipment_notes],
            ducts=structure.ducts(summary),
            furnace_room=furnace_area.name if furnace_area else None,
        )
    except ValueError as err:
        connection.send_error(msg["id"], "no_rooms", str(err))
        return
    result["available"] = True
    result["fitted"] = bool(rates)
    connection.send_result(msg["id"], result)
