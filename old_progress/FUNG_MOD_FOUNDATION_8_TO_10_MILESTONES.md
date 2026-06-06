# FungMod Foundation Hardening Milestones: 8/10 to 10/10

## Purpose

FungMod is now at a strong foundation stage: `run_configured_model(...)` executes foundation configs end-to-end; `AssembledModel.run()` exists for well-mixed ODEs; PET is behind an explicit plugin registry; process factories exist; output bundles are inspectable; and CI/guardrails exist.

This file defines the concrete work needed to move from an approximately 8/10 foundation to a 10/10 foundation before starting real biology.

Do not implement real biology in this phase.

## Non-goals

Do not implement PETase kinetics, cellulose/lignin/chitin/starch biology, fungal physiology, metabolism, literature data extraction, calibration against papers, JAX, 2D/3D spatial models, dynamic morphology, or substrate-specific chemistry.

## 10/10 foundation criteria

FungMod reaches 10/10 foundation when:

1. The generic configured workflow is decomposed and not a monolith.
2. Toy/scientific/strict modes are mechanically enforced.
3. Generic workflow tests cover success and failure paths.
4. Public APIs are stable, documented, and not placeholders.
5. PET is fully contained in plugin/example/data/test paths.
6. Foundation configs run without substrate-specific workflow code.
7. Output bundles are reproducibility-grade.
8. CI blocks hardcoding, shortcut patterns, type regressions, lint regressions, test failures, and low coverage.
9. Notebooks demonstrate public APIs only.
10. A formal foundation-complete gate exists before biology begins.

---

# Milestone F10.1: Decompose the generic configured workflow

## Reason

`run_configured_model(...)` works, but a large procedural workflow can become the new shortcut sink. The public function should stay simple while internals are separated and tested.

## Required design

Keep:

```python
result = run_configured_model(config_path, output_dir=None, ...)
```

Internally split responsibilities into:

```text
ConfiguredModelRunner
ConfiguredInputLoader
ConfiguredProcessAssembler
ConfiguredOutputWriter
```

Suggested files:

```text
src/fungal_model/workflows/configured_model.py
src/fungal_model/workflows/configured_inputs.py
src/fungal_model/workflows/configured_processes.py
src/fungal_model/workflows/configured_outputs.py
```

## Required tests

- `ConfiguredInputLoader` loads homogeneous config.
- `ConfiguredInputLoader` loads dummy non-PET surface config.
- `ConfiguredInputLoader` loads PET plugin config only with explicit PET registry.
- `ConfiguredProcessAssembler` builds first-order process from config.
- `ConfiguredProcessAssembler` builds non-PET surface process from config.
- `ConfiguredProcessAssembler` reports missing product map as structured failure.
- `ConfiguredOutputWriter` writes expected files.
- `run_configured_model(...)` still executes all foundation configs.

## Definition of done

The workflow is functionally identical, but loading, process assembly, execution orchestration, and output writing are separately testable.

---

# Milestone F10.2: Enforce toy/scientific/strict modes mechanically

## Reason

A toy benchmark must never masquerade as a scientific simulation.

## Required policy

Toy mode allows `confidence_level: testing`, `maturity: framework_benchmark`, artificial parameters, dummy substrates, and toy product maps.

Scientific mode must reject:

- `confidence_level: testing`;
- `maturity: framework_benchmark`;
- toy-only provenance;
- missing source;
- missing measurement method;
- missing validity range;
- unknown required parameter values;
- unknown required units;
- product maps marked toy/framework only.

Strict mode must include scientific-mode rules and reject at least one additional concrete condition already represented in the data model.

## Required implementation

Create a central policy module, e.g.

```text
src/fungal_model/validation/maturity.py
```

or

```text
src/fungal_model/core/maturity.py
```

Do not scatter these checks through workflow code.

Expose a clear contract such as:

```python
validate_run_maturity(
    *,
    mode: str,
    maturity: str,
    parameters: ParameterSet,
    entities: Sequence[Any],
    product_maps: Mapping[str, Any],
    process_configs: Sequence[Any],
) -> tuple[ValidationResult, ...]
```

or an equivalent preflight that raises a structured error.

## Required tests

- toy config runs in toy mode;
- the same toy config fails in scientific mode;
- `confidence_level: testing` fails in scientific mode;
- `maturity: framework_benchmark` fails in scientific mode;
- `value: null` for a required parameter fails before solving;
- missing source fails in scientific mode;
- missing measurement method fails in scientific mode;
- missing validity range fails in scientific mode;
- toy product map fails in scientific mode;
- strict mode rejects at least one extra condition beyond scientific mode.

## Definition of done

A toy foundation config cannot run as scientific unless all toy/test metadata are replaced by non-toy, sourced metadata.

