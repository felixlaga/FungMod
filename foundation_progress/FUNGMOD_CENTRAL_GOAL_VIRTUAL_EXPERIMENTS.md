# FUNGMod Central Goal: Virtual Experiments for Fungal and Enzyme-Mediated Substrate Degradation

## Read this before changing the codebase

This document defines the central goal of FungMod.

Any future implementation, refactor, data ingestion, notebook, API design, or model extension must be judged against this document.

If a proposed change does not move FungMod closer to this goal, it should not be implemented.

---

# 1. The central goal

FungMod is a mechanistic virtual-experiment engine for fungal and enzyme-mediated substrate degradation.

Given:

- a fungus or biological enzyme source;
- one or more substrates;
- one or more environments;
- known exact biological facts;
- uncertain parameter ranges or distributions;
- implemented physical/biochemical process laws;

FungMod should simulate the actual degradation process over time.

The main output is not merely whether a case is modelable.

The main output is the simulated process of a fungus or enzyme system acting on a substrate:

- substrate remaining over time;
- substrate mass loss over time;
- product release over time;
- degradation rate over time;
- time to defined degradation thresholds;
- final product yield;
- uncertainty intervals across sampled parameter ranges;
- tables and summaries that a researcher can analyze, plot, and cite.

Modelability checking is only a preflight guardrail.

It exists to prevent physically invalid or unsupported simulations.

It is not the central product.

---

# 2. The Atmodeller analogy

The guiding analogy is:

```text
Atmodeller:
    user inputs atmospheric/planetary parameters
    -> model outputs atmospheric state/composition/structure/spectra/etc.

FungMod:
    user inputs fungus/source + substrate + environment + parameter assumptions
    -> model outputs degradation dynamics over time
```

The goal is not only to say:

```text
this case is modelable
```

The goal is to output:

```text
what happens to the substrate over time
what products are formed
how fast degradation proceeds
how uncertain the prediction is
which environments/substrates/fungi look promising
```

---

# 3. What FungMod is

FungMod is:

```text
a registry-backed, uncertainty-aware, mechanistic virtual-experiment engine
for fungal and enzyme-mediated substrate degradation.
```

It should allow researchers to run in-silico screens such as:

```text
Which fungus is most promising on this substrate?
Which substrate is degraded fastest by this fungus?
How does pH or temperature change degradation dynamics?
Which environmental region gives the highest product yield?
Which cases are unsupported because no mechanism or parameter record exists?
Which missing experiment would most improve the prediction?
```

FungMod is especially useful when researchers do not have complete experimental datasets.

The point is to avoid physically growing every fungus on every substrate in every environment just to decide what is worth testing.

---

# 4. What FungMod is not

FungMod is not primarily a calibration package.

FungMod is not primarily a modelability checker.

FungMod is not a database dump.

FungMod is not a tool that invents biological facts.

FungMod is not a complete whole-fungus growth simulator yet.

FungMod must not pretend to simulate biological mechanisms that are not implemented.

FungMod must not claim that exploratory ranges are literature-curated values.

FungMod must not turn unsupported biology into fake simulations.

---

# 5. Primary user workflow

The eventual researcher-facing workflow should look conceptually like this:

```python
study = FungMod.virtual_experiment(
    fungi=["Pleurotus ostreatus", "Aspergillus niger"],
    substrates=["cellulose film", "cellobiose", "wheat straw"],
    environments=FungMod.environment_grid(
        temperature_C=[20, 25, 30, 35],
        ph=[4.5, 5.0, 5.5, 6.0],
        oxygen="aerobic",
    ),
)

result = study.simulate(
    mode="exploratory",
    n_samples=1000,
)

result.write_tables("outputs/")
result.write_quicklook_plots("outputs/figures/")
result.write_report("outputs/report/")
```

This is the target user experience.

It does not need to exist immediately, but every architecture decision should move toward it.

---

# 6. Modelability is a preflight check

Modelability exists to answer:

```text
Can FungMod honestly simulate this case?
If not, why not?
If yes, under what assumptions?
```

It should classify each case as:

```text
modelable
exploratory
underparameterized
unsupported
incompatible
```

But this is only a guardrail.

The actual goal is to simulate the degradation trajectory.

Correct workflow:

```text
define virtual experiment
-> run modelability preflight
-> simulate valid/exploratory cases
-> output degradation dynamics
-> write tables/figures/reports
```

Incorrect workflow:

```text
define virtual experiment
-> only output modelability table
-> stop
```

A modelability table is useful, but it is not the final scientific result.

