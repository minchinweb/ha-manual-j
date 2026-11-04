# What Manual J reads from House Structure

House Structure publishes the house in `hass.data["house_structure"]` (version
1). `structure.py` reads it, and `house_model.py` builds the Manual J/S/D
project from it. This is the reading side of House Structure's duct and
envelope fields; House Structure documents the parts themselves. Moved from
Home Thermal Lab's `docs/house-structure-duct-spec.md`.

## Duct runs

For each register with a duct (or an upstream) and a free area, the run is:

1. Each shared section from the plenum down to the register's section. Each
   carries the summed design airflow of the registers behind it, and counts as
   trunk.
2. The register's own branch segments, at the register's airflow.

A register whose section does not exist, or whose sections loop, is left out
with a warning. A register with a shared section and no airflow is noted, since
its share of the trunk airflow is missing.

## Envelope fields

- Walls and roofs: `r_value_si` (optional; the house's nominal R is used if
  blank).
- Windows: `glazing` (`double` or `triple`) and `frame` (`vinyl`, `wood` or
  `aluminium`), chosen from lists. Their U-values come from the consumer's table
  (`building.window_u`).
- Rooms: `below_grade_m`, the depth of the walls below grade. The share of each
  wall below grade is that depth over the room's height; the rest of the wall is
  outdoors. Without a depth, a below-ground room's walls are all taken as below
  grade (and the consumer says so).

## Equipment and buildings

The summary's `equipment` lists House Structure's furnaces (`input_high_w`,
`input_low_w`, `afue` as a fraction, `blower` as `[[m³/s, Pa], ...]`,
`area_id`) and air conditioners (`total_w`, `sensible_w`). The first of each
is checked against the loads (`loads.equipment_from`); a second one is noted.
Its `buildings` are the detached buildings (`title`, `area_ids`), sized on
their own at the setpoints Manual J keeps for them by name.

## Tests

`tests/test_house_model.py`: sections are shared by their registers, the
shared sections carry the summed airflow, unknown and looping sections leave
the register out, a register with no airflow is noted.
`tests/test_structure.py`: the summary is read, and an unknown version gives
nothing.
