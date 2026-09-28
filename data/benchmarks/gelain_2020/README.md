# Gelain 2020 culture benchmark evidence

See `docs/gelain-culture-benchmark.md` at the repository root for the model,
observation mapping, source limitations and interpretation.

- `plan.json`: fixed retrospective study design, bounds, seeds and loss choices.
- `source_parameters.json`: full precision all-condition published fit constants.
- `source_simulations.csv`: deposited **simulations**, not experimental data.
  Source workbooks, archive, license and hashes live under
  `data/experiments/source_intake/gelain_2020/`.
- `thesis_review.json`: recovered assay details and source selection history;
  reference metadata only. The full thesis is not bundled.
- `results/`: recorded run, numerical results and figures, input/code hashes,
  every optimizer start, solver checks and frozen predictions before scoring.

Experimental biomass/substrate observations remain exclusively in the reviewed
ExperimentDataset records under `data/experiments/literature/gelain_2020_t_harzianum/`.
No individual duplicates or complete SD arrays were recovered. Results are
exploratory software-tested evidence; the apparent growth/loss parameters are
not independently validated strain constants. Do not train on the simulation
reference, pool source-fit scores with holdout scores, or relabel normalization
weights as measurement uncertainty.

From the repository root, reproduce offline into a new empty directory:

```sh
python scripts/prepare_public_experimental_data.py --check
python scripts/run_gelain_2020_culture_benchmark.py --output outputs/gelain-new-run
```

The preserved `results/` directory is an intentional snapshot. Subsequent model
changes should use a new benchmark version and retain these failed predictions.
