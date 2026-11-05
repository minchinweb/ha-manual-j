# Manual J

A Home Assistant integration that sizes a house's heating and cooling: Manual
J (each room's heat loss and cooling load), Manual S (whether the furnace and
air conditioner suit those loads) and Manual D (whether each supply run gets
its air through the ducts). It works from the house that
[House Structure](https://github.com/minchinweb/ha-house-structure) describes,
and shows the results as the **HVAC design** tab on House Structure's
**Thermal Lab** page in the sidebar.

These are simplified steady-state calculations in the spirit of ACCA's
manuals, not ACCA's tables. Cooling uses the design temperature difference and
a design-day solar gain per face rather than CLTD and SCL tables, so cooling
loads are approximate. Check the results before buying equipment on them.

## Installation

It needs [House Structure](https://github.com/minchinweb/ha-house-structure)
installed first: the rooms, walls, roofs, windows, ducts, furnace, air
conditioner and detached buildings are all House Structure parts.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=minchinweb&repository=ha-manual-j&category=integration)

1. Click the button above. It opens this repository in HACS (the Marketplace
   in Home Assistant 2026.11 and later) on your own Home Assistant. If asked,
   confirm adding it as a custom repository.
2. Click **Download**, then restart Home Assistant.
3. Add the integration:

   [![Open your Home Assistant instance and start setting up this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=manual_j)

Without HACS, copy `custom_components/manual_j/` into Home Assistant's
`custom_components/` folder and restart.

It needs Home Assistant 2025.3 or later. It fetches nothing from the internet
and switches nothing.

## Settings

One entry, with no sub-entries. All of its settings are optional.

- **Outdoor temperature sensor**: the design temperatures come from its
  recorded hourly means over the last two years: the temperature exceeded in
  99.6% of hours for heating, and in 0.4% for cooling. Without one, or with
  too short a record, assumed design temperatures for Edmonton are used, and
  the tab says so.
- **Envelope defaults**: air leakage (air changes per hour) and the R-values
  of outside walls, roofs, outside doors and the basement floor. A House
  Structure part with its own R-value keeps it; these fill in the rest.
- **Detached buildings** (on Reconfigure, once House Structure has one): the
  indoor heating and cooling design temperatures for a building, such as a
  garage kept at 10 °C. Its rooms are sized on their own, at those
  temperatures. A building without them uses the house's.

When Manual J is installed, House Structure starts raising a repair for any
wall or roof without a size, and any room without a floor area, since the
loads are worked out from them. Before, nothing needed them.

## The HVAC design tab

- **Design conditions**: the assumed and recorded outdoor design
  temperatures, side by side.
- **Rooms**: each room's heat loss and cooling load, its calculated
  conductance (UA), and, when
  [Home Thermal Lab](https://github.com/minchinweb/ha-home-thermal-lab) is
  installed, the conductance its fitted zone model measured, their ratio and
  the envelope scale that would match them. Sizes House Structure doesn't give
  are assumed, and the room is flagged.
- **Equipment (Manual S)**: the design size of the furnace and air
  conditioner, set against House Structure's Furnace and Air conditioner
  parts: the ratio, and whether that's oversized, undersized or within
  bounds.
- **Detached buildings**: each sized on its own.
- **Ducts (Manual D)**: each supply run's pressure loss against what the
  blower curve leaves, and the round branch size for the target friction
  rate.
- **Notes**: what was assumed, and why.

The numbers are worked out each time the tab asks (the `manual_j/loads`
websocket command), so they follow changes in House Structure. The recorded
outdoor record is kept until the hour changes.

## Someday

Ideas not yet planned are in `docs/someday.md`. The first is Manual T:
choosing the supply registers by their throw, face velocity and placement.

## Development

```
uv sync
uv run invoke check
```

The calculations (`air.py`, `building.py`, `manual_j.py`, `manual_s.py`,
`manual_d.py`, `project.py`, `house_model.py`, `loads.py`) use only the
standard library. The tests use Home Assistant's own test harness, which needs
Linux; on Windows, run them under WSL with a Linux-side environment:

```
UV_PROJECT_ENVIRONMENT=$HOME/.venvs/ha-manual-j uv run pytest
```

The tab's page loads `tab.js` (the Home Assistant connection and theme) from
House Structure, at `/house_structure_static/tab.js`.

## Credits

Moved out of [Home Thermal Lab](https://github.com/minchinweb/ha-home-thermal-lab),
where it was the Loads tab. See `docs/` for the prior art reviewed.
