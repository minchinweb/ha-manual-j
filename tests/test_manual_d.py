# Copyright (c) 2026 MinchinWeb
"""Manual D: ducts."""

from __future__ import annotations

import math

import pytest

from custom_components.manual_j.air import air_density, inches
from custom_components.manual_j.manual_d import (
    ROUND_SIZES_IN,
    Segment,
    _area_and_diameter,
    _segment_drop,
    available_static,
    round_size_for_friction,
)


def test_round_duct_velocity_from_flow_and_area():
    seg = Segment.round_in(4, 1.0)
    v, rate, loss = _segment_drop(seg, 0.05, 1.2)
    area = math.pi * 0.1016**2 / 4
    assert v == pytest.approx(0.05 / area)
    assert rate > 0 and loss > 0


def test_bigger_duct_loses_less():
    small = Segment.round_in(4, 10.0)
    big = Segment.round_in(8, 10.0)
    _, rate_small, _ = _segment_drop(small, 0.05, 1.2)
    _, rate_big, _ = _segment_drop(big, 0.05, 1.2)
    assert rate_big < rate_small


def test_round_size_meets_target_and_next_smaller_does_not():
    flow, target = 0.06, 0.8
    size = round_size_for_friction(flow, target, 20.0, 723.0)
    density = air_density(20.0, 723.0)
    _, rate, _ = _segment_drop(Segment.round_in(size, 1.0), flow, density)
    assert rate <= target
    index = ROUND_SIZES_IN.index(int(size))
    if index > 0:
        _, smaller, _ = _segment_drop(
            Segment.round_in(ROUND_SIZES_IN[index - 1], 1.0), flow, density
        )
        assert smaller > target


def test_rectangular_duct_is_loss_equal_to_a_similar_round_one():
    area, d = _area_and_diameter(Segment.rect_in(10, 10, 1.0))
    # Huebscher: a square duct's equivalent round is about 1.09 times its side
    assert area == pytest.approx(inches(10) ** 2)
    assert d == pytest.approx(
        1.30 * (inches(10) ** 2) ** 0.625 / (2 * inches(10)) ** 0.25
    )
    assert d == pytest.approx(1.09 * inches(10), rel=0.01)


def test_blower_curve_interpolation():
    curve = ((0.0, 200.0), (0.1, 150.0), (0.2, 50.0))
    static, ok = available_static(curve, 0.05)
    assert static == pytest.approx(175.0)
    assert ok
    static, ok = available_static(curve, 0.3)
    assert static == pytest.approx(50.0)
    assert not ok
