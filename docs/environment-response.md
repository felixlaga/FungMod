# Environment response laws

FungMod answers "how does pH or temperature change degradation dynamics" only
through explicit laws. An environment is a static entity: every condition is
read once when a case is assembled, folded into the compiled kernels, and
recorded. A condition that no bound law reads stays metadata, and the output
tables say so. This page lists the laws that exist, how a registry template
binds them, how the result tables report them, and which shipped case carries
a sourced law today.

## Laws

| Law | Kind | Reads | Equation | Parameters (roles) | Source of the law |
| --- | --- | --- | --- | --- | --- |
| `temperature_arrhenius_reference` | modifier | temperature | `k = k_ref exp(-(E_a/R)(1/T - 1/T_ref))` | `activation_energy`, `reference_temperature`, optional measured bounds | Arrhenius |
| `temperature_cardinal_rosso` | modifier | temperature | CTMI: `gamma_T = (T-T_max)(T-T_min)^2 / {(T_opt-T_min)[(T_opt-T_min)(T-T_opt) - (T_opt-T_max)(T_opt+T_min-2T)]}`, zero outside `(T_min, T_max)` | `minimum_temperature`, `optimum_temperature`, `maximum_temperature` | Rosso, Lobry, Flandrois 1993 |
| `ph_gaussian` | modifier | pH | `exp(-0.5 ((pH-pH_opt)/sigma)^2)` | `ph_optimum`, `ph_width`, optional measured bounds | empirical |
| `ph_cardinal_rosso` | modifier | pH | CPM: `gamma_pH = (pH-pH_min)(pH-pH_max) / [(pH-pH_min)(pH-pH_max) - (pH-pH_opt)^2]`, zero outside `(pH_min, pH_max)` | `minimum_ph`, `optimum_ph`, `maximum_ph` | Rosso, Lobry, Bajard, Flandrois 1995 |
| `oxygen_monod` | modifier | oxygen concentration | `O2 / (K_O2 + O2)` | `oxygen_half_saturation` | Monod form |
| `water_activity_threshold` | modifier | water activity | `1` above the threshold, `0` below | `minimum_water_activity` | threshold |
| `water_activity_cardinal_rosso_robinson` | modifier | water activity | cardinal model with inflection and the maximum fixed at one: `gamma_aw = (aw-1)(aw-aw_min)^2 / {(aw_opt-aw_min)[(aw_opt-aw_min)(aw-aw_opt) - (aw_opt-1)(aw_opt+aw_min-2aw)]}`, zero at or below `aw_min` and at `1` | `minimum_water_activity`, `optimum_water_activity` | Rosso, Robinson 2001 |
| `ph_ionization_michaelis_menten` | process law | pH | `v = E kcat(pH) S / (Km(pH) + S)` with `kcat(pH) = k0 / f_es(pH)`, `Km(pH) = Km0 f_e(pH) / f_es(pH)`, `f(pH) = (10^(pK_low - pH) + 1)(10^(pH - pK_high) + 1)` | `turnover`, `michaelis_constant`, `free_enzyme_lower_pk`, `free_enzyme_upper_pk`, `complex_lower_pk`, `complex_upper_pk`, `minimum_ph`, `maximum_ph` | diprotic ionization model; the SABIO-RK "Michaelis-Menten (pH-dependent)" law type 24 |
| `thermal_inactivation` | process law | temperature | `dA/dt = -k_d,ref exp(-(E_d/R)(1/T - 1/T_ref)) A`, optionally routed to an inactive pool | `reference_rate_constant`, `inactivation_energy`, `reference_temperature`, optional measured bounds | first-order inactivation with Arrhenius dependence |

Modifiers multiply the rate of the process they are attached to; the two
cardinal laws follow the multiplicative gamma concept of Rosso et al. (1995).
Process laws own their rate expression. Every law validates its parameters
(ordering of cardinal values, the CTMI condition `T_opt >= (T_min + T_max)/2`,
ordered pKa pairs, positive constants), requires a source string, and warns
with `EnvironmentalValidityWarning` when a measured range is declared and the
case lies outside it. None of them models pH or temperature dynamics,
buffering, reversible unfolding, injury, adaptation, or an interaction between
conditions beyond the product of activities.

Unit-aware and compiled evaluations agree to machine precision across mixed
units (`tests/test_cardinal_response_laws.py`, `tests/test_ph_ionization_process.py`,
`tests/test_thermal_inactivation_process.py`); the two process laws also ship
as non-biological toy configs under `data/model_configs/`.

## Binding a law in a registry template

A case template binds a modifier by listing it with role fields that resolve
through the compatibility record's `parameter_roles`:

```yaml
modifiers:
  - type: temperature_cardinal_rosso
    minimum_temperature_role: growth_minimum_temperature
    optimum_temperature_role: growth_optimum_temperature
    maximum_temperature_role: growth_maximum_temperature
```

Single-process templates list modifiers under
`process_state_metadata.process_modifiers`; `culture_physiology` templates list
them per process template. A process law is bound by using its `process_type`
in the template and mapping its parameter roles. In both cases assembly
requires an exact registry environment condition for every condition a law
reads, generates an inline environment entity carrying exactly those
conditions, and refuses to run otherwise. Nothing is inferred from the
organism's name: if the roles are absent, the case is reported as missing
those parameters.

