# Gelain 2020 cross-solver reproduction v1

Does an independent simulator and optimiser (COPASI) reproduce FungMod's
all-condition least-squares optimum of the registry hydrolysis candidate
(`trichoderma_harzianum_p49p11` x `cellulose_celufloc_200`) on the three
Gelain 2020 cellulose loadings when both work on the same PEtab problem?
Retrospective: the data already informed the fit being reproduced. It
validates no biology.

- `plan.json`: the frozen plan (SHA-256
  `11dfe15850b80c3217dd821547613365cb77c88d39a007f65cd954ae1706d320`, pinned
  by `tests/test_gelain_petab.py`): sources and digests, the objective, the
  COPASI settings, the gates, the outcome vocabulary, the excluded claims and
  the amendment rule. A first dated amendment replaced the reference-fit
  digest after the criticism plan's amendment 3 re-ran stage A; a second
  (2026-10-06) re-pinned the criticism plan after its amendment 4, which
  changed only stage B, so the recorded results remain valid.
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

Recorded 2026-10-05 (second run, after the criticism plan's amendment 3):
outcome `reproduced`. Simulation agreement at FungMod's optimum is 1.6e-8 of
sigma; COPASI's local fit reaches 3.9760718 against FungMod's 3.9760719
(relative difference 2.5e-8), every parameter agrees to better than 1e-4, and
no random start goes lower. The first run (plan `a0f8abe9...`) recorded
`copasi_improves` (COPASI 1.3 percent below FungMod's then optimum); it found
the missing finite-difference step in FungMod's stage A optimiser. See
`docs/gelain-cross-solver.md`.

```bash
pip install "fungmod[standards,copasi]"
python scripts/run_gelain_2020_petab_reproduction.py --output data/benchmarks/gelain_2020_petab/results
```
