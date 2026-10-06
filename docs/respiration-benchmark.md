# Conserved fungal growth and respiration

FungMod now has an opt-in growth/respiration module that consumes substrate for
maintenance without automatically destroying biomass. Growth and maintenance
are separate reactions solved from elemental and charge conservation. A
well-mixed dynamic extension includes substrate, nitrogen, dissolved oxygen,
gas transfer, feed, dilution, and exported reaction products.

The module is `exploratory_software_tested`. The new empirical comparison tests
specific exchange rates conditional on known growth rates. It does not validate
whole-fungus dynamics, predict morphology, or identify intracellular metabolism.

## New primary data and their limits

The preserved CC-BY-4.0 XML articles and deterministic table extracts are in
`data/benchmarks/lameiras_respiration/`. The manifest records URLs, attribution,
retrieval date, byte counts, SHA-256 hashes, and extraction changes.

- [Lameiras, Heijnen and van Gulik (2015)](https://doi.org/10.1007/s11306-015-0781-z):
  four glucose-limited *Aspergillus niger* NW185 chemostat conditions at 30 °C,
  pH 3.0. Primary scoring uses the **unreconciled** Table 2 rates. Reconciled
  values are retained separately and never used for these fits. The paper's
  mean empirical biomass formula is C₁H₁.₈N₀.₁₂O₀.₆. Its CHNO representation
  omits minor ash, phosphorus and sulfur; neutral biomass is an explicit
  macrochemical convention.
- [Lameiras et al. (2017)](https://doi.org/10.1007/s00449-017-1854-3):
  six single-substrate batch references and eleven sequential six-substrate
  chemostat conditions, same strain/laboratory, 30 °C and pH 2.5. The conversion
  rates were reconciled using conservation. They can challenge transfer between
  regimes and expose gaps, but cannot independently validate the conservation
  equations used to construct them. Sequential dilution conditions share a
  culture and are not independent biological replicates.

Reported error bars are preserved verbatim and after unit conversion. Their
complete statistical meaning and covariance are not available here, so the
benchmark does not invent replicate observations, a likelihood, confidence
intervals, significance, or error-based fitting weights.

The 2017 Table 2 CO₂ cell at dilution 0.16/h reads `3.7 ± 3.9`, inconsistent
with its reported oxygen uptake and respiratory quotient. The TOC cell reads
`1.2 ± 1.9` and is also suspicious. Both remain verbatim and are quarantined
from scoring. No missing leading digits were guessed. Attempts to retrieve the
supplement failed: Springer hostname resolution returned `URLError: nodename
nor servname provided, or not known`; the Europe PMC supplementary-files request
timed out after 45 seconds. The successfully retrieved primary XML is enough for
the bounded comparisons below. Unverified supplemental contents are not used.

## Mechanism and numerical contract

`fungal_model.fungi.RespiratoryGrowthModel` uses the supplied true yield Y and
non-growth maintenance demand m in the Pirt relation:

```text
q_substrate = mu / Y + m
```

Growth is normalized to one mole of the empirical biomass formula, maintenance
to one mole of substrate. `MacrochemicalBalance` solves all other exchange
coefficients. All compositions, charges, parameters and mechanism assumptions
need explicit provenance. A yield in Cmol biomass/mol glucose may exceed one;
it is not a mass fraction. No named-organism branches enter generic chemistry.

For the declared 2015 CHNO formula and complete oxidation, the exchange law
implies qCO₂ = 6qS − μ and qO₂ = 6qS − 1.06μ. These equations omit chemically
unresolved excreted TOC. A carbon residual is useful evidence of that omission;
assigning an oxygen demand or Gibbs energy to unknown TOC would be invented
chemistry. Oxygen and CO₂ observations are never fitted in the primary test.

`ResourceLimitedCulture` adds this **explicit exploratory closure**:

```text
capacity = qmax S/(Ks + S) O/(Ko + O)
maintenance = min(m, capacity)
mu = Y max(capacity - m, 0) N/(Kn + N)
actual substrate uptake = maintenance + mu/Y
```

This maintenance-first allocation and multiplicative resource limitation are
assumptions. The literature basis is the
[Pirt maintenance relation](https://doi.org/10.1098/rspb.1965.0069) and
[Monod saturation form](https://doi.org/10.1146/annurev.mi.03.100149.002103), not
an experimentally established regulatory law for all fungi. Under nitrogen
limitation, unused uptake capacity is not consumed. Missing substrate or
oxidant stops both pathways. Unmet maintenance is reported, **not converted into
an inferred death, dormancy or viability state**. Without a death mechanism,
starved biomass remains; this limits long starvation predictions.

Batch and chemostat operation use dC/dt = reaction exchange + D(Cfeed − C),
plus kLa(O* − O) for oxygen. A biomass-free feed is required. Every other
species must explicitly belong to a reservoir: e.g. CO₂ export, solvent water
or buffered protons. Reservoir concentrations, pH and speciation are not outputs.
Integrated reaction extents and boundary exchanges supply an open-system atom
and charge ledger. Dissolved oxygen is a dynamic state in this API.

The shared `SolverSettings` controls integration. Named tolerances must cover
the four pool names, `extent:growth`, `extent:maintenance`, and each
`boundary:<pool-name>`, all in amount/volume units. Negative solver trial states
use a documented zero extension of the constitutive law; returned trajectories
are never clipped. Returned pool values below minus ten absolute tolerances
raise `IntegrationError`; tiny numerical roundoff remains visible.

The same closure is available on the compiled process core:
`compiled_processes()` returns growth and maintenance as generic
`resource_limited_growth` / `resource_limited_maintenance` processes carrying
the solved pathways' dynamic-pool stoichiometry and extent ledgers, plus a
`dilution_exchange` per pool and a `gas_transfer` for the oxidant, each with a
boundary ledger; `compiled_parameters()` restates the feed as parameters;
`simulate_compiled()` integrates them and returns the same `CultureTrajectory`
with `diagnostics["engine"]` naming the path. `simulate` keeps the native
right-hand side for its analytic piecewise Jacobian; the two agree to 1e-6
relative at tight tolerances (`tests/test_culture_processes.py`).

Entropy production is available through `RespiratoryGrowthModel.entropy_production`
only with complete sourced formation Gibbs energies and declared conditions.
Each operating pathway must produce nonnegative entropy; favorable maintenance
cannot hide uphill growth. This uses the declared energies without inventing
activity, pH or temperature corrections. The new fungal dataset does **not**
supply these energies, so no empirical fungal entropy or heat curve is emitted.
Thermodynamics constrains a supplied conversion and does not predict its rate.

## Retrospective holdout results

Each of the four dilution conditions is omitted from fitting in turn. The
other three unreconciled glucose-uptake means fit either a one-parameter
growth-only hypothesis or two-parameter growth-plus-maintenance hypothesis by
unweighted nonnegative least squares. Predictions use nominal μ = D; growth-rate
uncertainty, death and biomass retention are not inferred.

| Held-out observable | Growth only RMSE | Growth + maintenance RMSE | Reduction |
| --- | ---: | ---: | ---: |
| Glucose uptake | 1.556 | 0.386 | 75.2% |
| Oxygen uptake | 21.524 | 16.464 | 23.5% |
| CO₂ release | 12.995 | 8.563 | 34.1% |

All RMSE units are mmol species/(Cmol biomass·h). These comparisons are against
an explicit growth-only benchmark, not a claim that every previous FungMod
model improved. Twelve scored values per model comprise only four conditions;
the three observables are not twelve independent experiments.

The full-data point fit gives Y = 3.656 Cmol biomass/mol glucose and
m = 2.391 mmol glucose/(Cmol biomass·h). It is used only for the separately
labelled external challenge and exploratory dynamic examples. It is not reused
in any holdout. Parameter uncertainty remains unknown.

An exhaustive 256-scenario perturbation varies each dilution and uptake mean
by plus/minus its reported error. This is a sensitivity exercise, not a
confidence interval. Many fits reach zero maintenance; improved point prediction
does not establish a precisely known nonzero maintenance demand. Some unconstrained
fits require oxygen production or CO₂ uptake in the growth balance. They are
retained and flagged, and excluded only from the separately labelled aerobic
parameter envelope. No Gibbs feasibility is asserted without energies.

Freezing the 2015 parameters and composition for the 2017 glucose batch reference
overpredicts uptake by **16.4%**, oxygen consumption by **41.4%**, and CO₂ release
by **50.1%**. This is a failed broad-transfer challenge, not a successful external
validation. Different pH, cultivation regime and possible biomass composition
changes confound interpretation. The six-substrate data further show that uptake
allocation changes with dilution. The present single-substrate closure cannot
explain that regulation.

## Reproduce and inspect

```bash
python scripts/prepare_respiration_data.py --check
MPLCONFIGDIR=/tmp/fungmod-mpl python scripts/run_respiration_benchmark.py \
  --output outputs/respiration-expansion-local
python -m pytest tests/test_respiration.py tests/test_respiration_benchmark.py
```

The output directory must be empty. The runner writes four figures, frozen
training-only holdout predictions, the external challenge, all sensitivity
scenarios, dynamic trajectories, solver/conservation diagnostics, full parameter
provenance, environment versions and source/artifact hashes. The three dynamic
scenarios explicitly label their qmax, affinities, transfer rates and initial
conditions as illustrative assumptions. They are not experimental trajectories.

The low-level rate API can be used directly with the preserved study:

```python
from fungal_model.core.units import Q_
from fungal_model.research.respiration_benchmark import (
    fit_pirt, lameiras_glucose_model, load_respiration_data,
)

data = load_respiration_data()  # validates source and extract hashes
training = data["lameiras_2015"]["records"][:3]
fit = fit_pirt(
    growth_rates=Q_([r["dilution_per_h"] for r in training], "1/h"),
    substrate_uptake=Q_([
        r["unreconciled"]["substrate_uptake"]["value"] for r in training
    ], "1/h"),
    condition_ids=[r["id"] for r in training],
    source="Lameiras et al. 2015, Table 2, unreconciled rates",
    include_maintenance=True,
)
model = lameiras_glucose_model(fit, data)
exchange = model.specific_exchange(Q_(0.205, "1/h"))
print(exchange)  # signed mol species/(Cmol biomass h); uptake is negative
```

## Compatibility and next experiments

This is an additive advanced API. Existing `FungalCouplingModel` equations,
registry records, configured workflows, defaults and previous solver/benchmark
work are preserved. Existing active-to-inactive biomass maintenance remains
available under its documented interpretation. Automatically replacing it with
substrate respiration would change the meaning of existing models and could
double-count enzyme secretion costs; no such substitution is made.

Software tests cover independent chemical stoichiometry, charged ammonium and
a materially different ethanol/nitrate case, all four main solvers, limiting
resources, analytic sterile chemostat/gas-transfer solutions, washout, open
conservation, unit conversions, provenance/unknown guards, entropy requirements,
source checksums, exact extraction and training-only fits.

The recommended next experiment is a matched dynamic culture series measuring
residual sugars, biomass elemental composition, viable/total biomass, dissolved
oxygen, gas fluxes, nitrogen and secreted organic carbon under controlled pH.
Raw replicate uncertainties and covariance should be retained. These measurements
can separate transport capacity, changing yield, carbon secretion and starvation
responses before coupling respiration to enzyme secretion and spatial hyphal
growth. Risk is moderate for scientific interpretation, low for backward
compatibility because the new module is opt-in.