---

# 7. Main scientific outputs

FungMod should prioritize data tables over plots.

Plots are useful for quick visualization, but publication-quality plotting should be possible from exported tables.

## 7.1 Required time-series outputs

For each case and each sampled parameter set, FungMod should output time-series data such as:

```text
substrate_remaining(t)
substrate_degraded_fraction(t)
substrate_mass_loss_percent(t)
product_concentration(t)
product_release_rate(t)
enzyme_concentration_or_activity(t)
accessible_substrate_fraction(t)
fungal_biomass_or_growth_proxy(t), if implemented
uptake_flux(t), if implemented
respiration_or_CO2_proxy(t), if implemented
```

The exact states depend on the implemented process.

Do not output a biological state that is not actually modeled.

## 7.2 Required summary metrics

For each case and each sample, FungMod should compute biologically meaningful metrics such as:

```text
final_substrate_remaining
final_substrate_degraded_fraction
final_product_concentration
final_product_yield
maximum_degradation_rate
time_to_10_percent_degradation
time_to_50_percent_degradation
time_to_90_percent_degradation
area_under_product_release_curve
```

If a metric is not meaningful for the process, do not compute it silently. Record it as not applicable.

## 7.3 Required uncertainty summaries

For ensemble simulations, FungMod should output summary statistics across samples:

```text
count
mean
min
max
p05
p50
p95
```

For:

```text
final states
threshold times
product yields
sampled parameters
important rates
```

## 7.4 Required provenance and limitation outputs

Every simulation should output:

```text
which registry records were used
which parameter values were exact
which parameter values were ranges/distributions
which values were exploratory assumptions
which values were missing
which mechanisms were active
which mechanisms were not modeled
which data sources supported each value
which claims are not allowed
```

---

# 8. Standard output files

A FungMod virtual experiment should write a predictable output folder.

Minimum recommended files:

```text
modelability_preflight.csv
case_summary.csv
time_series_long.csv
final_states.csv
final_metrics.csv
threshold_times.csv
sampled_parameters.csv
sampled_parameter_summary.csv
summary_metrics.csv
trajectory_quantiles.csv
missing_parameters.csv
suggested_experiments.csv
provenance_table.csv
limitations_table.csv
screen_summary.json
```

Optional quick-look plots:

```text
substrate_remaining_vs_time.png
product_release_vs_time.png
degradation_fraction_vs_time.png
uncertainty_band_quicklook.png
environment_heatmap.png
case_ranking_quicklook.png
```

Plots must be reproducible from the tables.

Tables are the primary output.

---

# 9. Standard long-format time-series table

The most important output table should be a long-format time-series table.

Recommended schema:

```text
case_id
sample_id
fungus_id
fungus_name
substrate_id
substrate_name
environment_id
temperature_C
ph
oxygen
process_type
time
time_units
state
value
units
source
```

Example:

```text
case_001,sample_000,beta_glucosidase_source,beta-glucosidase source,cellobiose,Cellobiose,30C_pH5,30,5.0,aerobic,homogeneous_michaelis_menten,0.0,hour,cellobiose_concentration,3.06,mM,simulation
case_001,sample_000,beta_glucosidase_source,beta-glucosidase source,cellobiose,Cellobiose,30C_pH5,30,5.0,aerobic,homogeneous_michaelis_menten,1.0,hour,cellobiose_concentration,2.91,mM,simulation
case_001,sample_000,beta_glucosidase_source,beta-glucosidase source,cellobiose,Cellobiose,30C_pH5,30,5.0,aerobic,homogeneous_michaelis_menten,1.0,hour,beta_D_glucose_concentration,0.30,mM,simulation
```

This table is more important than built-in plots.

---

# 10. Biological interpretation rules

FungMod must distinguish:

```text
enzyme-source simulation
whole-fungus simulation
substrate-surface simulation
growth simulation
uptake simulation
```

Do not use whole-fungus language for an enzyme-only case.

For example, the SABIO-RK Reaction 618 case should be described as:

```text
A beta-glucosidase enzyme-source simulation hydrolyzing cellobiose to beta-D-glucose.
```

It must not be described as:

```text
Oryza sativa eating cellobiose.
```

Similarly, a future purified-enzyme PETase case must not be described as a fungus eating PET unless the model includes the relevant whole-organism mechanisms.

---

# 11. Process hierarchy

To simulate a fungus eating a substrate, FungMod will eventually need process layers.

## 11.1 Enzyme-only soluble substrate

Example:

