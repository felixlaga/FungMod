# Full example notebooks

The release includes three in-depth notebooks that can be executed from an
installed wheel or a repository checkout.

Install notebook support:

```bash
python -m pip install "fungmod[notebooks]"
```

## Zero to a complete report

[`20_zero_to_complete_virtual_experiment.ipynb`](https://github.com/felixlaga/FungMod/blob/main/notebooks/examples/20_zero_to_complete_virtual_experiment.ipynb)

This notebook covers:

- installed-package import and version;
- researcher-facing aliases and an environment grid;
- modelability preflight;
- exploratory ensemble simulation;
- mechanisms, assumptions, metrics, and threshold times;
- uncertainty and comparison guardrails;
- provenance, limitations, and suggested experiments;
- quick-look figures, Markdown/HTML report, index, and manifest verification.

It uses the scoped cellulose-equivalent enzyme-chain case. It does not claim
whole-fungus physiology or empirical validation.

## Advanced capabilities

[`21_advanced_capabilities.ipynb`](https://github.com/felixlaga/FungMod/blob/main/notebooks/examples/21_advanced_capabilities.ipynb)

This notebook covers:

- frozen, checksummed SABIO-RK source evidence;
- review-only proposal output;
- uncertainty-aware Reaction 618 simulation;
- provenance-bound competitive and substrate-inhibition benchmark laws;
- explicit dynamic reaction quotients and Gibbs energy;
- electron-balance binding and solver-time rate blocking;
- conservation, static entropy-rate, solver, and thermodynamic diagnostics;
- advanced manifest verification.

The inhibition and thermodynamic inputs are artificial framework benchmarks,
not biological evidence.

## Five fungal beta-glucosidases on cellobiose

[`22_five_fungal_beta_glucosidases.ipynb`](https://github.com/felixlaga/FungMod/blob/main/notebooks/examples/22_five_fungal_beta_glucosidases.ipynb)

This notebook covers:

- five literature-reported purified fungal beta-glucosidase parameter sets;
- matched 50 °C, pH 5 cellobiose scenarios at one explicit 10 nM enzyme dose;
- homogeneous Michaelis-Menten kinetics with dynamic competitive glucose
  inhibition;
- two glucose equivalents released per cellobiose consumed;
- paired inhibition-free counterfactuals;
- substrate, product, rate, threshold, and conditional-conversion summaries;
- provenance, assumptions, conservation, solver diagnostics, and manifests.

The parameter rows are attributed to
[Bohlin et al. (2010)](https://doi.org/10.1002/bit.22885) through the open
[Table 5 transcription](https://pmc.ncbi.nlm.nih.gov/articles/PMC3726394/).
The notebook models purified enzymes labelled by their fungal source. It does
not model organism growth, secretion, uptake, transport, biomass,
transglycosylation, or pathogenicity, and it blocks organism ranking. The
standardized dose and starting concentrations are explicit exploratory
scenario assumptions, not values attributed to the source paper.

## Run locally

From a clone:

```bash
jupyter lab notebooks/examples/
```

For non-interactive execution:

```bash
FUNGMOD_NOTEBOOK_OUTPUT_ROOT=outputs/notebooks \
  jupyter nbconvert \
  --to notebook \
  --execute notebooks/examples/20_zero_to_complete_virtual_experiment.ipynb \
  --output /tmp/fungmod-zero-to-results.ipynb
```

The notebooks honor:

- `FUNGMOD_NOTEBOOK_OUTPUT_ROOT` for generated artifacts;
- `FUNGMOD_NOTEBOOK_SAMPLES` for ensemble size in notebooks 20 and 21.

Automated tests use small sample counts; researchers can increase the count
when the explicit input distributions and compute budget justify it.
