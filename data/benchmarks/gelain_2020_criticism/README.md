# Gelain 2020 model-criticism study v1 (plan frozen, not run)

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
  Frozen on 2026-10-05 with SHA-256 `8b368ac8d6b683f688907c0bb38d4b5a3d2730d29a7b8ca4c37d92db1e187c7e`;
  `tests/test_gelain_criticism_plan.py` pins it.
- `results/`: absent until the study runs. Every run must cite this plan's
  digest and record any amendment first.

What exists today for each model: M0 is the registry case; M1 and M2 are
compositions of existing generic processes (proportional synthesis, first
order, enzyme-explicit Michaelis-Menten with product maps, the product
inhibition modifier) that need new exploratory case-template variants; M3
needs one new generic rate modifier (Kadam 2004 substrate reactivity with an
exponent) with provenance and a non-cellulose test. No fit, sample or score may
run under this plan before those pieces exist and the plan digest is cited.
