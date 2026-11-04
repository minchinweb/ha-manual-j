# Copyright (c) 2026 MinchinWeb
"""Air: its properties at a temperature and altitude, and the units used.

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Standard library only, so it is tested without
Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
"""

from __future__ import annotations

R_DRY_AIR = 287.05  # J/(kg K)
CP_AIR = 1006.0  # J/(kg K)
IN_TO_M = 0.0254
BTU_H_TO_W = 0.29307


def inches(value: float) -> float:
    """Inches as metres."""
    return value * IN_TO_M


def btu_h(value: float) -> float:
    """BTU/h as watts."""
    return value * BTU_H_TO_W


def pressure_pa(altitude_m: float) -> float:
    """Standard-atmosphere pressure at an altitude (Edmonton is about 723 m)."""
    return 101325.0 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588


def air_density(temp_c: float, altitude_m: float = 0.0) -> float:
    """Dry-air density, kg/m³."""
    return pressure_pa(altitude_m) / (R_DRY_AIR * (temp_c + 273.15))


def rho_cp(temp_c: float, altitude_m: float = 0.0) -> float:
    """Volumetric heat capacity of air, J/(m³ K): the watts per m³/s per kelvin."""
    return air_density(temp_c, altitude_m) * CP_AIR
