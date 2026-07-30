# Configured models

`run_configured_model(...)` loads a schema-checked YAML model, resolves its
entities and parameters, enforces maturity, assembles implemented processes,
runs the solver, applies validators, and writes a reproducible result bundle.

## Run a packaged benchmark

```python
import fungmod as fm

config = fm.example_data_path("model_configs/toy_homogeneous_ab.yml")
result = fm.run_configured_model(
    config,
    output_dir="outputs/configured/homogeneous_ab",
)
print(result.validation_report())
```

The packaged examples are immutable. Copy one before editing:

```python
from pathlib import Path
import shutil
import fungmod as fm

source = fm.example_data_path("model_configs/toy_homogeneous_ab.yml")
target = Path("my_model.yml")
shutil.copy2(source, target)
```

## Advanced thermodynamic benchmark

```python
config = fm.example_data_path(
    "model_configs/showcase_dynamic_thermodynamics.yml"
)
result = fm.run_configured_model(
    config,
    output_dir="outputs/configured/dynamic_thermodynamics",
)
```

The advanced benchmark demonstrates:

- explicit reaction/species metadata;
- an electron-balance binding;
- ideal-dilute activities with an explicit floor;
- standard Gibbs energy, temperature, gas constant, and tolerance records;
- solver-time blocking of unfavorable nonnegative forward rates;
- dynamic reaction-quotient and delta-G trajectories;
- a separate static condition-specific entropy-rate diagnostic;
- conservation, solver, validation, and manifest artifacts.

!!! danger "Framework benchmark only"

    Every non-constant value in this configuration is labelled artificial or
    testing. The model proves the execution contract; it is not biological
    thermodynamic evidence.

## Path resolution in installed wheels

Relative references beginning with `data/` or `data_registry/` first retain
their normal checkout behavior. If they do not exist in the current working
directory, FungMod resolves the matching immutable packaged asset. Arbitrary
missing paths still fail; no numerical fallback is introduced.
