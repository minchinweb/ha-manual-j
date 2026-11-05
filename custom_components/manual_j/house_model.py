# Copyright (c) 2026 MinchinWeb
"""Build the Manual J/S/D project from House Structure's published rooms.

Standard library only. House Structure (``hass.data["house_structure"]``)
gives each room's size, below-ground flag, walls and roofs (area, glass,
azimuth and tilt), windows (glass, transmittance and the wall or roof they
are in) and doors (size and the wall they are in). Wall and roof R-values,
and a window's glazing and frame, are used when given; otherwise they come
from ``Nominal``: house-level defaults.

Sizes that are missing are filled in where the room allows it, and each one is
noted on the room (``Geometry.notes``) so the HVAC design tab can show it:

- A room with a width and depth (or a wall's length on each axis) is taken as
  a rectangle, for its floor area and volume.
- A wall without an area takes its length (or the room's width or depth on its
  axis, or the side of a square room of the floor area) times its height (or
  the room's).
- A room without a height takes its walls' height, or ``Nominal.room_height_m``.

A door in an outside wall is its own surface, at ``Nominal.door_r``, and is
taken out of its wall's area, as a window is. A door with no size is left in
the wall (and noted). Doors in internal walls are not losses either.

Internal walls are not counted as losses. A neighbouring room is taken to be
at the same temperature, as Manual J does for a heated neighbour. A basement's
floor loses heat to the ground through ``Nominal.basement_floor_r``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
import math

from .air import rho_cp
from .building import (
    Design,
    Element,
    Room,
    Surface,
    envelope_scale,
    room_capacity,
    ua_from_rate,
    window_u,
)
from .manual_d import Run, Segment
from .project import Project

CFM_TO_M3S = 0.000471947
IN2_TO_M2 = 0.00064516
FT_TO_M = 0.3048

# Imperial R-values (ft² °F h/BTU) converted to m² K/W: R-20 is 3.5.
R_IP_TO_SI = 0.17611
R_20_SI = 3.5
R_35_SI = 6.2
# An exterior door: about R-3 for an insulated steel or solid wood door with
# its frame (U about 1.9 W/m² K). A rough built-in value; set it on the form.
R_3_SI = 3 * R_IP_TO_SI
# An uninsulated basement slab with the soil under it, as an effective
# R-value against the design ground temperature (about R-11). A rough value:
# the slab's loss depends on its width, the depth and the soil.
BASEMENT_FLOOR_R_SI = 2.0
ROOM_HEIGHT_M = 2.44  # 8 ft
NORTH_SOUTH = ("N", "S")


@dataclass(frozen=True)
class Nominal:
    """House-level defaults for what House Structure does not record.

    Attributes:
        wall_r: Nominal R-value of outside walls, m² K/W.
        roof_r: Nominal R-value of roofs, m² K/W.
        door_r: Nominal R-value of outside doors, m² K/W.
        basement_floor_r: Effective R-value of a below-ground room's floor,
            slab and soil together, m² K/W.
        glazing: ``double`` or ``triple``, for every window.
        frame: ``vinyl``, ``wood`` or ``aluminium``, for every window.
        ach: Infiltration, air changes per hour (or from a blower-door test).
        room_height_m: Ceiling height of a room that gives none, m.
        occupants: Occupants per area id, for cooling.
    """

    wall_r: float = R_20_SI
    roof_r: float = R_35_SI
    door_r: float = R_3_SI
    basement_floor_r: float = BASEMENT_FLOOR_R_SI
    glazing: str = "double"
    frame: str = "vinyl"
    ach: float = 0.35
    room_height_m: float = ROOM_HEIGHT_M
    occupants: dict[str, int] = field(default_factory=dict)


# The integration's settings for the envelope defaults: key, Nominal field, and
# whether the setting is an imperial R-value (converted to SI).
ENVELOPE_SETTINGS = (
    ("infiltration_ach", "ach", False),
    ("wall_r", "wall_r", True),
    ("roof_r", "roof_r", True),
    ("door_r", "door_r", True),
    ("basement_floor_r", "basement_floor_r", True),
)


def default_r_values(settings: Mapping) -> dict[str, float]:
    """Manual J's R-values, in m² K/W, for a wall, roof and outside door that has
    none typed in House Structure: the settings' values, else the built-in ones."""
    nominal, _ = nominal_from_settings(settings)
    return {
        "wall_r": nominal.wall_r,
        "roof_r": nominal.roof_r,
        "door_r": nominal.door_r,
    }


