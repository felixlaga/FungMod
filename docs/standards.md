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
| `mass_action` | `k · ∏ Sᵢ^(orderᵢ)` |
| `homogeneous_michaelis_menten` | `Vmax · S / (Km + S)` or `kcat · E · S / (Km + S)` |

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
- a rate-modifier wrapper (competitive, substrate, or product inhibition);
- a dynamic thermodynamic constraint that gates the rate at solver time.

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
        - SbmlExportError
        - SBML_EXPORTABLE_PROCESS_TYPES

::: fungal_model.standards.cross_engine
    options:
      members:
        - cross_engine_trajectory_check
        - CrossEngineComparison
        - simulate_reference_sbml
