# Configuration Inventory (Legacy)

> Identify every setting/parameter/flag the legacy procurement app reads. Facts only; cite evidence
> (config file, registry, DB settings table, or hard-coded constant). Read-only. Status: `Empty`.

## 1. Settings / Company Options
| Setting | Where stored | Default (observed) | Effect | Evidence |
|---------|--------------|--------------------|--------|----------|

## 2. Supplier Options
| Option | Scope | Effect | Evidence |
|--------|-------|--------|----------|

## 3. Calculation Parameters
| Parameter | Value (observed) | Used in (rule/calc) | Hard-coded or configurable | Evidence |
|-----------|------------------|---------------------|----------------------------|----------|
| MinDays | | order sizing | | |
| MaxDays | | order sizing | | |
| Rolling window (days) | | average sales | | |

## 4. Thresholds
| Threshold | Value | Classification/Trigger | Evidence |
|-----------|-------|------------------------|----------|

## 5. Flags / Feature Toggles
| Flag | Values | Behaviour when on/off | Evidence |
|------|--------|-----------------------|----------|

## 6. Hard-coded constants (magic numbers)
| Constant | Value | Location | Meaning (observed) | Evidence |
|----------|-------|----------|--------------------|----------|

> Note: legacy hard-coded constants are **facts to record**, not items to change in this phase.
