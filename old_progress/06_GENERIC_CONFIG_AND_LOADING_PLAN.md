# Generic Config and Loading Plan

## Objective

Make all model construction config-driven and generic.

## Stage C1: config classes

Create:

```python
ModelConfig
EntityConfigRefs
ProcessConfig
InitialStateConfig
TimeConfig
ValidatorConfig
OutputConfig
```

Each supports `to_dict()` and `validate()`.

## Stage C2: model config schema

Minimum model config includes kind, name, mode, maturity, entities, parameters, processes, initial state, time, validators, and outputs.

No PET-specific fields.

## Stage C3: loader registries

Implement registries for entities, substrates, geometries, validators, and product maps.

Foundation substrate types:

```text
generic_solid
generic_dissolved
pet_plugin
```

Tests: all load; unknown type fails.

## Stage C4: ProductMap

Implement `ProductMap` and `load_product_map(path)`.

Foundation product maps can be mass-equivalent framework benchmarks. They must be explicitly labelled toy/framework benchmark.

## Stage C5: parameter merging

Implement `merge_parameter_sets` with conflict detection.

Rules: duplicate identical OK, duplicate conflicting fail, unknown preserved, units compatible.

## Stage C6: validator registry

Implement foundation validators from config: non-negativity, mass balance, state units.

## Stage C7: load_model_config

Loads and validates model configs. Tests valid/invalid configs.

## Stage C8: run_configured_model

Implementation steps:

1. load config;
2. load entities through registries;
3. load product maps;
4. merge parameters;
5. build processes through factories;
6. assemble model;
7. run model;
8. save output if requested.

No PET strings.

## Done when

1. homogeneous, PET plugin, and non-PET configs load and run;
2. no PET-only loader remains;
3. state names, validators, product maps are config-driven;
4. tests cover valid and invalid configs.
