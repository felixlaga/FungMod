# Gelain 2020 model-criticism study v1

A preregistered comparison of explicit mechanisms added to the registry
hydrolysis candidate (`trichoderma_harzianum_p49p11` x `cellulose_celufloc_200`)
on the three Gelain 2020 cellulose loadings. It answers one question: which
mechanism reduces the biomass/cellulose misfit that BAYES-001 found (shared
noise multiplier 2.25 at the assumed 10% error), and which of its parameters do
the published duplicate means identify. It is retrospective model criticism on
data that already informed v1, v2 and BAYES-001; it is not blind, not
independent and validates no biology.

- `plan.json`: the frozen plan. Data digests, the four models (M0 baseline, M1
  induction state, M2 soluble product pool with Monod uptake and product
  inhibition, M3 conversion-dependent accessibility), every parameter with its
  bounds and units, the shared error model, stage A (least-squares
  whole-condition holdouts, complexity screen, profiles), stage B (posterior
  sampling, identifiability, posterior predictive coverage), the decision rules
  R1 to R4, the outcome vocabulary, the claims excluded and the amendment rule.
  Frozen on 2026-10-05 with SHA-256 `6849c8b3355d7c2f0906e8be0a3c18bab1b5c54926289573fd4e6090dc42eb86`;
  `tests/test_gelain_criticism_plan.py` pins it.
- `results/stage_a/`: recorded 2026-10-05 under the previous plan digest
  (amendment 2 added only the walker rule afterwards)
  (`inputs.json`, per-model `full_fit_*.json`, `folds_*.json`, frozen held-out
  predictions, `comparison.json`, `report.md`). Outcome: no addition passes the
  R1 screen; M1 and M3 are not supported; M2 improves pooled held-out error by
  23 percent but worsens biomass by 31 percent, above the plan's 10 percent
  allowance, so it is not supported under R1 either. See
  `docs/gelain-model-criticism.md`.
- `results/stage_b/<model>/`: all-condition posteriors as they complete
  (`bayesian_calibration.json`, thinned `posterior_samples.csv`,
  `coverage.json`, `verdicts.json` with R1 to R3 and the outcome,
  `report.md`, `inputs.json`, `artifacts.json`). M2 recorded 2026-10-05: not
  converged by the declared rule, so its verdicts are provisional; R2 and R3
  fail (multiplier [1.65, 2.87]; `mu`, `Ks`, `Ki` prior dominated, `P0`
  bounded below only); outcome not supported (fails R1). M1 recorded
  2026-10-05: not converged, provisional; R2 fails (multiplier [1.87, 2.53]),
  R3 passes (`kz_loss` weakly identified); outcome not supported (fails R1).
  M3 follows.

What exists today for each model: M0 is the registry case; M1 and M2 are
compositions of existing generic processes (proportional synthesis, first
order, enzyme-explicit Michaelis-Menten with product maps, the product
inhibition modifier) that need new exploratory case-template variants; M3
needs one new generic rate modifier (Kadam 2004 substrate reactivity with an
exponent) with provenance and a non-cellulose test. No fit, sample or score may
run under this plan before those pieces exist and the plan digest is cited.
