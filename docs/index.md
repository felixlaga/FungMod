# FungMod

FungMod is a registry-backed, uncertainty-aware, mechanistic
virtual-experiment engine for fungal and enzyme-mediated substrate degradation.
It connects explicit mechanisms and sourced parameters to trajectories,
summary metrics, uncertainty summaries, provenance, limitations, and suggested
follow-up experiments.

```bash
python -m pip install fungmod
```

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
result.write_report(
    "outputs/reaction_618/report",
    include_html=True,
    include_index=True,
)
```

## What you get

- modelability preflight before execution;
- substrate and product trajectories;
- degradation and product-release rates;
- final metrics and threshold times;
- sampled parameters and trajectory quantiles;
- mechanism, assumption, provenance, and limitation tables;
- suggested experiments for missing or uncertain inputs;
- conservation, thermodynamic, and solver diagnostics when configured;
- CSV, JSON, Markdown, HTML, and quick-look artifacts with a manifest.

## What the labels mean

!!! warning "Software verification is not empirical validation"

    FungMod's bundled cases include exploratory and artificial framework
    examples. A successful run proves that the configured software contract
    executed. It does not prove organism-specific accuracy, calibration,
    experimental agreement, or whole-fungus physiology.

| Label | Meaning |
| --- | --- |
| `implemented` | Code exists for the stated scope. |
| `technically verified` | Automated tests cover the software contract. |
| `exploratory` | Outputs depend on explicit assumptions, priors, or scoped pilots. |
| `scientifically validated` | Empirical evidence supports the stated prediction claim. This is not a blanket label for FungMod. |
| `unsupported` | The mechanism or workflow must fail explicitly or remain future work. |

Start with the [installation guide](install.md), then run the
[quickstart](quickstart.md). The [capability map](capabilities.md) distinguishes
implemented behavior from current scientific boundaries.
