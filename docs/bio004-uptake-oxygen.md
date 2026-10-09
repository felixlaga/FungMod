# Released-sugar uptake and dissolved oxygen

The BIO-004 M2/M3 user-table route extends an explicitly supplied culture with
one soluble resource pool, maintenance consumption and optional dissolved oxygen.
It is **software tested, not empirically validated**. Existing culture tables
without uptake quantities retain their previous model. No organism constants,
initial sugar, oxygen availability or release conversion are inferred.

## Input tables

Keep the regular `user_dataset.yml`, strain, enzyme, substrate and condition
tables, plus `kinetics.csv` (a header-only table is allowed for a culture-only
dataset). The existing culture rows still declare initial solid substrate and
biomass, biomass yield and loss, induction, and each consuming enzyme pool's
hydrolysis capacity, half saturation, initial enzyme, production and loss.

`culture.csv` and `aeration.csv` use the long-row columns:

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,units,evidence_type,source,method
```

The quantities below describe the culture as a whole: leave `enzyme_class`
blank. Values may use the existing exact-value or lower/upper-bound schema;
missing required values become explicit gaps. State `source` for every row and
`method` when its evidence type requires one. Estimates require exploratory
execution; a software test or guessed number is not a measurement.

Add all four uptake rows to `culture.csv`:

| Quantity | Meaning | Mass-sugar basis | Amount-sugar basis |
| --- | --- | --- | --- |
| `uptake_capacity` | Maximum sugar uptake per biomass per time | `g/g/h` or `1/h` | `mmol/g/h` |
| `uptake_half_saturation` | Sugar concentration at half maximum uptake | `g/L` | `mmol/L` |
| `maintenance_demand` | Sugar maintenance demand per biomass per time | `g/g/h` or `1/h` | `mmol/g/h` |
| `initial_soluble_sugar` | Explicit initial soluble pool | `g/L` | `mmol/L` |

`initial_biomass` remains a dry-mass concentration such as `g/L`.
`biomass_yield` is biomass per **soluble sugar consumed for growth**, such as
`g/g` or `g/mmol`. It is no longer the old direct solid-to-biomass yield in an
uptake-enabled culture. Convertible unit alternatives are accepted and checked
against each connected pool; no molar mass is supplied automatically.

In `substrates.csv`, name the soluble pool in `product` and declare the solid's
`product_yield`, `yield_basis`, `yield_evidence_type`, `yield_method` and `source`.
The release yield has units of sugar per solid, for example `g/g` or `mmol/g`.
It is carried into a provenance-bearing parameter record. A mass yield without
explicit yield evidence is refused for this route.

For dynamic oxygen, add these culture rows:

| Quantity | Meaning | Example units |
| --- | --- | --- |
| `oxygen_half_saturation` | Dissolved oxygen half saturation of sugar uptake | `mmol/L` |
| `oxygen_yield` | Oxygen consumed per biomass formed | `mmol/g` |
| `oxygen_maintenance` | Oxygen consumed per maintenance sugar consumed | `mmol/g` or `mmol/mmol` |

Then add all three `aeration.csv` rows, with `enzyme_class` blank:

| Quantity | Meaning | Example units |
| --- | --- | --- |
| `kla` | Measured volumetric gas-transfer coefficient | `1/h` |
| `oxygen_saturation` | Explicit dissolved saturation concentration | `mmol/L` |
| `initial_dissolved_oxygen` | Explicit initial dissolved oxygen | `mmol/L` |

`kla` requires `evidence_type=measured`. Saturation is supplied directly; this
route does not calculate it from temperature, pressure, vessel geometry or a
solubility correlation. `oxygen_yield` and `oxygen_maintenance` are demand
coefficients, despite the historical quantity name `oxygen_yield`. In particular,
`oxygen_maintenance` has **no time denominator**: the maintenance flux already
includes time. Zero demand is explicit and allowed. Missing oxygen rows remain
gaps once an oxygen mechanism has been requested.

## Implemented balances

Let `S` be solid, `G` soluble sugar, `X` dry biomass, `r_h` the existing
enzyme-mediated solid-consumption rate, `rho` the sugar-per-solid release yield,
`Y` the biomass-per-sugar growth yield, and `m` the maintenance demand.

```text
q = qmax G/(K_G + G)                      without an oxygen pool
q = qmax G/(K_G + G) O/(K_O + O)           with an oxygen pool
r_growth = Y max(q - m, 0) X
a_maintenance = min(q, m) X

