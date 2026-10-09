# Explicit chain scission and peroxide oxidation

BIO-004 supplies two optional mechanisms with native compiled rates, analytic
state derivatives, explicit material ledgers, and source records. Their shipped
examples are synthetic software benchmarks. They are not fitted constants,
validated predictions, or evidence that any named enzyme preparation has the
required activity.

## Chain scission and structural synergy (M5)

`chain_endo_scission` and `chain_exo_scission` represent a finite population of
chains, `G_i`, where `i` is the degree of polymerization. Every population from
`G_1` through a stated maximum must be supplied, including explicit zeros.
Concentrations count chains; `sum(i G_i)` counts monomer equivalents.

The source is [Niu, Shah and Kontoravdi (2016), Eqs. 12–20](https://doi.org/10.1016/j.bej.2015.10.017),
with equation locations, assumptions and limits frozen in
`data/mechanism_sources/niu2016_chain_scission/source.yml`.
For the source convention, solid chains have length at least four and exo
cleavage releases a dimer. For each solid parent `i` and each internal position
`j`, the implemented endo channel is:

```text
G_i -> G_j + G_(i-j)
r_endo(i,j) = kcat_endo E_endo F_a G_i /
              [Km_endo + F_a sum_(n>=4)((n-1) G_n)]
```

All `i-1` cut positions are enumerated. Symmetric positions are separate
channels; a central cut produces two copies of the same fragment. Exo channels
are:

```text
G_i -> G_2 + G_(i-2)
r_exo(i) = kcat_exo E_exo F_a G_i /
           [Km_exo + F_a sum_(n>=4)(G_n)]
```

This preserves the source's finite-chain accounting rather than assigning an
unsupported exhaustion coefficient to an aggregated chain-end state. The
reported `chain_ends` observable is one exo-eligible end per solid chain,
`sum_(i>=4) G_i`; it is not the number of both physical ends or a measured
surface-accessible end density. Endo cuts can create eligible chains, and exo
cuts exhaust a chain when its residual fragment leaves the solid population.
The `material_equivalents`, `solid_equivalents`, and `soluble_equivalents`
observables follow directly from the same distribution.

The API also permits an explicitly sourced solid threshold and exo fragment
length. A monomer-releasing xylan example tests that the implementation is not
cellulose-specific; that test does not establish a new biological parameter set.
Changing these structural conventions is a user-stated model adaptation.
`F_a` is a supplied accessibility fraction between zero and one. Enzyme amounts
are supplied molar concentrations. This route does not infer chain populations
from bulk substrate mass, infer adsorption from enzyme dose, describe
processivity, or include soluble-fragment hydrolysis automatically. It uses the
source's effective enzyme pools and has no adsorption occupancy coupling.

### Counterfactual comparisons

`fungal_model.screening.synergy.run_synergy_counterfactuals` accepts a callback
that builds and runs a specified subset of cocktail members and an observable
callback that returns a **net product increment** or another nonnegative,
consistently defined conversion increment. The caller must keep each member's
dose, substrate state, time grid, and conditions fixed across comparisons.

The helper computes `full_increment / sum(singleton_increments)`. Each singleton
contains exactly one member at its full-cocktail dose. Leave-one-out results are
also returned when requested, but they are not used as the denominator. Those
comparisons differ for cocktails with more than two members. A zero denominator
returns an undefined ratio (`NaN`) with a false `defined` mask. Negative or
nonfinite increments, incompatible shapes, duplicate members, and an excessive
member count are refused. No synergy multiplier is applied to a reaction rate.

## Peroxide-driven oxidative cleavage (M6)

`peroxide_oxidative_cleavage` and `peroxide_inactivation` use
[Kuusk et al. (2018), Eqs. 4 and 5](https://doi.org/10.1074/jbc.M117.817593).
The equation record is
`data/mechanism_sources/kuusk2018_peroxide/source.yml`.
With substrate `S`, peroxide `H`, and active enzyme `E`, their effective laws are:

```text
r_cut   = kcat E S H / (KiS KmH + KmH S + KmS H + S H)
r_inact = ki E H KmS / (KmS + S)
```

All constants are explicit. There is no default peroxide saturation constant,
product yield, decay constant, or feed. The cleavage event consumes one
peroxide and converts a supplied number of substrate monomer equivalents into
an oxidized-product pool. The product-yield coefficient has its own source.
Active enzyme is transferred to the inactive pool by the inactivation law.
The substrate-binding and substrate-Michaelis constants are separate inputs.
This is a homogeneous effective law from the source system, not a universal
surface reaction law.

The table adapter adds a constant peroxide feed when supplied and first-order
peroxide decay with a supplied coefficient. It tracks cumulative cleavage,
decay and feed amounts. The checks are:

- substrate equivalents plus oxidized-product equivalents remain constant;
- active plus inactive enzyme remain constant;
- peroxide plus cleavage and decay, minus cumulative feed, remains constant.

The cited effective inactivation law does not supply a peroxide-damage reaction
stoichiometry, so damage does not silently consume an invented peroxide amount.
The model assumes a primed enzyme pool. It does not infer reductant, dissolved
oxygen, redox cycling, endogenous peroxide production, or damage chemistry.
Zero peroxide or zero substrate gives zero cleavage. At fixed substrate and
peroxide, enzyme decay and accumulated turnover have the source-derived
exponential/integrated limit; tests exercise that limit and mixed concentration
units for cellulose and chitin examples.

Oxidative products are a separate explicit pool. There is no guessed allocation
of oxidative cuts among chain lengths, and M6 does not silently create M5 chain
ends. Joint oxidative–hydrolytic fragment redistribution requires a supported
fragment-allocation model and corresponding inputs before it can be added.

## Run explicit user tables

Start from either `data/user_mechanisms/chain_scission` or
`data/user_mechanisms/peroxide_oxidation`. They contain:

| File | Required content |
| --- | --- |
| `mechanism.yml` | Name, mechanism, mode, maturity, source, and time grid; chain mechanisms also require `solid_min_length`, `exo_fragment_length`, and `structure_source`. |
| `states.csv` | `state,role,value,units,source`; chain rows additionally give `chain_length`. Every initial concentration must be explicit. |
| `kinetics.csv` | `quantity,value,units,source`; the example lists all required names, and omitted or extra quantities are refused. |
| `feeds.csv` | Optional peroxide feed: `state,rate,units,source`, at most one constant feed naming the peroxide state. |

The chain roles are `chain`, `endo_enzyme`, and `exo_enzyme`. The peroxide roles
are `substrate`, `peroxide`, `enzyme`, `product`, and `inactive_enzyme`. State
units are molar concentrations; kinetic units are checked against their roles.
For peroxide, absent `feeds.csv` explicitly selects a batch experiment and is
recorded as zero feed. Generated cumulative ledgers start at zero because they
measure change since the initial time. Input digests and sources are retained.
The table format does not include parameter uncertainty; generated records state
that uncertainty was not supplied.

From the repository root, with the package installed:

```sh
fungmod assemble-mechanisms --user-data data/user_mechanisms/chain_scission --output /tmp/chain.yml
fungmod run-config /tmp/chain.yml --output /tmp/chain-results
fungmod assemble-mechanisms --user-data data/user_mechanisms/peroxide_oxidation --output /tmp/peroxide.yml
fungmod run-config /tmp/peroxide.yml --output /tmp/peroxide-results
```

Assembly preflights units, bindings and native model compilation before writing
and refuses to overwrite an existing configuration. Ready-made configurations
also exist at `data/model_configs/toy_chain_scission.yml` and
`data/model_configs/toy_peroxide_oxidation.yml`.

Ordinary user-data enzyme tables cannot represent these states. Explicitly
selecting `endoglucanase` or `lytic_polysaccharide_monooxygenase` there is refused
with instructions to use this adapter. Existing genome and UniProt user-data
imports retain their prior classification behavior and generated records. New
metadata can be selected through the separate opt-in
`data_registry/cazyme_families/cazyme_mechanisms_map.yml`; polyspecific GH5/GH12/GH45
and AA9/AA10 family hits remain tentative evidence, not proof of the particular
activity, substrate, product, or kinetic constants.

## Saved finite-run summaries

Configured runs write `mechanism_metrics.json` and `.csv` using the existing
metric-name, value, units, status and notes columns. Metric names include their
process or chain-population scope so independent mechanisms cannot overwrite
each other. Shared endo/exo channels produce one set of chain-population
summaries: final chain ends, solid, soluble and total monomer equivalents.
Degree of synergy is explicitly unknown for a single run.

For a separately performed counterfactual comparison, a configuration may supply
`metric_definitions.synergy_comparisons.chain_population_1` with a `source`,
`matched_conditions: true`, one `full_increment`, and a list of
`individual_increments`. Each increment is a scalar `{value, units}` mapping and
must already exclude its starting product amount. This attests matching member
doses and conditions; it does not run the comparisons or replace singleton
results with leave-one-out results. Zero denominator remains unknown.

Peroxide summaries report final cuts, oxidized product, active enzyme and
peroxide; the productive cut increment divided by initial active enzyme; and
final divided by initial active enzyme. Both ratios convert concentration units
and become unknown when initial active enzyme is zero. Turnover covers the
simulated interval only: it is not an asymptotic turnover prediction.

Feed and decay summaries use explicitly bound cumulative ledgers, always
subtracting their initial values. For example:

```yaml
metric_definitions:
  peroxide_ledgers:
    H:
      feed: mechanism_peroxide_feed
      decay: mechanism_peroxide_decay
```

The table adapter supplies these bindings. A missing binding yields unknown. An
explicit `null` declares no modeled contribution and reports zero, as a stated
model boundary rather than an inferred rate. Total modeled peroxide consumption
is productive cuts plus the tracked decay; no peroxide-damage stoichiometry is
added. A ledger's units must convert to the peroxide pool's units.

When a configured run belongs to a user-table ensemble, its metric rows also
appear in the final and across-sample summary tables. Existing culture and pH
metrics are deduplicated by metric name. These are reductions of simulated
trajectories, not new observations or empirical validation.