def nominal_from_settings(settings: Mapping) -> tuple[Nominal, str]:
    """The envelope defaults from the integration's settings, and a note of them.

    R-values are set as imperial R-values (R-20); infiltration in air changes
    per hour. Anything not set keeps the built-in default, and the note says
    which values are the built-in ones.
    """
    values: dict = {}
    for key, name, imperial in ENVELOPE_SETTINGS:
        value = settings.get(key)
        if value in (None, ""):
            continue
        value = float(value)
        if value <= 0:
            continue
        values[name] = value * R_IP_TO_SI if imperial else value
    nominal = Nominal(**values)
    parts = {
        "wall_r": f"walls R-{nominal.wall_r / R_IP_TO_SI:.0f}",
        "roof_r": f"roofs R-{nominal.roof_r / R_IP_TO_SI:.0f}",
        "door_r": f"outside doors R-{nominal.door_r / R_IP_TO_SI:.0f}",
        "basement_floor_r": (
            f"basement floors R-{nominal.basement_floor_r / R_IP_TO_SI:.0f}"
        ),
        "ach": f"air leakage {nominal.ach:g} ACH",
    }
    unset = [part for name, part in parts.items() if name not in values]
    note = (
        "Envelope where a part gives no value of its own: "
        + ", ".join(parts.values())
        + f"; windows {nominal.glazing} glazed in {nominal.frame} frames."
    )
    if unset:
        note += (
            " Built-in defaults, not measured: "
            + ", ".join(unset)
            + ". Set them on the integration's Reconfigure form."
        )
    return nominal, note


def _face(azimuth: float) -> str:
    """The nearest compass face (N, E, S or W) to an azimuth in degrees."""
    return ("N", "E", "S", "W")[round(azimuth / 90.0) % 4]


def _wall_face(wall: dict) -> str:
    """A wall's face in the house's grid (from its azimuth when not given)."""
    return wall.get("face") or _face(wall.get("azimuth") or 0.0)


@dataclass(frozen=True)
class Geometry:
    """A room's sizes, with what had to be assumed to get them.

    Attributes:
        floor_m2: Floor area, m², or None.
        height_m: Ceiling height, m.
        volume_m3: Air volume, m³, or None.
        walls: Each wall's gross area, m², in the order House Structure lists
            them; None for a wall that could not be sized.
        notes: What was assumed, for the room's line on the HVAC design tab.
        problems: What is wrong or left out, for the warnings.
    """

    floor_m2: float | None
    height_m: float
    volume_m3: float | None
    walls: tuple[float | None, ...]
    notes: tuple[str, ...]
    problems: tuple[str, ...]


def _longest(walls: list[dict], faces: tuple[str, ...]) -> float | None:
    """The longest typed length of the walls on these faces."""
    lengths = [
        w["length_m"] for w in walls if w.get("length_m") and _wall_face(w) in faces
    ]
    return max(lengths) if lengths else None


