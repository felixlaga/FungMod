# Gelain 2020 cellulose posterior-sampling study v1

Posterior sampling of the nine hydrolysis-candidate constants of the registry
case `trichoderma_harzianum_p49p11` x `cellulose_celufloc_200` on the compiled
core, jointly over the three Gelain 2020 cellulose loadings. Its product is an
identifiability report: which constants the published duplicate means identify
and which must stay ranges. It is retrospective, uses no replicate-level data
(the deposit holds none) and validates nothing.

- `plan.json`: registry case, observables, priors (the v2 joint-benchmark
  bounds, log-uniform), the assumed error model with its sampled scale
  multipliers, sampler settings, posterior-predictive grid and thinning.
- `results/bayesian_calibration.json`: settings, diagnostics, posterior
  summaries, identifiability verdicts with their declared thresholds, local
  Fisher information at the best sample, posterior predictive bands and the
  claim boundary.
- `results/posterior_samples.csv`: thinned post-burn-in samples in natural
  units (one column per constant and per noise-scale multiplier).
- `results/inputs.json`, `results/artifacts.json`, `results/report.md`:
  input digests, output digests and a human-readable summary table.

Observations come from `../gelain_2020_v2/observations.json` and the prior
bounds from `../gelain_2020_v2/plan.json`; the frozen least-squares fit of the
same candidate (`../gelain_2020_v2/results/full_fits/cellulose_hydrolysis_primary.json`)
only centers the initial walker ball. Run

    python scripts/run_gelain_2020_bayesian_calibration.py --output outputs/gelain-bayesian --processes 4

from the repository after installation; the run checkpoints its chain and
resumes from the checkpoint. See [the documentation](../../../docs/bayesian-calibration.md).
The registry records of the nine constants cite this artifact in their
provenance and keep their frozen point values.