dS/dt = -r_h
dG/dt = rho r_h - r_growth/Y - a_maintenance
dX/dt = r_growth - k_loss X
```

Maintenance is prioritized and capped by uptake. A culture with insufficient
uptake has zero growth; this model does not infer death from unmet maintenance.
Nitrogen is explicitly assumed nonlimiting. Without oxygen rows, oxygen is
explicitly assumed nonlimiting. Enzyme production retains the existing
uncosted secretion law; there is no catabolite repression, storage or morphology.

The resource balance records biomass loss `L_X` and maintenance substrate
`L_M`. At every time, it checks:

```text
S + G/rho + (X + L_X)/(rho Y) + L_M/rho = initial total
```

The output role `ledger_respired_carbon` is a maintenance **substrate-equivalent
ledger**, not a measured or chemically resolved carbon-dioxide concentration.
Growth-associated substrate use is included through `Y`; the invariant is an
accounting closure, not an elemental or electron balance.

For the oxygen-enabled culture:

```text
r_transfer = kLa (O_sat - O)
r_consumption = oxygen_yield r_growth + oxygen_maintenance a_maintenance
dO/dt = r_transfer - r_consumption
O + L_consumption - L_transfer = O_initial
```

The transfer ledger is signed, so outgassing from a supersaturated initial pool
is represented. Physical concentration pools remain nonnegative. The additional
oxygen invariant appears in the conservation diagnostics.

## Optional oxygen response of a hydrolysis rate

A `responses.csv` row can bind the dynamic oxygen pool to one existing consuming
enzyme class. Use `law=oxygen_monod`, `parameter=half_saturation`, a positive
`value`, concentration `units` such as `mmol/L`, the usual evidence columns,
and `kinetics_at_reference=yes`.

Here that declaration means the supplied hydrolysis capacity is the
**oxygen-unlimited capacity**. The rate is multiplied by `O/(K_response+O)`;
there is no finite reference oxygen or renormalization. The response is shared
across the case's explicitly supplied culture conditions. It reads the simulated
oxygen state, not the static oxygen field of an environment grid. It changes a
rate factor only: no additional oxygen stoichiometry is inferred for hydrolysis.
An oxygen-consuming enzyme needs its own explicit demand mechanism.

## Summary metrics

`final_metrics.csv` and `summary_metrics.csv` include peak soluble sugar, the
first saved time attaining that peak, final biomass and minimum dissolved
oxygen when the corresponding pools are bound. Extrema are over saved output
points; they do not claim an unresolved peak between solver outputs.

Time below an oxygen threshold is `unknown` until the caller explicitly supplies
`metric_definitions.oxygen_threshold: {value: ..., units: ...}` in a configured
model. A registry composition can place the same `metric_definitions` mapping
under `process_state_metadata`; the assembler carries it into the model config.
The threshold must be a finite, nonnegative concentration. Duration integrates
strictly below the threshold using linear interpolation between saved points,
including every downcrossing and upcrossing. No default biological cutoff is
inferred. The configured result bundle writes the same reductions.

## Comparison and limitations

For uptake cultures, `timecourse.csv` accepts `substrate`, `soluble_sugar`,
`biomass` and, when bound, `dissolved_oxygen` as `observable`. Units must be
compatible with that state's explicit initial-condition units. Name a consuming
enzyme class from the culture; all consuming classes observe the same pooled
culture states. Supply the regular time, value, uncertainty and source columns.
`product` is refused here because sugar remaining after uptake differs from
cumulative product formed.

Run `compare_with_timecourses(result, dataset)` through the existing API. It
interpolates within the simulated time interval, reports residuals and agreement,
and retains the existing warning that agreement is not independent validation.
`fit_user_dataset` remains restricted to enzyme-assay `km`, `kcat` and `vmax`;
it explicitly refuses culture-parameter fitting. Fitting uptake, maintenance or
oxygen constants needs a dedicated identifiability and provenance contract.

The supported network composition is parallel culture enzyme pools releasing
one shared sugar from an entry solid. Multiple soluble sugars, downstream assay
chains within that culture, competitive uptake, repression, oxygen solubility,
oxygen-dependent cell death and organism calibration are not supplied.

The frozen law-form records are `monod1949`, `pirt1965` and
`garcia_ochoa_gomez2009` under `data/mechanism_sources/`. Monod's original law and
the gas-transfer form were checked against primary-source text. The accessible
Pirt primary publisher abstract supports constant maintenance; its full paper
was inaccessible during verification. The finite-uptake cap is therefore stated
as an exploratory closure assumption rather than a directly verified Pirt
equation. These records supply no numeric fungal parameters. Synthetic tests
cover conservation, units, limits and derivatives on two different substrate and
enzyme bases; they do not establish biological accuracy.
