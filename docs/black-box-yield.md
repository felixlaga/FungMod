# Black-box yield: degree of reduction, conditioning, dissipation

This page documents the WP7 macrochemistry layer: how FungMod derives electron
balances from composition, how it decides a conservation solve is numerically
trustworthy, and how it predicts a biomass yield from a stated Gibbs energy
dissipation. Everything here is a constraint or an empirical correlation. None
of it predicts a rate.

## Degree of reduction

`fungal_model.chemistry.degree_of_reduction(composition, charge, nitrogen_reference="ammonia", per_carbon=False)`
returns, per formula unit,

```
gamma = 4 C + H - 2 O - 3 N + 5 P + 6 S - z
```

with H2O, CO2, NH3, H3PO4, H2SO4 and the proton as the zero references
(Roels 1983; Heijnen and Kleerebezem 2010). `per_carbon=True` divides by the
carbon count. Hand values: glucose 24 (4 per C-mol), CH1.8O0.5N0.2 biomass 4.2,
O2 -4, CO2, H2O, NH4+ and HCO3- all 0.

Refusals: an element outside C, H, O, N, P, S; a nitrogen reference other than
`"ammonia"`; `per_carbon=True` on a carbon-free species; a non-finite charge.

Helpers:

- `electron_equivalents_from_composition(composition, charge)` is the degree
  of reduction per formula unit, so a conserved reaction satisfies
  `sum_j nu_j gamma_j = 0`.
- `assign_electron_equivalents(reaction)` fills every `StoichiometricTerm`
  with composition-derived electron equivalents so `validate_electron_balance`
  can run without typed values. Every term must carry a composition and a charge.
- `OxygenDemand.from_degree_of_reduction(...)` gives the oxygen demand per C-mol
  substrate, `(gamma_S - Y_SX gamma_X) / 4`, on an explicit `"amount"` basis
  (mole O2 per mole substrate carbon). A yield that would need negative oxygen
  is refused. The identity assumes every other participant has zero degree of
  reduction under the ammonia reference.

`ElementalComposition.from_formula` now refuses symbols that are not IUPAC
element symbols (`ELEMENT_SYMBOLS`, 118 elements). Parentheses and hydrates
remain unsupported; use `from_elements` for fractional biomass formulas.

## Conditioning and residual scale in `MacrochemicalBalance.solve`

The solve records on every `MacrochemicalSolution`:

- `condition_number` and `smallest_singular_value` of the free-column
  conservation matrix (`None` when nothing is free), also in `to_dict()`.
- `residual_scale` (reported as `scale_value`) and `absolute_tolerance`.

A solve is refused when the condition number exceeds
`DEFAULT_MACROCHEMICAL_MAX_CONDITION_NUMBER` (a declared `Parameter`, 1e8) or
the caller's `max_condition_number`. Before this guard, two species that
differed by 1e-13 in nitrogen content produced coefficients of 1.7e12 and a
reaction that lost 4.9e-4 hydrogen atoms per event was returned as conserved.

Residual acceptance is now `max|r| <= tol * scale` with
`scale = max(1, max_j |nu_j| max_e a_ej)`, the largest single term in any
conservation sum. The static validators `validate_elemental_balance`,
`validate_charge_balance` and `validate_electron_balance` use the same rule and
report `scale_value`, `effective_tolerance` and `max_relative_residual`, so a
solved reaction passes or fails both layers consistently. A polymer
C60000H100002O50001 oxidation passes both; an injected 1e-6 atom imbalance
fails both.

`reaction_gibbs()` and `reaction_enthalpy()` skip species whose coefficient is
numerically zero and which lack that formation energy, and record them under
`omitted_zero_coefficient_species` in `to_dict()`. A species with a nonzero
coefficient and no energy is still refused.

## Gibbs energy dissipation yield

The reversible limit (`solve_for_reaction_gibbs` with target 0) is a ceiling,
not a prediction: for aerobic glucose growth it gives about 1.0 Cmol/Cmol
against measured fungal yields near 0.6. The standard black-box prediction is
the dissipation correlation of Heijnen and van Dijken (1992, Biotechnol Bioeng
39:833; Heijnen, van Loosdrecht and Tijhuis 1992, Biotechnol Bioeng 40:1139;
compared in Liu et al. 2007, Thermochim Acta 458:38):

```
D_e [kJ / Cmol X] = 200 + 18 (6 - C)^1.8 + exp{ [(3.8 - gamma_S)^2]^0.16 (3.6 + 0.4 C) }
```

with `C` the carbon atoms per substrate molecule and `gamma_S` the degree of
reduction per C-mol with ammonia as nitrogen reference. Glucose gives 236.

`heijnen_dissipation_per_cmol_biomass(carbon_atoms, degree_of_reduction_per_carbon)`
returns a sourced `Parameter` in kJ/mol and refuses inputs outside the
transcribed validity domain: 1 to 6 carbon atoms, degree of reduction 0 to 8,
ammonium nitrogen source, heterotrophic growth without reversed electron
transport, with a reported error of about 13 percent over yields of 0.01 to
0.80 Cmol/Cmol. `heijnen_dissipation_from_composition` evaluates it from a
composition. The constants are declared in `HEIJNEN_DISSIPATION_CONSTANTS`.

`DissipationYieldPrediction.predict(balance, biomass_species=..., substrate_species=..., dissipation_per_cmol_biomass=..., oxygen_species=None)`
solves the balance with biomass fixed at +1 formula unit, the substrate free,
and the reaction Gibbs energy set to `-D_e * C_X`. It reports:

- `yield_per_substrate`: `Y_SX = -1 / nu_S`, biomass formula units per
  substrate formula unit.
- `yield_per_carbon`: C-mol biomass per C-mol substrate.
- `carbon_ceiling_per_substrate`: `C_S / C_X`.
- `oxygen_per_cmol_biomass`: mole O2 per C-mol biomass, negative when consumed.

With the illustrative pH-7 energies from the audit record, the prediction is
0.669 Cmol/Cmol and 0.446 mol O2 per C-mol biomass, which matches the oxygen
demand from the electron balance to 1e-12. It refuses a non-consuming
substrate coefficient, a yield above the carbon ceiling, non-positive or
unsourced dissipation, and species missing from the balance. Maturity is
`literature_backed_software_tested`; the assumption record is
`heijnen_van_dijken_dissipation_correlation`.

## Carbon-limited Gibbs bound and yield caps

`GibbsEnergyYieldBound.validate_yield(declared, carbon_limit=None)` and
`enforce_yield` accept a `carbon_limit` on the same basis as the energies. The
effective ceiling is the smaller of the thermodynamic bound and the carbon
limit; `details["binding_limit"]` names which one. Without a carbon limit the
bound can still certify 3 Cmol/Cmol against a 4.78 ceiling; with
`carbon_limit=1` it rejects it.

`biomass_yield_coefficient` and `validate_biomass_yield_limit` no longer cap
yields at 1. A mass yield of 1.2 kg/kg on a light substrate or a C-mol-per-mole
yield is legitimate; whether a yield is admissible is a conservation or
energetics question, answered by the carbon limit or the dissipation
prediction.

## Limitations

- Formation energies are used as given for their declared conditions; no
  Alberty transform, no activity, pH or ionic-strength correction.
- The dissipation correlation is organism-independent and silent on ATP
  yields, maintenance, growth rate, product formation and nitrogen sources
  other than ammonium.
- Only the ammonia nitrogen reference is tabulated for the degree of reduction.
- `OxygenDemand` on the `"amount"` basis cannot be consumed by
  `validate_oxygen_limitation`, which works in kilograms; no molar mass is
  inferred.
