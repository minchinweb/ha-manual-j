# Copyright (c) 2026 MinchinWeb
"""Manual J, S and D for the HVAC design tab, set against what was observed.

Standard library only (tested without Home Assistant). ``panel.py`` gathers
House Structure's rooms, equipment and buildings, the outdoor record, and each
zone's fitted cooling rate when Home Thermal Lab publishes them, and passes them
here. Each room's calculated conductance (its nominal R-values, windows and
infiltration) is shown beside the conductance the zone fit measured, and the
recorded design temperatures beside the assumed ones.
"""

from __future__ import annotations

from dataclasses import replace

from .building import (
    Design,
    design_temperatures,
    ua_from_rate,
)
from .house_model import (
    Nominal,
    build_project,
    envelope_from_fit,
    fixed_conductances,
    room_capacities,
)
from .manual_s import AirConditioner, Furnace
from .project import calculate

# Without a sensible rating, the AC's sensible capacity is taken as this share.
SENSIBLE_SHARE = 0.8
# Without the downloaded dew points, cooling humidity is the default.
HUMIDITY_NOTE = (
    "Cooling humidity is the default outdoor humidity: the historical weather "
    "(with its dew points) couldn't be downloaded."
)


def design_from_summary(
    summary: dict, base: Design, source: str
) -> tuple[Design, dict]:
    """The design with the outdoor values worked out from a record.

    Args:
        summary: ``heat_outdoor_c``, ``cool_outdoor_c`` and, when known,
            ``cool_outdoor_w`` (the cooling design humidity), with the
            cross-checks, ``hours`` and ``warnings`` (see ``history.summarise``).
        base: The assumed design conditions.
        source: ``recorded`` (the outdoor sensor) or ``downloaded`` (Open-Meteo).

    Returns:
        The design to use, and the summary with ``source`` and ``assumed``.
    """
    changes = {
        "heat_outdoor_c": summary["heat_outdoor_c"],
        "cool_outdoor_c": summary["cool_outdoor_c"],
    }
    if summary.get("cool_outdoor_w") is not None:
        changes["cool_outdoor_w"] = summary["cool_outdoor_w"]
    info = {
        **summary,
        "source": source,
        "assumed": {
            "heat_outdoor_c": base.heat_outdoor_c,
            "cool_outdoor_c": base.cool_outdoor_c,
        },
    }
    return replace(base, **changes), info


def assumed_design(base: Design, warnings: list[str], hours: int = 0) -> dict:
    """The summary for the assumed design, with why it is used."""
    return {
        "source": "assumed",
        "assumed": {
            "heat_outdoor_c": base.heat_outdoor_c,
            "cool_outdoor_c": base.cool_outdoor_c,
        },
        "heat_outdoor_c": base.heat_outdoor_c,
        "cool_outdoor_c": base.cool_outdoor_c,
        "hours": hours,
        "warnings": list(warnings),
    }


def design_from_record(
    hourly_c: list[float | None], base: Design
) -> tuple[Design, dict]:
    """The design with the recorded heating and cooling outdoor temperatures.

    Falls back to ``base`` (and says so) when the record is too short or sparse.

    Args:
        hourly_c: Hourly outdoor temperatures, oldest first, one per hour; None
            where an hour is missing.
        base: The assumed design conditions.

    Returns:
        The design to use, and a summary: ``source`` (``recorded`` or
        ``assumed``), the temperatures, ``hours`` and ``warnings``.
    """
    try:
        found = design_temperatures(hourly_c)
    except ValueError as err:
        hours = sum(t is not None for t in hourly_c)
        return base, assumed_design(base, [str(err)], hours)
    summary = {
        "heat_outdoor_c": found["heat_c"],
        "heat_outdoor_99_c": found["heat_c_99"],
        "cool_outdoor_c": found["cool_c"],
        "cool_outdoor_1_c": found["cool_c_1"],
        "hours": found["hours"],
        "warnings": found["warnings"],
    }
    return design_from_summary(summary, base, "recorded")