```text
cellobiose + beta-glucosidase -> beta-D-glucose
```

Processes:

```text
homogeneous Michaelis-Menten
product release
mass balance
```

Outputs:

```text
cellobiose concentration over time
glucose concentration over time
degradation fraction
threshold times
```

This is the current first real case.

## 11.2 Enzyme-mediated solid substrate degradation

Example:

```text
cellulose film + cellulase system
```

Processes may include:

```text
surface accessibility
adsorption
surface catalysis
product release
accessible site depletion
```

Outputs:

```text
solid substrate mass remaining
accessible surface area
soluble product release
degradation fraction
threshold times
```

## 11.3 Whole fungus on substrate

Example:

```text
fungus growing on cellulose-containing biomass
```

Processes may include:

```text
enzyme secretion
extracellular hydrolysis
product uptake
biomass growth
maintenance
respiration
environmental response
```

Outputs:

```text
substrate mass loss
soluble products
fungal biomass proxy
uptake flux
growth rate
respiration proxy
threshold times
```

Do not add these processes until the underlying mechanism and parameters exist or can be represented honestly as ranges/unknowns.

---

# 12. Data philosophy

FungMod does not require complete datasets for every virtual experiment.

Instead, it requires layered scientific knowledge.

## 12.1 Deterministic facts

Examples:

```text
fungus/source has enzyme class X
enzyme class X cleaves bond class Y
substrate contains bond class Y
reaction produces product Z
process law is Michaelis-Menten or surface catalysis
```

These are categorical facts.

They should be sourced from databases or literature.

## 12.2 Parameter values and ranges

Examples:

```text
Km
kcat
enzyme concentration
secretion rate
uptake rate
temperature optimum
pH response
surface accessibility
adsorption constant
growth yield
maintenance rate
```

These may be:

```text
exact
range
distribution
unknown
not applicable
```

Every value must have provenance.

## 12.3 Experimental datasets

Experimental datasets are useful for:

```text
validation
calibration
benchmarking
case studies
```

But they are not required for every virtual screen.

The central use case is simulation under uncertainty when complete experiments do not exist.

---

# 13. Parameter meaning matters

FungMod must distinguish these categories:

```text
exact selected-entry value
literature range across multiple entries
organism-specific range
condition-specific range
user-supplied exploratory prior
synthetic test value
calibrated posterior
unknown value
not applicable value
```

These are not interchangeable.

Never use a broad literature range as if it were uncertainty on one exact experiment.

Never use a user-supplied exploratory prior as if it were literature-curated.

Never use toy values in scientific mode.

---

# 14. Researcher-facing API target

The long-term public API should be virtual-experiment-first.

Target conceptual API:

```python
study = FungMod.virtual_experiment(
    fungi=["fungus_A", "fungus_B"],
    substrates=["substrate_1", "substrate_2"],
    environments=FungMod.environment_grid(
        temperature_C=[20, 25, 30],
        ph=[4.5, 5.5, 6.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(
    mode="exploratory",
    n_samples=1000,
)

result.write_tables("outputs/study")
result.write_quicklook_plots("outputs/study/figures")
result.write_report("outputs/study/report")
```

The researcher should not need to know internal implementation details.

The first implementation may still require registry IDs.

Later implementations should support aliases and human-readable names.

---

# 15. API design principles

The public API should use biological language.

Good public concepts:

```text
VirtualExperiment
FungusScreen
SubstrateScreen
EnvironmentGrid
DegradationResult
ProductReleaseResult
ThresholdTimes
UncertaintySummary
SuggestedExperiment
```

Avoid exposing internal concepts unless necessary:

```text
ValueSpec
ProcessCompatibilityRecord
RegistryProcessAssembler
ParameterRecord
ModelConfig
```

Internal concepts may remain available for developers, but the researcher-facing API should focus on biological questions and outputs.

---

# 16. Required next milestone

The next major milestone should be:

```text
API-001: VirtualExperiment simulation API and standard biological output tables
```

This milestone must not add new biology.

It should wrap the workflows that already exist.

Definition of done:

```text
- researcher can define a virtual experiment from registry IDs;
- FungMod runs modelability preflight internally;
- FungMod simulates modelable/exploratory cases;
- FungMod writes time_series_long.csv;
- FungMod writes final_metrics.csv;
- FungMod writes threshold_times.csv;
- FungMod writes sampled_parameters.csv;
- FungMod writes summary_metrics.csv;
- FungMod writes provenance_table.csv;
- FungMod writes limitations_table.csv;
- optional quick-look plots are generated;
- Reaction 618 notebook uses this API;
- existing low-level APIs still work;
- no new biological mechanisms are introduced.
```

