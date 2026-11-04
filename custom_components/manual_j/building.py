# Copyright (c) 2026 MinchinWeb
"""The building as the manuals see it: surfaces, rooms and design conditions.

Also the design temperatures and humidity from a recorded outdoor history, and
the envelope from measurement: a room's heat capacity, the conductance a
fitted cooling rate implies, and the scale that brings nominal R-values in
line with it.

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Standard library only, so it is tested without
Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math

from .air import pressure_pa, rho_cp

KINDS = ("wall", "roof", "floor", "window", "door")
# Design-day solar gain on each face, W/m² (N, E, S, W and H for horizontal).
# Approximate clear-summer values near 53 N; verify before relying on them.
SOLAR_W_M2 = {"N": 100.0, "E": 630.0, "S": 220.0, "W": 630.0, "H": 790.0}

# --- Building -----------------------------------------------------------------


@dataclass(frozen=True)
class Surface:
    """One part of a room's envelope.

    Attributes:
        name: Label, used as the key in the load breakdown.
        kind: ``wall``, ``roof``, ``floor``, ``window`` or ``door``.
        area: Area, m².
        u: Overall coefficient, W/(m² K). Used in preference to ``r``.
        r: Thermal resistance, m² K/W, when no ``u`` is given.
        shgc: Solar heat gain coefficient (windows only).
        face: Compass face for windows and roofs (N, E, S, W or H).
        ground: Whether the surface meets the ground (its sink is the ground).
    """

    name: str
    kind: str
    area: float
    u: float | None = None
    r: float | None = None
    shgc: float = 0.0
    face: str = ""
    ground: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}")
        if self.area < 0:
            raise ValueError(f"{self.name}: negative area")
        if self.u is None and not self.r:
            raise ValueError(f"{self.name}: needs a U value or an R value")

    @property
    def conductance(self) -> float:
        """Conductance of the whole surface, W/K."""
        u = self.u if self.u is not None else 1.0 / self.r
        return u * self.area


@dataclass(frozen=True)
class Room:
    """A room: its volume, its envelope and its internal gains.

    Attributes:
        name: The room's name.
        volume: Air volume, m³.
        surfaces: The envelope (walls, roofs, floors, windows and doors).
        ach: Infiltration, air changes per hour.
        people: Occupants at design (cooling).
        gains_w: Sensible internal gains at design, W (appliances, lights).
        notes: Sizes that were assumed rather than given, to show with it.
    """

    name: str
    volume: float
    surfaces: tuple[Surface, ...]
    ach: float = 0.35
    people: int = 0
    gains_w: float = 0.0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Design:
    """Design conditions and air-side settings.

    The defaults are starting values for Edmonton, to confirm against ASHRAE
    climate data. Temperatures are °C; humidity ratios are kg water per kg dry
    air.
    """

    heat_outdoor_c: float = -27.0
    heat_indoor_c: float = 21.0
    cool_outdoor_c: float = 28.0
    cool_indoor_c: float = 24.0
    ground_c: float = 5.6  # design soil temperature for ground-coupled surfaces
    altitude_m: float = 723.0
    cool_outdoor_w: float = 0.0100
    cool_indoor_w: float = 0.0093
    solar_w_m2: Mapping[str, float] = field(default_factory=lambda: dict(SOLAR_W_M2))
    heat_rise_k: float = 20.0  # supply-air temperature rise in heating
    cool_rise_k: float = 11.0  # supply-air temperature drop in cooling
    duct_air_c: float = 20.0  # temperature used for duct friction


# --- Design temperatures from history -----------------------------------------

HOURS_PER_YEAR = 8760


def quantile(sorted_values: list[float], q: float) -> float:
    """The ``q`` quantile of sorted values, linearly interpolated (0 <= q <= 1)."""
    if not sorted_values:
        raise ValueError("no values")
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (pos - lo) * (sorted_values[hi] - sorted_values[lo])


def design_temperatures(
    hourly_c: list[float | None], min_hours: int = int(0.9 * HOURS_PER_YEAR)
) -> dict:
    """Design dry-bulb temperatures from a record of hourly outdoor temperatures.

    The ASHRAE convention, applied to the record: the heating design is the
    temperature exceeded in 99.6% of hours (the 0.4th percentile), and the
    cooling design the temperature exceeded in 0.4% of hours (the 99.6th
    percentile). The 99% and 1% values are returned as a cross-check.

    A year is a single sample of the weather. The 0.4% tail rests on about 35
    hours, so a second year, and a comparison with the station's ASHRAE values,
    should be used before trusting the result.

    Args:
        hourly_c: Hourly outdoor dry-bulb temperatures, °C; None for a missing hour.
        min_hours: Fewest valid hours to accept (default 90% of a year).

    Returns:
        ``heat_c`` and ``cool_c`` (the design values), ``heat_c_99`` and
        ``cool_c_1`` (the cross-checks), ``hours`` (valid hours used) and
        ``warnings``.
    """
    valid = sorted(t for t in hourly_c if t is not None and math.isfinite(t))
    n = len(valid)
    if n < min_hours:
        raise ValueError(
            f"only {n} valid hours; at least {min_hours} are needed for a design value"
        )
    warnings: list[str] = []
    if n < 2 * 0.9 * HOURS_PER_YEAR:
        warnings.append("Under two years of record: the 0.4% values rest on one year.")
    missing = len(hourly_c) - n
    if missing > 0.1 * len(hourly_c):
        warnings.append(f"{missing} of {len(hourly_c)} hours are missing.")
    return {
        "heat_c": quantile(valid, 0.004),
        "heat_c_99": quantile(valid, 0.010),
        "cool_c": quantile(valid, 0.996),
        "cool_c_1": quantile(valid, 0.990),
        "hours": n,
        "warnings": warnings,
    }


def humidity_ratio(dew_c: float, altitude_m: float = 0.0) -> float:
    """Humidity ratio (kg water per kg dry air) at a dew point."""
    e = 610.94 * math.exp(17.625 * dew_c / (dew_c + 243.04))  # Pa, over water
    p = pressure_pa(altitude_m)
    return 0.622 * e / (p - e)


def cooling_humidity(
    hours: list[tuple[float | None, float | None]],
    cool_c: float,
    altitude_m: float = 0.0,
) -> dict:
    """Design humidity ratio for cooling, from the hours as hot as the design.

    The design humidity is the average humidity ratio of the hours whose dry-bulb
    reaches the cooling design temperature, so it matches the design heat rather
    than an annual average.

    Args:
        hours: (dry-bulb, dew point) pairs in °C; either may be None.
        cool_c: The cooling design dry-bulb temperature.
        altitude_m: Site altitude.

    Returns:
        ``w`` (the humidity ratio), ``hours`` (hours used) and ``warnings``.
    """
    ws = [
        humidity_ratio(dew, altitude_m)
        for dry, dew in hours
        if dry is not None and dew is not None and dry >= cool_c
    ]
    warnings: list[str] = []
    if len(ws) < 5:
        warnings.append(
            "Fewer than 5 hot hours with a dew point: humidity is uncertain."
        )
    if not ws:
        raise ValueError("no hours with both a design-hot dry-bulb and a dew point")
    return {"w": sum(ws) / len(ws), "hours": len(ws), "warnings": warnings}


# --- Envelope from measurement -------------------------------------------------

CFM_TO_M3S = 0.000471947
M3H_PER_CFM = 1.69901
AIR_HEAT_CAPACITY_J_M3K = 1200.0 * 1005.0  # air at about 20 C
# Nominal whole-window U-values, W/(m² K), by glazing and frame. Only the
# double vinyl value is confirmed: 1.22 is the Canadian ENERGY STAR threshold
# for dual-glazed vinyl (JELD-WEN data sheet). The others are unverified
# estimates; check the product's NFRC label before relying on them.
NOMINAL_WINDOW_U = {
    ("double", "vinyl"): 1.22,
    ("double", "wood"): 1.6,
    ("double", "aluminium"): 2.8,
    ("triple", "vinyl"): 0.9,
    ("triple", "wood"): 1.0,
    ("triple", "aluminium"): 1.8,
}


def room_capacity(
    volume_m3: float, furnishing_kg: float = 0.0, furnishing_c: float = 1000.0
) -> float:
    """Heat capacity of a room's air and furnishings, J/K.

    The furnishings' mass is a guess unless it is measured, and it is the main
    uncertainty in turning a fitted rate into a conductance.
    """
    return volume_m3 * AIR_HEAT_CAPACITY_J_M3K + furnishing_kg * furnishing_c


def ua_from_rate(rate_per_h: float, capacity_j_k: float) -> float:
    """The conductance (W/K) behind a fitted rate (per hour): UA = rate * C / 3600."""
    return rate_per_h * capacity_j_k / 3600.0


def natural_ach(cfm50: float, volume_m3: float, n_factor: float = 20.0) -> float:
    """Natural air changes per hour from a blower-door test.

    Args:
        cfm50: Airflow at 50 Pa, CFM (the blower test's result).
        volume_m3: The house's volume, m³.
        n_factor: The leakage-to-natural ratio (about 20 for a typical house;
            it depends on height, exposure and climate).
    """
    ach50 = cfm50 * M3H_PER_CFM / volume_m3
    return ach50 / n_factor


def infiltration_ua(
    ach: float, volume_m3: float, indoor_c: float = 21.0, altitude_m: float = 0.0
) -> float:
    """Conductance of air leakage, W/K, at a given air-change rate."""
    return ach * volume_m3 / 3600.0 * rho_cp(indoor_c, altitude_m)


def window_u(glazing: str, frame: str) -> float:
    """Nominal window U-value from the glazing ("double" or "triple") and frame."""
    key = (glazing.lower(), frame.lower())
    if key not in NOMINAL_WINDOW_U:
        raise ValueError(f"no nominal U for {glazing!r} glazing in a {frame!r} frame")
    return NOMINAL_WINDOW_U[key]


@dataclass(frozen=True)
class Element:
    """A wall, roof or floor whose nominal R-value is known.

    Attributes:
        name: The element's name.
        area: Area, m².
        r_nominal: Nominal (as-built, from the construction) R-value, m² K/W.
    """

    name: str
    area: float
    r_nominal: float


def envelope_scale(
    elements: list[Element], fixed_ua: float, measured_ua: float
) -> dict:
    """Scale the nominal R-values so the elements' conductance matches a measurement.

    The measured conductance covers all of the envelope. Windows and anything
    else with a known U are taken out first (``fixed_ua``), and the rest is
    shared across the elements in proportion to their nominal conductances:
    each element's U is its nominal U times one factor, so the walls keep their
    relative differences.

    Args:
        elements: The elements to scale (walls, roofs).
        fixed_ua: Conductance of the parts not scaled (windows, doors), W/K.
        measured_ua: Conductance measured for the whole group, W/K, after the
            infiltration has been removed by the caller.

    Returns:
        ``scale`` (the factor), ``elements`` (each with its derived ``u`` and
        ``r``) and ``warnings``.
    """
    if not elements:
        raise ValueError("no elements to scale")
    nominal = sum(e.area / e.r_nominal for e in elements)
    target = measured_ua - fixed_ua
    if target <= 0:
        raise ValueError(
            "the measured conductance does not exceed the fixed parts (windows, "
            "infiltration): the blower test or the fit needs checking"
        )
    scale = target / nominal
    warnings: list[str] = []
    if not 0.5 <= scale <= 2.0:
        warnings.append(
            f"The scale factor is {scale:.2f}: the nominal R-values or the measured "
            "conductance are well off. Check the construction and the fit."
        )
    out = []
    for e in elements:
        u = scale / e.r_nominal
        out.append({"name": e.name, "area": e.area, "u": u, "r": 1.0 / u})
    return {"scale": scale, "elements": out, "warnings": warnings}
