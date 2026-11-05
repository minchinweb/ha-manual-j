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

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=minchinweb&repository=ha-manual-j&category=integration)

1. Click the button above. It opens this repository in the Marketplace
   (**Settings > Marketplace**, Home Assistant 2026.11 and later) on your own
   Home Assistant. It's a custom repository, so the Marketplace first asks
   you to connect GitHub, if you haven't (it reads public repositories
   only), and to confirm adding it. By hand: choose **Add from link** in the
   Marketplace and enter `https://github.com/minchinweb/ha-manual-j`.
2. Click **Install**. Restart Home Assistant if the Marketplace says to.
3. Add the integration:

   [![Open your Home Assistant instance and start setting up this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=manual_j)

Before Home Assistant 2026.11, install it with
[HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=minchinweb&repository=ha-manual-j&category=integration)
instead (download it, then restart Home Assistant). Without either, copy
`custom_components/manual_j/` into Home Assistant's `custom_components/`
folder and restart. Until that restart Home Assistant doesn't know Manual J is
there, and the **Add integration** link says it "does not support
configuration via the UI".

It needs Home Assistant 2025.3 or later. It switches nothing. It downloads the
historical weather for the home location from
[Open-Meteo](https://open-meteo.com/) (no key needed) once, and again only
when the location moves or a year ends (see below).

## Settings

One entry, with no sub-entries. All of its settings are optional.

- **Outdoor temperature sensor**: the design temperatures come from its
  recorded hourly means over the last two years: the temperature exceeded in
  99.6% of hours for heating, and in 0.4% for cooling. Without one, or with
  too short a record, they come from the **historical weather** at the home
  location: the last ten whole years of hourly temperatures from Open-Meteo's
  archive (reanalysis data, so about a 10 km grid, not a weather station).
  Only if that can't be downloaded are fixed design temperatures for Edmonton
  used. The tab says which it used.
- **Envelope defaults**: air leakage (air changes per hour) and the R-values
  of outside walls, roofs, outside doors and the basement floor. A House
  Structure part with its own R-value keeps it; these fill in the rest. For
  what each one means and what to enter from a blower-door or energy report,
  see [the setup guide](docs/manual-j-setup.md).
- **Detached buildings** (on Reconfigure, once House Structure has one): the
  indoor heating and cooling design temperatures for a building, such as a
  garage kept at 10 °C. Its rooms are sized on their own, at those
  temperatures. A building without them uses the house's.

The **cooling design humidity** comes from the same download's dew points
(the hours as hot as the cooling design), and the **altitude** from Home
Assistant's elevation (Settings → System → General).

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
