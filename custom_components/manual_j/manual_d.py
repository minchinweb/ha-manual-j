# Copyright (c) 2026 MinchinWeb
"""Manual D: the supply runs' pressure losses against the blower's static.

Sizes are in SI; inches are converted on the way in (``Segment.round_in`` and
friends).

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Standard library only, so it is tested without
Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
import math

from .air import IN_TO_M, air_density, inches
from .building import Design

MU_AIR = 1.8e-5  # Pa s, dynamic viscosity of air near 20 C
ROUGHNESS_M = 0.00015  # galvanised sheet metal
REGISTER_K = 1.5  # loss coefficient of a register's face, on its neck velocity
ROUND_SIZES_IN = (3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 24)


@dataclass(frozen=True)
class Segment:
    """A piece of duct between two points.

    Attributes:
        shape: ``round`` (``size_m`` is the diameter) or ``rect`` (width, height).
        size_m: Size in metres.
        length_m: Length, m.
        fittings_k: Sum of the loss coefficients of the fittings on it.
        flow_m3s: Air carried, m³/s. None means the run's own airflow; trunk
            segments give the total they carry.
        trunk: Whether the segment is trunk (higher velocity limit) or branch.
    """

    shape: str
    size_m: tuple[float, ...]
    length_m: float
    fittings_k: float = 0.0
    flow_m3s: float | None = None
    trunk: bool = False

    def __post_init__(self) -> None:
        if self.shape == "round" and len(self.size_m) != 1:
            raise ValueError("a round segment has one size (its diameter)")
        if self.shape == "rect" and len(self.size_m) != 2:
            raise ValueError("a rectangular segment has a width and a height")
        if self.shape not in ("round", "rect"):
            raise ValueError("shape must be 'round' or 'rect'")
        if any(x <= 0 for x in self.size_m) or self.length_m < 0:
            raise ValueError("sizes must be positive and lengths not negative")

    @classmethod
    def round_in(
        cls,
        diameter_in: float,
        length_m: float,
        fittings_k: float = 0.0,
        flow_m3s: float | None = None,
        trunk: bool = False,
    ) -> Segment:
        """A round duct given in inches (``4`` for 4" round)."""
        return cls(
            "round", (inches(diameter_in),), length_m, fittings_k, flow_m3s, trunk
        )

    @classmethod
    def rect_in(
        cls,
        width_in: float,
        height_in: float,
        length_m: float,
        fittings_k: float = 0.0,
        flow_m3s: float | None = None,
        trunk: bool = False,
    ) -> Segment:
        """A rectangular duct given in inches."""
        return cls(
            "rect",
            (inches(width_in), inches(height_in)),
            length_m,
            fittings_k,
            flow_m3s,
            trunk,
        )


@dataclass(frozen=True)
class Run:
    """A supply run: a register and the duct from the plenum to it.

    Attributes:
        name: The run's name.
        room: The room the register serves (a ``RoomLoad`` name).
        register_area_m2: Free area of the register, m².
        segments: The duct from the plenum to the register, in order.
        flow_m3s: Airflow to the register. None uses the room's design airflow.
        register_k: Loss coefficient of the register.
    """

    name: str
    room: str
    register_area_m2: float
    segments: tuple[Segment, ...]
    flow_m3s: float | None = None
    register_k: float = REGISTER_K

    def __post_init__(self) -> None:
        if self.register_area_m2 <= 0:
            raise ValueError(f"{self.name}: register area must be positive")


def _area_and_diameter(seg: Segment) -> tuple[float, float]:
    """Flow area and hydraulic diameter of a segment, m² and m."""
    if seg.shape == "round":
        d = seg.size_m[0]
        return math.pi * d * d / 4.0, d
    a, b = seg.size_m
    # Huebscher's equivalent round diameter for a rectangular duct.
    return a * b, 1.30 * (a * b) ** 0.625 / (a + b) ** 0.25


def _segment_drop(
    seg: Segment, flow: float, density: float
) -> tuple[float, float, float]:
    """Velocity (m/s), friction rate (Pa/m) and total loss (Pa) of a segment."""
    area, d = _area_and_diameter(seg)
    v = flow / area
    re = density * v * d / MU_AIR
    if re <= 0:
        f = 0.0
    elif re < 2300:
        f = 64.0 / re
    else:
        # Swamee-Jain, an explicit fit to the Colebrook equation.
        f = 0.25 / math.log10(ROUGHNESS_M / (3.7 * d) + 5.74 / re**0.9) ** 2
    pressure = density * v * v / 2.0
    rate = f / d * pressure
    loss = (f * seg.length_m / d + seg.fittings_k) * pressure
    return v, rate, loss


def round_size_for_friction(
    flow: float, target_pa_per_m: float, temp_c: float = 20.0, altitude_m: float = 0.0
) -> float:
    """The smallest standard round size (inches) with friction within target."""
    density = air_density(temp_c, altitude_m)
    for d_in in ROUND_SIZES_IN:
        _, rate, _ = _segment_drop(Segment.round_in(d_in, 1.0), flow, density)
        if rate <= target_pa_per_m:
            return float(d_in)
    return float(ROUND_SIZES_IN[-1])


def available_static(
    curve: tuple[tuple[float, float], ...], flow: float
) -> tuple[float, bool]:
    """The blower's external static (Pa) at an airflow, and whether it is on the curve.

    Linear between the curve's (flow, static) points. Outside the curve the
    nearest end is used and the flag is False.
    """
    if not curve:
        raise ValueError("the blower curve is empty")
    pts = sorted(curve)
    if flow <= pts[0][0]:
        return pts[0][1], True
    for (f0, s0), (f1, s1) in pairwise(pts):
        if flow <= f1:
            t = (flow - f0) / (f1 - f0)
            return s0 + t * (s1 - s0), True
    return pts[-1][1], False


def evaluate_run(
    run: Run, flow: float, design: Design, max_branch: float, max_trunk: float
) -> dict:
    """Pressure loss of one run at its airflow, with velocity checks."""
    density = air_density(design.duct_air_c, design.altitude_m)
    segments = []
    loss_total = 0.0
    for seg in run.segments:
        carried = seg.flow_m3s if seg.flow_m3s is not None else flow
        v, rate, loss = _segment_drop(seg, carried, density)
        limit = max_trunk if seg.trunk else max_branch
        loss_total += loss
        segments.append(
            {
                "shape": seg.shape,
                "size_in": [round(x / IN_TO_M, 2) for x in seg.size_m],
                "trunk": seg.trunk,
                "flow_m3s": carried,
                "velocity_mps": v,
                "friction_pa_per_m": rate,
                "loss_pa": loss,
                "velocity_ok": v <= limit,
            }
        )
    neck_velocity = flow / run.register_area_m2
    register_loss = run.register_k * density * neck_velocity**2 / 2.0
    loss_total += register_loss
    return {
        "name": run.name,
        "room": run.room,
        "flow_m3s": flow,
        "segments": segments,
        "register_loss_pa": register_loss,
        "loss_pa": loss_total,
    }
