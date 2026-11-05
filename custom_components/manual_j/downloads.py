# Copyright (c) 2026 MinchinWeb
"""The historical weather download, and where it is kept (needs Home Assistant).

The derived design values (``history.summarise``) are kept in Home
Assistant's storage (``.storage/manual_j.history``) with the location and
years they are for, so the download happens once, again only when the home
location moves or a new year has finished.
"""

from __future__ import annotations

import asyncio
from datetime import date
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .constants import DOMAIN
from .history import archive_url, parse_archive, summarise, window

_LOGGER = logging.getLogger(__name__)
STORE_KEY = f"{DOMAIN}.history"
STORE_VERSION = 1
TIMEOUT_S = 120
_LOCK = f"{DOMAIN}_history_lock"


def _place(hass: HomeAssistant) -> tuple[float, float]:
    """The home location, to about a kilometre (what the archive resolves)."""
    return round(hass.config.latitude, 2), round(hass.config.longitude, 2)


async def fetch_archive(hass: HomeAssistant, url: str) -> dict:
    """Open-Meteo's archive answer for ``url``."""
    session = async_get_clientsession(hass)
    async with session.get(
        url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)
    ) as response:
        response.raise_for_status()
        return await response.json()


async def downloaded_summary(hass: HomeAssistant) -> tuple[dict | None, str | None]:
    """The design values from the historical weather at the home location.

    Kept from an earlier download when it is for the same place and years;
    otherwise downloaded now (one request at a time).

    Returns:
        The summary (see ``history.summarise``), or None and why not.
    """
    lock = hass.data.setdefault(_LOCK, asyncio.Lock())
    async with lock:
        lat, lon = _place(hass)
        start, end = window(dt_util.now().date())
        store: Store = Store(hass, STORE_VERSION, STORE_KEY)
        kept = await store.async_load() or {}
        if kept.get("for") == [lat, lon, start.isoformat(), end.isoformat()]:
            return kept["summary"], None
        try:
            payload = await fetch_archive(hass, archive_url(lat, lon, start, end))
            temps, dews = parse_archive(payload)
            summary = await hass.async_add_executor_job(
                summarise, temps, dews, float(hass.config.elevation or 0), start, end
            )
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.warning("Could not download the historical weather: %s", err)
            return None, f"The historical weather couldn't be downloaded ({err})."
        await store.async_save(
            {"for": [lat, lon, start.isoformat(), end.isoformat()], "summary": summary}
        )
        return summary, None


def years(summary: dict) -> str:
    """The years a summary covers, as ``2016 to 2025``."""
    return f"{date.fromisoformat(summary['start']).year} to " + str(
        date.fromisoformat(summary["end"]).year
    )
