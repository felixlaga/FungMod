# Guardrails and Test Specification

## Objective

Make shortcuts mechanically difficult. Instructions are weak; tests and CI are stronger.

Create these foundation guardrail tests:

```text
tests/test_guardrails_no_hardcoding.py
tests/test_guardrails_no_shortcuts.py
tests/test_guardrails_public_api.py
tests/test_guardrails_config_generality.py
tests/test_guardrails_native_execution.py
```

## No-hardcoding tests

Scan generic paths:

```text
src/fungal_model/core/
src/fungal_model/processes/
src/fungal_model/solvers/
src/fungal_model/results/
src/fungal_model/modifiers/
src/fungal_model/workflows/configured_model.py
src/fungal_model/io/
```

Forbidden strings:

```text
PET
petase
hydrolysate
PETSubstrate
PETSurfaceHydrolysisRateLaw
PETAccessibleSurfaceAreaModel
pet_product_release_map
run_pet_surface_integration
```

Allowed locations:

```text
src/fungal_model/plugins/pet/
src/fungal_model/substrates/pet.py
examples/
data/
tests/test_pet_*.py
```

## No-shortcut tests

Fail or require explicit allowlist comments for patterns:

```text
.get("k_
.get('k_
or Q_(
or 1e-
or 0.0
or 1.0
fallback
default physical
temporary constant
```

Allowed benchmark constants must include:

```python
# FUNG_MOD_ALLOW_BENCHMARK_CONSTANT: toy benchmark; exit milestone Mx
```

## No unfinished public API

Public runnable APIs must not contain:

```text
TODO
pass
NotImplementedError
placeholder
scheduled after
future milestone
```

Exceptions are abstract base classes and explicitly unsupported plugin placeholders that are not exported as runnable.

Critical: `AssembledModel.run()` must not remain a placeholder.

## Public API test

Required foundation API:

```python
run_configured_model
load_model_config
ModelBuilder
ProcessLibrary
SimulationResult
```

Test that these exist and that a minimal configured model can run.

## Generic config tests

Required model configs:

```text
data/model_configs/toy_homogeneous_ab.yml
data/model_configs/toy_surface_pet_plugin.yml
data/model_configs/toy_surface_dummy_non_pet.yml
```

All must run via:

```python
run_configured_model(...)
```

No special PET workflow.

## State-name flexibility test

Create a config using arbitrary names:

```text
solid_substrate_amount
free_catalyst_concentration
released_product_amount
```

It must run. This prevents hidden assumptions like `PET`, `E`, or `hydrolysate`.

## Failure tests

Every generic path must test:

- missing process;
- missing parameter;
- unknown parameter value;
- missing provenance;
- incompatible units;
- unsupported substrate type;
- unsupported geometry;
- toy config in scientific mode;
- invalid state mapping;
- missing initial state.

## CI

Add GitHub Actions running `pytest` on push and PR. Later add ruff, pyright, notebook smoke tests, and coverage.

Protect `main` with required CI, PRs, up-to-date branch, and no force pushes.

## PR template

Create `.github/pull_request_template.md` with checkboxes for no hardcoding, no fallback constants, failure tests, non-PET generic tests, and progress-doc updates.

## SHORTCUTS.md

Every temporary shortcut must be listed:

```markdown
## Shortcut ID
Status:
Allowed until:
Reason:
Risk:
Exit condition:
Tests protecting it:
```

## Definition of done

Guardrails are done when Codex cannot silently add PET to core, fallback constants, unfinished public APIs, or generic features without non-PET tests.
