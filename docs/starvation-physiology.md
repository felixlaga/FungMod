# Starvation physiology: endogenous maintenance, closure consistency, Tijhuis

This page records what the resource-limited closure does when uptake cannot
pay the maintenance demand, how the closure now checks that its stoichiometry
matches its yields, and the temperature law for the maintenance Gibbs energy.
It is the WP6 result of the 2026-10-22 scientific audit. Nothing here ships a
biological value: every yield and demand still comes from the caller.

## The problem the audit found

The Pirt/Monod closure (`resource_limited_growth`, `resource_limited_maintenance`,
`costed_secretion`) caps maintenance at the uptake capacity and reports the
unpaid remainder as `unmet_maintenance`. Nothing else happened: a batch culture
whose substrate ran out kept its biomass frozen forever with a permanent
unmet-maintenance flag (fungi finding 2, processes finding F9). Beeftink, van
der Heijden and Heijnen (1990) showed that the deficit is paid by oxidising
biomass; van Bodegom (2007) and Wang and Post (2012) identify the missing term
as the main failure of pure Pirt closures under starvation.

Two further defects were fixed on the way:

* The yield `Y` in the growth rate and the `-1/Y` in the growth stoichiometry
  were never tied together; a config with `Y = 0.4` and a substrate coefficient
  of `-1` ran and produced an apparent yield of 0.94 (processes finding F5).
* With a zero maintenance demand the analytic growth Jacobian was wrong at an
  exhausted pool (`S = 0` or `O = 0`): the kink's "below the demand" branch
  returned zeros where the right derivative is the capacity derivative (fungi
  finding 9). Solutions were unaffected; only Newton quality was.

## Endogenous maintenance

With the capacity `c = q_max S/(K_S+S) O/(K_O+O)` and the demand `m`, the
specific deficit is

```text
d = max(m - c, 0)                      substrate formula units per biomass unit per time
r_e = d X / Y_e                        biomass formula units oxidised per volume per time
```

`Y_e` (`endogenous_yield`, dimensionless, positive) is the maintenance
substrate equivalent that oxidising one biomass formula unit supplies. The
natural derivation is energetic: `Y_e = |dG_cat per biomass formula unit| /
|dG_cat per substrate formula unit|` from the caller's macrochemical balance.
FungMod ships no value; the process is opt-in and refuses to build without the
symbol.

The caller supplies the stoichiometry of biomass oxidation from its balance.
The biomass coefficient must be `-1`; the oxidant and product coefficients
follow from the balance; reservoir species that are not states are left out
and ledgered through the optional `extent_state`, exactly as for the other
closure extents.

The gradient is one-sided at the tie `c = m`: for `c < m`

```text
dr_e/dS = -(dc/dS) X / Y_e      dr_e/dO = -(dc/dO) X / Y_e      dr_e/dX = d / Y_e
```

and zero otherwise. Growth and secretion take the other side of the same kink
(zero at the tie), so the three processes never pay or form anything twice.

The process is `fungal_model.processes.culture.EndogenousMaintenanceProcess`
(type `endogenous_maintenance`, maturity `literature_backed_software_tested`)
with the factory `fungal_model.processes.culture_factories.EndogenousMaintenanceFactory`.
The factory reads the closure fields of the other three processes plus
`parameters.endogenous_yield`.

```yaml
- id: starvation
  process_type: endogenous_maintenance
  states:
    substrate: resource_concentration
    biomass: cell_concentration
    nutrient: nutrient_concentration
    oxidant: acceptor_concentration
    extent: endogenous_extent
  parameters:
    true_yield: Y
    maintenance_demand: m
    uptake_capacity: q
    substrate_half_saturation: K_S
    nutrient_half_saturation: K_N
    oxidant_half_saturation: K_O
    endogenous_yield: Y_e
    time_units: hour
  stoichiometry:
    cell_concentration: -1.0
    acceptor_concentration: -1.0
```

What it does not represent: death, lysis, storage mobilisation, dormancy or a
recovery lag. The opt-in classes `ResourceLimitedCulture` and
`DegradingCulture` keep their frozen-biomass behaviour and still report
`unmet_maintenance`; they have not gained the term.

## Closure consistency at build time

Every closure extent is counted in the formula units of one pool, so the
stoichiometry must carry a unit coefficient for that pool and the inverse
yield for the substrate. `closure_constants()` now checks this when the
parameters are known and refuses a mismatch, naming the expected coefficient:

| Process | Required coefficients |
| --- | --- |
| `resource_limited_growth` | biomass `+1`; substrate `-1/Y` |
| `costed_secretion` | one credited pool `+1` (the product); substrate `-1/y` |
| `resource_limited_maintenance` | substrate `-1` |
| `endogenous_maintenance` | biomass `-1` |

The tolerance on `|nu_substrate Y + 1|` is the declared
`CLOSURE_STOICHIOMETRY_TOLERANCE` (1e-9), which absorbs the round-off of a
coefficient written as `-1/Y` and nothing more. A zero `Y` or `y` is refused
because the substrate coefficient would be undefined. The packaged
`toy_resource_limited_chemostat.yml` and the compiled representations of
`ResourceLimitedCulture` and `DegradingCulture` already satisfied the rule and
are unchanged.

## Zero-demand Jacobian

`ClosureConstants.budget_gradient` returns zeros only when the budget is
negative or when it is zero with a positive demand (the documented kink). With
`m = 0` the budget is the capacity itself, so an exhausted pool takes the
right derivative of the capacity. `ResourceLimitedCulture._rate_jacobian` uses
the same rule, `(available > demand) | (demand == 0)`. Tests compare both
against right-sided Richardson differences at `S = 0` and `O = 0`, and the
compiled closure gradient against the native one to 1e-12.

## Tijhuis maintenance Gibbs energy

`fungal_model.fungi.maintenance_correlation` implements the correlation of
Tijhuis, van Loosdrecht and Heijnen (1993, Biotechnol Bioeng 42:509-519):

```text
m_G(T) = m_G,ref exp[-(E_a,m / R)(1/T - 1/T_ref)]
m_G,ref = 4.5 kJ per C-mol biomass per hour,  E_a,m = 69 kJ/mol,  T_ref = 298.15 K
```

`tijhuis_maintenance_gibbs(temperature)` returns `m_G` (2.80, 7.12 and 13.21
kJ/(Cmol h) at 20, 30 and 37 degC); `substrate_maintenance_from_gibbs(m_G,
dG_cat)` returns the Pirt coefficient `m_S = m_G / |dG_cat|` and refuses a
non-negative catabolic Gibbs energy. The three constants are sourced
`Parameter` objects; the gas constant is the shared `UNIVERSAL_GAS_CONSTANT`.
C-moles are written with the SI `mole` because pint has no C-mol unit.

Validity: a cross-species compilation of chemostat maintenance data, not a
measurement on any fungus. Applying it to one culture is a recorded assumption
(`tijhuis_maintenance_assumption()`), and nothing in FungMod applies it by
default.

## Tests

* `tests/test_endogenous_maintenance.py`: batch starvation (biomass declines
  only after growth stops, decay rate tends to `m/Y_e`, abstract carbon ledger
  closes to 1e-12), kernel versus unit-aware rate in two unit systems, gradients
  versus Richardson differences at interior, exhausted and tie states, factory
  round trip and missing-field report, refusals of inconsistent stoichiometry.
* `tests/test_culture_processes.py`: zero-demand gradients at exhausted pools,
  compiled versus native parity at `m = 0`.
* `tests/test_respiration.py`: zero-demand native Jacobian, Tijhuis values and
  refusals.
