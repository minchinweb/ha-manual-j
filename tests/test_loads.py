# Copyright (c) 2026 MinchinWeb
"""Tests for the HVAC design tab's numbers (standard library only)."""

from __future__ import annotations

import pytest

from custom_components.manual_j.air import rho_cp
from custom_components.manual_j.building import Design, room_capacity, ua_from_rate
from custom_components.manual_j.house_model import (
    Nominal,
    build_project,
    envelope_from_fit,
    ground_fraction,
)
from custom_components.manual_j.loads import (
    HUMIDITY_NOTE,
    assemble,
    assemble_all,
    design_from_record,
    equipment_from,
)
from custom_components.manual_j.manual_s import AirConditioner, Furnace

HOURS = 2 * 8760


def _basement(**extra):
    room = {
        "title": "Basement",
        "floor_m2": 40.0,
        "height_m": 2.4,
        "below_ground": True,
        "walls": [{"azimuth": 0.0, "tilt": 90.0, "area_m2": 20.0, "glass_m2": 0.0}],
        "roofs": [],
        "windows": [],
    }
    room.update(extra)
    return {"basement": room}


def test_ground_fraction_is_depth_over_height():
    assert ground_fraction(_basement(below_grade_m=1.2)["basement"]) == pytest.approx(
        0.5
    )


def test_ground_fraction_is_clamped_and_defaults_to_all_ground():
    assert ground_fraction(_basement(below_grade_m=5.0)["basement"]) == 1.0
    assert ground_fraction(_basement()["basement"]) == 1.0
    above = {"below_ground": False, "below_grade_m": 1.0, "height_m": 2.4}
    assert ground_fraction(above) == 0.0


def test_below_grade_depth_splits_the_walls():
    project, warnings = build_project(
        _basement(below_grade_m=1.2), Nominal(), Design(), {"basement": "Basement"}
    )
    walls = [s for s in project.rooms[0].surfaces if s.kind == "wall"]
    below = next(s for s in walls if s.ground)
    above = next(s for s in walls if not s.ground)
    assert below.area == pytest.approx(10.0)
    assert above.area == pytest.approx(10.0)
    assert not any("below-grade depth" in w for w in warnings)


def test_no_depth_warns_and_takes_every_wall_as_ground():
    project, warnings = build_project(_basement(), Nominal(), Design())
    walls = [s for s in project.rooms[0].surfaces if s.kind == "wall"]
    assert len(walls) == 1 and walls[0].ground
    assert any("no below-grade depth" in w for w in warnings)


def test_envelope_fit_counts_only_the_above_grade_walls():
    rooms = _basement(below_grade_m=1.2)
    capacity = room_capacity(40.0 * 2.4)
    rate = 10.0 * 3600.0 / capacity  # a measured envelope of 10 W/K
    result = envelope_from_fit(
        rooms,
        {"basement": rate},
        {"basement": capacity},
        {"basement": 0.0},
        {"basement": 0.0},
        Nominal(),
    )
    (element,) = result["basement"]["elements"]
    assert element["area"] == pytest.approx(10.0)


def test_design_from_a_full_record_uses_the_recorded_extremes():
    hourly = [float(i % 40 - 30) for i in range(HOURS)]  # -30 to 9 °C
    design, info = design_from_record(hourly, Design())
    assert info["source"] == "recorded"
    assert design.heat_outdoor_c == pytest.approx(-30.0, abs=0.5)
    assert design.cool_outdoor_c == pytest.approx(9.0, abs=0.5)
    assert design.heat_outdoor_c == pytest.approx(info["heat_outdoor_c"])


def test_design_from_a_short_record_stays_assumed():
    base = Design()
    design, info = design_from_record([0.0] * 100 + [None] * 50, base)
    assert info["source"] == "assumed"
    assert design == base
    assert info["warnings"]


def test_furnace_and_ac_from_house_structure():
    equipment = {
        "furnaces": [
            {
                "title": "Furnace",
                "area_id": "utility",
                "input_high_w": 23400.0,
                "input_low_w": 15200.0,
                "afue": 0.95,
                "blower": [[0.2, 50.0], [0.4, 150.0]],
            }
        ],
        "air_conditioners": [{"title": "AC", "total_w": 3516.0, "sensible_w": None}],
    }
    furnace, ac, area, warnings = equipment_from(equipment)
    assert furnace.stages_input_w == pytest.approx({"high": 23400.0, "low": 15200.0})
    assert furnace.efficiency == pytest.approx(0.95)
    assert furnace.blower == ((0.2, 50.0), (0.4, 150.0))
    assert area == "utility"
    assert ac.total_w == pytest.approx(3516.0)
    assert ac.sensible_w == pytest.approx(0.8 * 3516.0)
    assert any("sensible" in w for w in warnings)


def test_no_equipment_is_none():
    assert equipment_from(None) == (None, None, None, [])
    assert equipment_from({"furnaces": [], "air_conditioners": []})[:2] == (None, None)


def test_missing_afue_is_taken_as_full_efficiency():
    furnace, _, _, warnings = equipment_from(
        {"furnaces": [{"input_high_w": 10000.0, "afue": None}]}
    )
    assert furnace.efficiency == 1.0
    assert any("AFUE" in w for w in warnings)


