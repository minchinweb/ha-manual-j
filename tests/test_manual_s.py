# Copyright (c) 2026 MinchinWeb
"""Manual S: the furnace and air conditioner."""

from __future__ import annotations

import pytest

from custom_components.manual_j.building import (
    Design,
)
from custom_components.manual_j.manual_s import (
    AirConditioner,
    Furnace,
    check_cooling,
    check_heating,
)


def test_furnace_output_applies_efficiency():
    f = Furnace({"high": 20000.0, "low": 13000.0}, efficiency=0.95)
    assert f.output_w("high") == pytest.approx(19000.0)
    assert f.output_w("low") == pytest.approx(12350.0)
    assert f.output_w("missing") is None


def test_furnace_needs_high_stage():
    with pytest.raises(ValueError):
        Furnace({"low": 10000.0})


def test_heating_check_oversized_and_undersized():
    f = Furnace({"high": 30000.0}, efficiency=1.0)
    design = Design()
    assert check_heating(10000.0, f, design)["verdict"] == "oversized"
    assert check_heating(40000.0, f, design)["verdict"] == "undersized"
    assert check_heating(25000.0, f, design)["verdict"] == "ok"


def test_cooling_capacity_falls_with_hotter_outdoors():
    ac = AirConditioner(total_w=10000.0, sensible_w=7500.0, rated_outdoor_c=35.0)
    at_rating, _ = ac.capacity_at(35.0)
    hotter, _ = ac.capacity_at(40.0)
    milder, _ = ac.capacity_at(28.0)
    assert at_rating == pytest.approx(10000.0)
    assert hotter < at_rating < milder


def test_cooling_check_uses_design_temperature():
    ac = AirConditioner(total_w=10000.0, sensible_w=7500.0)
    check = check_cooling(9000.0, 6000.0, ac, Design(cool_outdoor_c=35.0))
    assert check["capacity_total_w"] == pytest.approx(10000.0)
    assert check["verdict"] == "ok"
    assert check["ratio"] == pytest.approx(10000.0 / 9000.0)
