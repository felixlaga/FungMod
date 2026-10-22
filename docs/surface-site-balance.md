# Surface area law and enzyme-site balance

This page documents two additions to the generic surface-catalysis layer
(`fungal_model.processes.surface`), made in audit work package WP3:

1. a selectable **accessible-area law** on `SurfaceCatalysisProcess`, with an
   analytic Jacobian for both laws;
2. a new process, `SiteBindingSurfaceCatalysisProcess`, that closes the
   enzyme balance over accessible attack sites.

Neither changes a default trajectory. The default area law is still
`constant_until_depletion`; the site-binding process is opt-in by
`process_type`.

## Why

The audit (kinetics F1, F2, F3, F12; processes F8; fungi 5) showed that the
surface rate `v = k_s theta A` was zeroth order in substrate and stepped to
zero at depletion. On a 1 mg film the default LSODA run needed 419,575
right-hand-side evaluations, RK45 overshot to -0.4 percent of the loading and
failed `validate_non_negative`, and the finite-difference Jacobian reported
-0.25/s to -0.5/s near the step where the true derivative is 0. The model also
had no enzyme balance: `theta` was computed from the enzyme state as if none
were bound, so coverage did not depend on how much surface the enzyme was
spread over.

## Accessible-area laws

`AccessibleSurfaceAreaModel.area_model` selects the law.

### `constant_until_depletion` (default, unchanged)

`A = A_0` for any positive substrate amount; the process sets the rate to zero
at or below zero. The right-hand side is discontinuous at depletion. The
process records this in `validity.limitations`
(`area_model=constant_until_depletion: ...`), in `validity.labels` and in
`to_dict()["area_model"]`, so a limitations table shows the switch. The
analytic Jacobian reports `dv/dm = 0` (the step has no derivative) and
`dv/dE = k_s A_0 K/(1 + K E)^2` for `m > 0`.

### `mass_scaled`

```text
A(m) = A_0 (m / m_0)^n
v    = k_s theta A(m),  theta = K E / (1 + K E)
```

`m_0` is the loading at which `A_0` applies (parameter `reference_mass`,
substrate units) and `n` is a geometry exponent (parameter `area_exponent`,
dimensionless). Both are parameters with provenance; the package ships no
value. Sourced choices:

* `n = 1`: a film that thins uniformly, or the substrate-reactivity factor of
  Kadam, Rydholm and McMillan (2004), *Biotechnol Prog* 20:698, which is linear
  in remaining substrate.
* `n = 2/3`: an isotropically shrinking particle (area proportional to
  mass^(2/3)).

The rate is continuous and zero at `m = 0`. Derivatives used by the compiled
Jacobian:

```text
dv/dm = n v / m                       (m > 0)
dv/dm at m = 0: k_s theta A_0 / m_0   (n = 1), 0 otherwise (n < 1 is unbounded; 0 is the documented finite choice)
dv/dE = k_s A(m) K / (1 + K E)^2
```

