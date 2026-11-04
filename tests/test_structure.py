# Copyright (c) 2026 MinchinWeb
"""Reading House Structure's summary and Home Thermal Lab's fitted rates."""

from __future__ import annotations

from custom_components.manual_j import structure

SUMMARY = {
    "version": 1,
    "rooms": {"office": {"title": "Office"}},
    "ducts": {"trunk": {"length_m": 4.0}},
    "equipment": {"furnaces": [{"title": "Furnace", "input_high_w": 20000.0}]},
    "buildings": [
        {"id": "b1", "title": "Garage", "area_ids": ["garage"]},
        {"id": "b2", "title": "Shed", "area_ids": ["shed"]},
    ],
}


def test_the_parts_are_read():
    assert structure.rooms(SUMMARY) == {"office": {"title": "Office"}}
    assert structure.ducts(SUMMARY) == {"trunk": {"length_m": 4.0}}
    assert structure.equipment(SUMMARY) == {
        "furnaces": [{"title": "Furnace", "input_high_w": 20000.0}],
        "air_conditioners": [],
    }
    assert structure.building_names(SUMMARY) == ["Garage", "Shed"]


def test_an_unknown_version_or_none_gives_nothing():
    for data in (None, {}, {**SUMMARY, "version": 2}):
        assert structure.rooms(data) == {}
        assert structure.ducts(data) == {}
        assert structure.equipment(data) == {"furnaces": [], "air_conditioners": []}
        assert structure.buildings(data, {}) == []


def test_buildings_take_their_setpoints_by_name():
    setpoints = {"Garage": {"indoor_heat_c": 10.0}, "Gone": {"indoor_heat_c": 5.0}}
    assert structure.buildings(SUMMARY, setpoints) == [
        {"name": "Garage", "areas": ["garage"], "indoor_heat_c": 10.0},
        {"name": "Shed", "areas": ["shed"]},  # uses the house's
    ]


def test_fitted_rates_skip_what_they_cannot_read():
    data = {"office": {"a": 0.12}, "den": {"a": None}, "hall": {}, "attic": 3}
    assert structure.fitted_rates(data) == {"office": 0.12}
    assert structure.fitted_rates(None) == {}
