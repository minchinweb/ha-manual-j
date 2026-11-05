# Copyright (c) 2026 MinchinWeb
"""Setting Manual J up: its forms, its tab, its needs and ``manual_j/loads``."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockModule, mock_integration

from custom_components.manual_j.constants import (
    DOMAIN,
    FITTED,
    NEEDS,
    STRUCTURE_DOMAIN,
    TAB_KEY,
    TABS,
)
from custom_components.manual_j.panel import LOADS_HOURS

OFFICE = {
    "title": "Office",
    "floor_m2": 12.0,
    "height_m": 2.4,
    "volume_m3": 28.8,
    "below_ground": False,
    "walls": [{"azimuth": 180.0, "tilt": 90.0, "area_m2": 10.0, "glass_m2": 0.0}],
    "roofs": [{"azimuth": 0.0, "tilt": 30.0, "area_m2": 12.0, "glass_m2": 0.0}],
    "windows": [],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock, enable_custom_integrations: None
) -> None:
    """As in ``conftest.py``, with the recorder (a dependency) started first."""
    return


def _archive() -> dict:
    """Two years of Open-Meteo's hours: -30 to +30 C, the dew point 10 K below."""
    temps = [-30.0 + 60.0 * ((h // 24) % 365) / 365 for h in range(LOADS_HOURS)]
    return {
        "hourly": {"temperature_2m": temps, "dew_point_2m": [t - 10 for t in temps]}
    }


@pytest.fixture(autouse=True)
def archive():
    """Open-Meteo's historical weather, without the network."""
    with patch(
        "custom_components.manual_j.downloads.fetch_archive",
        AsyncMock(return_value=_archive()),
    ) as fetch:
        yield fetch


@pytest.fixture
async def house(hass: HomeAssistant) -> dict:
    """House Structure (a stand-in), with an office, a garage and a furnace."""
    mock_integration(hass, MockModule(STRUCTURE_DOMAIN))
    areas = ar.async_get(hass)
    office = areas.async_create("Office")
    garage = areas.async_create("Garage")
    utility = areas.async_create("Utility")
    summary = {
        "version": 1,
        "rooms": {office.id: OFFICE, garage.id: {**OFFICE, "title": "Garage"}},
        "ducts": {},
        "equipment": {
            "furnaces": [
                {
                    "title": "Furnace",
                    "area_id": utility.id,
                    "input_high_w": 20000.0,
                    "afue": 0.95,
                    "blower": [],
                }
            ],
            "air_conditioners": [],
        },
        "buildings": [{"id": "b1", "title": "Garage", "area_ids": [garage.id]}],
    }
    hass.data[STRUCTURE_DOMAIN] = summary
    hass.config.elevation = 650
    return {"office": office.id, "garage": garage.id}


async def _set_up(hass: HomeAssistant, form: dict | None = None):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], form or {}
    )
    await hass.async_block_till_done()
    return result


async def _reconfigure(hass: HomeAssistant, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_setting_up_adds_the_tab_and_the_needs(
    hass: HomeAssistant, house
) -> None:
    result = await _set_up(hass, {"wall_r": 18})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"wall_r": 18.0}
    tab = hass.data[TABS][TAB_KEY]
    assert tab["title"] == "HVAC design"
    assert tab["url"].startswith("/manual_j_static/index.html?v=")
    assert tab["order"] == 20
    assert hass.data[NEEDS][DOMAIN]["needs"] == ["wall_size", "roof_size", "room_floor"]

    entry = result["result"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert TAB_KEY not in hass.data[TABS]
    assert DOMAIN not in hass.data[NEEDS]


async def test_an_envelope_value_must_be_positive(hass: HomeAssistant, house) -> None:
    result = await _set_up(hass, {"roof_r": 0})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"roof_r": "invalid_roof_r"}


async def test_a_building_gets_its_own_setpoints(hass: HomeAssistant, house) -> None:
    entry = (await _set_up(hass, {"wall_r": 18}))["result"]
    result = await _reconfigure(hass, entry)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["settings", "building"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "building"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"building": "Garage"}
    )
    assert result["step_id"] == "setpoints"
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"indoor_heat_c": 20, "indoor_cool_c": 15}
    )
    assert bad["errors"] == {"indoor_cool_c": "invalid_indoor_cool_c"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"indoor_heat_c": 10}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    assert entry.data == {
        "wall_r": 18.0,
        "buildings": {"Garage": {"indoor_heat_c": 10.0}},
    }

    # changing the settings keeps the building's setpoints
    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"wall_r": 22}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    assert entry.data == {
        "wall_r": 22.0,
        "buildings": {"Garage": {"indoor_heat_c": 10.0}},
    }


