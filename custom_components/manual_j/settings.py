# Copyright (c) 2026 MinchinWeb
"""Manual J's settings from its forms, and back (standard library only).

One config entry holds them all:

- ``outdoor_entity``: the outdoor temperature sensor whose recorded hourly
  means give the design temperatures.
- The envelope defaults (``house_model.ENVELOPE_SETTINGS``): what a House
  Structure part without its own value is taken to be.
- ``buildings``: the indoor design temperatures for each of House Structure's
  detached buildings, by the building's name.
"""

from __future__ import annotations

from collections.abc import Mapping

from .constants import BUILDINGS, INDOOR_COOL, INDOOR_HEAT, OUTDOOR_ENTITY
from .house_model import ENVELOPE_SETTINGS

ENVELOPE_KEYS = tuple(key for key, _, _ in ENVELOPE_SETTINGS)
SETPOINT_KEYS = (INDOOR_HEAT, INDOOR_COOL)


class FieldError(ValueError):
    """A form value that can't be used; ``field`` names it."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _filled(form: Mapping, keys: tuple[str, ...]) -> dict:
    """The filled-in fields among ``keys`` (a cleared optional number is dropped)."""
    return {k: form[k] for k in keys if form.get(k) not in (None, "")}


def settings_from_form(form: Mapping, current: Mapping | None = None) -> dict:
    """The stored settings from the settings form.

    The building setpoints, which have a form of their own, are kept from
    ``current``.

    Raises:
        FieldError: An envelope value isn't more than 0.
    """
    data: dict = {}
    if form.get(OUTDOOR_ENTITY):
        data[OUTDOOR_ENTITY] = form[OUTDOOR_ENTITY]
    for key, value in _filled(form, ENVELOPE_KEYS).items():
        if float(value) <= 0:
            raise FieldError(key, "must be more than 0")
        data[key] = float(value)
    if (current or {}).get(BUILDINGS):
        data[BUILDINGS] = dict(current[BUILDINGS])
    return data


def settings_to_form(data: Mapping) -> dict:
    """The settings form's values from the stored settings."""
    return {k: data[k] for k in (OUTDOOR_ENTITY, *ENVELOPE_KEYS) if k in data}


def setpoints_from_form(form: Mapping, current: Mapping, name: str) -> dict:
    """The stored settings with one building's setpoints changed.

    Clearing both setpoints removes the building's entry, so it uses the
    house's again.

    Raises:
        FieldError: The heating setpoint isn't below the cooling one.
    """
    own = {k: float(v) for k, v in _filled(form, SETPOINT_KEYS).items()}
    if (
        INDOOR_HEAT in own
        and INDOOR_COOL in own
        and own[INDOOR_HEAT] >= own[INDOOR_COOL]
    ):
        raise FieldError(INDOOR_COOL, "heating must be below cooling")
    data = dict(current)
    setpoints = dict(data.get(BUILDINGS) or {})
    if own:
        setpoints[name] = own
    else:
        setpoints.pop(name, None)
    if setpoints:
        data[BUILDINGS] = setpoints
    else:
        data.pop(BUILDINGS, None)
    return data


def setpoints_to_form(data: Mapping, name: str) -> dict:
    """A building's setpoints form from the stored settings."""
    return dict((data.get(BUILDINGS) or {}).get(name) or {})
