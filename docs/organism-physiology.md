# Organism physiology in the registry

FungMod's first whole-organism registry case is *Trichoderma harzianum* P49P11
growing in submerged batch culture on particulate cellulose, the system studied
by [Gelain et al. (2020)](https://doi.org/10.1016/j.cesx.2020.100085). The case
runs in `scientific` mode through the public `VirtualExperiment` API and writes
biomass, cellulose, filter-paper activity and beta-glucosidase activity
trajectories to `time_series_long.csv`.

`scientific` keeps its established meaning: every input is an exact,
provenance-backed registry record and every mechanism is implemented and
tested. It does **not** mean experimentally validated. The organism constants
are a retrospective fit to published duplicate means, and the output tables say
so on every row that could be misread.

## What a `culture_physiology` template declares

A case template of process type `culture_physiology` composes generic process
laws into one well-mixed culture. It names *roles*, never organisms:

| Template section | Declares |
| --- | --- |
| `state_roles` | `substrate`, `biomass`, `enzyme`, indexed `enzyme_*` pools, and indexed `ledger_*` closure pools. |
| `initial_state_mapping` | Which parameter role supplies each initial value and its units, or an explicit zero. |
| `product_maps` | Stoichiometric maps whose coefficients may be fixed numbers or references to a parameter role (`parameter_role`) or its complement (`complement_of_parameter_role`), so a fitted yield enters the stoichiometry from a registry record. |
| `process_templates` | Ordered generic processes (`homogeneous_michaelis_menten`, `first_order`, `proportional_synthesis`, ...) with their state-role and parameter-role bindings and explicit assumptions. |
| `conservation` | The weighted closure ledger enforced by the `mass_balance` validator; every product map must balance under those weights at build time. |
| `state_species` | The registry identity behind every state (`organism`, `substrate`, `enzyme`, `ledger`). |
| `entities`, `geometry` | Inline substrate, enzyme and reactor metadata with provenance. |

The assembler fails closed: a parameter role that no process, product map or
initial state uses is rejected, as is a referenced role without a resolved
record, a process type without a registered factory, a product map that does
not balance under the closure weights, or a state without a declared identity.

Parameter records resolve through the process-compatibility record's
`parameter_roles`, exactly as for the enzyme-kinetics cases. In `scientific`
mode each record must be exact, non-exploratory, non-toy and authorized for
simulation; the modelability preflight lists the chosen record for every role.

## The generic physiology process

`proportional_synthesis` is the one new process law. It forms a product pool in
proportion to a producer pool, optionally with saturable induction by a third
pool:

```text
rate = q * producer                            (constitutive)
rate = q * producer * inducer / (K_I + inducer) (induced)
```

Only the product is changed; the producer and the inducer are not consumed and
the material cost of synthesis is not represented. That is the canonical
growth-associated production law for extracellular enzymes and is deliberately
not a costed secretion closure. The process compiles to a numeric kernel and is
tested on non-biological dissolved chemistry as well as on assay-activity units.

Enzyme activities carry their own base dimensions in the core unit registry:
`filter_paper_unit` (`FPU`) and `beta_glucosidase_assay_unit` (`BGU`). They do
not convert to mass, molarity or each other; a preparation-specific
specific-activity measurement would have to enter a model as an explicit
parameter.

## The *T. harzianum* P49P11 case

The registry carries the organism (`trichoderma_harzianum_p49p11`), its
assay-defined total-cellulase class, the Celufloc 200 cellulose substrate with
explicit unknown surface area and crystallinity, three culture-condition records
(10, 20 and 30 g/L cellulose at 29 °C, pH 5.0, dissolved oxygen above 30 %),
and fifteen parameter records:

- nine `calibrated` constants from the all-condition fit of the hydrolysis
  candidate in the recorded Gelain joint culture comparison (v2), each carrying
  the artifact path, its SHA-256, the training conditions, rank and
  condition-number diagnostics, and the list of constants that sit at a fitting
  bound (`K_ind`, `kF`, `kB`);
- the deposited initial biomass, the nominal cellulose loading of each
  condition, and the deposited zero initial activities.

The template composes six generic processes:

| Process | Law | Registry roles |
| --- | --- | --- |
| Cellulase-limited cellulose consumption | `k_h F S / (K_h + S)`, products `Y` biomass and `1 - Y` closure ledger | `hydrolysis_capacity`, `hydrolysis_half_saturation`, `biomass_yield` |
| Biomass loss | first order into a closure ledger | `biomass_loss_rate` |
| Filter-paper activity production | `qF X S / (K_ind + S)` | `cellulase_specific_production_rate`, `induction_half_saturation` |
| Filter-paper activity loss | first order | `cellulase_loss_rate` |
| Beta-glucosidase production | `qB X S / (K_ind + S)` | `beta_glucosidase_specific_production_rate`, `induction_half_saturation` |
| Beta-glucosidase loss | first order | `beta_glucosidase_loss_rate` |

`tests/test_organism_registry_case.py` proves that the assembled configured
model reproduces the frozen research implementation of the same candidate
(`fungal_model.research.gelain_models.simulate_candidate(model="hydrolysis")`)
for all three conditions, that the dry-mass ledger closes, and that the public
path writes the expected roles.

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_names(
    fungi=["T. harzianum P49P11"],
    substrates=["Celufloc 200"],
    environments=[
        "gelain_2020_cellulose_batch_10gl",
        "gelain_2020_cellulose_batch_20gl",
        "gelain_2020_cellulose_batch_30gl",
    ],
)
result = study.simulate(mode="scientific", output_dir="outputs/t_harzianum_cellulose")
```

## What this case does not claim

- The hydrolysis candidate is one of four cellulose candidates in the recorded
  comparison; the published Gelain equations fit the data better but are
  rank-deficient and bespoke, and the candidate itself failed the comparison's
  observable-worsening screen in the primary scenario. The registry records
  state this; the trajectories are retrospective, not predictions.
- Three constants sit at their fitting bounds: induction is effectively
  saturated and activity loss is effectively zero over the measured range. The
  data do not identify them.
- No nutrient or oxygen limitation, maintenance, soluble intermediate, product
  pool, morphology or pH dynamics is represented. Temperature and pH are
  metadata. The consumed cellulose not retained as biomass is an explicit
  closure ledger, not a measured product.
- There is no replicate-level uncertainty, so no uncertainty band is produced in
  `scientific` mode; `exploratory` mode samples nothing because every record is
  exact.

## Depletion and negative solver iterates

The cellulose pool is consumed almost completely within 96 h at every loading.
Multistep solvers evaluate the right-hand side at predicted states that can
sit slightly below zero near depletion, so the compiled core evaluates rates at
`max(state, 0)` and records the policy in `solver_metadata["kernel"]`
(`negative_state_policy`). The integrated trajectory is never clipped; the
`non_negative` validator reports any accepted state below its tolerance. See
[Compiled model core](compiled-core.md).

## Next organism records

The repository holds steady-state respiration data for *Aspergillus niger*
NW185 (Lameiras 2015/2017), protein-output steady states for *A. niger* AB94-85
and ABGT1026 (Jørgensen 2009) and an endpoint secretome composition for
*Trichoderma reesei* QM6a (Novy 2021). None of these supports a dynamic culture
template today: the registry's organism records require enzyme classes with a
process compatibility, and the data carry no enzyme-class evidence
(*A. niger*) or no time courses (*T. reesei*). They are the next intake
targets, together with the resource-limited growth, maintenance and costed
secretion closures of `DegradingCulture`, which no organism in the repository
yet parameterizes.