def equipment_from(
    equipment: dict | None,
) -> tuple[Furnace | None, AirConditioner | None, str | None, list[str]]:
    """The furnace and AC from House Structure's equipment.

    House Structure lists each furnace (``input_high_w``, ``input_low_w``,
    ``afue`` as a fraction, ``blower`` as ``[[m³/s, Pa], ...]``, ``area_id``)
    and air conditioner (``total_w``, ``sensible_w``). The first of each is
    checked against the loads. Missing values are filled in and named in the
    warnings.

    Returns:
        The furnace, the AC, the furnace's area id, and the warnings.
    """
    warnings: list[str] = []
    equipment = equipment or {}
    furnaces = equipment.get("furnaces") or []
    acs = equipment.get("air_conditioners") or []
    for kind, items in (("furnaces", furnaces), ("air conditioners", acs)):
        if len(items) > 1:
            first = items[0].get("title") or kind
            warnings.append(
                f"House Structure has {len(items)} {kind}; only the first "
                f"({first}) is checked against the loads."
            )
    furnace = None
    furnace_area = None
    if furnaces and furnaces[0].get("input_high_w"):
        data = furnaces[0]
        stages = {"high": float(data["input_high_w"])}
        if data.get("input_low_w"):
            stages["low"] = float(data["input_low_w"])
        afue = data.get("afue")
        if afue is None:
            warnings.append("Furnace AFUE is not given, so it is taken as 100%.")
        blower = tuple((float(f), float(p)) for f, p in data.get("blower") or ())
        furnace = Furnace(stages, efficiency=afue or 1.0, blower=blower)
        furnace_area = data.get("area_id")
    ac = None
    if acs and acs[0].get("total_w"):
        total = float(acs[0]["total_w"])
        sensible = acs[0].get("sensible_w")
        if sensible is None:
            sensible = SENSIBLE_SHARE * total
            warnings.append(
                "The AC's sensible capacity is not given, so it is taken as "
                f"{SENSIBLE_SHARE:.0%} of its total."
            )
        ac = AirConditioner(total_w=total, sensible_w=float(sensible))
    return furnace, ac, furnace_area, warnings


def assemble_all(
    rooms: dict[str, dict],
    names: dict[str, str],
    rates: dict[str, float],
    nominal: Nominal,
    design: Design,
    buildings: list[dict] | tuple = (),
    **house: object,
) -> dict:
    """The house's numbers, with each detached building calculated on its own.

    A detached building (a garage, say) has no duct or heating connection to the
    house, so its rooms leave the house's calculation and get their own Manual J
    and S, at its own indoor setpoints if it has them. ``house`` is passed to
    ``assemble`` for the house itself.

    Args:
        rooms, names, rates, nominal, design: As for ``assemble``.
        buildings: Each ``{"name", "areas", "indoor_heat_c"?, "indoor_cool_c"?}``:
            House Structure's buildings, with Manual J's setpoints for them.
        house: Keyword arguments for ``assemble`` (the furnace, AC and so on).

    Returns:
        ``assemble``'s result for the house, with ``buildings``: a list of
        ``{"name", "areas", "missing", "result"}``. ``missing`` names areas that
        have no room yet; ``result`` is None when none of them does.
    """
    detached = {area for b in buildings for area in b["areas"]}
    full_names = {a: names.get(a) or rooms[a].get("title") or a for a in rooms}
    result = assemble(
        {a: r for a, r in rooms.items() if a not in detached},
        names,
        rates,
        nominal,
        design,
        **house,
    )
    out = []
    for b in buildings:
        present = {a: rooms[a] for a in b["areas"] if a in rooms}
        missing = [full_names.get(a, a) for a in b["areas"] if a not in rooms]
        built = None
        if present:
            own = replace(
                design,
                heat_indoor_c=b.get("indoor_heat_c") or design.heat_indoor_c,
                cool_indoor_c=b.get("indoor_cool_c") or design.cool_indoor_c,
            )
            built = assemble(
                present,
                names,
                rates,
                nominal,
                own,
                design_info=house.get("design_info"),
            )
        out.append(
            {
                "name": b["name"],
                "areas": list(b["areas"]),
                "missing": missing,
                "result": built,
            }
        )
    result["buildings"] = out
    return result


