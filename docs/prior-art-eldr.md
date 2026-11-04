# Prior art: Eldr

**Repository:** https://github.com/SiliconSaga/eldr (shallow clone reviewed at `scratchpad/external/eldr`, latest commit only)
**Reviewed:** 2026-11-04
**What it is:** Python Manual J (heating, cooling 1b with orientation-resolved solar, latent), Manual S (equipment size verdict) and Manual D (equal-friction round ducts, per room). Reads a Sweet Home 3D `.sh3d` model directly, plus a YAML side-car of thermal inputs. Self-described as "demo-grade, not ACCA-certified."
**Size:** about 4,150 lines of package Python (excluding tests), and 380 `def test` functions across 15 test files. Dependencies: `pyyaml`, `defusedxml`.

## What the code does, briefly

| Area | Eldr's approach | Where |
|---|---|---|
| Conduction | `Σ U·A·ΔT` per surface; ΔT chosen per surface by category and space | `loads.py` `_conduction`, `_heating_dt_for`, `_cooling_dt_for` |
| Infiltration | `ACH × V / 60` CFM, sensible `1.08·CFM·ΔT`; latent `0.68·CFM·Δgr` | `loads.py` `heating_load`, `cooling_load` |
| Solar | Per-window `area × SHGC × HGF(bearing)`, HGF linearly interpolated between four cardinal anchors (20/75/45/75 BTU/hr·ft²) | `loads.py` `solar_hgf`, `_SOLAR_ANCHORS` |
| Internal gains | 230 BTU/hr per occupant + 1200 BTU/hr appliances; latent 200/occupant. Per-room split by floor area | `loads.py` constants, `per_room_loads` |
| Attic (cooling) | Sol-air estimate `outdoor_1% + 50°F × 0.85`, giving 133.5°F on Refrhus, a factor of 3.66 on the outdoor ΔT | `spaces.py` `sol_air_attic_temp_f` |
| Buffer spaces | Factor per space, four-rung precedence: observed temp > explicit factor > `vented` > default | `spaces.py` `policy_for`, `_factor` |
| Below-grade | Effective soil-inclusive U loaded at full outdoor ΔT in heating; ground-coupled (≈0) in cooling | `loads.py` `GROUND_COUPLED_CATEGORIES` |
| Manual S | Smallest half-ton size ≥ larger of heating/cooling load; verdict oversized >15%, undersized <−10%, else matched | `sizing.py` |
| Manual D | `FR = 0.109136·Q^1.9 / D^5.02` solved for D; round, next standard size up; velocity `183.346·CFM/D²`; flags velocity > 900 fpm and "oversize" | `ductd.py` |
| Climate | 16 hard-coded US design stations (approximate 99% heat, 1% cool), nearest by great-circle from lat/long | `climate.py` |
| Geometry | Level stack from room polygons; ceilings/floors resolved by XY overlap with the level above/below; walls inferred envelope vs interior | `geometry.py` (1,004 lines), `stack.py` |
| Reporting | Markdown report, `--json` export, `--diff` between two runs, narrative `--overview` | `report.py`, `jsonexport.py`, `diff.py`, `overview.py` |

## What we can copy (ideas, with attribution)

Licence: the repo has no LICENSE file at the root (only the `.gitignore`, `docs/`, `README.md`, `eldr/`), so **copying code is not safe**. Re-implementing the *method* from ASHRAE/ACCA is fine; lift only the ideas, rewrite the code, and cite the README as the source of the idea.

1. **Per-surface assembly tags with a category-preserving rule.** A tag picks a U-value within a category and cannot move a surface between envelope and interior. Our current model keys U by surface name, so a mis-tag can change category. Eldr's rule is the safer design.
2. **Assembly coverage table + "lost tag" detector.** Area per `(category, assembly)` across runs. Redrawing a wall drops its tag; a shrinking variant area is the only signal. Directly useful for our history-based forecasts.
3. **Borrow disclosure.** Any U-value borrowed from a related category warns at runtime and appears in the report. Our integration should do the same for any default we fill in (e.g. Edmonton design temps, default `ach`).
4. **Unbound-name warnings.** A declared space/level name that matches no surface warns, and the report lists "no policy declared." Worth copying for our `spaces`-like config.
5. **Diff tool that leads with design conditions.** `--diff` prints "design conditions changed" first and only then per-component rows, with absolute AND relative thresholds (50 BTU/hr, 2 CFM, 1%). Good template for comparing forecast runs.
6. **JSON export carries the applied values, not the declared ones.** Their `cooling_factor` is what the engine applied, which fixed a real bug (declared 0.5 vs applied 3.66). Our exports should do the same.
7. **Value validation at load.** Finite, physical, and "attic hotter than the house" errors. Cheap to add.
8. **Test-suite shape.** Tests named by behaviour, plus a fixture house. Good model if we need coverage on the forecast layer.

## What to re-implement (method, our own code)

