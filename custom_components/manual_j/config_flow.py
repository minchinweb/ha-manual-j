# Copyright (c) 2026 MinchinWeb
"""Set Manual J up, and change its settings (see ``settings.py``).

The first form takes the outdoor sensor and the envelope defaults. Reconfigure
offers the same form, and, when House Structure has detached buildings, a
second one for a building's indoor design temperatures.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
import voluptuous as vol

from . import structure
from .constants import DOMAIN, OUTDOOR_ENTITY, STRUCTURE_DOMAIN
from .settings import (
    ENVELOPE_KEYS,
    SETPOINT_KEYS,
    FieldError,
    setpoints_from_form,
    setpoints_to_form,
    settings_from_form,
    settings_to_form,
)

_NUMBER = selector.NumberSelector(
    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
)
_TEMPERATURE = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
TITLE = "Manual J"


def _settings_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(OUTDOOR_ENTITY): _TEMPERATURE,
            **{vol.Optional(key): _NUMBER for key in ENVELOPE_KEYS},
        }
    )


def _setpoints_schema() -> vol.Schema:
    return vol.Schema({vol.Optional(key): _NUMBER for key in SETPOINT_KEYS})


class ManualJConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manual J's one config entry."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with no building chosen."""
        self._building: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The outdoor sensor and the envelope defaults."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = settings_from_form(user_input)
            except FieldError as err:
                errors[err.field] = f"invalid_{err.field}"
            else:
                return self.async_create_entry(title=TITLE, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _settings_schema(), user_input or {}
            ),
            errors=errors,
        )

    def _buildings(self) -> list[str]:
        return structure.building_names(self.hass.data.get(STRUCTURE_DOMAIN))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The settings, or a building's setpoints when there are buildings."""
        if not self._buildings():
            return await self.async_step_settings()
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["settings", "building"]
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the outdoor sensor or the envelope defaults."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = settings_from_form(user_input, entry.data)
            except FieldError as err:
                errors[err.field] = f"invalid_{err.field}"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                _settings_schema(), user_input or settings_to_form(entry.data)
            ),
            errors=errors,
        )

    async def async_step_building(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the building to set the indoor temperatures of."""
        names = self._buildings()
        if user_input is not None and user_input.get("building") in names:
            self._building = user_input["building"]
            return await self.async_step_setpoints()
        return self.async_show_form(
            step_id="building",
            data_schema=vol.Schema(
                {
                    vol.Required("building"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    )
                }
            ),
        )

    async def async_step_setpoints(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A building's indoor design temperatures."""
        entry = self._get_reconfigure_entry()
        name = self._building or ""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = setpoints_from_form(user_input, entry.data, name)
            except FieldError as err:
                errors[err.field] = f"invalid_{err.field}"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="setpoints",
            data_schema=self.add_suggested_values_to_schema(
                _setpoints_schema(), user_input or setpoints_to_form(entry.data, name)
            ),
            description_placeholders={"building": name},
            errors=errors,
        )