def assemble(
    rooms: dict[str, dict],
    names: dict[str, str],
    rates: dict[str, float],
    nominal: Nominal,
    design: Design,
    furnace: Furnace | None = None,
    ac: AirConditioner | None = None,
    design_info: dict | None = None,
    extra_warnings: list[str] | None = None,
    ducts: dict[str, dict] | None = None,
    furnace_room: str | None = None,
) -> dict:
    """The HVAC design tab's numbers: loads, equipment, ducts and the observed contrast.

    Args:
        rooms: House Structure's rooms by area id.
        names: Display names by area id.
        rates: Each zone's fitted cooling rate ``a`` (per hour) by area id,
            from Home Thermal Lab; empty when it isn't installed.
        nominal: House-level defaults (R-values, glazing, infiltration).
        design: The design conditions in use.
        furnace: The furnace, if its nameplate is known.
        ac: The air conditioner, if its nameplate is known.
        design_info: The summary from ``design_from_record``, shown as is.
        extra_warnings: Further warnings to show (such as the humidity note).
        ducts: House Structure's shared duct sections by name.
        furnace_room: The name of the room the furnace sits in, if chosen.

    Returns:
        ``design``, ``rooms`` (each with its calculated and fitted conductance,
        the envelope scale and ``assumed``: the sizes that were assumed),
        ``totals``, ``equipment``, ``ducts`` and ``warnings``, all plain values.
    """
    full_names = {a: names.get(a) or rooms[a].get("title") or a for a in rooms}
    project, warnings = build_project(rooms, nominal, design, full_names, ducts)
    project = replace(project, furnace=furnace, ac=ac)
    result = calculate(project)

    area_of = {full_names[a]: a for a in rooms}
    capacities = room_capacities(rooms, nominal)
    fixed: dict[str, float] = {}
    infiltration: dict[str, float] = {}
    for room in project.rooms:
        area = area_of[room.name]
        fixed[area], infiltration[area] = fixed_conductances(room, design)
    envelope = envelope_from_fit(rooms, rates, capacities, fixed, infiltration, nominal)

    out_rooms = []
    for room in project.rooms:
        area = area_of[room.name]
        load = result["rooms"][room.name]
        ua_calc = sum(s.conductance for s in room.surfaces) + infiltration[area]
        rate = rates.get(area)
        ua_fit = (
            ua_from_rate(rate, capacities[area])
            if rate is not None and area in capacities
            else None
        )
        env = envelope.get(area)
        out_rooms.append(
            {
                "area_id": area,
                "name": room.name,
                "heating_w": load["heating_w"],
                "cooling_sensible_w": load["cooling_sensible_w"],
                "cooling_latent_w": load["cooling_latent_w"],
                "cooling_total_w": load["cooling_total_w"],
                "airflow_m3s": load["airflow_m3s"],
                "ua_calc_w_k": ua_calc,
                "ua_fit_w_k": ua_fit,
                "fit_ratio": ua_fit / ua_calc if ua_fit and ua_calc else None,
                "scale": env["scale"] if env else None,
                "warnings": env["warnings"] if env else [],
                "assumed": list(room.notes),
            }
        )

    return {
        "furnace_room": furnace_room,
        "design": {
            "heat_outdoor_c": design.heat_outdoor_c,
            "heat_indoor_c": design.heat_indoor_c,
            "cool_outdoor_c": design.cool_outdoor_c,
            "cool_indoor_c": design.cool_indoor_c,
            "altitude_m": design.altitude_m,
            "info": design_info or {"source": "assumed"},
        },
        "rooms": out_rooms,
        "totals": result["totals"],
        "equipment": result["equipment"],
        "ducts": result["ducts"],
        "warnings": [
            *(extra_warnings or []),
            *warnings,
            *result["warnings"],
        ],
    }
