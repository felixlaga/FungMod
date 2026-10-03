# Conserved fungal digestion and secretion

FungMod now has an opt-in, mechanistic feedback loop linking extracellular
digestion to resource-limited growth and protein secretion. This advances the
living-culture model: enzymes release assimilable nutrients, and nutrient uptake
supports further biomass and enzyme synthesis. The implementation conserves
elements and charge and exposes the cost of sending resources to secretion.

Its maturity is `exploratory_software_tested`. The time courses below use explicit
illustrative parameters, **not organism-calibrated degradation kinetics**. The
new empirical comparison tests a separate total-protein-output component. No
complete fungus, spatial morphology, or biological optimum is claimed.

## Implemented mechanism

`fungal_model.fungi.DegradingCulture` composes a `ResourceLimitedCulture` with
seven distinct dynamic pools: assimilable substrate S, biomass X, nitrogen N,
oxidant O, degradable substrate P, active enzyme E, and inactive protein I.
It integrates five material-balanced pathways:

1. Biomass synthesis, using the previously implemented respiratory growth yield.
2. Non-growth substrate maintenance, prioritized within uptake capacity.
3. Protein secretion, with its own sourced composition and synthesis reaction.
4. Enzyme-catalysed substrate conversion to assimilable product.
5. Inactivation, transferring active protein into a chemically identical inactive pool.

Every reaction must independently conserve all represented elements and charge.
Hydrolysis consumes P and produces S; any other exchanged species must be an
explicit reservoir. Protein synthesis consumes S, N and O and produces E; it
cannot create biomass or undeclared pools. Inactivation does not destroy matter.
These are the implemented boundaries of the present aerobic secretion closure;
anaerobic synthesis and arbitrary enzyme mixtures are not silently approximated.

Let uptake capacity be `a = qmax S/(KS+S) O/(KO+O)`, realized maintenance
`m = min(a, m_required)`, and available synthesis substrate per biomass
`b = max(a-m_required, 0) N/(KN+N)`. A supplied allocation fraction `f` gives:

```text
biomass synthesis extent = (1-f) YX b X
protein synthesis extent = f YE b X
maintenance extent       = m X
hydrolysis extent        = kcat E P/(KP+P)
inactivation extent      = kd E
```

`YX` and `YE` are formula-mole yields. Growth and secretion divide one substrate
budget; adding secretion never adds an unaccounted uptake flux. Their nitrogen
and oxygen costs follow the respective chemical balances. Different affinities
for different processes, oxygen storage and ATP accounting remain unresolved.
This is a supplied allocation hypothesis, not an identified regulatory network.

All seven pools undergo the configured well-mixed dilution. Feed S/N/O and feed P
are explicit; there is no external biomass/protein feed. Oxygen transfer is
`kLa (Ostar-O)`. Exported CO2, solvent water and buffered proton exchange are
tracked through explicit reservoirs. Reservoir concentrations, intracellular
pH and viability are not predictions. Biomass persists when maintenance becomes
unmet; that is reported as missing physiology, not survival or dormancy.

This API assumes accessible, homogeneous substrate kinetics. It does not infer
surface area, adsorption, retained solids, a growing hyphal network or pellets.
Tests exercise both polysaccharide/sugar/ammonium and materially different
polyester/hydroxyacid/nitrate chemistry without substrate branches in the model.

## API and outputs

The new public classes are `DegradingCulture` and `DegradingCultureTrajectory`.
Assembly requires explicit `MacrochemicalSpecies`, solved hydrolysis/secretion
balances, allocation, catalytic capacity, substrate half-saturation, enzyme
inactivation and feed concentration. All kinetic parameters require provenance.
Every initial pool must be supplied; no enzyme seed or soluble nutrient appears
implicitly. Without either seed enzyme or usable nutrient, digestion cannot
bootstrap itself. Active extracellular enzyme can continue digestion without
living biomass, which is a separate case from ongoing synthesis.

The research example can be run as follows; its function names and provenance
explicitly identify its assumptions:

```python
import numpy as np
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.research.degrading_culture_example import (
    illustrative_culture, illustrative_initial_state,
)

model = illustrative_culture(
    allocation=0.1, gas_transfer_per_h=20,
    catalytic_per_h=100, inactivation_per_h=0.01,
)
result = model.simulate(
    initial_state=illustrative_initial_state(nitrogen_mol_L=0.02),
    times=Q_(np.linspace(0, 120, 481), "h"),
    solver_settings=SolverSettings(
        method="BDF", rtol=1e-9, atol=1e-13, max_step=Q_(0.5, "h")
    ),
)
print(result.batch_degradation("polymer"))
print(result.diagnostics)
```

