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
  `7952e010b55f55887e22025c22a192fb1c7f2eb3f61fc130b71af2a019a98672` after
  four dated amendments (machine-readable error-model fields; the walker
  rule; the stage A optimiser settings added after PETAB-001 found the
  optimiser stopping above the minimum: log-space difference step 1e-3,
  tolerances 1e-10, up to three restarts; the M2 all-condition sampler
  override, the holdout sampler and its output convention, and the 12 hour
  cap for that chain). `tests/test_gelain_criticism_plan.py` pins it.
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
  `report.md`, `inputs.json`, `artifacts.json`). M2 re-recorded 2026-10-06
  under amendment 4 (centred on the converged stage A fit, 36000 steps,
  8000 burn-in): still not converged by the declared rule (autocorrelation
  times 824 to 1393 steps against 28000 post-burn-in), so its verdicts are
  provisional; R2 and R3 fail (multiplier [1.63, 2.23]; `mu` and `P0`
  bounded below only, `Ks` and `Ki` prior dominated); outcome improves fit
  but unidentified (R1, not R3). The first M2 chain (2026-10-05, centred on
  the superseded fit, multiplier [1.65, 2.87]) is summarised in the ledger
  (CRIT-002, CRIT-003). `holdout_<condition>/` under the M2 folder: the
  plan's per-fold posteriors (8000 steps, 2000 burn-in, likelihood on the
  two training loadings, centred on the fold's stage A fit) with the
  fitted-data and the held-out coverage kept apart (recorded 2026-10-06: held-out coverage 22/32, 69 percent for 10 g/L, 32/32, 100 percent for 20 g/L, 19/32, 59 percent for 30 g/L; no fold chain converged).
  M1 recorded
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