async def test_loads_are_worked_out_from_house_structure(
    hass: HomeAssistant, house, hass_ws_client
) -> None:
    await _set_up(hass, {"outdoor_entity": "sensor.outside"})
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "buildings": {"Garage": {"indoor_heat_c": 10.0}}}
    )
    hass.data[FITTED] = {house["office"]: {"a": 0.1}}
    # two years of hours: winter at -30, summer at +30
    hourly = [-30.0 if (h // 24) % 365 < 180 else 30.0 for h in range(LOADS_HOURS)]
    client = await hass_ws_client(hass)
    with patch(
        "custom_components.manual_j.panel.hourly_outdoor", return_value=hourly
    ) as record:
        await client.send_json_auto_id({"type": "manual_j/loads"})
        reply = await client.receive_json()
    assert reply["success"], reply
    result = reply["result"]
    assert result["available"]
    assert result["fitted"]
    assert record.call_args.args[1] == "sensor.outside"
    assert result["design"]["info"]["source"] == "recorded"
    assert [r["name"] for r in result["rooms"]] == ["Office"]
    assert result["rooms"][0]["ua_fit_w_k"] is not None
    assert result["equipment"]["heating"]["capacity_w"] == pytest.approx(19000.0)
    assert result["furnace_room"] == "Utility"
    garage = result["buildings"][0]
    assert garage["name"] == "Garage"
    assert garage["result"]["design"]["heat_indoor_c"] == 10.0


async def test_loads_without_rooms_say_so(
    hass: HomeAssistant, house, hass_ws_client
) -> None:
    await _set_up(hass)
    hass.data[STRUCTURE_DOMAIN] = {"version": 1, "rooms": {}}
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "manual_j/loads"})
    reply = await client.receive_json()
    assert reply["result"] == {
        "available": False,
        "reason": "House Structure has no rooms yet.",
    }


async def _loads(hass: HomeAssistant, hass_ws_client) -> dict:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "manual_j/loads"})
    reply = await client.receive_json()
    assert reply["success"], reply
    return reply["result"]


async def test_without_a_sensor_the_design_is_downloaded_once(
    hass: HomeAssistant, house, hass_ws_client, archive
) -> None:
    await _set_up(hass)
    result = await _loads(hass, hass_ws_client)
    design = result["design"]
    assert design["info"]["source"] == "downloaded"
    assert design["info"]["years"].endswith(str(dt_util.now().year - 1))
    assert design["heat_outdoor_c"] < -29
    assert design["altitude_m"] == 650
    assert any("Open-Meteo" in w for w in result["warnings"])
    assert not any("default outdoor humidity" in w for w in result["warnings"])
    await _loads(hass, hass_ws_client)
    assert archive.await_count == 1  # set-up's download is kept


async def test_a_failed_download_falls_back_to_the_assumed_design(
    hass: HomeAssistant, house, hass_ws_client, archive
) -> None:
    archive.side_effect = aiohttp.ClientError("offline")
    await _set_up(hass)
    result = await _loads(hass, hass_ws_client)
    info = result["design"]["info"]
    assert info["source"] == "assumed"
    assert "couldn't be downloaded" in info["warnings"][0]
    assert any("default outdoor humidity" in w for w in result["warnings"])
