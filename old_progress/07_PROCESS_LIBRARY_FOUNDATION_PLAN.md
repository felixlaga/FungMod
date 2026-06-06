# Process Library Foundation Plan

## Objective

Build a real factory-based process library before adding biology.

## Foundation process types

1. First-order process: analytic framework benchmark.
2. Mass-action process: generic reaction benchmark.
3. Homogeneous Michaelis-Menten: dissolved kinetics benchmark only.
4. Surface catalysis: generic surface framework benchmark.

These are not real biology yet.

## ProcessFactory interface

```python
class ProcessFactory:
    process_type: str
    def can_build(self, context, process_config) -> BuildDecision: ...
    def build(self, context, process_config) -> Process: ...
```

`BuildDecision` includes can_build, reasons, missing_fields, missing_parameters, incompatible_entities.

## ProcessLibrary

```python
class ProcessLibrary:
    def register_factory(self, factory): ...
    def factory_for(self, process_type): ...
    def build_processes(self, context, process_configs): ...
```

Provide `ProcessLibrary.default_foundation()`.

## Factory rules

Factories must read state names, parameter symbols, product maps, and assumptions from config/entities. They must not insert fallback parameters, assume PET, assume state names, invent product maps, or invent accessible surface.

## Dummy non-PET substrate

Create a generic solid benchmark substrate, not pretending to be real cellulose biology. It exists only to prove generic surface infrastructure.

## Tests

Required: duplicate factory fails, unknown process type fails, first-order factory builds, homogeneous factory builds, surface factory builds PET and non-PET, surface factory has no PET import, missing fields fail, missing parameters fail during assembly, wrong units fail.

## Done when

1. default foundation library exists;
2. configs build processes through factories;
3. PET and non-PET surface configs use the same factory;
4. homogeneous config uses the same workflow;
5. factories return structured build decisions;
6. no biology-specific logic is needed.
