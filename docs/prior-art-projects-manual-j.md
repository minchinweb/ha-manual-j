# Prior art: projects.manual-j (Code4Community-Lexington)

**Repository:** https://github.com/Code4Community-Lexington/projects.manual-j (shallow clone reviewed at `scratchpad/external/projects.manual-j`, latest commit only)
**Licence:** GPL-3.0 (`LICENSE` present). Copying code would bring GPL obligations into our project; see "Licence" below.
**Reviewed:** 2026-11-04
**Status:** early student-project skeleton. The calculation is not implemented yet. The useful content is the kickoff write-up and a transcribed solar-gain table.

## What the repo contains

| Path | Lines | What it is |
|---|---|---|
| `docs/kickoff.md` | 39 | Project brief: goals, the method sketch, the list of surfaces to capture, next steps |
| `docs/development.md` | 3 | Run instructions (`./run.sh`) |
| `data/Table_3_Transcribed.csv` | 781 | Transcribed ACCA-style table: window solar-gain values by shading, glass, pane, direction and temperature band |
| `src/dao/types.py` | 81 | Type aliases and placeholder classes for location weather, winter/summer surfaces, glass |
| `src/controller/controller.py` | 14 | `calculate_winter_j`, the only calculation |
| `src/dao/db.py` | 3 | `import duckdb` only |
| `src/run.sh` | 13 | Venv + run script |
| `src/app.py`, `src/frontend/` | 0 | Empty |

