# BIO-001 Cellulose Surface Degradation

Date: 2026-06-07

Status: complete for a first exploratory insoluble cellulose-like surface
degradation virtual experiment.

## What BIO-001 Adds

BIO-001 adds a narrow biological extension beyond soluble homogeneous
Michaelis-Menten kinetics: enzyme-mediated degradation of a generic insoluble
cellulose-like film through accessible surface sites.

The new registry case is:

- enzyme/source: `generic_cellulase_source`;
- enzyme class: `cellulase_generic`;
- substrate: `cellulose_film_generic`;
- environment: `bio001_cellulose_surface_pilot_environment`;
- process compatibility: `bio001_cellulase_cellulose_film_surface_catalysis`;
- process type: `surface_catalysis`.

No live data fetch was performed, no new datasets were added, and no precise
literature values were invented.

## Process Law Used

BIO-001 reuses the existing generic `SurfaceCatalysisProcess` through the
configured process factory:

```text
theta = K_ads * E / (1 + K_ads * E)
rate = k_surface * theta * A_accessible
```

The process represents equilibrium enzyme coverage on an accessible surface and
surface-proportional cleavage of the solid substrate into a soluble product
class.

## Simulated States

The BIO-001 virtual experiment exposes:

- `solid_substrate_remaining`;
- `free_enzyme_concentration`;
- `soluble_product_concentration`;
- `substrate_degraded_fraction` derived from the solid substrate state;
- `solid_substrate_degraded_fraction` derived from the solid substrate state;
- `accessible_site_fraction_remaining` derived as a proportional proxy from the
  remaining solid substrate.

The model does not independently evolve accessible surface area or morphology.
The accessible-site fraction is therefore reported as a derived proxy, with this
limitation stated in `limitations_table.csv`.

## Output Tables

The virtual-experiment API writes the standard output bundle:

- `time_series_long.csv`;
- `final_metrics.csv`;
- `threshold_times.csv`;
- `summary_metrics.csv`;
- `sampled_parameters.csv`;
- `provenance_table.csv`;
- `limitations_table.csv`.

BIO-001-specific rows include:

- `solid_substrate_remaining`;
- `solid_substrate_degraded_fraction`;
- `accessible_site_fraction_remaining`;
- `soluble_product_concentration`;
- `final_product_yield`;
- threshold times for 10%, 50%, and 90% substrate degradation;
- maximum product release and substrate depletion rates.

Thresholds that are not reached during the simulated time span are marked
`not_reached`.

## Parameters And Maturity

All BIO-001 numerical parameters are exploratory priors:

| Symbol | Role | Value kind | Maturity |
| --- | --- | --- | --- |
| `cellulose_surface_rate_constant` | surface catalytic rate | distribution | `exploratory_prior` |
| `cellulose_adsorption_constant` | Langmuir adsorption constant | range | `exploratory_prior` |
| `cellulose_accessible_surface_area` | accessible surface area | range | `exploratory_prior` |
| `initial_cellulose_film_mass` | initial solid substrate amount | range | `exploratory_prior` |
| `cellulase_initial_concentration` | initial free enzyme concentration | range | `exploratory_prior` |

All values use:

```text
source: user-supplied exploratory range
confidence_level: exploratory_assumption
```

They are not literature-curated values.

## Scientific Interpretation

BIO-001 is an exploratory virtual experiment for process integration and output
semantics. It is useful for testing the mechanics of insoluble substrate
degradation tables, uncertainty propagation, threshold times, and provenance.

It is not validated against cellulose hydrolysis data.

## Mechanisms Not Included

BIO-001 does not include:

- whole-fungus growth;
- enzyme secretion;
- enzyme uptake or product uptake;
- biomass dynamics;
- respiration or CO2 production;
- oxygen limitation;
- cellulase mixtures or synergistic endoglucanase/cellobiohydrolase effects;
- beta-glucosidase conversion of soluble oligomers;
- lignin, hemicellulose, or full lignocellulose structure;
- dynamic adsorption/desorption states;
- surface renewal, pore accessibility, crystallinity, or morphology changes;
- calibrated pH or temperature response laws.

## Needed For Whole-Fungus Degradation

A future whole-fungus substrate-degradation milestone would need sourced or
calibrated mechanisms for enzyme secretion, enzyme transport/binding,
substrate accessibility evolution, fungal biomass growth, product uptake,
respiration, environmental response, and multi-enzyme lignocellulose
deconstruction. BIO-001 intentionally stops before those mechanisms.
