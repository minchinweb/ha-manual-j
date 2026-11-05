# Setting up Manual J

Manual J is set up from **Settings → Devices & services → Add integration**. The first form asks for the house's envelope and air leakage. Every field can be left empty; empty means the default described below.

## Fields

| Field | What to enter |
|---|---|
| **Outdoor temperature sensor** | An outdoor temperature sensor. Its recorded hourly values over the last two years set the design temperatures. Leave empty to use assumed design temperatures for Edmonton. |
| **Air leakage (air changes per hour)** | The natural air changes per hour. Leave empty for 0.35, a fairly tight house. An older house is often 0.5 to 0.7. From a blower-door test, divide the ACH50 result by 20. For example, 3.07 ACH50 gives 0.15. |
| **Outside wall R-value (imperial)** | The effective R-value of the outside walls, studs included. R-20 batts in 2×6 framing are about R-15 overall. Leave empty for R-20. |
| **Roof R-value (imperial)** | The effective R-value of the ceilings under the roof. Leave empty for R-35. |
| **Outside door R-value (imperial)** | The R-value of the doors to outside, with their frames. Leave empty for R-3, an insulated steel or solid wood door. A glass patio door is better entered as a window in House Structure. |
| **Basement floor R-value (imperial)** | The basement slab and the soil under it, as one effective R-value. Leave empty for R-11, an uninsulated slab. |

## Imperial and SI values

The form takes imperial R-values. To convert an RSI value to imperial, divide by 0.1761. For example, 2.64 RSI is about R-15.

The per-wall `r_value_si` field in House Structure takes RSI, not imperial.

## Report values

- **Air leakage:** use the report's ACH50 figure, divided by 20.
- **Walls:** use the effective R-value, not the nominal one. The nominal value counts only the insulation and overstates a framed wall.
- **"N/A" for the basement slab:** the report gives no value for the slab. Leave the basement floor field empty to use R-11.

## Where a wall, roof or door has its own value

A wall, roof or door entered in House Structure with its own R-value keeps that value. The defaults in this form apply only to parts without one.