The result contains unit-bearing concentrations, pathway rates, cumulative
reaction/reservoir exchanges, cumulative boundary exchanges, unmet maintenance,
solver diagnostics and the complete model provenance. Batch summaries report
fraction removed and interpolated first-crossing threshold times. They reject
nonzero dilution because washout is not degradation. An unreached threshold is
`None`, not an invented extrapolation. Thresholds use the requested output grid,
not an event solve; the maximum output interval is reported.

`secretion_allocation` converts a supplied synthesized-protein/new-biomass mass
ratio to a substrate allocation fraction using **explicit** biomass/protein
formula masses and synthesis yields:

```text
f = (r MX/ME) / (YE/YX + r MX/ME)
```

Total measured extracellular protein cannot be substituted without resolving
composition, active fraction, loss/retention and the observation mapping. No
FPU, transcript count, spectrum count or protein mass is converted into active
enzyme by default. Calibration uncertainty remains unknown where unsupported.

## New primary data and honest comparison

[Jørgensen et al. (2009)](https://doi.org/10.1186/1471-2164-10-44), Table 1,
provides extracellular protein output for two *A. niger* strains grown on two
carbon sources at the same nominal growth rate. The CC BY 2.0 article XML and
all four physiological table rows are preserved with SHA-256 checksums in
`data/benchmarks/jorgensen_2009_secretion/`. Offline extraction preserves
verbatim text, units, reported SDs and significance markers. Maltose residuals
remain in the reported glucose-equivalent basis.

| Carbon source | Strain | Protein output, mg/(g dry biomass h), mean ± SD |
| --- | --- | --- |
| Xylose | AB94-85 | 0.68 ± 0.01 |
| Xylose | ABGT1026 | 0.72 ± 0.02 |
| Maltose | AB94-85 | 1.98 ± 0.28 |
| Maltose | ABGT1026 | 1.69 ± 0.24 |

Conditions are nominal growth/dilution 0.16/h, 30°C, pH 3, dissolved oxygen
above 40% air saturation and dispersed filamentous growth. Three culture runs
per strain were switched sequentially from xylose to maltose: four group means
summarize twelve steady states in **six culture runs**, not twelve independent
cultures. Published SDs are neither SEM nor confidence intervals. Raw replicate
values and cross-condition covariances are unavailable. These conditions and
the measurement basis are from the [primary article](https://pmc.ncbi.nlm.nih.gov/articles/PMC2639373/).

`research.secretion_benchmark` compares `qP = r * mu` with either one pooled
effective ratio or a separate ratio for each carbon source. Each prediction
holds out the target strain's **both** carbon-source conditions. Training uses
only the other strain. Carbon identity and nominal growth rate are supplied
predictors; held-out protein output never enters a fit. The source-conditioned
comparison has two coefficients versus one, and each coefficient uses one
training mean per fold. That exactly identifies a ratio at this growth rate,
with zero residual degrees of freedom for that coefficient; it does not
identify a growth-associated mechanism or a non-growth secretion intercept.

| Retrospective comparator | Held-out protein-output RMSE, mg/(g dry biomass h) |
| --- | --- |
| One pooled ratio | 0.586931 |
| Carbon-source-dependent ratios | 0.207002 |

The improvement is **64.7%** across four predictions in two strain folds.
It supports retaining carbon-source dependence as an explicit modelling input.
It is not independent laboratory validation, a demonstrated regulatory law,
or calibration of the active-enzyme degradation model. No SD-based likelihood,
confidence interval or significance claim is inferred. The entire integrated
trajectory remains illustrative; the AB strains do not inherit the prior
NW185 glucose respiratory fit or cross-substrate kinetic constants.

## Dynamic experiment and numerical evidence

The offline runner produces four figures, machine-readable trajectories,
holdout fits/splits, sensitivity assumptions, source hashes, dependency versions
and an artifact hash manifest. Its four scenarios compare coupled aerated
growth, low oxygen transfer, low nitrogen and zero secretion. Under the chosen
illustrative parameters, 90% polymer removal occurs at about 5.05, 9.17 and
5.71 h in the first three cases; no secretion and no initial enzyme gives no
polymer conversion. Oxygen/nitrogen limitation leaves much of the liberated
sugar unused, even though extracellular enzymes can continue hydrolysis.
These numbers are **not experimental forecasts**.

The 33-point allocation sweep shows faster digestion at increased allocation
but less final biomass over the tested interval. Nine explicitly supplied
enzyme-kinetic combinations give 90% removal times from 5.02 to 46.56 h.
That envelope is assumption sensitivity, not a confidence or credible interval.
It makes the missing kinetic measurements consequential and visible.

Maximum open atom/charge residual across the four scenarios is
`3.35e-15 mol/L`; maximum pool disagreement between BDF and a tighter Radau
reference is `3.01e-10 mol/L`. The enlarged sweep initially exposed a BDF
finite-difference perturbation overflow in states with no kinetic feedback.
Both culture APIs now provide piecewise analytic Jacobians, including exact
zero ledger columns. Independent finite differences test the derivatives;
four solvers test the coupled dynamics, and analytic inactivation/dilution
solutions test protein accounting. No trajectories are clipped and tolerances
are not relaxed. Tiny negative numerical residues within the documented
10-atol allowance remain visible, so raw removal fractions can exceed one
by roundoff. Such residues are not biological substrate production or loss.

## Thermodynamics and the next biological gaps

Atom/charge conservation is necessary but is not a complete energy budget.
The integrated dynamics deliberately report thermodynamics as unavailable until
complete, mutually compatible formation energies and activities exist for the
biomass, active/inactive proteins, substrates and reservoirs. No arbitrary
protein formation energies or entropy-maximization principle were supplied.
The existing macrochemical entropy API and closed detailed-balance free-energy
solver retain their own supported scopes. An open growing culture cannot be
treated as a closed mixture simply relaxing to equilibrium.

The recommended next task is to recover matched dynamic biomass, nutrient,
respiration and absolute protein measurements, then resolve active-protein
composition and loss before fitting regulation/storage. [Pakula et al.
(2016)](https://doi.org/10.1186/s13068-016-0547-5) supplies a relevant primary
study of protein-production load in *T. reesei*, with time-course cultivation
and protein-composition supplements. It motivates the resource cost but was
**not used as numerical validation in this release**. Its data require separate
intake, provenance and assay review. After these mappings, add hyphal tips,
branching and spatial transport with measured geometry; existing Cartesian
transport alone does not establish fungal morphology.

Other unresolved mechanisms include induction/repression, intracellular carbon
storage, multiple enzyme classes, adsorption, viability/death, recycling, pH,
organic-product secretion and ecological interactions. The present allocation
law is constant during a run and the evidence at one growth rate cannot identify
its dynamics. Full-fungus prediction therefore remains open.

## Reproduction and compatibility

From a development checkout:

```bash
MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python scripts/prepare_secretion_data.py --check
MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python scripts/run_degrading_culture_benchmark.py --output outputs/my-new-digestion-run
.venv/bin/python -m pytest -q tests/test_degrading_culture.py tests/test_secretion_benchmark.py tests/test_degrading_culture_benchmark.py tests/test_respiration.py
```

The destination must not already exist. Failed preview runs are not silently
overwritten or treated as completed evidence. The completed local run is in
`outputs/degrading-culture-2026-10-03-final/`, which is a generated, ignored
artifact directory. Source, extraction scripts and checksummed input data are
packaged; outputs are reproducible rather than bundled as defaults.

Scientific behavior impact: the new opt-in API introduces costed secretion,
digestion and inactivation, with explicit uncertainty and maturity. Existing
configured `VirtualExperiment` behavior, registry defaults and chemistry are
unchanged. The existing respiration API gains an analytic Jacobian and additive
Jacobian diagnostics; its mathematical rate law is unchanged, though numerical
roundoff and step choices may differ. No commits, remote publication or registry
promotion are part of this task. Software risk is moderate for a new coupled
API; scientific extrapolation risk remains high without matched measurements.

New tests cover material/charge budgets, materially different chemistry,
resource starvation, common uptake allocation, zero-secretion reduction,
analytic decay, solver agreement, threshold boundaries, unit/provenance guards,
Jacobian derivatives, preserved source SDs, checksum tampering, held-out-strain
leakage, the complete parameter sweep and preservation of previous artifacts.
The complete command/result ledger is maintained in `progress.md` under
`DIGESTION-001`.