Maturity: `literature_backed_software_tested`. Limitation recorded on the
process: crystallinity, amorphous-fraction and pore-accessibility evolution
are not represented (deferred; see the audit's kinetics F3).

Config keys on a `surface_catalysis` process:

```yaml
parameters:
  adsorption_constant: K_ads
  surface_rate_constant: k_surface
  accessible_surface_area: A_0
  area_model: mass_scaled        # default: constant_until_depletion
  reference_mass: m_0            # required for mass_scaled
  area_exponent: n_area          # required for mass_scaled
```

The factory refuses `mass_scaled` without `reference_mass` or
`area_exponent`, refuses unknown `area_model` names, and refuses stray
`reference_mass`/`area_exponent` keys under the constant law.

Python:

```python
AccessibleSurfaceAreaModel.mass_scaled(
    name="...", area=Q_(1.0, "meter ** 2"),      # or parameter_symbol="A_0"
    reference_mass_symbol="m_0", exponent_symbol="n_area",
)
```

### Effect on the audit case

1e-6 kg, `K = 1 L/mol`, `E = 1 mol/L`, `k_s = 1e-6 kg/m^2/s`, `A_0 = 1 m^2`,
10 s, default tolerances:

| Law | Solver | nfev | min m (kg) | non-negative validator |
| --- | --- | --- | --- | --- |
| constant (default) | LSODA | 419,575 | -2.9e-12 | pass |
| constant (default) | RK45 | 152 | -3.7e-9 | fail |
| mass_scaled, n = 1 | LSODA | 45 | 6.7e-9 (exact decay) | pass |
| mass_scaled, n = 1 | BDF | 80 | 6.8e-9 | pass |
| mass_scaled, n = 1 | RK45 | 50 | 6.7e-9 | pass |
| mass_scaled, n = 2/3 | LSODA | 72 | -1.8e-12 | pass |

For `n < 1` the rate has a cusp at `m = 0` (finite depletion time), and
explicit solvers overshoot by a small amount within the validator's tolerance.

## Enzyme-site binding process

`SiteBindingSurfaceCatalysisProcess` (`process_type:
site_binding_surface_catalysis`) states: total enzyme `E_T` (concentration,
conserved by the process), substrate amount `m`, and the products of the
product map. Parameters: `a_s` (attack sites per substrate amount, mol per
substrate unit), `K_d` (enzyme units), `k_cat,s` (1/s), `V` (liter).

```text
S_0   = a_s m / V
Sigma = E_T + S_0 + K_d
Delta = sqrt(Sigma^2 - 4 E_T S_0)
E_b   = (Sigma - Delta) / 2          evaluated as 2 E_T S_0 / (Sigma + Delta)
v     = k_cat,s E_b V / a_s          (substrate amount per time)
```

Limits: `E_T << S_0` gives the conventional Michaelis-Menten form in sites,
`v -> k_cat,s E_T S_0 / (K_d + S_0) V / a_s`; `S_0 << E_T` gives the inverse
form, `v -> k_cat,s m E_T / (K_d + E_T)`. Sources: Andersen, Kari, Borch and
Westh (2018), *Math Biosci* 296:93; Kari, Andersen, Borch and Westh (2017),
*ACS Catal* 7:4904. Maturity: `literature_backed_software_tested`.

Analytic Jacobian:

```text
dE_b/dE_T = (1 - (Sigma - 2 S_0)/Delta) / 2
dE_b/dS_0 = (1 - (Sigma - 2 E_T)/Delta) / 2      (both 0 when Delta = 0)
dv/dE_T   = k_cat,s V/a_s dE_b/dE_T
dv/dm     = k_cat,s dE_b/dS_0                     (dS_0/dm = a_s/V)
```

An unknown `a_s` (a `Parameter` with `value: null`) stays unknown: the rate
raises `UnknownParameterError`, and the modelability preflight reports it. It
is never derived from an accessible area.

Config:

```yaml
- id: solid_site_binding_cleavage
  process_type: site_binding_surface_catalysis
  states: {enzyme: E_total, substrate: solid_mass}
  parameters:
    sites_per_mass: a_s
    dissociation_constant: K_d
    site_turnover: k_cat_s
    volume: V_liquid
    rate_units: kilogram / second
  product_map: release_map
  primary_source: "Andersen et al. 2018 Math Biosci 296:93; Kari et al. 2017 ACS Catal 7:4904."
  maturity: literature_backed_software_tested
```

The factory refuses a missing `sites_per_mass`, a blank `primary_source`, any
other maturity label, a product map that does not consume the substrate, and
a product map that touches the enzyme state.

Limitations recorded on the process: equilibrium binding to one site class;
no adsorption/desorption dynamics, product inhibition, non-productive binding
or site renewal; `a_s` constant per unit remaining substrate.

## Helpers

* `fungal_model.kinetics.langmuir.langmuir_coverage_derivative`:
  `d theta/dE = K/(1 + K E)^2`.
* `fungal_model.kinetics.site_binding`: `site_binding_bound_enzyme`,
  `site_binding_bound_enzyme_derivatives` (unit-aware) and the float kernels
  `bound_enzyme_magnitude`, `bound_enzyme_derivative_magnitudes`. Both
  unit-aware functions are re-exported from
  `fungal_model.kinetics.surface_kinetics`.

## Tests

`tests/test_surface_site_balance.py` and additions to
`tests/test_generic_surface_processes.py`: the depletion case with LSODA, BDF
and RK45 (nfev < 2000, no negative mass beyond atol, validator passes, exact
decay for n = 1 and the finite depletion time for n = 2/3); compiled Jacobian
against Richardson-extrapolated differences at interior states and at
`m = 0`; the constant law recorded in `to_dict()`; site binding reaching both
limits within 1e-3 at ratio 1e-3, `E_T` constant to 1e-12, Jacobian against
Richardson including zero states; non-PET, non-cellulose dummy names; factory
refusals.
