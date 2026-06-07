# ENV-001 Environment Grids

Status: implemented

Date: 2026-06-07

## What ENV-001 Implements

- `EnvironmentGrid` for researcher-facing virtual experiments.
- Runtime environment case generation from temperature, pH, and oxygen labels.
- Stable generated environment IDs such as `temp_20C_ph_5p0_aerobic`.
- In-memory registry overlay for generated environment records.
- Standard virtual-experiment output tables with environment metadata.
- `environment_summary.csv` grouped by generated or registry environment.

## What ENV-001 Does Not Implement

- No new biological mechanisms.
- No new SABIO-RK entries or fetched datasets.
- No inferred pH response curve.
- No inferred temperature response curve.
- No fungal growth, secretion, uptake, oxygen limitation, PET chemistry, or cellulose morphology model.
- No permanent mutation of `data_registry/environments/environments.yml` when a user creates a grid.

## Environment Grids Versus Response Models

An environment grid creates virtual-experiment cases. It does not by itself
modify rates. Temperature and pH affect kinetics only when an implemented
modifier, condition-specific parameter record, or explicit tested response
model is active.

Generated grid environments are runtime metadata unless a later layer attaches
an environmental response model. This distinction is written to output tables
through `environment_source` and `environment_effect_status`.

## Reaction 618 Kinetics

For SABIO-RK Reaction 618, the selected entry is scoped to 30 C and pH 5.0.
ENV-001 does not extrapolate that selected kinetic law across temperatures or
pH values. Environment-grid runs reuse the kinetic parameters as metadata-only
context and write `environment_effect_status=metadata_only` plus limitations
stating that no temperature or pH response law was applied.

## Output Tables

ENV-001 writes the API-001 tables plus:

- `final_states.csv`
- `environment_summary.csv`

The standard tables include:

- `environment_id`
- `temperature_C`
- `ph`
- `oxygen`
- `environment_source`
- `environment_effect_status`

## Remaining Limitations

- Runtime grid environments are not persisted to the registry.
- Metadata-only environment cases can compare output tables by context, but do
  not claim environmental rate dependence.
- Broad literature ranges remain provenance/uncertainty records, not calibrated
  pH or temperature response curves.
- Environment heatmap plots are not part of ENV-001; tables remain the primary
  output.
