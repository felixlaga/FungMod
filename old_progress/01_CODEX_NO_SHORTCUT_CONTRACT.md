# Codex No-Shortcut Contract for FungMod

## Binding instruction

Codex must build FungMod as a durable scientific modeling framework before adding real biology.

Codex must not optimize for making the current PET example pass. Codex must optimize for generic architecture, explicit failure, and long-term maintainability.

## Forbidden behavior

Codex must not:

1. hardcode PET in generic/core modules;
2. create PET-specific branches in generic loaders;
3. keep `run_pet_surface_integration` as the main pathway;
4. manually construct solvers in high-level workflows once `AssembledModel.run()` exists;
5. add fallback constants;
6. silently create toy parameters;
7. treat toy configs as scientific;
8. use notebooks to hide implementation;
9. call a feature generic without a non-PET test;
10. mark a milestone complete without guardrail/failure tests;
11. add real biology before the framework is ready;
12. use broad rewrites that hide shortcuts;
13. skip updating progress documentation;
14. add TODO placeholders in public APIs;
15. implement a partial public API that looks finished.

## Allowed temporary behavior

Temporary adapters are allowed only if all are true:

1. explicitly named temporary or legacy;
2. covered by tests;
3. assigned an exit milestone;
4. not used as the generic path.

Allowed temporary wrapper:

```python
def run_pet_surface_integration(...):
    warnings.warn("Use run_configured_model", DeprecationWarning)
    return run_configured_model("data/model_configs/pet_surface_demo.yml", ...)
```

Forbidden:

```python
def run_configured_model(...):
    if substrate_type == "pet":
        ...
```

## Generic means generic

A generic feature must be tested on at least two cases:

1. PET plugin/example or another specific plugin case;
2. non-PET dummy/foundation case.

If not, name it plugin-specific or experimental.

## No biology before foundation

Until foundation milestones are complete, do not implement:

- real fungal species models;
- real enzyme mechanisms from papers;
- PETase literature kinetics;
- cellulose/lignin/chitin pathways;
- metabolism;
- growth physiology beyond dummy benchmark processes;
- calibrated datasets.

Only framework-safe dummy/foundation processes are allowed.

## Required Codex report per task

Codex must report:

```text
What changed:
What did not change:
Shortcut removed:
Shortcut remaining:
Tests added:
Tests run:
Files touched:
Risk level:
Next milestone:
```

## Definition of done

A task is done only when:

1. all tests pass;
2. new tests cover the change;
3. no new PET hardcoding exists in core;
4. no fallback constants were added;
5. public APIs are not placeholders;
6. examples still run or are deliberately migrated;
7. progress docs are updated;
8. remaining shortcuts are listed in `SHORTCUTS.md`;
9. failure behavior is tested;
10. a non-PET path exists if the feature is generic.