def room_geometry(summary: dict, nominal: Nominal, name: str = "") -> Geometry:
    """A room's floor, height, volume and wall areas, filling in what is missing.

    See the module's docstring for the order things are tried in. Each value
    that is not the room's own (or worked out exactly from its own) is noted.
    """
    name = name or summary.get("title") or "Room"
    walls = summary.get("walls") or []
    notes: list[str] = []
    problems: list[str] = []

    width = summary.get("width_m")
    depth = summary.get("depth_m")
    if not width:
        width = _longest(walls, NORTH_SOUTH)
    if not depth:
        depth = _longest(walls, ("E", "W"))
    floor = summary.get("floor_m2")
    height = summary.get("height_m")
    volume = summary.get("volume_m3")
    if not floor and width and depth:
        floor = width * depth
        notes.append(
            f"Floor area {floor:.1f} m², as a rectangle {width:.2f} m by {depth:.2f} m."
        )
    if not height:
        wall_heights = [w["height_m"] for w in walls if w.get("height_m")]
        if volume and floor:
            height = volume / floor
        elif wall_heights:
            height = max(wall_heights)
            notes.append(f"Ceiling height {height:.2f} m, from its walls.")
        else:
            height = nominal.room_height_m
            notes.append(f"Ceiling height {height:.2f} m, assumed.")
    if not volume and floor:
        volume = floor * height
        if notes:
            notes.append(f"Volume {volume:.1f} m³, from the floor area and height.")
    if not floor and volume:
        floor = volume / height

    # Walls without an area share their axis' length with the others on their face.
    unsized = Counter(
        _wall_face(w) for w in walls if not w.get("area_m2") and not w.get("length_m")
    )
    sized: list[float | None] = []
    assumed: list[str] = []
    for i, wall in enumerate(walls, start=1):
        face = _wall_face(wall)
        gross = wall.get("area_m2")
        wall_height = wall.get("height_m") or height
        if not gross:
            side = width if face in NORTH_SOUTH else depth
            if wall.get("length_m"):
                gross, how = wall["length_m"] * wall_height, "its length"
            elif side:
                axis = "width" if face in NORTH_SOUTH else "depth"
                gross, how = side / unsized[face] * wall_height, f"the room's {axis}"
            elif floor:
                gross = math.sqrt(floor) / unsized[face] * wall_height
                how = "a square room"
            else:
                problems.append(
                    f"{name}: wall {i} ({face}) has no size, and the room has no "
                    "floor area or width to assume one from, so it is left out."
                )
                sized.append(None)
                continue
            assumed.append(f"wall {i} ({face}) {gross:.1f} m² from {how}")
        glass = wall.get("glass_m2") or 0.0
        doors = wall.get("door_m2") or 0.0
        if glass + doors > gross + 1e-6:
            problems.append(
                f"{name}: wall {i} ({face}) has {glass + doors:.2f} m² of windows "
                f"and doors but is only {gross:.2f} m²; check the wall's, windows' "
                "and doors' sizes."
            )
        sized.append(gross)
    if assumed:
        notes.append(
            "Wall areas assumed: "
            + "; ".join(assumed)
            + f", {height:.2f} m high unless the wall gives its own height."
        )
    unsized_doors = [
        d["title"]
        for d in summary.get("doors") or []
        if d.get("in") == "wall" and not d.get("area_m2")
    ]
    if unsized_doors:
        notes.append(
            "Outside doors with no size, counted as wall: "
            + ", ".join(unsized_doors)
            + "."
        )
    if summary.get("below_ground") and summary.get("below_grade_default"):
        notes.append(
            f"Below-grade depth {summary.get('below_grade_m'):.2f} m is the house's "
            "default."
        )
    return Geometry(
        floor_m2=floor,
        height_m=height,
        volume_m3=volume,
        walls=tuple(sized),
        notes=tuple(notes),
        problems=tuple(problems),
    )


def outside_doors(summary: dict) -> list[dict]:
    """A room's doors to outside that have a size (the ones that lose heat)."""
    return [
        d
        for d in summary.get("doors") or []
        if d.get("in") == "wall" and (d.get("area_m2") or 0.0) > 0
    ]


def ground_fraction(summary: dict, height: float | None = None) -> float:
    """The share (0 to 1) of a room's walls that are below grade.

    A basement with a below-grade depth has its walls below the grade line for
    that depth, so the share is the depth over the room's height. Without a
    depth, a below-ground room's walls are all taken as below grade.

    Args:
        summary: The room, as House Structure publishes it.
        height: The room's height; from the summary when not given.
    """
    if not summary.get("below_ground"):
        return 0.0
    depth = summary.get("below_grade_m")
    if height is None:
        height = room_geometry(summary, Nominal()).height_m
    if depth is None or not height:
        return 1.0
    return min(max(depth / height, 0.0), 1.0)


