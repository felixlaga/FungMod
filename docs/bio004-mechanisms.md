# Six source-backed mechanism extensions

The plan in PR #134 is implemented as six explicit, opt-in mechanisms. Their
maturity is **software-tested with checked law-form evidence**. All bundled
examples use invented inputs labelled for software verification. They are not
calibrations, empirical validation, organism-specific constants or forecasts.

| Mechanism | Implemented scope | Input route |
| --- | --- | --- |
| M1 adsorption | Finite enzyme depletion and binding capacity; stable quasi-steady Langmuir partition; activity of bound enzyme | [Adsorption tables](bio004-adsorption.md), configured process |
| M2 sugar uptake | Explicit solid-to-sugar yield, soluble pool, capped Pirt maintenance and Monod uptake, biomass/loss/carbon ledgers | [Culture tables](bio004-uptake-oxygen.md) |
| M3 oxygen | Explicit gas-transfer coefficient and saturation, uptake/growth/maintenance oxygen costs, signed transfer and consumption ledgers, state-driven oxygen response | [Aeration and response tables](bio004-uptake-oxygen.md) |
| M4 buffered pH | Explicit proton coefficients, ideal monoprotic buffer capacity, bounded pH state, signed proton or pH-stat titrant ledger | `medium.csv` below, `add-medium`, configured process |
| M5 chain-mediated synergy | Sourced finite chain population balances for endo/exo action, exact fragment and chain-end accounting; matched singleton counterfactuals | [Explicit chain tables](bio004-chain-peroxide.md) |
| M6 peroxide cleavage | Ternary peroxide/substrate rate, substrate-protected enzyme inactivation, explicit peroxide feed/decay and product yield | [Explicit peroxide tables](bio004-chain-peroxide.md) |

Mechanisms share the existing compiled process engine. The generic core has no
fungus, enzyme or substrate-specific rate branches. New foundations add declared
signed/bounded states, dynamic environment authorities, unit-bearing reaction
coefficients, derived observables and checked mechanism-law source records.
Existing configurations retain nonnegative rate evaluation and static environment
semantics. The seven pinned pre-existing user datasets keep identical generated
records. The default CAZy map is unchanged; enriched mechanism classifications
are an explicit opt-in map and never supply rates or enzyme doses.

## Source and scope decisions

Source records in `data/mechanism_sources/*/source.yml` identify DOI, equation
location and transcription, assumptions, applicability, retrieval date, support
type and redistribution terms. Law-form evidence is distinct from evidence for
parameter values. File-based readiness checks refuse a promoted mechanism whose
source record is missing or invalid. A source that supplies a law does not
license transferring its constants between preparations or organisms.

The source review resolved two deliberately open points in the plan. M5 uses
Niu et al.'s finite-chain scission equations, preserving exact chain exhaustion;
it does not invent an aggregate end-consumption closure. M6 uses Kuusk et al.'s
full ternary equation, so substrate depletion remains explicit. Oxidative cuts
are not allocated to M5's individual chain lengths without a sourced fragment
allocation. No imposed synergy multiplier is present. The reported degree of
synergy divides full-mixture product increments by the sum of matched singleton
increments. Leave-one-out comparisons are separate, and zero denominators are
explicitly undefined.

## Buffered pH and pH-stat

For hydrogen concentration `H = C_standard * 10**(-pH)`, the implemented buffer
value and pH balance are

```text
beta = ln(10) * (H + Kw/H + sum(C_i*Ka_i*H/(Ka_i+H)**2))
dpH/dt = -sum(nu_H_j*r_j)/beta
proton_ledger' = sum(nu_H_j*r_j)
```