---

# 17. API-001 implementation outline

Recommended files:

```text
src/fungal_model/api/
    __init__.py
    virtual_experiment.py
    environment_grid.py
    result_tables.py
    metrics.py
    quicklook.py
```

Recommended public exports:

```python
VirtualExperiment
EnvironmentGrid
DegradationScreenResult
DegradationMetrics
```

Recommended API:

```python
from fungal_model.api import VirtualExperiment, EnvironmentGrid

study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
    registry="data_registry/registry_index.yml",
)

result = study.simulate(
    mode="exploratory",
    n_samples=128,
    seed=1,
    output_dir="outputs/reaction_618_virtual_experiment",
)

result.write_tables()
result.write_quicklook_plots()
```

---

# 18. API-001 metric requirements

For the first enzyme-only case, compute:

```text
substrate_degraded_fraction(t)
product_formed(t)
time_to_10_percent_substrate_degradation
time_to_50_percent_substrate_degradation
time_to_90_percent_substrate_degradation
final_substrate_remaining
final_product_concentration
maximum_product_release_rate
maximum_substrate_depletion_rate
```

These metrics should be generic enough to work for later degradation processes when state mappings are known.

If required state mappings are missing, write a clear not-applicable row rather than failing silently.

---

# 19. Environment-grid target

FungMod must eventually support virtual screens over environments.

Example:

```python
grid = EnvironmentGrid(
    temperature_C=[20, 25, 30, 35],
    ph=[4.5, 5.0, 5.5, 6.0],
    oxygen=["aerobic"],
)
```

This should generate environment cases.

However, do not pretend that temperature or pH affects rates unless a modifier/process law exists.

If no environmental response model is available, FungMod may still simulate separate conditions only when parameters are condition-specific, but must report the limitation.

---

# 20. Suggested-experiment output

FungMod should help researchers decide what to measure next.

For each underparameterized or highly uncertain case, output suggested experiments.

Examples:

```text
Measure enzyme concentration/activity under the target environment.
Measure glucose release over time at fixed enzyme loading.
Measure substrate mass loss time course.
Measure accessible surface area before and after incubation.
Measure pH/temperature response curve for the enzyme system.
```

This is important because FungMod is a virtual screening and experimental-design tool.

---

# 21. Rule for adding new biology

Do not add a new biological mechanism unless it can produce a meaningful output table.

Bad:

```text
Add fungus growth because it sounds important.
```

Good:

```text
Add product uptake + biomass growth because the target output requires biomass_proxy(t)
and the registry has uptake/yield/maintenance parameter records or honest ranges.
```

Each new mechanism must define:

```text
required inputs
state variables
process law
parameters
units
validity domain
output states
summary metrics
limitations
tests
```

---

# 22. Rule for adding new data

Do not ingest random data.

Every new data source must answer a specific need:

```text
Does this source add categorical mechanism evidence?
Does it add a parameter value/range?
Does it add a validation time course?
Does it add substrate composition/bond classes?
Does it add environment-response data?
```

Each data source must be stored as:

```text
raw snapshot
curated record
selection/exclusion report
registry mapping
tests
limitations
```

---

# 23. Current first real case

The first real case is SABIO-RK Reaction 618:

```text
Cellobiose + H2O = 2 beta-D-Glucose
beta-glucosidase
homogeneous Michaelis-Menten
```

This case is enzyme-only.

It is not whole-fungus degradation.

It should be used to prove the virtual-experiment output layer:

```text
time-series outputs
threshold times
final metrics
uncertainty summaries
sampled parameters
provenance
limitations
```

If FungMod cannot produce a clean virtual-experiment result for this simple case, it is not ready for more complex fungus/substrate systems.

---

# 24. Do not forget the central question

Before every implementation, ask:

```text
Does this help a researcher simulate what happens when a fungus or enzyme system acts on a substrate over time?
```

If the answer is no, do not implement it.

If the answer is only:

```text
it makes the registry prettier
```

or:

```text
it adds more data without making simulations better
```

or:

```text
it adds biology without outputs
```

then the change is not a priority.

---

# 25. One-sentence memory

FungMod exists to let researchers run mechanistic virtual experiments of fungi or enzyme systems degrading substrates across environments, producing clean time-series and summary tables of substrate loss, product release, degradation rates, threshold times, uncertainty, provenance, and limitations.

Never forget this.
