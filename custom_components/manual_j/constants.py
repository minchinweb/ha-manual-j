# Copyright (c) 2026 MinchinWeb
"""Names shared across the integration (standard library only)."""

from __future__ import annotations

DOMAIN = "manual_j"

# House Structure: its published summary, and what Manual J adds to it.
STRUCTURE_DOMAIN = "house_structure"
STRUCTURE_EVENT = "house_structure_updated"
STRUCTURE_VERSION = 1
TABS = "house_structure_tabs"
TABS_EVENT = "house_structure_tabs_updated"
NEEDS = "house_structure_needs"
NEEDS_EVENT = "house_structure_needs_updated"
# the sizes Manual J calculates from, so House Structure asks for them
NEEDED = ("wall_size", "roof_size", "room_floor")

# Home Thermal Lab's fitted cooling rates, when it is installed
FITTED = "home_thermal_lab_fitted"
FITTED_EVENT = "home_thermal_lab_fitted_updated"

# The HVAC design tab on House Structure's Thermal Lab page
TAB_KEY = "hvac_design"
TAB_TITLE = "HVAC design"
TAB_ORDER = 20
STATIC_URL = "/manual_j_static"

# Settings
OUTDOOR_ENTITY = "outdoor_entity"
BUILDINGS = "buildings"  # setpoints by House Structure building name
INDOOR_HEAT = "indoor_heat_c"
INDOOR_COOL = "indoor_cool_c"