def room_floors(rooms: dict[str, dict], nominal: Nominal) -> dict[str, float]:
    """Each room's floor area (given or assumed), by area id, where there is one."""
    out = {}
    for area_id, summary in rooms.items():
        floor = room_geometry(summary, nominal).floor_m2
        if floor:
            out[area_id] = floor
    return out


def roof_share(roof: dict, area_id: str, floors: Mapping[str, float]) -> float:
    """The share (0 to 1) of a roof that is over this room.

    House Structure lists a roof over several rooms in each of them with its
    whole area, so each takes a part: its floor area over theirs, or an equal
    part when any of them has no floor area.
    """
    areas = roof.get("area_ids") or [area_id]
    if len(areas) <= 1:
        return 1.0
    if all(a in floors for a in areas):
        total = sum(floors[a] for a in areas)
        if total > 0:
            return floors.get(area_id, 0.0) / total
    return 1.0 / len(areas)


def build_project(
    rooms: dict[str, dict],
    nominal: Nominal,
    design: Design,
    names: dict[str, str] | None = None,
    ducts: dict[str, dict] | None = None,
) -> tuple[Project, list[str]]:
    """A Manual J project from the rooms House Structure publishes.

    Args:
        rooms: House Structure's rooms by area id (``structure_rooms``).
        nominal: House-level defaults for R-values, glazing and infiltration.
        design: Design conditions.
        names: Optional display names by area id (defaults to the room title).
        ducts: House Structure's shared duct sections by name (``ducts`` in its
            summary); registers name the section they hang off.

    Returns:
        The project and a list of warnings (rooms skipped, and what was assumed).
    """
    names = names or {}
    warnings: list[str] = []
    built: list[Room] = []
    pending: list[tuple[dict, str, int]] = []
    floors = room_floors(rooms, nominal)
    for area_id, summary in rooms.items():
        name = names.get(area_id) or summary.get("title") or area_id
        geometry = room_geometry(summary, nominal, name)
        warnings.extend(geometry.problems)
        volume = geometry.volume_m3
        if not volume:
            warnings.append(
                f"{name}: no volume, floor area or width and depth, so the room is "
                "not in the calculation."
            )
            continue
        below = ground_fraction(summary, geometry.height_m)
        if summary.get("below_ground") and summary.get("below_grade_m") is None:
            warnings.append(
                f"{name}: no below-grade depth (its own or the house's default in "
                "House Structure), so all its walls are taken as below grade."
            )
        surfaces: list[Surface] = []
        for i, (wall, gross) in enumerate(
            zip(summary.get("walls", []), geometry.walls, strict=True), start=1
        ):
            net = (
                (gross or 0.0)
                - (wall.get("glass_m2") or 0.0)
                - (wall.get("door_m2") or 0.0)
            )
            if net > 0:
                r = wall.get("r_value_si") or nominal.wall_r
                if below > 0:
                    surfaces.append(
                        Surface(
                            f"wall {i} below grade",
                            "wall",
                            net * below,
                            r=r,
                            ground=True,
                        )
                    )
                if below < 1:
                    surfaces.append(
                        Surface(f"wall {i}", "wall", net * (1 - below), r=r)
                    )
        for i, roof in enumerate(summary.get("roofs", []), start=1):
            share = roof_share(roof, area_id, floors)
            net = share * ((roof.get("area_m2") or 0.0) - (roof.get("glass_m2") or 0.0))
            if net > 0:
                r = roof.get("r_value_si") or nominal.roof_r
                surfaces.append(Surface(f"roof {i}", "roof", net, r=r, face="H"))
        for i, win in enumerate(summary.get("windows", []), start=1):
            glass = win.get("glass_m2") or 0.0
            if glass <= 0:
                continue
            face = "H" if win.get("in") == "roof" else _face(win.get("azimuth") or 0.0)
            glazing = win.get("glazing") or nominal.glazing
            frame = win.get("frame") or nominal.frame
            surfaces.append(
                Surface(
                    f"window {i}",
                    "window",
                    glass,
                    u=window_u(glazing, frame),
                    shgc=win.get("transmittance") or 0.0,
                    face=face,
                )
            )
        for i, door in enumerate(outside_doors(summary), start=1):
            surfaces.append(
                Surface(
                    f"door {i}",
                    "door",
                    door["area_m2"],
                    r=nominal.door_r,
                    face=_face(door.get("azimuth") or 0.0),
                )
            )
        if summary.get("below_ground") and geometry.floor_m2:
            surfaces.append(
                Surface(
                    "basement floor",
                    "floor",
                    geometry.floor_m2,
                    r=nominal.basement_floor_r,
                    ground=True,
                )
            )
        if not surfaces:
            warnings.append(f"{name}: no walls, roofs or windows with sizes.")
        room = Room(
            name=name,
            volume=volume,
            surfaces=tuple(surfaces),
            ach=nominal.ach,
            people=nominal.occupants.get(area_id, 0),
            notes=geometry.notes,
        )
        built.append(room)
        for j, reg in enumerate(summary.get("registers", []), start=1):
            if (reg.get("duct") or reg.get("upstream")) and reg.get("free_area_in2"):
                pending.append((reg, name, j))
    if not built:
        raise ValueError("no room has enough data for a Manual J")
    runs = _runs(pending, ducts or {}, warnings)
    return Project(rooms=tuple(built), design=design, runs=tuple(runs)), warnings


