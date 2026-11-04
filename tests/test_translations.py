# Copyright (c) 2026 MinchinWeb
"""The form text: ``translations/en.json`` is ``strings.json``."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.manual_j.settings import ENVELOPE_KEYS, SETPOINT_KEYS

PKG = Path(__file__).parent.parent / "custom_components" / "manual_j"


def _load(name: str) -> dict:
    return json.loads((PKG / name).read_text(encoding="utf-8"))


def test_english_matches_strings():
    # custom integrations only read translations/, which can't use [%key:...%]
    assert _load("translations/en.json") == _load("strings.json")
    assert "[%key:" not in (PKG / "strings.json").read_text(encoding="utf-8")


def test_every_field_is_labelled_and_explained():
    steps = _load("strings.json")["config"]["step"]
    for step in ("user", "settings"):
        fields = {"outdoor_entity", *ENVELOPE_KEYS}
        assert set(steps[step]["data"]) == fields, step
        assert set(steps[step]["data_description"]) == fields, step
    assert set(steps["setpoints"]["data"]) == set(SETPOINT_KEYS)
    assert set(steps["reconfigure"]["menu_options"]) == {"settings", "building"}


def test_every_error_has_text():
    errors = _load("strings.json")["config"]["error"]
    for key in (*ENVELOPE_KEYS, "indoor_cool_c"):
        assert f"invalid_{key}" in errors
