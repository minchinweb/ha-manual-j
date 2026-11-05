# Copyright (c) 2026 MinchinWeb
"""Manual J: heating and cooling loads, equipment and ducts for the house.

Manual J (room loads), S (equipment) and D (ducts), calculated from the house
House Structure describes, the design weather from the recorded outdoor
temperature, and House Structure's furnace and air conditioner. The results
are the **HVAC design** tab on House Structure's Thermal Lab page.

Set up from the web interface only (see ``config_flow.py``). It depends on
House Structure, which Home Assistant then sets up first. On setup it:

- adds the HVAC design tab (``hass.data["house_structure_tabs"]``);
- starts downloading the historical weather for the design temperatures
  (``downloads.py``), if it hasn't already;
- tells House Structure which sizes it calculates from
  (``hass.data["house_structure_needs"]``), so a wall without a size raises a
  repair once Manual J is installed, and not before.

Both are taken back when it unloads. The calculations (``air.py``,
``building.py``, ``manual_j.py``, ``manual_s.py``, ``manual_d.py``,
``project.py``, ``house_model.py`` and ``loads.py``) use only the standard
library, and are tested without Home Assistant.
"""

from __future__ import annotations

from homeassistant.helpers import config_validation as cv

from .constants import (
    DEFAULTS,
    DOMAIN,
    NEEDED,
    NEEDS,
    NEEDS_EVENT,
    TAB_KEY,
    TABS,
    TABS_EVENT,
)
from .downloads import downloaded_summary
from .house_model import default_r_values
from .panel import async_register, tab

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config) -> bool:
    """Serve the HVAC design page and add its websocket command."""
    await async_register(hass)
    return True


def _publish_defaults(hass, entry) -> None:
    """Publish the R-values used where a part has none typed, for House Structure."""
    hass.data.setdefault(DEFAULTS, {})[DOMAIN] = {
        "title": entry.title,
        "r_values": default_r_values(dict(entry.data)),
    }


async def _settings_changed(hass, entry) -> None:
    """Publish the R-values again when the settings change."""
    _publish_defaults(hass, entry)


async def async_setup_entry(hass, entry) -> bool:
    """Add the tab, and say which of House Structure's sizes are needed."""
    hass.data.setdefault(TABS, {})[TAB_KEY] = await tab(hass)
    hass.bus.async_fire(TABS_EVENT)
    hass.data.setdefault(NEEDS, {})[DOMAIN] = {
        "title": entry.title,
        "needs": list(NEEDED),
    }
    hass.bus.async_fire(NEEDS_EVENT)
    _publish_defaults(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_settings_changed))
    # the historical weather, so the tab has it on first opening
    entry.async_create_background_task(
        hass, downloaded_summary(hass), f"{DOMAIN} historical weather"
    )
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Take the tab and the needs back."""
    hass.data.get(TABS, {}).pop(TAB_KEY, None)
    hass.bus.async_fire(TABS_EVENT)
    hass.data.get(NEEDS, {}).pop(DOMAIN, None)
    hass.data.get(DEFAULTS, {}).pop(DOMAIN, None)
    hass.bus.async_fire(NEEDS_EVENT)
    return True
