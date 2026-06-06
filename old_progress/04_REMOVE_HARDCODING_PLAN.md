# Remove Hardcoding Plan

## Objective

Remove all domain-specific hardcoding from generic framework code before adding biology.

## Stage H1: allowed-domain map

Create `tests/allowed_domain_specific_paths.yml` listing where PET and future plugins may appear. Guardrail tests should use this map.

## Stage H2: stop PET-first public API

Introduce generic API:

```python
run_configured_model
load_model_config
ProcessLibrary
```

Move PET workflow to plugin/example/deprecated wrapper. If retained, it must delegate to `run_configured_model` only.

## Stage H3: replace PET-only substrate loading

Bad:

```python
if data.get("substrate_type") != "pet":
    raise ValueError("Only PET...")
```

Target:

```python
registry = SubstrateLoaderRegistry.default()
return registry.load(data)
```

Register PET plus at least one generic non-PET loader.

## Stage H4: replace hardcoded workflows

Create `ModelConfig` and `run_configured_model`. Convert PET into a config. Add non-PET dummy config. Add homogeneous config.

Tests: all run through same function.

## Stage H5: product maps from config

Bad:

```text
PET -> hydrolysate
```

Target:

```yaml
product_map: data/product_maps/...
```

Product maps must support arbitrary state names.

## Stage H6: remove PET rate-law dependency from workflows

Workflows must not import `PETSurfaceHydrolysisRateLaw`. Processes are built through factories.

## Stage H7: config-driven state names

No hardcoded `PET`, `E`, or `hydrolysate` in generic paths.

Test: renamed PET states still run.

## Stage H8: config-driven validators

Mass balance weights and other validators come from config.

## Stage H9: plugin boundary

PET-specific helpers may live in:

```text
src/fungal_model/plugins/pet/
src/fungal_model/substrates/pet.py
examples/
data/
tests/test_pet_*.py
```

They must not be imported by generic workflows/processes/loaders.

## Done when

1. PET is plugin/example/data only.
2. Generic workflow has no PET logic.
3. Generic loaders use registries.
4. `run_configured_model` runs PET and non-PET.
5. State names, product maps, and validators are config-driven.
6. Guardrail tests fail on new hardcoding.
