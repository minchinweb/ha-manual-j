# Copyright (c) 2026 MinchinWeb
"""Manual J: each room's heating and cooling loads and the airflow they call for.

Cooling uses the design temperature difference and a design-day solar gain
per face rather than ACCA's CLTD and SCL tables, so cooling loads are
approximate.

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Standard library only, so it is tested without
Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .air import air_density, rho_cp
from .building import Design, Room

H_FG = 2.45e6  # J/kg, latent heat of water near room temperature
PEOPLE_SENSIBLE_W = 70.0
PEOPLE_LATENT_W = 45.0


@dataclass(frozen=True)
class RoomLoad:
    """A room's design loads, with the parts that make them up."""

    room: str
    heating_w: float
    heating_parts: Mapping[str, float]
    cooling_sensible_w: float
    cooling_sensible_parts: Mapping[str, float]
    cooling_latent_w: float
    cooling_latent_parts: Mapping[str, float]
    airflow_m3s: float

    @property
    def cooling_total_w(self) -> float:
        return self.cooling_sensible_w + self.cooling_latent_w


def heating_load(room: Room, design: Design) -> tuple[float, dict[str, float]]:
    """Heat loss at the design winter temperature, W, and its parts.

    Conduction through each surface plus infiltration. Internal gains are not
    counted, as in Manual J.
    """
    parts: dict[str, float] = {}
    for s in room.surfaces:
        sink = design.ground_c if s.ground else design.heat_outdoor_c
        parts[s.name] = s.conductance * (design.heat_indoor_c - sink)
    air_flow = room.ach * room.volume / 3600.0
    parts["infiltration"] = (
        air_flow
        * rho_cp(design.heat_indoor_c, design.altitude_m)
        * (design.heat_indoor_c - design.heat_outdoor_c)
    )
    return sum(parts.values()), parts


def cooling_load(
    room: Room, design: Design
) -> tuple[dict[str, float], dict[str, float]]:
    """Sensible and latent gains at the design summer conditions, W.

    Each gain is clipped at zero, so a surface that would cool the room is not
    credited. Opaque surfaces take no solar gain in this simplified method.
    Returns the sensible parts and the latent parts.
    """
    sensible: dict[str, float] = {}
    for s in room.surfaces:
        sink = design.ground_c if s.ground else design.cool_outdoor_c
        gain = s.conductance * (sink - design.cool_indoor_c)
        if s.kind == "window":
            gain += s.area * s.shgc * design.solar_w_m2.get(s.face, 0.0)
        sensible[s.name] = max(gain, 0.0)
    air_flow = room.ach * room.volume / 3600.0
    sensible["infiltration"] = max(
        air_flow
        * rho_cp(design.cool_indoor_c, design.altitude_m)
        * (design.cool_outdoor_c - design.cool_indoor_c),
        0.0,
    )
    sensible["people"] = room.people * PEOPLE_SENSIBLE_W
    sensible["internal"] = room.gains_w
    latent = {
        "infiltration": air_flow
        * air_density(design.cool_indoor_c, design.altitude_m)
        * H_FG
        * max(design.cool_outdoor_w - design.cool_indoor_w, 0.0),
        "people": room.people * PEOPLE_LATENT_W,
    }
    return sensible, latent


def room_airflow(heating_w: float, cooling_sensible_w: float, design: Design) -> float:
    """Supply air a room needs, m³/s: the larger of its heating and cooling flows."""
    heat = heating_w / (
        rho_cp(design.heat_indoor_c, design.altitude_m) * design.heat_rise_k
    )
    cool = cooling_sensible_w / (
        rho_cp(design.cool_indoor_c, design.altitude_m) * design.cool_rise_k
    )
    return max(heat, cool, 0.0)


def room_load(room: Room, design: Design) -> RoomLoad:
    """Manual J for one room."""
    heat, heat_parts = heating_load(room, design)
    sens, lat = cooling_load(room, design)
    sensible = sum(sens.values())
    return RoomLoad(
        room=room.name,
        heating_w=heat,
        heating_parts=heat_parts,
        cooling_sensible_w=sensible,
        cooling_sensible_parts=sens,
        cooling_latent_w=sum(lat.values()),
        cooling_latent_parts=lat,
        airflow_m3s=room_airflow(heat, sensible, design),
    )
