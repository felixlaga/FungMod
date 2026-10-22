# Extended environment laws: cardinal water activity and enzyme temperature optima

Three environment laws were added by audit work package WP5. They sit next to
the laws on the [environment response](environment-response.md) page and
follow the same rules: an environment is static, each law reads one condition,
the activity is folded into a constant kernel at build time, every parameter
is a sourced record, and no value ships with the code.

## Why

The audit found two gaps. The only water-activity law was a unit step, while
the mould literature uses a smooth cardinal response (Rosso and Robinson
2001). The only enzyme-level temperature law was monotone Arrhenius, so an
enzyme could show an optimum only by running irreversible inactivation long
enough. Two optimum-type laws with published parameter meanings fill that gap.

## Laws

| Law | Reads | Equation | Parameters (roles) | Source of the law |
| --- | --- | --- | --- | --- |
| `water_activity_cardinal_rosso` | water activity | CM_2: `gamma = (a_w - a_w,max)(a_w - a_w,min)^2 / {(a_w,opt - a_w,min)[(a_w,opt - a_w,min)(a_w - a_w,opt) - (a_w,opt - a_w,max)(a_w,opt + a_w,min - 2 a_w)]}`, zero outside `(a_w,min, a_w,max)` | `minimum_water_activity`, `optimum_water_activity`, `maximum_water_activity` | Rosso L, Robinson TP (2001) Int J Food Microbiol 63:265-273 |
| `temperature_sharpe_schoolfield` | temperature | `a(T) = exp[-(E_a/R)(1/T - 1/T_ref)] D(T_ref)/D(T)`, `D(T) = 1 + exp((dH_H/R)(1/T_H - 1/T)) [+ exp((dH_L/R)(1/T - 1/T_L))]` | `activation_energy`, `reference_temperature`, `high_inactivation_enthalpy`, `high_half_inactivation_temperature`; optional `low_inactivation_enthalpy` and `low_half_inactivation_temperature` (both or neither); optional measured bounds | Schoolfield RM, Sharpe PJH, Magnuson CE (1981) J Theor Biol 88:719-731 |
| `temperature_equilibrium_model` | temperature | `a(T) = exp[-(E_a/R)(1/T - 1/T_ref)] f(T)/f(T_ref)`, `f(T) = 1/(1 + exp((dH_eq/R)(1/T_eq - 1/T)))` | `activation_energy`, `reference_temperature`, `equilibrium_enthalpy`, `equilibrium_temperature`; optional measured bounds | Peterson ME, Daniel RM, Danson MJ, Eisenthal R (2007) Biochem J 402:331-337 |

`R` is `UNIVERSAL_GAS_CONSTANT`. All three laws carry the maturity label
`literature_backed_software_tested`: the law is published and tested, the
parameter values are not supplied here.

### Cardinal water activity

The expression is the order-two cardinal model (CM_2) of the Rosso family,
the same algebra as the CTMI temperature law. `kinetics/cardinal.py` now holds
it once as `cardinal_cm2_activity(x, x_min, x_opt, x_max)`, and the CTMI
delegates to it. Rosso and Robinson fix `a_w,max` at 1.0 (pure water). FungMod
does not hard-code that: `maximum_water_activity` is a required parameter
record whose value and source say so. The law refuses `a_w,opt < (a_w,min +
a_w,max)/2` (the denominator would change sign inside the range), cardinal
values or environment values outside `[0, 1]`, and unordered cardinals. The
threshold law `water_activity_threshold` stays available with its own
limitation text.

### Sharpe-Schoolfield

Arrhenius activation divided by a reversible inactivation sum, normalised to
one at `T_ref` so a rate constant measured at `T_ref` keeps its meaning.
`T_H` is the temperature at which the high-temperature term alone halves the
activity; the optional low-temperature pair `(dH_L, T_L)` adds the second term
of the 1981 paper with the exponent sign reversed, so both enthalpies are
entered as positive magnitudes. The `T/T_ref` pre-factor of the original
expression is absorbed into the Arrhenius term, as in current
parameterisations of this law. The sums are evaluated in log space, so extreme
temperatures give zero rather than overflow.

### Equilibrium Model

`f(T)` is the active fraction of a rapidly reversible active/inactive
transition with midpoint `T_eq` (`f(T_eq) = 0.5`) and enthalpy `dH_eq`. The
modifier multiplies `f` by Arrhenius activation and normalises at `T_ref`.
Algebraically this equals the high-temperature Sharpe-Schoolfield form with
`dH_H = dH_eq` and `T_H = T_eq`; the two types are kept separate because the
published parameter meanings and sources differ. Irreversible inactivation
is not part of either law; it stays in the `thermal_inactivation` process.

## Composition

Both temperature laws include their own Arrhenius term and normalise at
`T_ref`. A process therefore carries exactly one temperature law; do not stack
them on `temperature_arrhenius_reference`. Each modifier declares
`condition` (`temperature` or `water_activity`) and `read_states = ()` for
the condition guard, and folds through `constant_activity_kernel`.

## Binding in a registry template

```yaml
modifiers:
  - type: water_activity_cardinal_rosso
    minimum_water_activity_role: growth_minimum_water_activity
    optimum_water_activity_role: growth_optimum_water_activity
    maximum_water_activity_role: growth_maximum_water_activity
  - type: temperature_sharpe_schoolfield
    activation_energy_role: activation_energy
    reference_temperature_role: reference_temperature
    high_inactivation_enthalpy_role: high_inactivation_enthalpy
    high_half_inactivation_temperature_role: high_half_inactivation_temperature
    # optional, both or neither:
    low_inactivation_enthalpy_role: low_inactivation_enthalpy
    low_half_inactivation_temperature_role: low_half_inactivation_temperature
    # optional measured bounds:
    minimum_temperature_role: measured_minimum_temperature
    maximum_temperature_role: measured_maximum_temperature
  - type: temperature_equilibrium_model
    activation_energy_role: activation_energy
    reference_temperature_role: reference_temperature
    equilibrium_enthalpy_role: equilibrium_enthalpy
    equilibrium_temperature_role: equilibrium_temperature
```

Assembly requires an exact registry environment condition for the condition
each law reads, as for every other environment law. A declared measured range
produces an `EnvironmentalValidityWarning` when the case lies outside it; an
undeclared range produces nothing, so declare one.

## Tests

`tests/test_water_activity_cardinal.py`: the generic CM_2 equals the CTMI
module on one cardinal triple; one at the optimum; zero at and beyond the
bounds; domain refusals; unit-aware and compiled parity on a first-order
benchmark; config builder; template role builder emits the dict and refuses a
missing or unresolved role.

`tests/test_temperature_optimum_laws.py`: `a(T_ref) = 1` for both laws;
decreasing above `T_H`; `f(T_eq) = 0.5` and monotone; closed-form grid
agreement including the low-temperature term; Celsius and kilojoule input;
folded constants equal `activity`; warnings only outside declared bounds; the
Equilibrium Model equals the high-only Sharpe-Schoolfield form; builders refuse
half pairs and missing roles.

## Limitations

All three are time-zero, growth-level or enzyme-level shapes. None models
solute identity, hysteresis, moisture gradients, unfolding kinetics,
irreversible denaturation, thermal history, or an interaction between
conditions beyond the multiplicative gamma concept. No parameter value is
shipped: every case must bind sourced records.