def test_only_the_first_furnace_is_checked():
    furnaces = [
        {"title": "Main", "input_high_w": 20000.0, "afue": 0.95},
        {"title": "Shop", "input_high_w": 9000.0, "afue": 0.8},
    ]
    furnace, _, _, warnings = equipment_from({"furnaces": furnaces})
    assert furnace.stages_input_w == {"high": 20000.0}
    assert any("2 furnaces" in w and "Main" in w for w in warnings)


def test_assemble_contrasts_calculated_and_fitted_conductance():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [{"area_m2": 20.0, "glass_m2": 0.0}],
            "roofs": [],
            "windows": [],
        }
    }
    rate = 0.05
    furnace = Furnace({"high": 30000.0, "low": 20000.0}, efficiency=0.95)
    ac = AirConditioner(total_w=3500.0, sensible_w=2800.0)
    result = assemble(
        rooms,
        {"office": "Office"},
        {"office": rate},
        Nominal(),
        Design(),
        furnace=furnace,
        ac=ac,
        extra_warnings=[HUMIDITY_NOTE],
    )
    (room,) = result["rooms"]
    design = Design()
    infiltration = (
        0.35 * 50.0 / 3600.0 * rho_cp(design.heat_indoor_c, design.altitude_m)
    )
    assert room["ua_calc_w_k"] == pytest.approx(20.0 / 3.5 + infiltration)
    assert room["ua_fit_w_k"] == pytest.approx(ua_from_rate(rate, room_capacity(50.0)))
    assert room["heating_w"] > 0
    assert result["equipment"]["heating"]["capacity_w"] == pytest.approx(28500.0)
    assert result["equipment"]["cooling"]["verdict"] in (
        "undersized",
        "ok",
        "oversized",
    )
    assert HUMIDITY_NOTE in result["warnings"]
    assert result["design"]["info"]["source"] == "assumed"


def test_assemble_without_a_fit_leaves_the_fitted_value_empty():
    rooms = {"office": {"volume_m3": 50.0, "walls": [{"area_m2": 9.0}]}}
    result = assemble(rooms, {}, {}, Nominal(), Design())
    assert result["rooms"][0]["ua_fit_w_k"] is None
    assert result["rooms"][0]["fit_ratio"] is None
    assert result["equipment"]["heating"] is None
    assert result["equipment"]["cooling"] is None
    # The design size is there even with no equipment configured.
    assert result["equipment"]["cooling_design"]["load_total_w"] > 0
    assert result["equipment"]["heating_design"]["load_w"] > 0


def test_the_furnace_room_is_passed_through():
    rooms = {"office": {"volume_m3": 50.0, "walls": [{"area_m2": 9.0}]}}
    result = assemble(rooms, {}, {}, Nominal(), Design(), furnace_room="Basement")
    assert result["furnace_room"] == "Basement"
    assert assemble(rooms, {}, {}, Nominal(), Design())["furnace_room"] is None


def _room(title, area_m2=30.0):
    return {
        "title": title,
        "floor_m2": area_m2,
        "height_m": 2.4,
        "walls": [{"azimuth": 0.0, "tilt": 90.0, "area_m2": 12.0, "glass_m2": 0.0}],
        "roofs": [],
        "windows": [],
    }


def test_a_detached_building_leaves_the_house_and_is_sized_on_its_own():
    rooms = {"office": _room("Office"), "garage": _room("Garage", 40.0)}
    names = {"office": "Office", "garage": "Garage"}
    result = assemble_all(
        rooms,
        names,
        {},
        Nominal(),
        Design(),
        buildings=[{"name": "Garage", "areas": ["garage"]}],
    )
    assert [r["name"] for r in result["rooms"]] == ["Office"]
    (garage,) = result["buildings"]
    assert garage["missing"] == []
    assert [r["name"] for r in garage["result"]["rooms"]] == ["Garage"]
    assert garage["result"]["equipment"]["heating_design"]["load_w"] > 0
    assert garage["result"]["equipment"]["heating"] is None


def test_a_building_setpoint_changes_its_heat_loss():
    rooms = {"office": _room("Office"), "garage": _room("Garage", 40.0)}
    names = {"office": "Office", "garage": "Garage"}
    warm = assemble_all(
        rooms,
        names,
        {},
        Nominal(),
        Design(),
        buildings=[{"name": "Garage", "areas": ["garage"]}],
    )["buildings"][0]["result"]["equipment"]["heating_design"]["load_w"]
    cold = assemble_all(
        rooms,
        names,
        {},
        Nominal(),
        Design(),
        buildings=[{"name": "Garage", "areas": ["garage"], "indoor_heat_c": 10.0}],
    )["buildings"][0]["result"]["equipment"]["heating_design"]["load_w"]
    assert cold < warm  # a colder setpoint is a smaller temperature difference


def test_a_building_with_no_rooms_yet_is_reported_as_missing():
    rooms = {"office": _room("Office")}
    result = assemble_all(
        rooms,
        {"office": "Office"},
        {},
        Nominal(),
        Design(),
        buildings=[{"name": "Garage", "areas": ["garage"]}],
    )
    (garage,) = result["buildings"]
    assert garage["result"] is None
    assert garage["missing"] == ["garage"]