def _segment(seg: dict, flow_m3s: float | None, trunk: bool) -> Segment:
    """A duct segment as House Structure stores it (feet and inches)."""
    length = seg["length_ft"] * FT_TO_M
    k = seg.get("fittings_k") or 0.0
    if seg["shape"] == "round":
        return Segment.round_in(seg["diameter_in"], length, k, flow_m3s, trunk)
    return Segment.rect_in(
        seg["width_in"], seg["height_in"], length, k, flow_m3s, trunk
    )


def _chain(upstream: str | None, sections: dict[str, dict]) -> list[str]:
    """The shared sections from the plenum down to ``upstream`` (none if None)."""
    chain: list[str] = []
    name = upstream
    while name is not None:
        if name not in sections:
            raise ValueError(f"no duct section called {name!r}")
        if name in chain:
            raise ValueError("the duct sections loop back on themselves")
        chain.append(name)
        name = sections[name].get("upstream")
    return list(reversed(chain))


def _runs(
    pending: list[tuple[dict, str, int]],
    sections: dict[str, dict],
    warnings: list[str],
) -> list[Run]:
    """Each register's run: its shared sections from the plenum, then its branch.

    A shared section carries the airflow of every register behind it, so its
    loss and velocity are checked at that total. A register with no airflow
    adds nothing to its sections, which is said in the warnings.
    """
    paths = []
    for reg, room, index in pending:
        label = reg.get("title") or f"{room} register {index}"
        try:
            chain = _chain(reg.get("upstream"), sections)
        except ValueError as err:
            warnings.append(f"{label}: {err}. The register is not in the calculation.")
            continue
        if chain and not reg.get("flow_cfm"):
            warnings.append(
                f"{label}: no design airflow, so the shared ducts it runs through "
                "carry less than they will."
            )
        paths.append((reg, room, index, label, chain))
    carried: dict[str, float] = {}
    for reg, _, _, _, chain in paths:
        flow = reg["flow_cfm"] * CFM_TO_M3S if reg.get("flow_cfm") else 0.0
        for name in chain:
            carried[name] = carried.get(name, 0.0) + flow
    runs = []
    for reg, room, _, label, chain in paths:
        segments = [
            _segment(seg, carried[name] or None, trunk=True)
            for name in chain
            for seg in sections[name]["segments"]
        ]
        for seg in reg.get("duct") or ():
            flow = seg["flow_cfm"] * CFM_TO_M3S if seg.get("flow_cfm") else None
            segments.append(_segment(seg, flow, bool(seg.get("trunk"))))
        flow = reg["flow_cfm"] * CFM_TO_M3S if reg.get("flow_cfm") else None
        runs.append(
            Run(
                name=label,
                room=room,
                register_area_m2=reg["free_area_in2"] * IN2_TO_M2,
                segments=tuple(segments),
                flow_m3s=flow,
            )
        )
    return runs


