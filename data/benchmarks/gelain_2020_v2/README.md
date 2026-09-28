# Gelain joint culture comparison v2

The fixed retrospective plan compares seven model/family combinations on 144
published non-initial measurements. Activities retain their original assay
meaning. Original means have no SD/replicate arrays or reported detection limits.

- `observations.json`: experimental means with workbook/sheet/cell provenance.
- `source_parameters.json`, `source_simulations.csv`: reproduction references,
  **not observations and never training initialization**.
- `plan.json`: model hypotheses, bounds, assumptions and development screens.
- `results/`: frozen predictions, all fit attempts, numerical checks, covariance
  sensitivity, identifiability diagnostics, conditional bootstrap and validation
  readiness packets. The old v1 results remain unchanged.

Run `python scripts/run_gelain_2020_joint_benchmark.py --output outputs/gelain-joint`
from the repository after installation. Choose an empty output directory.
See [the scientific contract](../../../docs/gelain-joint-benchmark.md) and the
[source intake](../../experiments/source_intake/README.md). No profile is
empirically validated by this retrospective comparison.
