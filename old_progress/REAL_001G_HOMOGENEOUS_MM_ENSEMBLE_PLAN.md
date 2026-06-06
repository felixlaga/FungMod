# REAL-001G: Native Homogeneous Michaelis-Menten Exploratory Ensemble Support

## Purpose

The SABIO-RK Reaction 618 pilot now works in a notebook through a manual workaround:

```text
- scientific modelability correctly reports underparameterized;
- missing parameter: enzyme_concentration_beta_glucosidase;
- a user-supplied exploratory loguniform range was used for that missing parameter;
- 32/32 manual homogeneous Michaelis-Menten sample runs succeeded;
- plots and CSV summaries were generated.
```

This proves the scientific workflow is valid, but the implementation is still wrong architecturally because the notebook is doing package-level work manually.

The next goal is to move the successful notebook workaround into the FungMod codebase.

This milestone implements native exploratory ensemble support for:

```text
process_type: homogeneous_michaelis_menten
```

inside `simulate_screen(...)`.

The end result should be that the notebook can call `simulate_screen(...)` directly for SABIO-RK Reaction 618, instead of copying registries and sampling parameters manually.

---

## Scientific context

SABIO-RK is a curated biochemical reaction kinetics database. It stores reaction participants, rate laws, kinetic parameters, biological source metadata, experimental/environmental conditions such as pH/temperature/buffer, and literature references. This makes it appropriate as a source for kinetic-record-backed FungMod registry cases.

The current selected SABIO-RK pilot case is:

```text
SABIO-RK Reaction ID: 618
Selected EntryID: 35622
Reaction: Cellobiose + H2O = 2 beta-D-Glucose
Enzyme: beta-glucosidase
EC number: 3.2.1.21
Organism/source: Oryza sativa
Kinetic law: Michaelis-Menten
Km_cellobiose: 15.3 mM
kcat_cellobiose: 0.13 s^(-1)
initial_cellobiose_concentration: 3.06 mM
temperature: 303.15 K / 30 °C
pH: 5.0
missing: enzyme_concentration_beta_glucosidase
```

Scientific mode must remain underparameterized because the selected SABIO-RK local snapshot does not provide enzyme concentration.

Exploratory mode may run if the user supplies an explicit range/distribution for the missing enzyme concentration.

---

## Core rule

Do not convert the unknown SABIO-RK enzyme concentration into a fake literature value.

Keep this distinction:

```text
scientific/literature-curated registry:
    enzyme_concentration_beta_glucosidase = unknown
    modelability = underparameterized

exploratory registry or exploratory override:
    enzyme_concentration_beta_glucosidase = distribution/range
    modelability = exploratory/modelable for ensemble runs
```

The exploratory value must always be marked as:

```text
maturity: exploratory_prior
source: user-supplied exploratory range
confidence_level: exploratory_assumption
```

It is not a SABIO-RK value.

---

## Non-goals

Do not implement:

```text
fungal growth
enzyme secretion
product uptake
biomass growth
oxygen limitation
PET chemistry
cellulose surface morphology
surface area/crystallinity dynamics
bulk SABIO-RK import
new real datasets
new biological papers
```

Do not weaken the current honest failure behavior.

---

# Current failure that this milestone fixes

The current notebook call:

```python
screen = simulate_screen(
    fungus_ids=[FUNGUS_ID],
    substrate_ids=[SUBSTRATE_ID],
    environment_ids=[ENVIRONMENT_ID],
    registry=exploratory_registry,
    mode="exploratory",
    n_samples=32,
    seed=1,
    output_dir=screen_output_dir,
)
```

fails with:

```text
RegistryScreenSimulationError:
R4 exploratory screen currently supports only existing generic surface_catalysis configs,
not 'homogeneous_michaelis_menten'.
```

This failure originates from `src/fungal_model/screening/ensemble.py`, where `_simulate_case_ensemble(...)` currently rejects every process type except `surface_catalysis`.

---

# Target architecture

The ensemble code should dispatch by process type.

Avoid one giant conditional if possible.

Preferred structure:

```text
src/fungal_model/screening/
    ensemble.py
    case_builder.py
    case_assembly.py              # optional new shared helpers
    process_assemblers.py          # optional process-specific builders
```

At minimum, implement clean functions such as:

```python
simulate_case_ensemble(...)
simulate_surface_catalysis_ensemble(...)
simulate_homogeneous_michaelis_menten_ensemble(...)
```

or a small dispatcher:

```python
ENSEMBLE_PROCESS_HANDLERS = {
    "surface_catalysis": ...,
    "homogeneous_michaelis_menten": ...,
}
```

Do not duplicate large chunks of surface-catalysis logic if shared code can be extracted safely.

---

# Required behavior

## 1. Existing surface_catalysis ensemble behavior must still work

Do not break current tests for:

```text
tests/test_registry_ensemble_simulation.py
```

If surface-catalysis behavior changes, it must be intentional and covered by tests.

