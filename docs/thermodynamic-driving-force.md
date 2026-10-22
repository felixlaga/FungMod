# Thermodynamic driving force

The dynamic Gibbs constraint couples one forward process rate to the reaction
Gibbs energy evaluated on the trajectory. It has two enforcement modes. The
legacy mode gates the rate; the driving-force mode scales it continuously.

## Equations

Symbols: `c_k` concentration of a bound state in standard units, `c0` the
standard concentration, `a_min` the activity floor, `nu_k` the signed
stoichiometric coefficient, `R` the gas constant, `T` the temperature in kelvin.

```
a_k   = max(c_k / c0, a_min)        trajectory participant
a_k   = a_fixed,k                   fixed participant (declared, sourced)
ln Q  = sum_k nu_k ln a_k
dG    = dG0(T) + R T ln Q
```

`block_unfavorable_forward_rate` (legacy, default): `r = r_fwd * 1[dG < -tol]`.

`driving_force`: `r_net = r_fwd * phi`, `phi = 1 - exp(dG / (R T))`.
`phi` is 1 far from equilibrium, 0 at equilibrium, and negative above it, so
`r_net < 0` is reverse net flux (Beard and Qian 2007, PLoS ONE 2:e144; Noor et
al. 2013, FEBS Lett 587:2772). The analytic gradient is
`d phi / d y_k = -exp(dG / (R T)) nu_k / y_k` where the floor is inactive and 0
where the floor is active or the participant is fixed.

Temperature dependence of the standard energy is optional. With both
`standard_enthalpy` (`dH0`) and `reference_temperature` (`T_ref`) declared:

```
dG0(T) = dH0 - T (dH0 - dG0(T_ref)) / T_ref
```

This is the constant-enthalpy Gibbs-Helmholtz form (Tewari and Goldberg 1989,
J Biol Chem 264:3966; Du et al. 2018, Biophys J 114:2691). Without both keys
the declared `dG0` is used at every temperature and the constraint record says
`temperature_dependence: none_declared`.

## Configuration

```yaml
thermodynamic_constraints:
  - id: hydrolysis_dynamic
    process_id: hydrolysis
    reaction_id: hydrolysis_reaction
    electron_balance_check_id: hydrolysis_electron_balance
    enforcement_mode: driving_force        # or block_unfavorable_forward_rate
    standard_energy:
      method: standard_delta_gibbs
      standard_delta_gibbs: {...}          # J/mol at reference_temperature
      standard_enthalpy: {...}             # optional, J/mol; needs reference_temperature
      reference_temperature: {...}         # optional, kelvin; needs standard_enthalpy
    activity_model:
      type: ideal_dilute_concentration_ratio_with_explicit_floor
      standard_concentration: {...}
      minimum_activity: {...}
      fixed_activities:                    # optional
        water:
          value: 1.0
          source: Biochemical standard state, unit solvent activity.
    temperature: {...}
    gas_constant: {...}
    absolute_tolerance: {...}
    provenance_refs: [...]
```

Every `{...}` is a full parameter record (name, symbol, value, units, source,
confidence_level, measurement_method). `fixed_activities` keys are species ids
of the bound reaction; each needs a positive value and a nonblank source. A
fixed participant binds no state (`state_name: ""`), contributes a constant to
`ln Q`, and is reported under its species id in `activities`.

## What `absolute_tolerance` does

In driving-force mode the tolerance only sets the recorded `favorable` flag
(`dG < -tol`); the rate is always `r_fwd * phi`.

In block mode the tolerance is part of the gate. A positive tolerance therefore
creates a dead zone: an exergonic reaction with `|dG| < tol` is blocked. This
legacy behaviour is kept and recorded in the constraint's assumption records.

## Recorded outputs

Each evaluation records activities, `ln Q`, `Q`, `dG0(T)`, `dG`, `favorable`,
and `rate_blocked`. In driving-force mode it also records
`driving_force_factor` (`phi`) and `rate_blocked` is always `False`. The
constraint record (`to_dict()`) adds `temperature_dependence`,
`standard_enthalpy`, `reference_temperature`, `reverse_saturation:
not_represented`, `maturity`, `law_provenance`, and `assumptions`.

Maturity of the driving-force law: `literature_backed_software_tested`.

## Limitations

- The reverse flux inherits the forward law's saturation. For a saturable
  forward law (Michaelis-Menten) the result is not Haldane-consistent near and
  above equilibrium; a reversible modular law is a separate, deferred family.
- A forward law that vanishes at zero reactant gives `r_net = 0` there, so a
  reactant-free boundary state is a fixed point in both modes. This fixed
  point is an artefact of the activity floor (which caps `1 / a_reactant`
  inside `phi`) combined with a forward law that vanishes at zero reactant.
  It is not physics: the reversible limit at `A = 0` would be
  `r_net -> -k B / K`. Start such a reaction with the reactant above the
  activity floor, and do not let an analytic kernel inherit the fixed point
  silently.
- A species listed in `fixed_activities` that also binds a trajectory state
  keeps that state integrated by the solver while the constraint ignores it.
  The participant record carries `overridden_state_name` and the
  `fixed_activity_participants` assumption names the ignored state.
- Activities are ideal-dilute ratios with an explicit floor; no activity
  coefficients, no pH or ionic-strength transform, no pMg.
- `dG / (R T) > 700` is refused (`ValueError`) rather than overflowing.
- In the compiled core, driving-force mode currently runs through the
  unit-aware `enforce` path with finite-difference gradients; the numeric
  kernel with the analytic gradient from `compile_rate_factor` is integrator
  wiring for the compiled-core package.

## Detailed-balance equilibrium

`DetailedBalanceNetwork.equilibrium` now scales each conservation residual
`w_j . c - w_j . c_0` by `|w_j| . c_0`, after row-reducing the null-space
basis so that each residual row is one pivot species. For a nonnegative row
the scale is the pool total, so a 1e-12 M pool next to a 1 M pool is
conserved to machine precision instead of passing with a 10 percent error.
Reduced rows may carry negative entries (`A <-> B + C` conserves `B - C`),
whose signed total is legitimately zero when `B_0 = C_0`; the
absolute-coefficient scale stays strictly positive for every row because the
solver already requires `c_0 > 0`, so no floor constant is involved.
