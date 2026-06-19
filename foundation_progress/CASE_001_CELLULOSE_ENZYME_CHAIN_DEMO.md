# CASE-001: Researcher-Facing Cellulose-Like Enzyme-Chain Virtual Experiment

## Goal

Expose the existing BIO-002 two-step enzyme-chain behavior through the
researcher-facing virtual-experiment API from names and aliases:

```text
generic cellulase source + cellulose film + 30 C pH 5 assay
-> solid cellulose-equivalent substrate -> cellobiose -> glucose
```

## Status

Status: `complete` for the scoped PR-02 API path once PR-02 is merged.

Researchers can use the top-level API without calling the lower-level BIO-002
demo helper:

```python
from fungal_model import virtual_experiment

study = virtual_experiment(
    fungi="generic cellulase source",
    substrates="cellulose film",
    environments="30 C pH 5 assay",
)

result = study.simulate(mode="exploratory", n_samples=1)
result.write_tables()
```

The path resolves to:

- `generic_cellulase_source`;
- `cellulose_film_generic`;
- `sabiork_reaction_618_selected_conditions`;
- `extracellular_enzyme_chain`;
- `bio002_extracellular_enzyme_chain_template`.

## Standard Outputs

The researcher-facing API writes the standard virtual-experiment output bundle,
including:

- `time_series_long.csv`;
- `final_metrics.csv`;
- `threshold_times.csv`;
- `summary_metrics.csv`;
- `limitations_table.csv`;
- `suggested_experiments.csv`;
- `output_manifest.json`;
- `virtual_experiment_summary.json`.

## Scientific Scope

CASE-001 reuses the existing BIO-002 registry/template records. It does not add
new biology, validation data, live source calls, or invented parameters.

The output is explicitly exploratory. It represents an enzyme-chain,
cellulose-equivalent virtual experiment only. It is not whole-fungus growth,
secretion, uptake, biomass, PET, lignin, full lignocellulose, organism-specific
physiology, or empirical validation.

## Evidence

Executable coverage:

- `tests/test_case001_researcher_enzyme_chain_virtual_experiment.py`;
- `tests/test_bio002_extracellular_enzyme_chain.py`;
- `tests/test_bio002_generic_chain_assembly.py`.
