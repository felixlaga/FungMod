# API-003: Researcher-Facing Virtual Experiment API

## Status

Implemented.

API-003 adds the first public API intended for researcher-facing virtual
experiments. It keeps the existing registry-ID API intact while adding a
top-level convenience function and public scientific simulation mode.

## Public API Added

Top-level:

```python
from fungal_model import virtual_experiment, EnvironmentGrid

study = virtual_experiment(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose"],
    environments=["30C_pH5_assay"],
)
```

Class-based:

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_names(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose"],
    environments=["30C_pH5_assay"],
)
```

Existing exact-ID usage remains supported through
`VirtualExperiment.from_registry(...)`.

## Name Resolution

`virtual_experiment(...)` and `VirtualExperiment.from_names(...)` resolve
fungus/source, substrate, and environment names through `RegistryResolver`.
Resolution checks registry IDs, names, display names, scientific names, aliases,
EC numbers, database IDs, and simple case-insensitive exact matches.

Unknown names fail clearly with a `ResolutionError`. Ambiguous names fail with
an `AmbiguousResolutionError` and candidate IDs. The API never silently chooses
among ambiguous biological records.

`EnvironmentGrid` inputs remain supported. Runtime grid environments are
generated in memory, and existing condition-specific parameter records are
copied to those runtime environment IDs as metadata-only contexts.

## Scientific Vs Exploratory Simulation

Exploratory mode:

```python
result = study.simulate(mode="exploratory", n_samples=128)
```

- allows exact values and explicitly sampleable uncertainty;
- allows explicitly marked exploratory priors;
- samples uncertainty and writes uncertainty summaries;
- preserves sampled-parameter provenance and allowed-use fields.

Scientific mode:

```python
result = study.simulate(mode="scientific")
```

- requires the scientific preflight status to be `modelable`;
- uses one exact sample per case;
- rejects unknown required parameters;
- rejects uncertain values and broad ranges;
- excludes exploratory priors;
- rejects toy or synthetic parameter records;
- requires parameter `allowed_use` to permit scientific use;
- labels the run as `scientific_exact_unvalidated`.

Scientific mode does not mean experimentally validated. It means FungMod used
exact, non-exploratory registry values with currently implemented process laws.
Model limitations, provenance, missing-parameter reports, and suggested
experiments remain visible.

## Table Access

`DegradationScreenResult` now exposes standard output tables without rerunning
simulation:

```python
result.time_series()
result.final_metrics()
result.threshold_times()
result.sampled_parameters()
result.provenance()
result.limitations()
result.missing_parameters()
result.suggested_experiments()
```

These methods load the written CSV tables. They do not recompute trajectories
or rerun model assembly.

## Output Manifest

Virtual-experiment simulation writes `output_manifest.json` in the output
folder. The manifest records:

- output kind;
- output schema version;
- simulation mode;
- run label;
- quicklook paths;
- table paths;
- files present in the output folder.

## Examples

Alias-based exploratory screen:

```python
from fungal_model import EnvironmentGrid, virtual_experiment

study = virtual_experiment(
    fungi="beta-glucosidase source",
    substrates="cellobiose substrate",
    environments=EnvironmentGrid(temperature_C=[20, 25, 30], ph=[5.0], oxygen="aerobic"),
)

preflight = study.preflight(mode="exploratory")
result = study.simulate(mode="exploratory", n_samples=100)
rows = result.final_metrics()
```

Scientific exact run when all required values are exact and allowed for
scientific use:

```python
study = virtual_experiment(
    fungi="beta-glucosidase source",
    substrates="cellobiose",
    environments="30C_pH5_assay",
)

preflight = study.preflight(mode="scientific")
if preflight[0].status == "modelable":
    result = study.simulate(mode="scientific")
```

The default Reaction 618 registry case remains scientifically
underparameterized because the selected SABIO-RK entry does not provide enzyme
concentration. Exploratory mode can use the explicitly marked exploratory prior;
scientific mode cannot.

## Limitations

API-003 does not:

- add new biology;
- fetch live external data;
- promote proposed records;
- make exploratory priors scientific;
- validate Reaction 618 experimentally;
- add whole-fungus growth, secretion, uptake, biomass, or environmental
  response models;
- resolve unknown biology beyond what is already present in the local registry.

## Architecture Debt

Scientific exact simulation is represented internally as a one-sample
`RegistryScreenResult` so it can reuse the standard table writer. This is
intentional for API-003, but later work may want a more explicit
`ScientificRunResult` wrapper.

The homogeneous Michaelis-Menten process still preserves legacy product
contribution semantics. Stoichiometric product yields are available as
case-template metadata from ASSEMBLY-001, but process-level stoichiometric
contributions remain future work.

## Next Phase

Recommended next phase: BIO-READINESS or CURATION-001, with special attention
to source-backed reaction/product record generation, reviewed product maps, and
a policy for when exact scientific runs can be presented as calibrated or
validated rather than merely exact and unvalidated.
