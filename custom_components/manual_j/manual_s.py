# Copyright (c) 2026 MinchinWeb
"""Manual S: whether the furnace and air conditioner suit the loads.

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Standard library only, so it is tested without
Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

from .air import rho_cp
from .building import Design


@dataclass(frozen=True)
class Furnace:
    """A furnace's nameplate data and blower curve.

    Attributes:
        stages_input_w: Input per stage in W (gas input, or electric draw). Keys
            are ``high`` and, if it has one, ``low``.
        efficiency: AFUE as a fraction (0.95 for a 95% furnace); 1.0 for electric.
        blower: The blower's (airflow m³/s, external static Pa) points, from its
            nameplate or data sheet. Needed for the duct check.
    """

    stages_input_w: Mapping[str, float]
    efficiency: float = 1.0
    blower: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        if "high" not in self.stages_input_w:
            raise ValueError("furnace needs a high-stage input")
        if not 0 < self.efficiency <= 1.0:
            raise ValueError("efficiency must be a fraction in (0, 1]")

    def output_w(self, stage: str = "high") -> float | None:
        """Heat output of a stage, W, or None if the furnace has no such stage."""
        if stage not in self.stages_input_w:
            return None
        return self.stages_input_w[stage] * self.efficiency


@dataclass(frozen=True)
class AirConditioner:
    """An air conditioner's rated capacity, corrected to the design temperature.

    Attributes:
        total_w: Total cooling capacity at the rated outdoor temperature, W.
        sensible_w: Sensible capacity at the rated outdoor temperature, W.
        rated_outdoor_c: The outdoor temperature the rating is for (35 C is
            the usual rating point).
        capacity_per_k: Fractional change in capacity per kelvin away from the
            rating point. A rough stand-in for the manufacturer's curves.
    """

    total_w: float
    sensible_w: float
    rated_outdoor_c: float = 35.0
    capacity_per_k: float = 0.0085

    def capacity_at(self, outdoor_c: float) -> tuple[float, float]:
        """Total and sensible capacity at an outdoor temperature, W."""
        factor = 1.0 + self.capacity_per_k * (self.rated_outdoor_c - outdoor_c)
        return self.total_w * factor, self.sensible_w * factor


def _verdict(ratio: float, max_ratio: float) -> str:
    if ratio < 1.0:
        return "undersized"
    if ratio > max_ratio:
        return "oversized"
    return "ok"


def check_heating(
    load_w: float, furnace: Furnace, design: Design, max_ratio: float = 1.4
) -> dict:
    """Manual S for heating: the high stage against the whole-house heat loss."""
    capacity = furnace.output_w("high")
    ratio = capacity / load_w if load_w > 0 else math.inf
    low = furnace.output_w("low")
    return {
        "load_w": load_w,
        "capacity_w": capacity,
        "ratio": ratio,
        "verdict": _verdict(ratio, max_ratio),
        "low_stage_w": low,
        "low_stage_ratio": low / load_w if low is not None and load_w > 0 else None,
        "airflow_m3s": capacity
        / (rho_cp(design.heat_indoor_c, design.altitude_m) * design.heat_rise_k),
    }


def check_cooling(
    total_w: float,
    sensible_w: float,
    ac: AirConditioner,
    design: Design,
    max_ratio: float = 1.15,
) -> dict:
    """Manual S for cooling: total and sensible capacity against the loads."""
    cap_total, cap_sensible = ac.capacity_at(design.cool_outdoor_c)
    ratio = cap_total / total_w if total_w > 0 else math.inf
    return {
        "load_total_w": total_w,
        "load_sensible_w": sensible_w,
        "capacity_total_w": cap_total,
        "capacity_sensible_w": cap_sensible,
        "ratio": ratio,
        "sensible_ratio": cap_sensible / sensible_w if sensible_w > 0 else math.inf,
        "verdict": _verdict(ratio, max_ratio),
        "airflow_m3s": cap_sensible
        / (rho_cp(design.cool_indoor_c, design.altitude_m) * design.cool_rise_k),
    }