---

# Milestone F10.3: Strengthen failure-path tests for the generic workflow

## Reason

Happy-path tests prove the system works. Failure-path tests prove it is safe.

## Required failure cases

Add tests for:

1. missing config file;
2. invalid top-level config kind;
3. missing `processes`;
4. missing `initial_state`;
5. unknown substrate loader;
6. PET config without explicit PET registry;
7. unknown product-map loader;
8. unknown validator type;
9. unknown process type;
10. missing product map;
11. missing state unit;
12. missing required parameter;
13. conflicting duplicate parameters;
14. incompatible initial-state units;
15. unsupported geometry;
16. failed validation in non-strict mode is recorded;
17. failed validation in strict mode raises, if strict mode uses raising behavior.

Each failure test should assert exception type, stage, details/missing capability, no false success output, and human-readable error text.

---

# Milestone F10.4: Make output bundles reproducibility-grade

## Reason

A future user should be able to reconstruct what happened from the output directory.

## Required existing files

Keep:

```text
input_model_config.json
configured_model_run.json
configured_metadata.json
process_build_decisions.json
initial_state.json
time_grid.json
validators.json
merged_parameters.json
entity_snapshots/
output_manifest.json
```

## Add if missing

```text
run_environment.json
package_versions.json
source_revision.json
solver_settings.json
```

If Git metadata is unavailable, write a truthful null value, not fake metadata.

## Required tests

- every file in the manifest exists;
- manifest includes itself;
- mode/maturity are recorded;
- solver metadata is included;
- package version is included;
- process-build decisions are included.

---

# Milestone F10.5: Make public API intentionally stable

## Required public API

Top-level `fungal_model` should expose stable foundation primitives such as:

```python
run_configured_model
load_model_config
load_substrate
load_geometry
load_product_map
load_parameter_set
ModelBuilder
AssembledModel
ProcessLibrary
ProcessRegistry
ProcessODESolver
RunRequest
SimulationResult
Parameter
ParameterSet
```

PET-specific APIs must not be exported from top-level `fungal_model`; they belong under `fungal_model.plugins.pet`.

## Required tests

- top-level does not expose PET workflow names;
- `fungal_model.workflows` does not expose PET workflow names;
- plugin PET helper is available only from `fungal_model.plugins.pet`;
- public API candidates contain no `TODO`, `placeholder`, or public `NotImplementedError`;
- public API names are documented in README or docs.

---

# Milestone F10.6: Add notebook smoke tests for generic foundation notebooks

## Required policy

Foundation notebooks must import `fungal_model`, call public APIs, and not define core classes, rate laws, solvers, process factories, or hidden implementation.

## Required tests

- every foundation notebook imports `fungal_model`;
- notebooks do not define `class .*Process`, `class .*Solver`, or core rate-law functions;
- quickstart notebook executes in smoke mode;
- notebook outputs are redirected to temporary folders or disabled during tests.

---

# Milestone F10.7: Harden CI and branch-protection documentation

CI should run:

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml
```

Add or maintain:

- `tests/test_quality_config.py`;
- `.github/BRANCH_PROTECTION.md`;
- README section stating CI is required before merging.

Branch protection should require PRs, CI passing, up-to-date branches, no force pushes, and no direct bypass.

---

# Milestone F10.8: Add a foundation-complete gate

Create:

```text
FOUNDATION_COMPLETE.md
```

Initially:

```text
Status: not complete
```

Foundation can be marked complete only when:

- all guardrail tests pass;
- all configured workflow tests pass;
- all failure-path tests pass;
- all maturity-mode tests pass;
- all output reproducibility tests pass;
- CI passes;
- coverage gate passes;
- no active foundation-blocking architecture debt remains;
- PET is plugin-only;
- notebooks use public APIs only;
- README honestly states limitations;
- `run_configured_model` runs homogeneous, dummy non-PET, and PET-plugin foundation configs.

Add a test that checks this file. If status is `complete`, the test must verify that no disallowed active architecture debt remains.

---

# When biology may begin

Biology may begin only after:

1. `FOUNDATION_COMPLETE.md` says `Status: complete`;
2. all F10 milestones pass;
3. CI is green;
4. `ARCHITECTURE_DEBT.md` has no active foundation-blocking debt;
5. foundation examples run end-to-end;
6. toy/scientific mode enforcement works.

After that, do not jump to “all mushrooms/all substrates.” Start with:

1. `data/literature/` dataset schema;
2. literature parameter provenance templates;
3. experiment dataset object;
4. calibration workflow on synthetic data;
5. one narrow literature case only after the dataset/calibration framework is tested.

Only after this should actual fungal/substrate biology be implemented.
