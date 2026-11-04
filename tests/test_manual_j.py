# Copyright (c) 2026 MinchinWeb
"""Manual J: room loads."""

from __future__ import annotations

import pytest

from custom_components.manual_j.air import air_density
from custom_components.manual_j.building import (
    Design,
    Room,
    Surface,
)
from custom_components.manual_j.manual_j import cooling_load, heating_load


def _wall(area=10.0, u=0.3, **kw):
    return Surface("wall", "wall", area, u=u, **kw)


def test_heating_conduction_without_infiltration():
    room = Room("r", volume=30.0, surfaces=(_wall(),), ach=0.0)
    design = Design(heat_outdoor_c=-27.0, heat_indoor_c=21.0)
    total, parts = heating_load(room, design)
    # 10 m² at 0.3 W/m²K across a 48 K difference
    assert total == pytest.approx(144.0)
    assert parts["infiltration"] == 0.0


def test_ground_surface_uses_ground_temperature():
    floor = Surface("slab", "floor", 10.0, u=0.5, ground=True)
    room = Room("r", volume=30.0, surfaces=(floor,), ach=0.0)
    design = Design(ground_c=5.6, heat_indoor_c=21.0)
    total, _ = heating_load(room, design)
    assert total == pytest.approx(10.0 * 0.5 * (21.0 - 5.6))


def test_infiltration_scales_with_volume_and_air_change():
    room = Room("r", volume=36.0, surfaces=(), ach=1.0)  # 36 m³/h = 0.01 m³/s
    design = Design(heat_outdoor_c=-27.0, heat_indoor_c=21.0, altitude_m=0.0)
    total, _ = heating_load(room, design)
    expected = 0.01 * air_density(21.0) * 1006.0 * 48.0
    assert total == pytest.approx(expected, rel=1e-3)


def test_window_solar_gain_on_its_face():
    win = Surface("window", "window", 2.0, u=0.0, shgc=0.5, face="S")
    room = Room("r", volume=30.0, surfaces=(win,), ach=0.0)
    design = Design(solar_w_m2={"S": 220.0})
    sens, _ = cooling_load(room, design)
    assert sens["window"] == pytest.approx(2.0 * 0.5 * 220.0)


def test_people_and_internal_gains_are_cooling_only():
    room = Room("r", volume=30.0, surfaces=(), ach=0.0, people=2, gains_w=300.0)
    sens, lat = cooling_load(room, Design())
    assert sens["people"] == pytest.approx(140.0)
    assert sens["internal"] == pytest.approx(300.0)
    assert lat["people"] == pytest.approx(90.0)
    assert "people" not in heating_load(room, Design())[1]
