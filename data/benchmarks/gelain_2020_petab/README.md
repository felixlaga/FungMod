# Gelain 2020 cross-solver reproduction v1

Does an independent simulator and optimiser (COPASI) reproduce FungMod's
all-condition least-squares optimum of the registry hydrolysis candidate
(`trichoderma_harzianum_p49p11` x `cellulose_celufloc_200`) on the three
Gelain 2020 cellulose loadings when both work on the same PEtab problem?
Retrospective: the data already informed the fit being reproduced. It
validates no biology.

- `plan.json`: the frozen plan (SHA-256
  `a0f8abe9561ad1936a2ef06055cd7af8a04cf4902008790d0a14c3cb58f3184a`, pinned
  by `tests/test_gelain_petab.py`): sources and digests, the objective, the
  COPASI settings, the gates, the outcome vocabulary, the excluded claims and
  the amendment rule.
- `results/petab/`: the exported PEtab problem (`problem.yaml`, `model.xml`,
  `conditions.tsv`, `observables.tsv`, `measurements.tsv`, `parameters.tsv`,
  `export_metadata.json`) and `problem_metadata.json` with the source digests,
  the nominal values, the sigmas and FungMod's objective at the nominal values.
- `results/copasi/`: the COPASI file the importer produced with the corrected
  weights (`copasi_problem.cps`, its COMBINE archive and data file) and
  `copasi_reproduction.json` (versions, settings, weights, simulation at the
  nominal values, the local fit and every random start).
- `results/comparison.json`, `results/report.md`: the gates applied, the
  parameter table, the cross-check of FungMod at COPASI's best point and the
  outcome in the plan's vocabulary.

Recorded 2026-10-05: outcome `copasi_improves`. Simulation agreement at
FungMod's optimum is 1.7e-8 of sigma; COPASI's best objective 3.9768 is 1.3
percent below FungMod's recorded 4.0307, and FungMod evaluates COPASI's point
to the same objective (relative difference 7e-9). See
`docs/gelain-cross-solver.md`.

```bash
pip install "fungmod[standards,copasi]"
python scripts/run_gelain_2020_petab_reproduction.py --output data/benchmarks/gelain_2020_petab/results
```
