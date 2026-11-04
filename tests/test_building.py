# Copyright (c) 2026 MinchinWeb
"""Surfaces, air, design temperatures and the envelope from measurement."""

from __future__ import annotations

import pytest

from custom_components.manual_j.air import air_density, btu_h, inches
from custom_components.manual_j.building import (
    Element,
    Surface,
    cooling_humidity,
    design_temperatures,
    envelope_scale,
    humidity_ratio,
    infiltration_ua,
    natural_ach,
    room_capacity,
    ua_from_rate,
    window_u,
)


def _wall(area=10.0, u=0.3, **kw):
    return Surface("wall", "wall", area, u=u, **kw)


def test_surface_needs_u_or_r():
    with pytest.raises(ValueError):
        Surface("x", "wall", 10.0)


def test_r_value_gives_u_value():
    s = Surface("wall", "wall", 10.0, r=3.5)
    assert s.conductance == pytest.approx(10.0 / 3.5)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        Surface("x", "ceiling", 10.0, u=0.2)


def test_air_density_at_edmonton_is_thinner_than_sea_level():
    sea = air_density(20.0, 0.0)
    edmonton = air_density(20.0, 723.0)
    assert sea == pytest.approx(1.204, abs=0.005)
    assert edmonton == pytest.approx(1.10, abs=0.01)


def test_unit_helpers():
    assert inches(4) == pytest.approx(0.1016)
    assert btu_h(80000) == pytest.approx(23446, rel=1e-3)


def test_design_temperatures_from_a_year_of_hours():
    # A year of hours spanning -30 to +30 C, evenly spread.
    hours = [-30.0 + 60.0 * i / (8760 - 1) for i in range(8760)]
    result = design_temperatures(hours)
    # 0.4% of 8760 hours is about 35 hours: the coldest value is near -30.
    assert result["heat_c"] == pytest.approx(-30.0 + 60.0 * 35 / 8759, abs=0.1)
    assert result["cool_c"] == pytest.approx(30.0 - 60.0 * 35 / 8759, abs=0.1)
    assert (
        result["heat_c"] < result["heat_c_99"] < result["cool_c_1"] < result["cool_c"]
    )
    assert result["hours"] == 8760
    assert any("one year" in w for w in result["warnings"])


def test_design_temperatures_skip_missing_hours():
    hours = [10.0] * 8000 + [None] * 500 + [-20.0] * 300
    result = design_temperatures(hours, min_hours=8000)
    assert result["hours"] == 8300
    assert result["heat_c"] == pytest.approx(-20.0)


def test_design_temperatures_need_enough_hours():
    with pytest.raises(ValueError):
        design_temperatures([0.0] * 100)


def test_two_years_drop_the_single_year_warning():
    hours = [float(i % 40 - 20) for i in range(2 * 8760)]
    result = design_temperatures(hours)
    assert not any("one year" in w for w in result["warnings"])


def test_humidity_ratio_at_a_known_dew_point():
    # 20 C dew point at sea level: about 0.0147 kg/kg
    assert humidity_ratio(20.0, 0.0) == pytest.approx(0.0147, abs=0.0002)


def test_cooling_humidity_uses_only_hot_hours():
    hours = [(30.0, 18.0)] * 6 + [(20.0, 5.0)] * 100 + [(30.0, None)]
    result = cooling_humidity(hours, cool_c=28.0)
    assert result["hours"] == 6
    assert result["w"] == pytest.approx(humidity_ratio(18.0))
    assert result["warnings"] == []


def test_few_hot_hours_warn():
    result = cooling_humidity([(30.0, 18.0)] * 2, cool_c=28.0)
    assert result["warnings"]


def test_cooling_humidity_needs_hot_hours():
    with pytest.raises(ValueError):
        cooling_humidity([(10.0, 5.0)], cool_c=28.0)


def test_capacity_and_rate_to_conductance():
    cap = room_capacity(50.0)  # air only
    assert cap == pytest.approx(50.0 * 1200.0 * 1005.0)
    # a rate of 0.01 per hour on that room is about 16.7 W/K
    assert ua_from_rate(0.01, cap) == pytest.approx(0.01 * cap / 3600.0)
    assert room_capacity(50.0, furnishing_kg=1000.0) > cap


def test_blower_door_to_natural_ach():
    # 2000 CFM50 on 400 m³ is about 8.5 ACH50, so about 0.42 natural at N = 20
    ach = natural_ach(2000.0, 400.0, n_factor=20.0)
    assert ach == pytest.approx(2000.0 * 1.69901 / 400.0 / 20.0)
    assert infiltration_ua(ach, 400.0) > 0


def test_window_u_lookup_is_case_insensitive():
    assert window_u("Double", "Vinyl") == 1.22
    with pytest.raises(ValueError):
        window_u("single", "vinyl")


def test_envelope_scale_recovers_a_known_factor():
    elements = [Element("wall", 40.0, 3.5), Element("roof", 20.0, 6.0)]
    # Build the measured conductance from a scale of 1.5 on the nominal U values
    nominal = 40.0 / 3.5 + 20.0 / 6.0
    fixed = 5.0
    measured = fixed + 1.5 * nominal
    result = envelope_scale(elements, fixed_ua=fixed, measured_ua=measured)
    assert result["scale"] == pytest.approx(1.5)
    wall = result["elements"][0]
    assert wall["u"] == pytest.approx(1.5 / 3.5)
    assert wall["r"] == pytest.approx(3.5 / 1.5)
    assert result["warnings"] == []


def test_envelope_scale_warns_on_implausible_factor():
    elements = [Element("wall", 40.0, 3.5)]
    result = envelope_scale(elements, fixed_ua=0.0, measured_ua=40.0 / 3.5 * 3.0)
    assert result["warnings"]


def test_envelope_scale_rejects_measurement_below_fixed_parts():
    with pytest.raises(ValueError):
        envelope_scale([Element("wall", 40.0, 3.5)], fixed_ua=50.0, measured_ua=10.0)