## What the output tables say

Every assembled config records `provenance.environment_response`: which
conditions act on rates, through which law, bound to which process. The
virtual-experiment tables derive `environment_effect_status` from it:

- `active_response_model`: at least one law reads a condition. The
  `environment_response_model` column lists the laws as `condition:law`
  pairs.
- `condition_specific_parameters`: no law is bound, but the parameter records
  are scoped to the environment.
- `metadata_only`: neither; the same constants were used for every
  environment.

Comparison, ranking and response plots across environments are allowed only
when every condition that varies across the screened environments is covered
by an active law or by condition-specific records. A grid that varies
temperature for a case whose only law reads pH keeps
`active_response_model` but blocks ranking, and the guardrail names the
uncovered condition. `limitations_table.csv` carries an `environment_effect`
row in every case and a `ph_response` row for the pH-ionization law.

`EnvironmentGrid` values become in-memory environment records. The grid's
own `environment_effect_status` is the status before assembly; the assembled
case decides. Condition-specific parameter records are reused for grid cases
only when they belong to a single registry environment; records that differ
only by environment (the three *T. harzianum* cellulose loadings) are not
copied, and the grid case reports the role as missing rather than choosing
one condition's value. Cases outside a law's declared measured range still run, with
the validity warning raised and recorded, so that an extrapolation is
visible rather than silent.

## The sourced case: BGL1A on cellobiose, pH 4 to 8

*Phanerochaete chrysosporium* K-3 GH1 beta-glucosidase BGL1A (recombinant,
UniProt Q25BW5) on cellobiose is the first registry case with an active
response law. SABIO-RK Reaction 618 entry 38522 deposits the pH-dependent
Michaelis-Menten law of Tsukada, Igarashi, Fushinobu and Samejima (2008,
Biotechnol Bioeng 99:1295-1302, PMID 18023045), fitted over pH 4 to 8 at
30 degrees Celsius in sodium acetate, MES, HEPES and EPPS buffers. The raw
export is archived with its SHA-256 and the registry copies the constants
verbatim:

| Record | Symbol | Value | Deposited deviation |
| --- | --- | --- | --- |
| `tsukada_2008_bgl1a_k0_cellobiose` | `k0` | 1.81 /s | 0.05 /s |
| `tsukada_2008_bgl1a_Km0_cellobiose` | `Km0` | 6.8 mM | 0.29 mM |
| `tsukada_2008_bgl1a_pKe1` | `pKe1` | 4.4 | 0.2 |
| `tsukada_2008_bgl1a_pKe2` | `pKe2` | 7.7 | 0.2 |
| `tsukada_2008_bgl1a_pKes1` | `pKes1` | 4.1 | 0.1 |
| `tsukada_2008_bgl1a_pKes2` | `pKes2` | 7.6 | 0.1 |
| `tsukada_2008_bgl1a_ph_series_minimum` / `_maximum` | measured range | 4.0 / 8.0 | not applicable |

The entry records no substrate or enzyme concentration, so the assay loadings
(5 mM cellobiose, 1 micromolar enzyme) are explicit `exploratory_prior`
assumptions. The case therefore runs in `exploratory` mode only; `scientific`
mode is blocked and names the two assumed symbols. Five registry environments
(`tsukada_2008_bgl1a_assay_30c_ph4` to `_ph8`) or an `EnvironmentGrid` over
pH drive the law; the time to 50 percent cellobiose conversion is shortest at
pH 6 and longest at pH 8 among the registry points, and the trajectory at
pH 5 reproduces an independent integration of the deposited formula
(`tests/test_bgl1a_ph_response_case.py`). Temperature is the 30 degree set
point of the source and stays metadata.

What the case is not: a whole-fungus, secretion, uptake or wood-decay model;
a validated prediction of any time course (the source reports initial rates);
a statement about buffer or ionic-strength effects.

## What is implemented but not yet bound to an organism

The cardinal temperature and pH laws and the thermal inactivation law are
implemented, compiled and tested with artificial values, but no shipped case
binds them. The repository holds no sourced cardinal temperatures, cardinal pH
values, or inactivation energies for *T. harzianum* P49P11 or for the
cellulase and beta-glucosidase activity pools of the Gelain 2020 cultures:
the Gelain fit sits at one condition (29 degrees Celsius, pH 5) and its
activity-loss constants are effective losses at that condition, not thermal
inactivation constants. Literature retrieval for those values was not
possible in the session that added the laws (the network policy denied every
publisher host); the candidate sources found by search are listed in
`data/experiments/candidate_reviews/trichoderma_harzianum_cardinal_growth_review.yml`
with status `proposed` and no transcribed numbers. Until such records exist,
every *T. harzianum* case keeps `environment_effect_status: metadata_only` and
its limitation rows say so.

To bind a law to an organism: archive the source with a checksum under
`data/experiments/`, author `literature_processed` parameter records for each
role with the measured range, add the roles to the compatibility record, list
the modifier or process law in the template, and add a test that pins the
records to the archived source and checks the assembled response.
