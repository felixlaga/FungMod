# Quickstart

This walkthrough creates a small registry-backed exploratory study and writes a
complete result bundle.

## 1. Define the study

```python
import fungmod as fm

study = fm.virtual_experiment(
    fungi="beta-glucosidase source",
    substrates="cellobiose",
    environments="SABIO-RK Reaction 618 selected assay conditions",
)
```

Researcher-facing names and aliases are resolved against the bundled registry.
You can also pass exact registry IDs.

## 2. Preflight before simulation

```python
for report in study.preflight(mode="exploratory"):
    print(report.summary())
```

Preflight classifies cases as modelable, exploratory, underparameterized,
unsupported, or incompatible. It is a guardrail—not the final scientific
output.

## 3. Simulate

```python
result = study.simulate(
    mode="exploratory",
    n_samples=32,
    seed=618,
    output_dir="outputs/reaction_618",
)
```

The fixed seed makes sampling from explicit exploratory ranges reproducible.
For Reaction 618, the selected kinetic records are provenance-backed while the
enzyme-concentration range remains an explicit exploratory prior. Quantiles
therefore describe that input range; they are not calibrated confidence
intervals.

## 4. Inspect tables

```python
print(result.final_metrics()[:5])
print(result.threshold_times()[:5])
print(result.uncertainty_summary()[:5])
print(result.provenance()[:5])
print(result.limitations()[:5])
print(result.suggested_experiments()[:5])
```

Each accessor reads a standard CSV artifact. It does not rerun the solver.

## 5. Write a report

```python
report = result.write_report(
    "outputs/reaction_618/report",
    include_html=True,
    include_index=True,
)
print(report)
```

Open `outputs/reaction_618/report/index.html` to navigate the report, tables,
manifest, decision-support files, and quick-look figures.

## 6. Treat the manifest as the bundle contract

```python
import json
from pathlib import Path

manifest = json.loads(
    Path("outputs/reaction_618/output_manifest.json").read_text()
)
print(manifest["output_schema_version"])
print(*manifest["files"], sep="\n")
```

The manifest records the output schema version, run mode, tables, figures, and
all files in the bundle.

## Next

- Run the [zero-to-report notebook](notebooks.md#zero-to-a-complete-report).
- Learn how [virtual-experiment modes](concepts/virtual-experiments.md) differ.
- Use the [output reference](concepts/outputs.md) for downstream analysis.