## 2. Add homogeneous_michaelis_menten ensemble behavior

For a case whose selected compatibility record has:

```text
process_type: homogeneous_michaelis_menten
```

`simulate_screen(...)` must:

1. Assess modelability in exploratory mode.
2. Reject unsupported cases.
3. Reject underparameterized cases unless required missing parameters are supplied by an active range/distribution/exact exploratory record.
4. Resolve process parameter roles.
5. Sample every `ValueSpec(kind="range")` or `ValueSpec(kind="distribution")`.
6. Convert sampled values into exact per-sample parameter records/config values.
7. Build a per-sample `ModelConfig` using the existing registry case builder.
8. Run `run_configured_model(...)`.
9. Store sampled parameters.
10. Store scalar final states.
11. Store trajectories if available.
12. Store failures without crashing the whole screen unless all samples fail.
13. Write output summaries.

## 3. Keep scientific mode strict

The real SABIO-RK Reaction 618 registry must continue to report:

```text
status: underparameterized
missing: enzyme_concentration_beta_glucosidase
```

in scientific mode.

Do not make scientific mode use the exploratory enzyme concentration range.

## 4. Add explicit exploratory parameter record or override mechanism

One of these designs is acceptable.

### Preferred design: separate exploratory parameter record

Add a clearly marked record such as:

```yaml
record_id: exploratory_reaction_618_enzyme_concentration_beta_glucosidase_range
parameter_symbol: enzyme_concentration_beta_glucosidase
process_type: homogeneous_michaelis_menten
enzyme_class: beta_glucosidase
substrate_class: cellobiose
fungus_id: sabiork_beta_glucosidase_source
substrate_id: cellobiose
environment_id: sabiork_reaction_618_selected_conditions
maturity: exploratory_prior
value:
  kind: distribution
  distribution: loguniform
  parameters:
    lower: 1.0e-6
    upper: 1.0e-3
  units: mM
  source: user-supplied exploratory range
  confidence_level: exploratory_assumption
  notes: >
    Not curated from SABIO-RK. Used only for exploratory sensitivity analysis
    because SABIO-RK EntryID 35622 does not provide enzyme concentration.
provenance:
  source_database: SABIO-RK
  source_reaction_id: "618"
  selected_kinlaw_entry_id: "35622"
  exploratory_prior: true
```

The parameter selection logic must choose this record only in exploratory mode, not scientific mode.

### Acceptable design: notebook-created temporary registry helper

If registry selection cannot yet distinguish scientific/exploratory records safely, keep the temporary-registry approach but integrate it behind a supported helper/API. The notebook should not need to manually edit YAML records.

Example:

```python
exploratory_registry = with_exploratory_parameter_override(
    registry,
    parameter_symbol="enzyme_concentration_beta_glucosidase",
    value_spec=ValueSpec(...),
)
```

This is acceptable only if tests prove scientific mode remains strict.

---

# Output files

For each `simulate_screen(...)` run, write:

```text
screen_summary.json
sampled_parameters.csv
final_states.csv
sample_failures.csv
```

If trajectories are available, also write:

```text
trajectories/
    sample_000.csv
    sample_001.csv
    ...
trajectory_quantiles.csv
```

Minimum scalar summary columns:

```text
sample
fungus_id
substrate_id
environment_id
process_type
status
enzyme_concentration_beta_glucosidase
final_cellobiose_concentration
final_beta_glucosidase_concentration
final_beta_D_glucose_concentration
```

The exact state names may differ. Use actual state IDs from the generated config.

Important:

```text
final_* columns must be scalar last values, not full trajectory lists.
trajectory_* outputs may contain full time series.
```

The manual notebook run produced trajectory lists inside final-state columns. This must be fixed in the codebase.

---

# Ensemble summary statistics

Add summary stats for sampled parameters and final states.

Minimum stats:

```text
count
mean
min
max
p05
p50
p95
```

Write these to:

```text
final_state_summary.csv
sampled_parameter_summary.csv
```

If this is too much for one implementation pass, at least write `final_states.csv` with scalar values and record the missing summary stats as architecture debt.

---

# Notebook update

Update:

```text
notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb
```

The notebook should no longer rely on the manual workaround.

Final notebook flow:

```text
1. Load registry.
2. Load SABIO-RK KineticRecord.
3. Run scientific modelability:
   - expected: underparameterized because enzyme concentration is unknown.
4. Load or create exploratory enzyme-concentration range:
   - 1e-6 to 1e-3 mM loguniform.
   - clearly marked user-supplied exploratory assumption.
5. Run simulate_screen(...) in exploratory mode.
6. Display sampled_parameters.csv.
7. Display final_states.csv.
8. Plot sampled enzyme concentration.
9. Plot final beta-D-glucose distribution.
10. Plot final cellobiose distribution.
11. State limitations.
```

Required notebook warning:

