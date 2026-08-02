# Scientific user guide

This guide is for researchers who want to *use* FungMod to run virtual
experiments and interpret the results. It is deliberately concise and separate
from the internal development ledger (`progress.md`) and roadmap documents. For
exact function signatures, see the [API reference](api.md).

!!! warning "Software verification is not empirical validation"

    A successful FungMod run proves that a configured software contract executed.
    It does **not** prove organism-specific accuracy, calibration, experimental
    agreement, or whole-fungus physiology. Read [What the labels
    mean](#maturity-labels) before drawing scientific conclusions.

## 1. What FungMod is

FungMod is a registry-backed, uncertainty-aware, mechanistic virtual-experiment
engine for fungal and enzyme-mediated substrate degradation. It connects:

- **explicit mechanisms** (kinetics, thermodynamics, transport, modifiers),
- **provenance-backed parameters** drawn from a curated registry, and
- **numerical solvers**

to produce trajectories, summary metrics, uncertainty summaries, provenance and
assumption tables, limitations, and suggested follow-up experiments.

Its design principle is to **fail honestly**: physical quantities carry units,
parameters require provenance before a scientific simulation runs, missing values
stay missing rather than being guessed, and validation failures are returned as
results rather than hidden.

## 2. Installation

```bash
python -m pip install fungmod
```

FungMod supports Python 3.11–3.13 on Linux, macOS, and Windows. For a pinned or
containerised environment, see [Reproducibility](#9-reproducibility). Full install
options are in the [installation guide](install.md).

## 3. Core concepts

| Concept | Meaning |
| --- | --- |
| **Virtual experiment** | A study assembled from a fungus/enzyme source, one or more substrates, and one or more environments. |
| **Registry** | The curated, provenance-labelled store of entities and parameters that inputs are resolved against. |
| **Provenance** | The traceable source attached to every scientific parameter. Simulations refuse to run scientifically on unsourced parameters. |
| **Maturity label** | An honesty tag on every capability and output (see below). |
| **Configured model** | A fully specified model defined by a YAML config, run end to end without the virtual-experiment resolver. |

### Maturity labels

| Label | Meaning |
| --- | --- |
| `implemented` | Code exists for the stated scope. |
| `technically verified` | Automated tests cover the software contract. |
| `exploratory` | Outputs depend on explicit assumptions, priors, or scoped pilots. |
| `scientifically validated` | Empirical evidence supports the stated prediction claim. This is **not** a blanket label for FungMod. |
| `unsupported` | The mechanism or workflow must fail explicitly or remain future work. |

## 4. Your first virtual experiment

```python
import fungmod as fm

study = fm.virtual_experiment(
    fungi="beta-glucosidase source",
    substrates="cellobiose",
    environments="SABIO-RK Reaction 618 selected assay conditions",
)

result = study.simulate(
    mode="exploratory",
    n_samples=32,
    seed=618,
    output_dir="outputs/reaction_618",
)

# A machine-readable summary of the final state across sampled cases.
print(result.final_metrics())

# Write a full CSV/JSON/Markdown/HTML report bundle with an index.
result.write_report(
    "outputs/reaction_618/report",
    include_html=True,
    include_index=True,
)
```

Setting `seed` makes the run reproducible: the same inputs and seed produce the
same numbers on any machine.

## 5. Understanding the outputs

A report bundle contains:

- **Trajectories** — substrate and product concentrations over time.
- **Rates and threshold times** — degradation and product-release rates, and the
  times at which thresholds are crossed.
- **Final metrics** — end-state values per sampled case.
- **Uncertainty summaries** — sampled parameters and trajectory quantiles.
- **Mechanism, assumption, provenance, and limitation tables** — what was
  assumed and where every number came from.
- **Suggested experiments** — for missing or uncertain inputs.
- **Diagnostics** — conservation, thermodynamic, and solver checks when
  configured.
- **A manifest** tying the artifacts together.

Always read the limitation and provenance tables alongside the metrics. The
[Outputs and artifacts](concepts/outputs.md) page describes the file layout.

## 6. Configured models

When you have a fully specified model rather than a registry lookup, run it from
a YAML config:

```python
import fungmod as fm

report = fm.run_configured_model(
    fm.example_data_path("model_configs/showcase_dynamic_thermodynamics.yml"),
    output_dir="outputs/configured_showcase",
)
print(report.solver_metadata["success"])
```

See [Configured models](configured-models.md) for the config schema and bundled
examples.

## 7. Uncertainty, sensitivity, and calibration

Advanced analyses are available as canonical `fungmod` subpackages:

```python
from fungmod import uncertainty, calibration, transport
```

- **Uncertainty** (`fungmod.uncertainty`): Monte Carlo propagation
  (`run_monte_carlo`, `ParameterUncertaintySpec`), local sensitivity
  (`local_sensitivity`), and independent-input variance-based **global
  sensitivity** (`global_sensitivity`, Saltelli first-order and Jansen
  total-order estimators).
- **Calibration** (`fungmod.calibration`): least-squares fitting
  (`fit_least_squares`, `FittableParameter`) and a publication-oriented
  **calibration evidence audit** (`audit_calibration_evidence`) whose software
  pass never authorizes a publication claim.
- **Transport** (`fungmod.transport`): 1D and uniform-Cartesian 2D/3D
  finite-volume reaction–diffusion engines.

Exact signatures and options are in the [API reference](api.md). See also the
[calibration evidence](calibration-evidence.md) page.

## 8. Sourcing and curating parameters

FungMod separates *proposing* candidate parameters from *promoting* them into the
trusted registry, with cryptographic curator signatures in between:

```python
import fungmod as fm

proposal = fm.source_proposal(provider="sabiork", reaction_id="618")
print(len(proposal.reaction_records))
```

The advanced curation and registry-promotion workflow
(`review_source_proposal`, `sign_curation_bundle`, `plan_registry_promotion`,
`apply_registry_promotion`) is documented in the project README under
"Propose Source Records".

## 9. Reproducibility

FungMod ships a single-command, deterministic reproduction of its headline
artifacts:

```bash
# from a repository checkout
python scripts/reproduce.py          # full reproduction
python scripts/reproduce.py --quick  # fast smoke
# or:
make reproduce
```

This regenerates the Reaction 618 virtual experiment, the configured
dynamic-thermodynamics showcase, and the literature comparison, writing
everything under `outputs/reproduction/` with a machine-readable summary.

For a pinned dependency environment, install from the lock file:

```bash
python -m pip install -r requirements-lock.txt
python -m pip install . --no-deps
```

For a fully isolated environment, use the container:

```bash
docker build -t fungmod .
docker run --rm -v "$PWD/outputs:/opt/fungmod/outputs" fungmod
```

## 10. Citing FungMod

If you use FungMod in your research, please cite it. See [Citing
FungMod](citing.md) for the recommended citation, the machine-readable
`CITATION.cff`, and the archived DOI.

## 11. Getting help and contributing

- Usage questions: [GitHub Discussions](https://github.com/felixlaga/FungMod/discussions)
  (see [SUPPORT.md](https://github.com/felixlaga/FungMod/blob/main/SUPPORT.md)).
- Bugs and feature requests: the
  [issue chooser](https://github.com/felixlaga/FungMod/issues/new/choose).
- Contributing code, docs, or data:
  [CONTRIBUTING.md](https://github.com/felixlaga/FungMod/blob/main/CONTRIBUTING.md),
  including the scientific-contribution rules.
