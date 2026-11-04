# Copyright (c) 2026 MinchinWeb
"""What Manual J reads from the other integrations (standard library only).

House Structure publishes the house in ``hass.data["house_structure"]``: its
rooms by area id, the shared duct sections, the equipment and the detached
buildings. Home Thermal Lab, when it is installed, publishes each zone's
fitted cooling rate in ``hass.data["home_thermal_lab_fitted"]``. Neither is
imported: both are plain data, read through these functions, which give
nothing when the data is missing or of a version they don't know.
"""

from __future__ import annotations

from collections.abc import Mapping

from .constants import INDOOR_COOL, INDOOR_HEAT, STRUCTURE_VERSION


def _summary(data: Mapping | None) -> Mapping:
    if not data or data.get("version") != STRUCTURE_VERSION:
        return {}
    return data


def rooms(data: Mapping | None) -> dict[str, dict]:
    """House Structure's rooms by area id (none if it isn't set up)."""
    return dict(_summary(data).get("rooms") or {})


def ducts(data: Mapping | None) -> dict[str, dict]:
    """House Structure's shared duct sections by name."""
    return dict(_summary(data).get("ducts") or {})


def equipment(data: Mapping | None) -> dict:
    """House Structure's ``{"furnaces": [...], "air_conditioners": [...]}``."""
    found = _summary(data).get("equipment") or {}
    return {
        "furnaces": list(found.get("furnaces") or []),
        "air_conditioners": list(found.get("air_conditioners") or []),
    }


def buildings(data: Mapping | None, setpoints: Mapping | None) -> list[dict]:
    """House Structure's detached buildings, with Manual J's setpoints for them.

    Args:
        data: House Structure's summary.
        setpoints: Manual J's setpoints by building name:
            ``{name: {"indoor_heat_c"?, "indoor_cool_c"?}}``.

    Returns:
        Each building as ``{"name", "areas", "indoor_heat_c"?,
        "indoor_cool_c"?}``, the shape ``loads.assemble_all`` takes. A
        building with no setpoints uses the house's.
    """
    out = []
    for building in _summary(data).get("buildings") or []:
        name = building.get("title") or "Building"
        own = (setpoints or {}).get(name) or {}
        out.append(
            {
                "name": name,
                "areas": list(building.get("area_ids") or []),
                **{k: own[k] for k in (INDOOR_HEAT, INDOOR_COOL) if k in own},
            }
        )
    return out


def building_names(data: Mapping | None) -> list[str]:
    """The names of House Structure's detached buildings, in order."""
    return [b["name"] for b in buildings(data, None)]


def fitted_rates(data: Mapping | None) -> dict[str, float]:
    """Home Thermal Lab's fitted cooling rate ``a`` (per hour) by area id.

    ``data`` is ``{area_id: {"a": per_hour}}``; anything else is skipped.
    """
    out: dict[str, float] = {}
    for area, fit in (data or {}).items():
        try:
            out[str(area)] = float(fit["a"])
        except KeyError, TypeError, ValueError:
            continue
    return out
