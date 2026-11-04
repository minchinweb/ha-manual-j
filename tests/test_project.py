# Copyright (c) 2026 MinchinWeb
"""Manual J, S and D together."""

from __future__ import annotations

import pytest

from custom_components.manual_j.building import (
    Room,
    Surface,
)
from custom_components.manual_j.manual_d import (
    ROUND_SIZES_IN,
    Run,
    Segment,
)
from custom_components.manual_j.manual_s import (
    AirConditioner,
    Furnace,
)
from custom_components.manual_j.project import Project, calculate


def _wall(area=10.0, u=0.3, **kw):
    return Surface("wall", "wall", area, u=u, **kw)


def test_full_calculation_returns_consistent_totals():
    wall = _wall(area=20.0, u=0.3)
    window = Surface("window", "window", 3.0, u=1.8, shgc=0.6, face="S")
    rooms = (
        Room("Office", 50.0, (wall, window), ach=0.5, people=1),
        Room("Bedroom", 40.0, (wall,), ach=0.5),
    )
    furnace = Furnace(
        {"high": 25000.0, "low": 16000.0},
        efficiency=0.95,
        blower=((0.0, 250.0), (0.1, 150.0), (0.2, 60.0)),
    )
    ac = AirConditioner(total_w=12000.0, sensible_w=9000.0)
    runs = (
        Run(
            "Office supply",
            "Office",
            register_area_m2=0.02,
            segments=(
                Segment.round_in(8, 4.0, trunk=True, flow_m3s=0.08),
                Segment.round_in(4, 3.0, fittings_k=0.5),
            ),
        ),
        Run(
            "Bedroom supply",
            "Bedroom",
            register_area_m2=0.02,
            segments=(Segment.round_in(4, 5.0, fittings_k=0.9),),
        ),
    )
    result = calculate(Project(rooms=rooms, furnace=furnace, ac=ac, runs=runs))

    rooms_out = result["rooms"]
    assert result["totals"]["heating_w"] == pytest.approx(
        rooms_out["Office"]["heating_w"] + rooms_out["Bedroom"]["heating_w"]
    )
    assert result["totals"]["cooling_total_w"] == pytest.approx(
        result["totals"]["cooling_sensible_w"] + result["totals"]["cooling_latent_w"]
    )
    assert result["equipment"]["heating"]["verdict"] in (
        "ok",
        "oversized",
        "undersized",
    )
    assert len(result["ducts"]["runs"]) == 2
    assert result["ducts"]["budget_pa"] is not None
    for run in result["ducts"]["runs"]:
        assert run["loss_pa"] > 0
        assert run["branch_round_in"] in ROUND_SIZES_IN


def test_calculation_without_furnace_still_gives_loads():
    room = Room("Office", 50.0, (_wall(),), ach=0.5)
    result = calculate(Project(rooms=(room,)))
    assert result["equipment"]["heating"] is None
    assert result["rooms"]["Office"]["heating_w"] > 0
    assert result["ducts"]["runs"] == []


def test_run_in_unknown_room_is_an_error():
    room = Room("Office", 50.0, (_wall(),))
    run = Run("x", "Nowhere", 0.02, (Segment.round_in(4, 1.0),))
    furnace = Furnace({"high": 20000.0}, blower=((0.0, 200.0), (0.2, 50.0)))
    with pytest.raises(ValueError):
        calculate(Project(rooms=(room,), furnace=furnace, runs=(run,)))
