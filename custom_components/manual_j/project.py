# Copyright (c) 2026 MinchinWeb
"""The whole house: Manual J, then S, then D, as one plain result.

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Standard library only, so it is tested without
Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
"""

from __future__ import annotations

from dataclasses import dataclass

from .air import rho_cp
from .building import Design, Room
from .manual_d import Run, available_static, evaluate_run, round_size_for_friction
from .manual_j import room_load
from .manual_s import AirConditioner, Furnace, check_cooling, check_heating


@dataclass(frozen=True)
class Project:
    """Everything the three calculations need.

    Attributes:
        rooms: The rooms (Manual J).
        design: Design conditions and air settings.
        furnace: Furnace nameplate and blower curve (Manual S and D).
        ac: Air conditioner nameplate (Manual S).
        equipment_static_pa: Static used by the coil, filter and cabinet, Pa.
        runs: Supply runs (Manual D).
        friction_target_pa_m: Friction rate to size branches to, Pa/m.
        branch_max_mps: Velocity limit for branch duct, m/s.
        trunk_max_mps: Velocity limit for trunk duct, m/s.
        heating_max_ratio: Largest acceptable furnace-to-load ratio.
        cooling_max_ratio: Largest acceptable AC-to-load ratio.
    """

    rooms: tuple[Room, ...]
    # frozen, so one shared default is safe
    design: Design = Design()  # noqa: RUF009
    furnace: Furnace | None = None
    ac: AirConditioner | None = None
    equipment_static_pa: float = 75.0
    runs: tuple[Run, ...] = ()
    friction_target_pa_m: float = 0.8
    branch_max_mps: float = 4.6  # 900 fpm
    trunk_max_mps: float = 6.1  # 1200 fpm
    heating_max_ratio: float = 1.4
    cooling_max_ratio: float = 1.15


def calculate(project: Project) -> dict:
    """Run Manual J, S and D for a project.

    Returns a plain dict (numbers, strings, lists and dicts only) so the
    integration can publish it as sensor attributes. Keys: ``rooms``,
    ``totals``, ``equipment``, ``airflow_m3s``, ``ducts`` and ``warnings``.
    """
    d = project.design
    warnings: list[str] = []

    loads = {room.name: room_load(room, d) for room in project.rooms}
    rooms_out = {
        name: {
            "heating_w": load.heating_w,
            "heating_parts": dict(load.heating_parts),
            "cooling_sensible_w": load.cooling_sensible_w,
            "cooling_sensible_parts": dict(load.cooling_sensible_parts),
            "cooling_latent_w": load.cooling_latent_w,
            "cooling_latent_parts": dict(load.cooling_latent_parts),
            "cooling_total_w": load.cooling_total_w,
            "airflow_m3s": load.airflow_m3s,
        }
        for name, load in loads.items()
    }

    heat_total = sum(load.heating_w for load in loads.values())
    sens_total = sum(load.cooling_sensible_w for load in loads.values())
    lat_total = sum(load.cooling_latent_w for load in loads.values())
    ua_total = 0.0
    for room in project.rooms:
        ua_total += sum(s.conductance for s in room.surfaces)
        ua_total += (
            room.ach * room.volume / 3600.0 * rho_cp(d.heat_indoor_c, d.altitude_m)
        )
    totals = {
        "heating_w": heat_total,
        "cooling_sensible_w": sens_total,
        "cooling_latent_w": lat_total,
        "cooling_total_w": sens_total + lat_total,
        "ua_w_per_k": ua_total,
    }

    # The design size is what the loads call for, whether or not the equipment
    # is configured; the installed size, when there is one, is checked against it.
    equipment: dict = {
        "heating": None,
        "cooling": None,
        "heating_design": {
            "load_w": heat_total,
            "max_w": heat_total * project.heating_max_ratio,
        },
        "cooling_design": {
            "load_total_w": sens_total + lat_total,
            "load_sensible_w": sens_total,
            "max_total_w": (sens_total + lat_total) * project.cooling_max_ratio,
        },
    }
    system_flow = 0.0
    if project.furnace is not None:
        heat_check = check_heating(
            heat_total, project.furnace, d, project.heating_max_ratio
        )
        equipment["heating"] = heat_check
        system_flow = max(system_flow, heat_check["airflow_m3s"])
    if project.ac is not None:
        cool_check = check_cooling(
            sens_total + lat_total, sens_total, project.ac, d, project.cooling_max_ratio
        )
        equipment["cooling"] = cool_check
        system_flow = max(system_flow, cool_check["airflow_m3s"])

    ducts: dict = {
        "runs": [],
        "airflow_m3s": 0.0,
        "blower_static_pa": None,
        "budget_pa": None,
    }
    if project.runs:
        run_flows = {}
        for run in project.runs:
            if run.room not in loads:
                raise ValueError(
                    f"run {run.name!r} serves an unknown room {run.room!r}"
                )
            run_flows[run.name] = (
                run.flow_m3s
                if run.flow_m3s is not None
                else loads[run.room].airflow_m3s
            )
        total_flow = sum(run_flows.values())
        ducts["airflow_m3s"] = total_flow
        if project.furnace is None or not project.furnace.blower:
            warnings.append(
                "Duct check skipped: the furnace's blower curve is not set."
            )
        else:
            static, in_range = available_static(project.furnace.blower, total_flow)
            if not in_range:
                warnings.append("The duct airflow is outside the blower curve.")
            budget = static - project.equipment_static_pa
            ducts["blower_static_pa"] = static
            ducts["budget_pa"] = budget
            for run in project.runs:
                flow = run_flows[run.name]
                result = evaluate_run(
                    run, flow, d, project.branch_max_mps, project.trunk_max_mps
                )
                result["margin_pa"] = budget - result["loss_pa"]
                result["branch_round_in"] = round_size_for_friction(
                    flow, project.friction_target_pa_m, d.duct_air_c, d.altitude_m
                )
                result["ok"] = result["margin_pa"] >= 0 and all(
                    s["velocity_ok"] for s in result["segments"]
                )
                ducts["runs"].append(result)
        if system_flow and total_flow > system_flow * 1.05:
            warnings.append(
                "The runs' total airflow is more than the equipment's airflow."
            )

    return {
        "rooms": rooms_out,
        "totals": totals,
        "equipment": equipment,
        "airflow_m3s": system_flow,
        "ducts": ducts,
        "warnings": warnings,
    }
