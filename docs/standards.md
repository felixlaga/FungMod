# Standards and interoperability

FungMod can export its supported well-mixed kinetic models to community
systems-biology standards, so models can be inspected, simulated, and archived
with other tools. This is an optional feature:

```bash
python -m pip install "fungmod[standards]"
```

## SBML export

[SBML](https://sbml.org/) (the Systems Biology Markup Language) is the standard
exchange format for kinetic models. FungMod exports to **SBML Level 3 Version 2**.

Exportable processes (`fungmod.standards.SBML_EXPORTABLE_PROCESS_TYPES`):

| FungMod process | Kinetic law |
| --- | --- |
| `first_order_decay` | `k · S` |
| `mass_action` | `k · ∏ Sᵢ^(orderᵢ)` over reactants and catalysts; catalysts are listed as modifiers |
| `homogeneous_michaelis_menten` | `Vmax · S / (Km + S)` or `kcat · E · S / (Km + S)` |
| `proportional_synthesis` | `q · P` or `q · P · I / (K_I + I)` (a source reaction; producer and inducer are modifiers) |

Two representation choices keep exported models faithful where SBML has no
direct equivalent:

- **Parameter-bound stoichiometry.** A product coefficient that a registry
  case binds to a parameter (a biomass yield `Y` and its complement `1 - Y`,
  recorded as `coefficient_bindings` on the product map and carried by the
  process as `product_coefficient_bindings`) is written as a separate reaction
  whose kinetic law is `Y · rate` or `(1 - Y) · rate`, so changing `Y` in the
  SBML changes the model exactly as it does in FungMod. The export is refused
  if the numeric coefficient disagrees with the bound parameter's value.
- **Assay-activity units.** `filter_paper_unit` and
  `beta_glucosidase_assay_unit` have no SI base. They are written as named
  dimensionless unit definitions (the name keeps the FungMod unit string), the
  kinetic laws carry every numeric conversion explicitly, and the model notes
  list them. No SI equivalent is implied; see
  `fungal_model.core.units.ASSAY_BASE_UNITS`.

`to_sbml(..., names_as_ids=True)` repeats each parameter's identifier as its
SBML name, for tools that address entities by name (COPASI does).

### From a config file

```python
from fungmod.standards import write_model_config_sbml

write_model_config_sbml(
    "data/model_configs/toy_homogeneous_ab.yml",
    "toy_homogeneous_ab.xml",
)
```

### From an assembled model

```python
import fungmod as fm
from fungmod.standards import to_sbml

config  = fm.load_model_config("path/to/config.yml")
inputs  = fm.ConfiguredInputLoader().load(config)
model   = fm.ConfiguredProcessAssembler().assemble(config, inputs).model

sbml_xml = to_sbml(model, initial_state=inputs.initial_state, model_id=config.name)
```

Species are written as SBML amounts in a unit ("size 1") compartment; parameters
become global SBML parameters with unit definitions derived from FungMod's pint
units. Enzymes in enzyme-explicit Michaelis-Menten laws are written as reaction
*modifiers* (they appear in the rate law but are not consumed).

### What is refused

To keep the exported model faithful, FungMod **refuses** to export (raising
`SbmlExportError`) rather than emit an inexact model when it encounters:

- an unsupported process (surface catalysis, transglycosylation, …);
- a rate-modifier wrapper of any kind (inhibition, substrate reactivity, or a
  temperature, pH, oxygen or water-activity response);
- a dynamic thermodynamic constraint that gates the rate at solver time.

## SED-ML simulation export

[SED-ML](https://sed-ml.org/) describes *how* to run a model. FungMod exports a
**SED-ML Level 1 Version 4** uniform time course over an exported SBML model,
reporting the time course of every species:

```python
from fungmod.standards import to_sbml, to_sedml
from fungmod.core.units import Q_

sbml = to_sbml(model, initial_state=initial_state, model_id="mm")
sedml = to_sedml(sbml, output_end_time=Q_(120.0, "second"), number_of_steps=40)
```

The SED-ML references the SBML by a relative filename (default `model.xml`) and
reads species targets from the SBML itself, so identifiers always match. The
solver algorithm defaults to CVODE (`KISAO:0000019`).

## COMBINE archive generation

A [COMBINE archive](https://combinearchive.org/) (`.omex`) bundles the model and
its simulation into one self-describing file (a ZIP with an OMEX `manifest.xml`).
FungMod builds it with the standard library, so archives are portable and
byte-reproducible:

```python
from fungmod.standards import write_combine_archive, model_config_to_combine_archive
from fungmod.core.units import Q_

write_combine_archive(
    model, "experiment.omex",
    initial_state=initial_state,
    output_end_time=Q_(120.0, "second"), number_of_steps=40,
)

# Or straight from a config (time span defaults from the config):
model_config_to_combine_archive("path/to/config.yml", "experiment.omex")
```

The archive contains `manifest.xml`, `model.xml` (SBML), and `simulation.sedml`
(SED-ML, marked as the master file), and opens in any COMBINE-aware tool.

## PEtab (parameter estimation)

[PEtab](https://petab.readthedocs.io/) is the community standard for specifying
parameter-estimation problems. FungMod exports a **calibration case** — a
calibration config (model + dataset + fittable parameters + observable mappings)
— as a complete PEtab problem directory:

```python
from fungmod.standards import calibration_config_to_petab

export = calibration_config_to_petab(
    "data/calibration/synthetic/first_order_ab/calibration_config.yml",
    "petab_problem/",
)
# export.problem_yaml, export.sbml_model, export.observables,
# export.measurements, export.conditions, export.parameters
```

The mapping is direct: the model becomes `model.xml` (SBML); dataset
measurements become the measurement table (with values and times converted to
the model's species units and seconds); observable mappings become the
observable table; fittable parameters and their bounds become the parameter
table; and a `problem.yaml` links them. The files are written with the standard
library, so only the `standards` extra (for the SBML model) is required. The
result passes `petab.lint_problem`.

### Multi-condition problems from assembled models

`conditions_to_petab` exports an estimation problem whose conditions are built
by code (a registry case materialised at several environments, for example)
rather than described by one calibration config:

```python
from fungmod.standards import PetabCondition, PetabObservable, PetabParameter, conditions_to_petab

export = conditions_to_petab(
    [PetabCondition("10gl", model_10, initial_10, "hour", times_h, observed, sigma), ...],
    observables=[PetabObservable("biomass", "biomass_dry_mass_concentration", "gram / liter"), ...],
    parameters=[PetabParameter("gelain_hydrolysis_Y", 0.01, 1.0, 0.37, "log10", name="Y"), ...],
    output_dir="petab_problem/",
    model_id="gelain_2020_cellulose_hydrolysis_candidate",
)
```

Every condition must assemble to the same model structure; species whose
initial values differ, and parameters whose values differ, become columns of
the condition table. Each observed value carries its noise standard deviation:
a scale that is constant for an observable is written as a number in
`noiseFormula` (the form COPASI's importer honours), otherwise as per-row
`noiseParameters`. Bounds and nominal values are on the linear scale in each
parameter's model units.

## Reproduction in COPASI

`fungal_model.standards.copasi` imports a PEtab problem written by
`conditions_to_petab` into [COPASI](https://copasi.org/) through
`copasi-petab-importer`, simulates it with tight integrator tolerances, fits
it with Levenberg-Marquardt from the nominal values and from log-uniform random
starts, and re-evaluates every optimum on the PEtab objective

`J = Σ ((simulation − measurement) / σ)²`

from COPASI's own time courses. COPASI weights a dependent column by a
multiplier of the squared residual and the importer stores `σ` there, which
would weight by `σ` instead of `1/σ²`; the runner rewrites every weight to
`1/σ²`, switches off per-experiment weight normalisation, and records both
values. The `copasi` extra (`pip install "fungmod[copasi]"`) provides
`python-copasi`, `copasi-basico` and `copasi-petab-importer`. The Gelain
cross-solver reproduction built on this is described in
[the cross-solver study](gelain-cross-solver.md).

## Export correctness and migration

SBML formulas contain explicit unit conversion factors. Parameter values and
PEtab bounds remain in their original parameter units; species contributions
also convert between compatible state units. Regenerate older exports that used
mixed time or concentration units. The numeric amount-in-a-unit-compartment
convention remains; this is not a new physical compartment model.

PEtab `problem.yaml` includes **training rows only**. Validation and holdout rows
are written to separate `validation_measurements.tsv` and
`holdout_measurements.tsv` files, never referenced as fitting measurements.
`export_metadata.json` records the split, row counts, and noise policy.

Every observation requires a finite positive declared uncertainty. Unknown or
zero uncertainty now fails before files are written; the old implicit `1.0`
noise fallback is removed. Supplied scales and a normal-error export convention
do not establish experimental variance or a scientifically justified likelihood.

## BioModels-ready deposit

FungMod can produce a curated, annotated, submission-ready deposit for the
SABIO-RK Reaction 618 β-glucosidase case (cellobiose → glucose):

```python
from fungmod.standards import write_biomodels_deposit

deposit = write_biomodels_deposit("reaction_618_deposit/")
# deposit.sbml_model, deposit.combine_archive, deposit.readme
```

The deposit contains an SBML model with **SBO** terms and **MIRIAM** annotations
(ChEBI for cellobiose/glucose, EC 3.2.1.21 and UniProt Q8L7J2 for the enzyme,
KEGG/MetaNetX for the reaction, NCBI Taxonomy for *Oryza sativa*, PubMed for the
reference), a COMBINE archive bundling it with a SED-ML time course, and a
`README.md` documenting provenance, the identifiers used, explicit modelling
assumptions, and BioModels submission steps. Km and kcat are the curated
SABIO-RK values; initial concentrations are explicit assumptions.

SBO terms and MIRIAM annotations are also available for any export: pass
`annotations=` (a mapping of element name → `MiriamAnnotation`) to
[`to_sbml`](#api-reference), and SBO terms are added automatically by kinetic
role.

## Cross-engine trajectory checks

An export is only trustworthy if an independent engine reproduces the same
trajectory. FungMod ships a small, independent SBML integrator and a checker:

```python
import numpy as np
from fungmod.core.units import Q_          # (via fungmod.core.units)
from fungmod.standards import cross_engine_trajectory_check

comparison = cross_engine_trajectory_check(
    model,
    initial_state=inputs.initial_state,
    times=Q_(np.linspace(0.0, 120.0, 41), "second"),
)
print(comparison.worst_absolute_difference)   # ~1e-7 (solver tolerance)
assert comparison.agrees(atol=1e-6)
```

`cross_engine_trajectory_check` runs FungMod's own ODE solver and the reference
SBML engine on the same model and time grid and reports the per-species maximum
absolute difference. The reference simulator is deliberately restricted to the
subset of SBML that FungMod emits and raises on anything outside it.

## API reference

::: fungal_model.standards.sbml
    options:
      members:
        - to_sbml
        - write_sbml
        - model_config_to_sbml
        - write_model_config_sbml
        - MiriamAnnotation
        - SbmlExportError
        - SBML_EXPORTABLE_PROCESS_TYPES

::: fungal_model.standards.biomodels
    options:
      members:
        - write_biomodels_deposit
        - build_reaction_618_model
        - BioModelsDeposit
        - REACTION_618_ANNOTATIONS

::: fungal_model.standards.sedml
    options:
      members:
        - to_sedml
        - DEFAULT_KISAO_ID

::: fungal_model.standards.combine
    options:
      members:
        - write_combine_archive
        - model_config_to_combine_archive

::: fungal_model.standards.petab
    options:
      members:
        - calibration_config_to_petab
        - conditions_to_petab
        - PetabCondition
        - PetabObservable
        - PetabParameter
        - PetabExport
        - PetabExportError

::: fungal_model.standards.copasi
    options:
      members:
        - reproduce_in_copasi
        - simulate_in_copasi
        - petab_objective
        - read_petab_tables
        - CopasiReproduction
        - CopasiReproductionError
        - CopasiUnavailableError

::: fungal_model.standards.cross_engine
    options:
      members:
        - cross_engine_trajectory_check
        - CrossEngineComparison
        - simulate_reference_sbml
