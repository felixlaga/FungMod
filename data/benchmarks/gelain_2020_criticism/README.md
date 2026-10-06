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
  Frozen on 2026-10-05; current SHA-256
  `9897ab11026a81794a27f512264afa5ed70f341f23f1d73264076956497d43d7` after
  three dated amendments (machine-readable error-model fields; the walker
  rule; the stage A optimiser settings added after PETAB-001 found the
  optimiser stopping above the minimum: log-space difference step 1e-3,
  tolerances 1e-10, up to three restarts). `tests/test_gelain_criticism_plan.py`
  pins it.
- `results/stage_a/`: re-recorded 2026-10-05 under amendment 3 (the
  declared optimiser; `inputs.json` records the settings, every fit records
  its starts and restarts; per-model `full_fit_*.json`, `folds_*.json`,
  frozen held-out predictions, `profiles_primary.json` for the model that
  passed, `comparison.json`, `report.md`). Outcome: M2 passes the R1 screen in
  both scenarios (pooled held-out error 23 percent lower than M0 in the
  primary scenario and 26 percent lower under the correlated assumption, with
  every observable better); M1 and M3 fail it (no pooled improvement;
  substrate worse). The first stage A run (plan `9bb36f8d...`, before the
  optimiser was declared) had recorded M2 as failing R1 because biomass
  worsened by 31 percent; that was the stalled optimiser, not the mechanism.
  See `docs/gelain-model-criticism.md`.
- `results/stage_b/<model>/`: all-condition posteriors as they complete
  (`bayesian_calibration.json`, thinned `posterior_samples.csv`,
  `coverage.json`, `verdicts.json` with R1 to R3 and the outcome,
  `report.md`, `inputs.json`, `artifacts.json`). M2 recorded 2026-10-05: not
  converged by the declared rule, so its verdicts are provisional; R2 and R3
  fail (multiplier [1.65, 2.87]; `mu`, `Ks`, `Ki` prior dominated, `P0`
  bounded below only); outcome improves fit but unidentified (R1, not R3)
  after its R1 component was refreshed against the amendment 3 stage A
  screen (the chain itself, centred on the first stage A fit, was not
  re-run). M1 recorded
  2026-10-05: not converged, provisional; R2 fails (multiplier [1.87, 2.53]),
  R3 passes (`kz_loss` weakly identified); outcome not supported (fails R1).
  M3 recorded 2026-10-05: not converged, provisional; R2 fails (multiplier
  [1.94, 2.62]), R3 fails (`n` bounded above only); outcome not supported
  (fails R1). M0 reuses BAYES-001.

What exists today for each model: M0 is the registry case; M1 and M2 are
compositions of existing generic processes (proportional synthesis, first
order, enzyme-explicit Michaelis-Menten with product maps, the product
inhibition modifier) that need new exploratory case-template variants; M3
needs one new generic rate modifier (Kadam 2004 substrate reactivity with an
exponent) with provenance and a non-cellulose test. No fit, sample or score may
run under this plan before those pieces exist and the plan digest is cited.