Git history: the clone is shallow (`--depth 1`), so only the latest commit is visible (`5c1f264`, merge of PR #2 from `ds/build`).

## What the code actually computes

Only one function does anything:

```python
temperature_delta = 70 - location_weather.winter_design_temperature_fahrenheit
for surface in winter_surfaces:
    temperature_loss_btus_per_hour += surface[0].get_heat_transfer_multiplier(temperature_delta) * surface[1]
```

- Winter only. No summer, no latent, no infiltration, no ducts, no equipment sizing.
- Indoor setpoint hard-coded to 70 °F (the source has a `TODO: no magic numbers`).
- `WinterSurface.get_heat_transfer_multiplier` is `pass`, so it returns `None`. The controller would therefore raise `TypeError` on the first surface. Read-only review: I did not run it (see "Not verified").
- Surfaces are `(WinterSurface, area)` tuples; no floor, as the comment says. Basements, slabs and the attic are in the kickoff's list but not in code.

## What we can copy (ideas only)

Licence check first: GPL-3.0 means any copied code must be GPL-compatible for us to ship, and our integration is not GPL. **Do not copy code.** Ideas, data facts and the method outline are fine to use with attribution, and the ACCA sources they point to are the real references.

1. **The kickoff's surface checklist.** Its list (wall exterior, wall insulation, roof exterior, roof insulation, ceilings, doors, glass doors, windows, skylights, floors, floor insulation, basements) is a good prompt list for our house-structure UI. Our current set is narrower. Add at least the roof/ceiling split, glass doors and skylights.
2. **The UX point.** The authors say the existing spreadsheets are "a nightmare to use", and they propose asking one item at a time, branching on the answer, with a checklist so nothing is forgotten (for example, the attic). That matches our House Structure tab direction. Worth keeping in mind for the setup flow.
3. **The "only the outside matters" framing.** The brief notes that interior walls with air-conditioned rooms on both sides contribute zero ΔT and can be dropped. Our `house_model.py` already does this; the brief is a good plain-language justification to reuse in our docs.
4. **The solar-gain table as a test fixture (not as data we ship).** See the next section; it is useful for checking our own solar table values, not for use in production.

## Data: `Table_3_Transcribed.csv`

- 780 data rows, 168 distinct `(external shade, glass, internal shade, pane, direction)` combinations, 6 temperature columns (10, 15, 20, 25, 30, 35). Format is consistent: no field-count mismatches.
- It is a transcription of an ACCA-style solar gain table and the header does not name the source table or edition. **Confirm the source edition before relying on it**. The filename says "Table 3", and the kickoff mentions the ACCA spreadsheet "MJ8ae".
- Values rise with the temperature column for almost all rows, as they should. **Nine rows decrease somewhere in the row**, which is either a transcription error or a faithful copy of an oddity in the source. Check against the printed table before using any of them:

| CSV line | Shade / glass / internal / pane / direction | Values (10…35) | Suspicious step |
|---|---|---|---|
| 9 | none / clear / none / double or single+low-e / E/W | 88, 70, 72, 74, 76, 78 | 88 then 70 (first value looks like a typo) |
| 28 | none / clear / draperies / triple or double+low-e / NE/NW | 25, 28, 27, 28, 29, 30 | 28 then 27 |
| 35 | none / clear / roller half-drawn / single / SE/SW | 62, 56, 60, 54, 68, 72 | zig-zag |
| 226, 361, 496, 631 | shade screen 0.15/0.25/0.35/0.45 / tinted / roller half-drawn / double+low-e / N | 10, 12, 14, 6, 18, 20 | 14 then 6 |
| 478 | shade screen 0.35 / tinted / draperies / single / E/W | 23, 37, 31, 35, 39, 43 | 37 then 31 |
| 604 | shade screen 0.45 or blinds / tinted / none / double+low-e / SE/SW | 23, 35, 27, 29, 31, 33 | 35 then 27 |

Lines 226, 361, 496 and 631 share the identical value pattern across four different shade coefficients. That looks like a copy-paste error in the transcription rather than real data, which is the most likely fault in this file.

Two more things to check before any use:
- Header column names are the temperature delta (ΔT in °F) and the values have no unit stated. Assume BTU/hr/ft² of glass, and confirm.
- Direction labels are combined (`NE/NW`, `E/W`, `SE/SW`) with no separate values, so our per-bearing solar model (the `solar_hgf` idea in Eldr) cannot use them directly.

## Errors and pitfalls to avoid (from the code and the brief)

1. **Non-functional controller.** `get_heat_transfer_multiplier` returns `None`, so the one calculation fails at runtime. Do not treat this repo as a working reference for the method.
2. **Type-hint misuse.** Annotations like `list(Modifier)` and `list(HeatTransferMultiplier)` call `list()` where a type expression is meant (`list[Modifier]`). They are also written as tuples with trailing commas: `self.surface = surface,` stores a one-element tuple, not the surface. Both would bite as soon as the code is run or type-checked.
3. **Hard-coded 70 °F indoor setpoint.** Our config makes this a parameter. Keep it that way.
4. **Winter-only and surface-only.** No infiltration, no internal gains, no latent, no sensible/latent split. The brief says "thermal leakage" is the whole story, which is incomplete for a summer design load. Our `manual_j.py` already covers infiltration, people, appliances and latent, and should keep them.
5. **Single-direction ΔT.** The kickoff's `ΔT_total = ΔT · Σ A/R` is the core conduction formula and is correct for a single temperature regime. It ignores the below-grade effective-U rule (Eldr's README and our own `ground` flag) and treats a basement the same as an exterior wall. Use the effective-U approach documented in `docs/prior-art-eldr.md`.
6. **Series/parallel R handling.** The brief explains series sums of R and parallel summing of heat flow, which is right. Be careful with a double-pane window "in series" (the air gap is part of the R), and use the window U-value from the rating, not summed plies.
7. **Solar table direction granularity.** Combined directions (NE/NW, E/W, SE/SW) cannot be split into bearings without assumptions. Our solar model should keep per-face values and document any merge.

## Anything else useful for our forecasts

- **The kickoff's "why" argument**: heat pumps and rules of thumb cause oversized equipment. That is the same motivation as our Manual S verdict and a useful framing for the README.
- **The 1-line formula for a summer-free winter design load** (`Q = ΔT · Σ A/R`) is a quick sanity check to run against our winter numbers. If our total differs greatly from this simple sum, our infiltration or ΔT is the first place to look.
- **The table transcription problems are a warning about our own data work.** If we transcribe any ASHRAE/ACCA values, we should run the same monotonicity and duplicate-row checks used above, and record the source edition.

## Licence

GPL-3.0 (see `LICENSE`). Ideas and facts are not copyrightable; code and the CSV's selection/arrangement are. If we want the table, we should derive our own from the published ACCA source rather than redistribute this transcription.

## Not verified

- **Runtime behaviour.** I tried to import `src/dao/types.py` and compile `controller.py` to confirm the `None` return and the annotation problem. The shell command was denied by the permission classifier, so I did not run that code. The findings above come from reading the source. Confirm with a local run in a fresh venv, outside this repo, if you need it verified.
- **CSV source edition** and whether the nine non-monotone rows are in the printed table.
- **Whether the repo is still maintained.** The shallow clone shows only the latest commit, so activity cannot be judged from it.
