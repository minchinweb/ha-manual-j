# Copyright (c) 2026 MinchinWeb
"""Tests for building the Manual J project from House Structure's rooms."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.manual_j.building import Design
from custom_components.manual_j.house_model import (
    R_IP_TO_SI,
    Nominal,
    build_project,
    envelope_from_fit,
    nominal_from_settings,
    room_capacities,
    room_geometry,
)
from custom_components.manual_j.manual_s import Furnace
from custom_components.manual_j.project import calculate

ROOMS = {
    "office": {
        "title": "Office",
        "floor_m2": 12.0,
        "height_m": 2.4,
        "volume_m3": 28.8,
        "below_ground": False,
        "walls": [
            {"azimuth": 180.0, "tilt": 90.0, "area_m2": 10.0, "glass_m2": 2.0},
            {"azimuth": 90.0, "tilt": 90.0, "area_m2": 8.0, "glass_m2": 0.0},
        ],
        "roofs": [{"azimuth": 0.0, "tilt": 30.0, "area_m2": 12.0, "glass_m2": 0.0}],
        "windows": [
            {
                "azimuth": 180.0,
                "tilt": 90.0,
                "in": "wall",
                "glass_m2": 2.0,
                "transmittance": 0.7,
            },
        ],
    },
    "basement": {
        "title": "Basement",
        "floor_m2": 40.0,
        "height_m": 2.3,
        "volume_m3": None,
        "below_ground": True,
        "walls": [{"azimuth": 0.0, "tilt": 90.0, "area_m2": 20.0, "glass_m2": 0.0}],
        "roofs": [],
        "windows": [],
    },
    "empty": {"title": "Empty", "walls": [], "roofs": [], "windows": []},
}


def test_volume_falls_back_to_floor_times_height_and_skips_unknown():
    project, warnings = build_project(ROOMS, Nominal(), Design())
    basement = next(r for r in project.rooms if r.name == "Basement")
    assert basement.volume == pytest.approx(40.0 * 2.3)
    assert any("Empty" in w for w in warnings)


def test_walls_take_net_area_and_windows_their_glazing():
    project, _ = build_project(ROOMS, Nominal(), Design())
    office = next(r for r in project.rooms if r.name == "Office")
    walls = [s for s in office.surfaces if s.kind == "wall"]
    windows = [s for s in office.surfaces if s.kind == "window"]
    assert sum(w.area for w in walls) == pytest.approx(8.0 + 8.0)
    assert windows[0].area == pytest.approx(2.0)
    assert windows[0].face == "S"
    assert windows[0].shgc == pytest.approx(0.7)
    assert windows[0].u == pytest.approx(1.22)


def test_below_ground_walls_are_ground_coupled():
    project, _ = build_project(ROOMS, Nominal(), Design())
    basement = next(r for r in project.rooms if r.name == "Basement")
    assert all(s.ground for s in basement.surfaces)


def test_project_runs_through_manual_j():
    project, _ = build_project(ROOMS, Nominal(), Design())
    result = calculate(project)
    assert result["totals"]["heating_w"] > 0
    assert result["rooms"]["Office"]["heating_w"] > 0


def test_room_capacities_use_volume():
    caps = room_capacities(ROOMS)
    assert caps["office"] == pytest.approx(28.8 * 1200.0 * 1005.0)
    assert "empty" not in caps


def test_no_usable_room_is_an_error():
    with pytest.raises(ValueError):
        build_project({"empty": ROOMS["empty"]}, Nominal(), Design())


def test_register_ducts_become_runs():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [{"area_m2": 10.0, "glass_m2": 0.0, "azimuth": 0.0}],
            "roofs": [],
            "windows": [],
            "registers": [
                {
                    "title": "Office register",
                    "free_area_in2": 60.0,
                    "flow_cfm": 90.0,
                    "duct": [
                        {
                            "shape": "round",
                            "diameter_in": 4.0,
                            "length_ft": 14.0,
                            "fittings_k": 0.9,
                        },
                        {
                            "shape": "rect",
                            "width_in": 10.0,
                            "height_in": 6.0,
                            "length_ft": 3.0,
                            "trunk": True,
                            "flow_cfm": 400.0,
                        },
                    ],
                }
            ],
        }
    }
    project, _ = build_project(rooms, Nominal(), Design())
    (run,) = project.runs
    assert run.room == "Office"
    assert run.register_area_m2 == pytest.approx(60 * 0.00064516)
    assert run.flow_m3s == pytest.approx(90 * 0.000471947)
    assert len(run.segments) == 2
    # no furnace, so no blower curve: the duct check is skipped, and says so
    result = calculate(project)
    assert result["ducts"]["runs"] == []
    assert any("Duct check skipped" in w for w in result["warnings"])


def test_stored_r_values_and_glazing_override_the_defaults():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [
                {"area_m2": 10.0, "glass_m2": 0.0, "azimuth": 0.0, "r_value_si": 5.0}
            ],
            "roofs": [],
            "windows": [
                {
                    "in": "wall",
                    "glass_m2": 2.0,
                    "azimuth": 180.0,
                    "transmittance": 0.5,
                    "glazing": "triple",
                    "frame": "wood",
                }
            ],
        }
    }
    project, _ = build_project(rooms, Nominal(), Design())
    room = project.rooms[0]
    wall = next(s for s in room.surfaces if s.kind == "wall")
    window = next(s for s in room.surfaces if s.kind == "window")
    assert wall.r == pytest.approx(5.0)
    assert window.u == pytest.approx(1.0)  # triple wood


def test_envelope_from_fit_recovers_the_scale():
    rooms = {
        "office": {
            "title": "Office",
            "volume_m3": 50.0,
            "walls": [{"area_m2": 40.0, "glass_m2": 0.0}],
            "roofs": [],
            "windows": [],
        }
    }
    nominal_ua = 40.0 / 3.5
    fixed, infil = 2.0, 5.0
    cap = room_capacities(rooms)["office"]
    # the fitted rate that would give a measured envelope of 1.0 x nominal
    rate = (fixed + infil + nominal_ua) * 3600.0 / cap
    result = envelope_from_fit(
        rooms,
        rates={"office": rate},
        capacities={"office": cap},
        fixed_ua={"office": fixed},
        infiltration={"office": infil},
        nominal=Nominal(),
    )
    assert result["office"]["scale"] == pytest.approx(1.0)
    assert result["office"]["elements"][0]["r"] == pytest.approx(3.5)


def test_rooms_without_a_fit_are_left_out():
    rooms = {"office": {"volume_m3": 50.0, "walls": [{"area_m2": 9.0}]}}
    assert envelope_from_fit(rooms, {}, {}, {}, {}, Nominal()) == {}


CFM = 0.000471947


def _tree_rooms(**overrides):
    """Two rooms whose registers hang off one shared trunk."""

    def room(title, reg_title, flow, duct):
        return {
            "title": title,
            "volume_m3": 50.0,
            "walls": [{"area_m2": 10.0, "glass_m2": 0.0}],
            "roofs": [],
            "windows": [],
            "registers": [
                {
                    "title": reg_title,
                    "free_area_in2": 60.0,
                    "flow_cfm": flow,
                    "upstream": overrides.get("upstream", "Trunk"),
                    "duct": duct,
                }
            ],
        }

    branch_a = [{"shape": "round", "diameter_in": 4.0, "length_ft": 10.0}]
    branch_b = [{"shape": "rect", "width_in": 10.0, "height_in": 6.0, "length_ft": 4.0}]
    return {
        "a": room("A", "A reg", 300.0, branch_a),
        "b": room("B", "B reg", 200.0, branch_b),
    }


TREE = {
    "Plenum": {
        "upstream": None,
        "segments": [
            {"shape": "round", "diameter_in": 10.0, "length_ft": 6.0, "fittings_k": 0.5}
        ],
    },
    "Trunk": {
        "upstream": "Plenum",
        "segments": [{"shape": "round", "diameter_in": 8.0, "length_ft": 12.0}],
    },
}


def test_registers_share_their_upstream_sections():
    project, warnings = build_project(_tree_rooms(), Nominal(), Design(), ducts=TREE)
    runs = {r.name: r for r in project.runs}
    a = runs["A reg"]
    # the plenum, the trunk, then the register's own branch
    assert [s.trunk for s in a.segments] == [True, True, False]
    assert a.segments[0].length_m == pytest.approx(6 * 0.3048)
    assert a.segments[1].length_m == pytest.approx(12 * 0.3048)
    assert a.segments[2].length_m == pytest.approx(10 * 0.3048)
    # the shared sections carry both registers' airflow
    assert a.segments[0].flow_m3s == pytest.approx(500 * CFM)
    assert a.segments[1].flow_m3s == pytest.approx(500 * CFM)
    assert a.segments[2].flow_m3s is None
    assert runs["B reg"].segments[0].flow_m3s == pytest.approx(500 * CFM)
    assert not any("airflow" in w for w in warnings)


def test_shared_sections_are_checked_at_their_total_airflow():
    project, _ = build_project(_tree_rooms(), Nominal(), Design(), ducts=TREE)
    project = replace(
        project,
        furnace=Furnace({"high": 30000.0}, blower=((0.1, 50.0), (0.8, 400.0))),
    )
    result = calculate(project)
    runs = {r["name"]: r for r in result["ducts"]["runs"]}
    flows = [s["flow_m3s"] for s in runs["A reg"]["segments"]]
    assert flows[0] == pytest.approx(500 * CFM)
    assert flows[2] == pytest.approx(300 * CFM)


def test_an_unknown_upstream_section_leaves_the_register_out():
    project, warnings = build_project(
        _tree_rooms(upstream="Nowhere"), Nominal(), Design(), ducts=TREE
    )
    assert project.runs == ()
    assert any("no duct section called 'Nowhere'" in w for w in warnings)


def test_looping_sections_are_reported():
    loop = {
        "X": {"upstream": "Y", "segments": TREE["Trunk"]["segments"]},
        "Y": {"upstream": "X", "segments": TREE["Trunk"]["segments"]},
    }
    project, warnings = build_project(
        _tree_rooms(upstream="X"), Nominal(), Design(), ducts=loop
    )
    assert project.runs == ()
    assert any("loop" in w for w in warnings)


def test_a_register_without_airflow_is_said_to_understate_its_trunk():
    rooms = _tree_rooms()
    del rooms["a"]["registers"][0]["flow_cfm"]
    _, warnings = build_project(rooms, Nominal(), Design(), ducts=TREE)
    assert any("no design airflow" in w for w in warnings)


def test_registers_with_no_sections_keep_their_full_duct():
    project, _ = build_project(_tree_rooms(upstream=None), Nominal(), Design())
    (run,) = project.runs[:1]
    assert len(run.segments) == 1  # only its own branch, as before


# --- Assumed sizes -------------------------------------------------------------


def _wall(face, **extra):
    azimuth = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}[face]
    return {"face": face, "azimuth": azimuth, "tilt": 90.0, "glass_m2": 0.0, **extra}


def test_given_sizes_are_used_without_notes():
    geo = room_geometry(ROOMS["office"], Nominal())
    assert geo.floor_m2 == pytest.approx(12.0)
    assert geo.walls == (10.0, 8.0)
    assert geo.notes == ()
    assert geo.problems == ()


def test_width_and_depth_give_a_rectangle_and_size_the_walls():
    room = {
        "title": "Den",
        "width_m": 4.0,
        "depth_m": 3.0,
        "height_m": 2.5,
        "walls": [_wall("S"), _wall("E")],
    }
    geo = room_geometry(room, Nominal())
    assert geo.floor_m2 == pytest.approx(12.0)
    assert geo.volume_m3 == pytest.approx(30.0)
    # a south wall runs along the width, an east wall along the depth
    assert geo.walls == pytest.approx((10.0, 7.5))
    assert any("rectangle" in n for n in geo.notes)
    assert any("Wall areas assumed" in n for n in geo.notes)


def test_two_cross_wall_lengths_and_a_height_give_the_room():
    room = {
        "title": "Den",
        "height_m": 2.5,
        "walls": [_wall("N", length_m=5.0), _wall("W", length_m=4.0)],
    }
    geo = room_geometry(room, Nominal())
    assert geo.floor_m2 == pytest.approx(20.0)
    assert geo.volume_m3 == pytest.approx(50.0)
    assert geo.walls == pytest.approx((12.5, 10.0))


def test_wall_height_is_used_when_the_room_has_none():
    room = {
        "title": "Den",
        "walls": [_wall("N", length_m=5.0, height_m=2.2), _wall("E", length_m=4.0)],
    }
    geo = room_geometry(room, Nominal())
    assert geo.height_m == pytest.approx(2.2)
    assert geo.volume_m3 == pytest.approx(20.0 * 2.2)
    assert any("from its walls" in n for n in geo.notes)


def test_a_room_with_only_a_floor_area_is_taken_as_square():
    room = {"title": "Den", "floor_m2": 16.0, "walls": [_wall("S"), _wall("S")]}
    geo = room_geometry(room, Nominal(room_height_m=2.5))
    assert geo.height_m == pytest.approx(2.5)
    assert any("assumed" in n for n in geo.notes)
    # two south walls share the square's 4 m side
    assert geo.walls == pytest.approx((5.0, 5.0))
    assert any("square room" in n for n in geo.notes)


def test_a_wall_that_cannot_be_sized_is_reported():
    room = {"title": "Den", "walls": [_wall("S")]}
    geo = room_geometry(room, Nominal())
    assert geo.walls == (None,)
    assert any("left out" in p for p in geo.problems)


def test_a_volume_alone_gives_a_square_room_at_the_assumed_height():
    room = {"title": "Den", "volume_m3": 40.0, "walls": [_wall("S")]}
    geo = room_geometry(room, Nominal(room_height_m=2.5))
    assert geo.floor_m2 == pytest.approx(16.0)
    assert geo.walls == pytest.approx((10.0,))
    assert any("assumed" in n for n in geo.notes)


def test_windows_bigger_than_their_wall_are_reported():
    room = {
        "title": "Den",
        "volume_m3": 30.0,
        "walls": [_wall("S", area_m2=2.0, glass_m2=3.0)],
    }
    _, warnings = build_project({"den": room}, Nominal(), Design())
    assert any("only 2.00 m²" in w for w in warnings)


def test_assumed_walls_count_in_the_heat_loss():
    room = {"title": "Den", "floor_m2": 16.0, "height_m": 2.5, "walls": [_wall("N")]}
    project, _ = build_project({"den": room}, Nominal(), Design())
    (wall,) = [s for s in project.rooms[0].surfaces if s.kind == "wall"]
    assert wall.area == pytest.approx(4.0 * 2.5)
    assert project.rooms[0].notes


def test_a_basement_floor_loses_heat_to_the_ground():
    room = {
        "title": "Basement",
        "floor_m2": 40.0,
        "height_m": 2.3,
        "below_ground": True,
        "below_grade_m": 1.5,
        "walls": [],
    }
    nominal = Nominal(basement_floor_r=2.0)
    project, _ = build_project({"b": room}, nominal, Design())
    (floor,) = [s for s in project.rooms[0].surfaces if s.kind == "floor"]
    assert floor.ground and floor.area == pytest.approx(40.0)
    loads = calculate(project)["rooms"]["Basement"]["heating_parts"]
    design = Design()
    expected = 40.0 / 2.0 * (design.heat_indoor_c - design.ground_c)
    assert loads["basement floor"] == pytest.approx(expected)


def test_the_house_default_depth_is_noted():
    room = {
        "title": "Basement",
        "floor_m2": 40.0,
        "height_m": 2.3,
        "below_ground": True,
        "below_grade_m": 1.8,
        "below_grade_default": True,
        "walls": [],
    }
    geo = room_geometry(room, Nominal())
    assert any("house's default" in n for n in geo.notes)


def test_a_shared_roof_is_split_by_floor_area():
    roof = {"area_m2": 40.0, "glass_m2": 0.0, "tilt": 45.0, "area_ids": ["a", "b"]}

    def room(title, floor):
        return {"title": title, "floor_m2": floor, "height_m": 2.4, "roofs": [roof]}

    rooms = {"a": room("A", 30.0), "b": room("B", 10.0)}
    project, _ = build_project(rooms, Nominal(), Design())
    areas = {
        r.name: sum(s.area for s in r.surfaces if s.kind == "roof")
        for r in project.rooms
    }
    # the roof is counted once in all, not once per room
    assert areas == pytest.approx({"A": 30.0, "B": 10.0})


def test_a_shared_roof_is_split_equally_without_floor_areas():
    roof = {"area_m2": 40.0, "area_ids": ["a", "b"]}
    rooms = {
        "a": {"title": "A", "volume_m3": 20.0, "roofs": [roof]},
        "b": {"title": "B", "volume_m3": 20.0, "height_m": 2.0, "roofs": [roof]},
    }
    # only "b" gives a height, so only "b" gets a floor area exactly; "a" gets
    # one through the assumed height, so both have one: split by floor area
    project, _ = build_project(rooms, Nominal(room_height_m=2.0), Design())
    total = sum(s.area for r in project.rooms for s in r.surfaces if s.kind == "roof")
    assert total == pytest.approx(40.0)
    one = {"a": {"title": "A", "roofs": [roof]}, "b": rooms["b"]}
    project, _ = build_project(one, Nominal(), Design())
    (b,) = project.rooms  # "a" has no size at all, so is left out
    assert sum(s.area for s in b.surfaces if s.kind == "roof") == pytest.approx(20.0)


def test_settings_override_the_envelope_defaults():
    nominal, note = nominal_from_settings(
        {"infiltration_ach": 0.6, "wall_r": 15, "roof_r": "", "basement_floor_r": 0}
    )
    assert nominal.ach == pytest.approx(0.6)
    assert nominal.wall_r == pytest.approx(15 * R_IP_TO_SI)
    assert nominal.roof_r == Nominal().roof_r
    assert nominal.basement_floor_r == Nominal().basement_floor_r
    assert "walls R-15" in note and "0.6 ACH" in note
    # the unset ones are named as built-in defaults
    assert "Built-in defaults" in note
    assert "roofs R-35" in note.split("Built-in defaults")[1]


def test_an_outside_door_is_its_own_surface():
    wall = {
        "face": "S",
        "azimuth": 180.0,
        "area_m2": 10.0,
        "glass_m2": 2.0,
        "door_m2": 1.8,
    }
    doors = [
        {"title": "Front door", "in": "wall", "azimuth": 180.0, "area_m2": 1.8},
        {"title": "Back door", "in": "wall", "azimuth": 0.0, "area_m2": None},
        {"title": "Door to hall", "in": "internal_wall", "area_m2": 1.6},
    ]
    rooms = {
        "a": {
            "title": "A",
            "floor_m2": 10.0,
            "height_m": 2.4,
            "walls": [wall],
            "doors": doors,
        }
    }
    project, _ = build_project(rooms, Nominal(), Design())
    (room,) = project.rooms
    by_kind = {}
    for s in room.surfaces:
        by_kind.setdefault(s.kind, []).append(s)
    # the wall loses its window and its door; the sized outside door is its own
    assert sum(s.area for s in by_kind["wall"]) == pytest.approx(10.0 - 2.0 - 1.8)
    (door,) = by_kind["door"]
    assert (door.area, door.r, door.face) == (pytest.approx(1.8), Nominal().door_r, "S")
    # the unsized outside door stays in the wall, and the room says so
    assert any("Back door" in note for note in room.notes)


def test_doors_r_value_is_a_setting():
    nominal, note = nominal_from_settings({"door_r": 5})
    assert nominal.door_r == pytest.approx(5 * R_IP_TO_SI)
    assert "outside doors R-5" in note


def test_no_settings_say_everything_is_a_default():
    nominal, note = nominal_from_settings({})
    assert nominal == Nominal()
    assert "air leakage 0.35 ACH" in note.split("Built-in defaults")[1]