- **Attic sol-air for summer.** Our cooling load currently has no hot-attic term. A flat `ΔT_attic = (T_out + k·α) − T_in` with `k ≈ 50 °F`, `α ≈ 0.85` is a crude but usable starting point, and we can replace it with an observed attic temperature from a sensor. The engine must use the same value as any report that prints it.
- **Below-grade effective U at full outdoor ΔT.** This is what our current `ground` flag does not do cleanly. Eldr's rule (effective U includes the soil path; apply full outdoor ΔT in heating; ground-couple only in cooling) is the one to adopt. Our `Surface.ground` routes the sink to `ground_c` in both modes, which understates winter loss if the U is an effective one.
- **Buffer-space precedence.** Observed temperature > factor > vented flag > default. Lets us use a crawl/garage sensor where we have one.
- **Equal-friction duct sizing** if we extend Manual D beyond what `manual_d.py` already does (we already have Darcy-type friction with roughness; Eldr's fit is a simpler alternative and a useful cross-check).

## Errors and pitfalls to avoid

1. **Effective below-grade U.** A bare-wall U fed to `basement_wall` / `floor` overstates heating load silently. Eldr says so in the README; we must say so in our UI too.
2. **Cooling clipping.** Our `cooling_load` clips each surface at zero, which is right for below-grade surfaces in summer but hides negative gains elsewhere. Eldr does not clip conduction (a surface can subtract). Decide deliberately; document it.
3. **Flat solar.** Eldr uses four cardinal anchors with linear interpolation and no shading, overhangs, time-of-day, or diffuse component. Good enough for a demo; not for forecasts. Our per-face design-day values remain comparable, so keep ours unless we measure.
4. **Sol-air overestimates in practice.** The factor of 3.66 on the outdoor ΔT is large. Eldr flags it as "the least obvious number the engine produces." Show the applied value and say whether it is observed or estimated.
5. **Vented-attic default.** Eldr defaults the attic to *unvented* (0.5 factor for heating) against typical ACCA practice (vented = full outdoor ΔT). Eldr discloses this; we should decide our default explicitly and disclose it.
6. **Manual S thresholds are not ACCA's.** Eldr uses 15%/−10% verdicts and rounds up to half-ton steps. ACCA's sizing guidance uses different limits. Do not call our equivalent "Manual S" without the caveat.
7. **Fixed supply ΔT for cooling CFM.** Eldr hardcodes 20 °F. Our implementation uses the configured `cool_rise_k`; keep that.
8. **Fitting factor fudge.** Duct lengths are straight length × 1.5. Eldr says it is not a true equivalent length; available-static-pressure derivation is off by default for that reason. Don't copy the fudge into a number we present as design.
9. **Hard-coded design stations.** 16 US stations, approximate values. Ours uses an Edmonton config with a "check against ASHRAE" note; keep that.
10. **Level-name collisions.** Eldr merges duplicate SH3D level names silently when no `levels:` block exists. Our Home Assistant area mapping must not merge by name.
11. **Undrawn spaces.** An undrawn floor void defaults to a crawlspace or ground; an overhang needs an explicit `below_void: outdoor`. Eldr reports each gap; we should too, because a silent default can change a number by several times.
12. **Ground ΔT only in cooling.** `ground_temp_f` is ignored in heating. Make sure our config does not expose a ground temperature that looks like it affects winter.

## Anything else useful for our forecasts

- **Absolute-vs-relative change thresholds** (50 BTU/hr, 2 CFM, 1%) when reporting a change between two forecast runs. Avoids noise and avoids reporting rounding as change.
- **Narrative "overview" generated from the numbers** (so the write-up cannot drift from the engine). Relevant to the HVAC design tab's text.
- **Honesty caveats selected automatically from the model** (e.g. "northDirection not set; orientation split is provisional"). Same pattern could flag our provisional inputs (e.g. default ACH, Edmonton design temps).
- **Levels-as-stack model** for partial ceilings and per-room floor/ceiling attribution. Our `house_model.py` handles rooms; the stack logic is the part we don't have and may need when multi-storey forecasts matter.
- **Design doc trail** in `docs/` with dated design + plan files. Worth emulating for our decisions (we already have `docs/`).

## Net assessment

Eldr is a well-documented demo. The structure is clean (UI-agnostic engine, read-only model, a verifiable JSON contract), and its README is an unusually honest list of what is estimated. Its physics is simpler than ours in some places (no psychrometrics, no altitude, fixed design stations, flat solar) and it has features we lack (level stack, sol-air attic, orientation solar, per-surface assemblies, diff and coverage reports). Recommended uses: take the **process ideas** (assembly coverage, borrow disclosure, diff thresholds, applied-value exports, effective below-grade U rule) and the **attic gain concept**; do not copy code without a licence.

## Open items

- Licence: none found at root. Ask the author, or treat as all-rights-reserved.
- Not verified: whether the test suite passes (not run; clone was read-only review).
- Not verified: the Manual S limits against ACCA's current published guidance.