The source is Chiriac and Balea (1997), DOI
[10.1021/ed074p937](https://doi.org/10.1021/ed074p937), equations 1 and 11.
Each `nu_H_j` is a user-supplied proton amount per driver extent, including its
units and evidence. A negative coefficient alkalinises the medium. The pH-stat
mode fixes the stated initial/setpoint pH and accumulates a signed titrant
ledger; positive means base demand for acid production, negative acid demand
for alkalinisation. Titrant identity is recorded. Ledgers start at zero because
they count accumulation since the run began.

`medium.csv` can accompany a regular user dataset or augment an explicit
configuration. Its columns are `quantity,value,units,buffer,process,evidence_type,
source,measurement_method,notes`, with `titrant` additionally required for a
pH-stat setpoint. Every numerical input is explicit:

| Quantity | Units and role |
| --- | --- |
| `buffer_concentration`, `buffer_pka` | Positive amount/volume and dimensionless pKa, paired by `buffer` ID |
| `initial_ph`, `minimum_ph`, `maximum_ph` | Dimensionless; initial inside ordered bounds within 0–14 |
| `water_ion_product` | Positive concentration squared |
| `standard_concentration` | Positive concentration defining the pH concentration convention |
| `temperature` | Positive kelvin, matching the environment and buffer pKa condition |
| `proton_coefficient` | Proton amount per driver extent; `process` is an existing configured process ID |
| `ph_threshold` (optional) | Dimensionless target; first crossing is interpolated from saved samples |
| `ph_stat_setpoint` (optional) | Dimensionless, equal to initial pH, plus explicit `titrant` identity |

Rows retain evidence classification (`measured`, `literature`, `design` or
`estimate`). Estimates require exploratory mode. This scalar medium adapter
retains the supplied values exactly; it does not generate uncertainty ranges.
For a different condition or uncertainty study, supply condition-specific values
or explicit parameter configurations. The table applies to every case in its
dataset, so all referenced drivers and initial conditions must agree; split
datasets when the medium differs. In a legacy one-pool culture, the driver ID is
`substrate_consumption`; multiple-pool configurations expose their driver IDs
in the generated process definitions. Missing buffers, evidence or coefficients
fail explicitly. No acid production is inferred from a strain or nutrient name.

```bash
fungmod add-medium data/mechanism_examples/buffered_ph/reaction.yml \
  --medium data/mechanism_examples/buffered_ph/medium.csv \
  --output /tmp/buffered-ph.yml
fungmod run-config /tmp/buffered-ph.yml --output /tmp/buffered-ph-run
```

This shipped example is synthetic and uses toy mode. `add-medium` currently
requires an inline environment so it can remove static pH as a second authority.
Dynamic Gaussian, cardinal and ionization laws then read the pH state; any
conflicting static authority or trial value outside the declared domain is
refused. The model assumes fixed volume/temperature and independent ideal
monoprotic buffers. It does not perform ionic-strength corrections, electrolyte
speciation, intracellular regulation or implicit organic-acid secretion.

## Verification and limits

Tests cover units, unknown/refused inputs, source integrity, analytical gradients,
static/dynamic equivalence, conservation at every saved time, depletion and
zero-rate limits, two materially different synthetic substrate systems,
end-to-end user tables and CLI execution, and pinned legacy records. pH checks
include analytical acidifying/alkalinising titration curves, high-buffer and
zero-proton limits, and exact signed pH-stat accounting. Oxygen checks include
supersaturation and the analytical gas-transfer limit. Signed core states cross
zero without projection, while legacy nonnegative states preserve their policy.

The explicit routes do not auto-parameterize from an organism name, annotation
or source title. Dynamic adsorption, catabolite repression, stalling, universal
LPMO priming, in situ peroxide generation, unsourced chain allocation and
multi-sugar preference are outside the delivered scope. The existing enzyme
kinetics fitting API keeps its documented parameter contract; culture timecourse
comparison does not imply culture-parameter fitting. Scientific mode means
exact admissible inputs, not empirical validation. The recommended next task is
to select a licensed condition-matched experimental dataset, freeze a calibration
and independent holdout plan, and evaluate one mechanism at a time.

Configured mechanism runs also write `mechanism_metrics.json` and `.csv`.
Adsorption summaries include endpoint bound fractions and an enzyme-balance
residual; zero-enzyme fractions are explicitly unknown. Chain summaries include
final populations and an unknown synergy ratio unless a matched counterfactual
comparison is supplied. Peroxide summaries include finite-run turnover, remaining
activity and explicitly declared peroxide ledgers. Uptake and oxygen summaries
include sugar extrema, final biomass and oxygen threshold duration when specified.
Buffered runs report final pH, an explicitly supplied threshold
(or unknown), signed pH-stat titrant and, for changing pH, the maximum analytical
proton-balance residual across all saved times. User-table result summaries carry
the same reductions. These diagnostics are numerical checks, not validation data.