```text
This exploratory ensemble uses a user-supplied enzyme-concentration range.
The enzyme concentration is not curated from SABIO-RK EntryID 35622.
This remains an enzyme-only kinetic pilot, not a whole-fungus degradation model.
```

---

# Required tests

Add or update tests.

## Scientific strictness tests

```text
tests/test_sabiork_reaction_618_registry_case.py
```

Required:

```text
- scientific mode remains underparameterized for Reaction 618 with the literature-curated registry;
- missing item is enzyme_concentration_beta_glucosidase;
- deterministic build is blocked when enzyme concentration is unknown.
```

## Exploratory ensemble tests

Create or extend:

```text
tests/test_registry_ensemble_homogeneous_mm.py
```

Required:

```text
- simulate_screen supports homogeneous_michaelis_menten;
- exploratory Reaction 618 case runs with the exploratory enzyme concentration range;
- all sampled enzyme concentrations are within [1e-6, 1e-3] mM;
- fixed seed gives reproducible sampled enzyme concentrations;
- unknown required parameter still blocks ensemble if no exploratory range is supplied;
- output includes sampled_parameters.csv;
- output includes final_states.csv;
- final state columns are scalar, not list-valued trajectories;
- sample_failures.csv exists;
- surface_catalysis ensemble tests still pass.
```

## Notebook smoke test

If the repository already has notebook smoke-test infrastructure, add:

```text
notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb
```

At minimum, test that the notebook can import FungMod, load the registry, load the KineticRecord, and run scientific modelability.

Do not require live SABIO-RK API access.

---

# Implementation details to inspect before coding

Codex must inspect:

```text
src/fungal_model/screening/ensemble.py
src/fungal_model/screening/case_builder.py
src/fungal_model/screening/modelability.py
src/fungal_model/registry/store.py
src/fungal_model/registry/records.py
src/fungal_model/processes/
```

Specifically inspect the existing config shape expected by the homogeneous Michaelis-Menten factory.

Do not guess the required parameter role names.

From the current Reaction 618 compatibility record, roles appear to be:

```yaml
parameter_roles:
  km: Km_cellobiose
  kcat: kcat_cellobiose
  substrate_initial_concentration: initial_cellobiose_concentration
  enzyme_initial_concentration: enzyme_concentration_beta_glucosidase
```

But Codex must verify these against the actual code.

---

# Required progress update

Update:

```text
foundation_progress/REAL_001_SABIO_RK_PROGRESS.md
```

Add a section:

```text
REAL-001G: Native homogeneous Michaelis-Menten exploratory ensemble support
```

Record:

```text
Status:
Files changed:
Tests added:
Tests run:
Test results:
Scientific modelability result:
Exploratory ensemble result:
Output files produced:
Architecture debt added:
Data debt added:
Known limitations:
Next recommended phase:
```

---

# Architecture debt to avoid

Do not leave these unresolved unless explicitly recorded:

```text
- ensemble.py has duplicated logic for each process type;
- private helper imports are used across modules without a clear shared internal API;
- final-state outputs contain full trajectory lists;
- exploratory priors are indistinguishable from literature-curated parameters;
- scientific mode accidentally uses exploratory priors;
- notebook contains core simulation logic that belongs in src/.
```

If any of these remain, record them as architecture debt.

---

# Data debt to record

The following data debt should remain explicit:

```text
- enzyme_concentration_beta_glucosidase is not supplied by SABIO-RK EntryID 35622;
- exploratory range 1e-6 to 1e-3 mM is user-supplied, not literature-curated;
- no time-course validation dataset is used;
- this is enzyme-only, not living fungus growth;
- no secretion, uptake, biomass, or oxygen model is included.
```

---

# Definition of done

REAL-001G is done when:

```text
- simulate_screen can run homogeneous_michaelis_menten cases;
- Reaction 618 scientific mode remains underparameterized;
- Reaction 618 exploratory mode can run with a clearly marked enzyme-concentration range;
- 32-sample exploratory screen succeeds;
- output files include scalar final states and sampled parameters;
- notebook uses simulate_screen directly, not manual YAML-editing loops;
- tests prove fixed-seed reproducibility;
- tests prove sampled values stay inside the range;
- tests prove scientific mode does not use exploratory priors;
- progress file is updated;
- no whole-fungus claims are made.
```

---

# After REAL-001G

The next scientifically sensible phase is one of:

```text
REAL-002A:
    curate additional SABIO-RK Reaction 618 kinetic-law entries to build literature-derived ranges for Km/kcat across organisms/entries;

REAL-002B:
    find a real time-course dataset for beta-glucosidase/cellobiose or cellulase/product release and use ExperimentDataset comparison/calibration;

ARCH-001:
    generalize process-specific ensemble handlers into a clean plugin/assembler interface before adding more processes.
```

Recommended next phase after REAL-001G:

```text
ARCH-001 if the ensemble implementation duplicated too much code.
Otherwise REAL-002A.
```
