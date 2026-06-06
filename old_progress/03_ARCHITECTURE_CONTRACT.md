# Foundation Architecture Contract

## Required architecture

```text
model config
  -> loaders/registries
  -> entities
  -> process factories
  -> model builder
  -> assembled model
  -> native solver
  -> simulation result
  -> validators/plots/reports
```

Each layer must be independently tested.

## Config layer

A model run must be defined by a generic config:

```yaml
kind: model_config
name:
mode: toy | scientific | strict
maturity: toy | synthetic | framework_benchmark | scientific
entities:
  fungus:
  substrates:
  enzymes:
  environment:
  geometry:
parameters:
processes:
initial_state:
time:
validators:
outputs:
```

All quantities need units. All parameters need provenance. State names and validators are config-driven.

## Loader/registry layer

Required registries:

```python
EntityLoaderRegistry
SubstrateLoaderRegistry
GeometryLoaderRegistry
ProcessFactoryRegistry
ValidatorRegistry
ProductMapRegistry
```

No generic loader should have `if substrate_type == "pet"` style branches. Small dispatch maps are acceptable only as formal registries.

## Entity layer

Foundation entities:

```python
Fungus
Enzyme
Substrate
Product
Environment
Geometry
ProductMap
ModelConfig
```

At foundation stage these may be dummy/toy. They must still be generic and support:

```python
to_dict()
validate()
source/provenance
maturity
assumptions
```

## Process factory layer

Foundation factories:

```python
FirstOrderFactory
MassActionFactory
HomogeneousMichaelisMentenFactory
SurfaceCatalysisFactory
```

They build benchmark processes from configs and entities. They do not implement real biology.

Each factory exposes:

```python
can_build(context, process_config) -> BuildDecision
build(context, process_config) -> Process
```

## Process layer

A process is executable and already bound to state names/parameters.

Required process interface:

```python
name
process_type
required_state_variables
changed_state_variables
required_parameters
assumptions
validity
failure_modes
rate(state, time, parameters, environment, geometry)
contributions(rate)
```

Processes must not know about PET unless plugin-specific.

## ModelBuilder layer

`ModelBuilder` must:

1. receive entities, parameters, process configs, process library;
2. ask factories to build processes;
3. check process requirements;
4. check state mappings;
5. check parameter presence, units, and provenance;
6. check geometry support;
7. return `AssembledModel`;
8. produce `AssemblyReport`.

It must not solve.

## AssembledModel layer

Required:

```python
model.processes
model.parameters
model.context
model.state_variables
model.assumptions
model.validators
model.solver_settings
model.assembly_report
model.run(...)
model.to_dict()
```

`run()` must not be a placeholder.

## Solver layer

Required foundation solver:

```python
ProcessODESolver
```

It must canonicalize units, build RHS from process rates/contributions, integrate, reconstruct quantities, record rates, and return `SimulationResult`.

## Result layer

`SimulationResult` must include time, states, process rates, derived quantities, parameters, assumptions, validation, warnings, solver metadata, assembly report, config snapshot, entity snapshots, mode, maturity, and model version.

## Workflow layer

Generic workflow:

```python
run_configured_model(config_path, output_dir=None)
```

Responsibilities: load config, load entities, merge parameters, build processes, build model, run model, validate, save result. It must not know about PET.

## Invariants

1. Core does not import plugins.
2. Processes do not import PET.
3. Generic workflows do not mention PET.
4. Loaders use registries.
5. State names come from config.
6. Product maps come from config.
7. Solving happens through `AssembledModel.run()`.
8. Results are always `SimulationResult`.
9. Failure reports are structured.
10. Toy status is explicit.