def envelope_from_fit(
    rooms: dict[str, dict],
    rates: dict[str, float],
    capacities: dict[str, float],
    fixed_ua: dict[str, float],
    infiltration: dict[str, float],
    nominal: Nominal,
) -> dict[str, dict]:
    """Each room's measured envelope: its walls' and roofs' R-values, from its fit.

    For each room with a fitted rate ``a`` (per hour, from the zone fit), the
    measured conductance is ``a * C / 3600``. The room's infiltration and
    windows (their nominal U-values, in ``fixed_ua``) come off the top, and the
    walls and roofs are scaled to what is left (``envelope_scale``).

    Args:
        rooms: House Structure's rooms by area id.
        rates: The fitted cooling rate ``a`` per area id, per hour.
        capacities: Each room's heat capacity, J/K (``room_capacities``).
        fixed_ua: Each room's window conductance, W/K (nominal U times area).
        infiltration: Each room's infiltration conductance, W/K (``infiltration_ua``).
        nominal: The house defaults (only the element R-values are scaled).

    Returns:
        By area id: ``scale``, the derived ``elements`` and ``warnings``. Rooms
        without a fitted rate or capacity are left out.
    """
    out: dict[str, dict] = {}
    floors = room_floors(rooms, nominal)
    for area_id, summary in rooms.items():
        if area_id not in rates or area_id not in capacities:
            continue
        # The fit's rate covers the above-grade envelope (the ground has its own
        # term), so a basement's walls count only above the grade line.
        geometry = room_geometry(summary, nominal)
        above = 1.0 - ground_fraction(summary, geometry.height_m)
        walls = summary.get("walls", [])
        gross = {("wall", i): area for i, area in enumerate(geometry.walls, start=1)}
        elements = []
        for kind, items in (("wall", walls), ("roof", summary.get("roofs", []))):
            for i, item in enumerate(items, start=1):
                area = gross.get((kind, i), item.get("area_m2"))
                net = (area or 0.0) - (item.get("glass_m2") or 0.0)
                if kind == "wall":
                    net *= above
                else:
                    net *= roof_share(item, area_id, floors)
                if net <= 0:
                    continue
                r = item.get("r_value_si") or (
                    nominal.wall_r if kind == "wall" else nominal.roof_r
                )
                elements.append(Element(f"{kind} {i}", net, r))
        if not elements:
            continue
        measured = ua_from_rate(rates[area_id], capacities[area_id])
        target_fixed = fixed_ua.get(area_id, 0.0) + infiltration.get(area_id, 0.0)
        out[area_id] = envelope_scale(elements, target_fixed, measured)
    return out


def fixed_conductances(room: Room, design: Design) -> tuple[float, float]:
    """A room's window conductance and its infiltration conductance, W/K."""
    windows = sum(s.conductance for s in room.surfaces if s.kind == "window")
    infiltration = (
        room.ach
        * room.volume
        / 3600.0
        * rho_cp(design.heat_indoor_c, design.altitude_m)
    )
    return windows, infiltration


def room_capacities(
    rooms: dict[str, dict], nominal: Nominal | None = None
) -> dict[str, float]:
    """Each room's heat capacity (air only), J/K, by area id."""
    nominal = nominal or Nominal()
    return {
        area_id: room_capacity(volume)
        for area_id, summary in rooms.items()
        if (volume := room_geometry(summary, nominal).volume_m3)
    }
