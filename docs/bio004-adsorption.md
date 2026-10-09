# Adsorbed-enzyme hydrolysis

BIO-004 M1 adds `adsorbed_enzyme_hydrolysis` for an explicitly declared dry-mass solid and one enzyme pool. Its maturity is **software_tested**, not biologically validated. The checked-in examples contain invented inputs for software verification only.

## Law and evidence

The single-site Langmuir relation follows Jäger et al. (2010), equation 1, [doi:10.1186/1754-6834-3-18](https://doi.org/10.1186/1754-6834-3-18). Imposing enzyme conservation gives:

```text
C = Gamma_max * S
E_bound = C * E_free / (Kd + E_free)
E_total = E_free + E_bound
rate = k_bound * E_bound
```

The implementation solves the positive quadratic root with enzyme depletion retained. Association input `K` is equivalent to `Kd = 1/K`; supply exactly one. Free and bound pools are recomputed as the solid declines, rather than assuming that free enzyme equals total enzyme.

The proportional bound-enzyme rate is a separately declared case assumption. The primary abstract of [Medve et al. (1998)](https://doi.org/10.1002/(SICI)1097-0290(19980905)59:5%3C621::AID-BIT13%3E3.0.CO;2-C) reports a linear relation for bound CBH I under the studied conditions, and a different response for EG II. This does not establish a universal activity law. Frozen law records are in `data/mechanism_sources/jaeger_2010_langmuir/` and `data/mechanism_sources/medve_1998_bound_activity/`; they import no biological constants. The latter record explicitly identifies its abstract-level evidence.

## User CSV inputs

Use the normal user-dataset directory with `user_dataset.yml`, `strains.csv`, `enzymes.csv`, `conditions.csv`, `substrates.csv`, and `kinetics.csv`. Custom enzyme classes additionally require `enzyme_classes.csv`.

In `substrates.csv`, explicitly set `physical_state=solid_polymer`, `amount_basis=dry_mass`, and the product and product yield. Put adsorption measurements in `kinetics.csv`, not as morphology columns in `substrates.csv`. Each case uses the usual strain, enzyme-class, substrate and condition identifiers.

| Quantity in `kinetics.csv` | Required units | Example protein basis |
| --- | --- | --- |
| `substrate_initial_concentration` | Dry solid mass / volume | `g/L` |
| `enzyme_concentration` | Enzyme amount / volume | `mg/L` |
| `binding_capacity` | Enzyme amount / dry solid mass | `mg/g` |
| `adsorption_constant` **or** `adsorption_dissociation_constant` | Reciprocal enzyme concentration **or** enzyme concentration | `L/mg` **or** `mg/L` |
| `bound_rate_constant` | Dry solid mass / enzyme amount / time | `g/mg/hour` |

Enzyme amount may use mass, moles, or an explicitly supported assay activity unit such as `FPU` or `BGU`. Every quantity in a case must use a compatible enzyme basis. No molecular weight or activity-to-protein conversion is inferred. For example, a molar preparation may use `umol/L`, `umol/g`, `L/umol`, and `g/umol/hour`; an activity preparation may use `FPU/L`, `FPU/g`, `L/FPU`, and `g/FPU/hour`.

Every input still needs its evidence type, method, and source. Estimated inputs require exploratory mode. A missing bound-rate constant remains an explicit parameter gap; there is no default. Association/dissociation constants must be positive and capacity/rate constants nonnegative. Missing or simultaneous `K` and `Kd`, dissolved substrates, incompatible units, mixed legacy Michaelis–Menten fields, and unconsumed morphology inputs are refused.

Complete runnable examples:

- `data/mechanism_examples/adsorption_film/`: synthetic low-capacity film, protein mass basis, association constant.
- `data/mechanism_examples/adsorption_chitin/`: synthetic high-capacity chitin-like material, enzyme molar basis, dissociation constant.
- `data/model_configs/toy_adsorbed_enzyme_hydrolysis.yml`: a configured synthetic model with analytic Jacobian and material-balance checks.

From the repository root:

```python
from fungal_model import load_user_dataset, virtual_experiment

dataset = load_user_dataset("data/mechanism_examples/adsorption_film")
study = virtual_experiment(
    fungi="strain", substrates="solid", environments="assay", user_data=dataset
)
result = study.simulate(
    mode="exploratory", n_samples=1, seed=7,
    output_dir="outputs/adsorption_film", quicklook=False,
)
```

The single sample above checks execution. It does not constitute calibrated uncertainty or empirical validation.

## Results and limits

Each output time has free enzyme, bound enzyme, total enzyme, bound fraction, an explicit `bound_fraction_defined` mask, and the residual `free + bound - total`. When total enzyme is zero, free enzyme, bound enzyme and rate are zero, while the fraction is undefined (`NaN` in memory, JSON `null` or a blank CSV value, with the mask false), not zero. The mask is exported as `0` for undefined and `1` for defined. They are exported as named derived quantities under the process identifier and appear in `time_series_long.csv` with corresponding enzyme roles. `conservation_diagnostics.csv` includes an algebraic enzyme-pool balance row in addition to configured substrate/product conservation rows. The algebraic residual checks the instantaneous partition even if another explicit process changes total enzyme.

This model assumes instantaneous equilibrium, one homogeneous reversible site population, fixed binding/activity constants, and a proportional rate from the bound pool. It does not predict adsorption transients, competitive binding among enzyme species, irreversible or nonproductive binding, crystallinity effects, diffusion, or substrate-specific activity without supporting input measurements. The user-data network route refuses competing adsorption pools because their shared-site allocation is not implemented.

The law is not directly exported as SBML by the current exporter; its unsupported-process error is explicit. Existing Michaelis–Menten and surface-catalysis routes remain separate and unchanged unless adsorption quantities are supplied.

Configured runs write process-scoped initial and final bound fractions and the
maximum absolute free-plus-bound-minus-total enzyme residual across saved times
to `mechanism_metrics.json` and `.csv`. A bound fraction is unknown when total
enzyme is zero; summary JSON contains an empty value with `status: unknown`,
not a numeric zero or NaN. User-table runs forward these metrics into their final
and across-sample summary tables. The residual is a numerical conservation
check, not empirical validation.
