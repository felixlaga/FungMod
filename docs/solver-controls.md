# Solver controls

The compiled well-mixed core (`fungal_model.solvers`) integrates
`dy/dt = N v(t, y)` with `scipy.integrate.solve_ivp`. This page documents the
controls a model config can set, how the compiled Jacobian is assembled, and
what the solver records. It describes numerical behaviour only; no rate law,
parameter or biological claim lives here.

## The `solver` block

A model config may carry an optional top-level `solver` block. Every key is
optional; an absent key keeps the `SolverSettings` default. Unknown keys and
invalid values are refused when the config is loaded.

```yaml
solver:
  method: BDF            # LSODA (default), BDF, Radau, DOP853, RK45, RK23
  rtol: 1.0e-9           # default 1.0e-8
  atol:                  # a number (each state's own units) or one entry per state
    dissolved_substrate_amount: {value: 1.0e-12, units: kilogram}
    released_product_amount: {value: 1.0e-12, units: kilogram}
  max_step: {value: 0.5, units: second}
  first_step: {value: 1.0, units: millisecond}
  jacobian: compiled     # finite_difference_by_backend (default) or compiled
```

`ModelConfig.solver` holds the parsed `SolverConfig`;
`SolverConfig.to_solver_settings()` and `SolverSettings.from_config()` turn it
into the settings the assembled model carries. The configured-model runner, the
screening path and the calibration predictor all assemble through
`ConfiguredProcessAssembler`, so one block governs every public entry point of
a config. The recorded `solver_settings.json` of a run shows the settings that
were used.

### Why per-state absolute tolerances matter

SciPy's error control is local: `atol_i + rtol * |y_i|`. The default scalar
`atol = 1e-10` is applied in whatever unit each state declares. The same
nanomolar Michaelis-Menten model is therefore controlled by `atol` when its
states are declared in mol/L (0.1 percent of a 100 nM substrate) and by `rtol`
when they are declared in micromolar; the audit measured a 2.2 percent
trajectory error in the first case and 4e-8 in the second. A per-state `atol`
with units removes the dependence on the declared unit: with
`atol = 1e-20 mol/L` on every state the three unit systems agree to better
than 1e-11 (`tests/test_solver_numerics.py`). The defaults are unchanged, so
recorded trajectories do not move; declare tolerances in the block when trace
states matter.

## The compiled Jacobian

`jacobian: compiled` makes the implicit methods (LSODA, BDF, Radau) use
`CompiledModel.jacobian`, assembled from one gradient kernel per process:

- **Analytic** where the process offers `compile_jacobian`: first-order
  decay, mass action, both Michaelis-Menten forms, proportional synthesis, the
  Pirt closure processes, the exchanges, and since this change thermal
  inactivation (`dv/dA = k_d(T)`), pH-ionization Michaelis-Menten
  (`dv/dS = kcat(pH) E Km(pH) / (Km(pH) + S)^2`, `dv/dE = kcat(pH) S / (Km(pH) + S)`)
  and substrate transglycosylation (with `D = Km_h + S + S^2/Km_t`:
  `dr_h/dS = E kcat_h (Km_h - S^2/Km_t) / D^2`,
  `dr_t/dS = E kcat_t (S/Km_t)(2 Km_h + S) / D^2`, `dr/dE = kcat_x (branch numerator) / D`).
- **Finite differences** of the process's own kernel otherwise (modifier-wrapped
  processes, surface catalysis, quantity-wrapped processes). The kind of every
  process is recorded under `solver_metadata["kernel"]["jacobian_kernels"]`.

### Finite-difference step

The step of state `i` is

```text
h_i = eps^(1/3) * max(|y_i|, sigma_i),    sigma_i = atol_i / rtol  (state units)
```

with `eps` the machine epsilon; central differences unless `y_i - h_i < 0`,
then one-sided so the rate is never evaluated below zero. The cube root of
`eps` balances the truncation and roundoff errors of a central difference
(Nocedal and Wright, *Numerical Optimization*, 2nd ed., Springer 2006, section
8.1), and `atol_i / rtol` is the threshold SciPy's own `num_jac` uses. The
earlier step `1e-6 * max(|y_i|, 1)` was blind to units: for a state in mol/L
it perturbed by 1 µM, and the gradient of a Michaelis-Menten rate at 100 nM
substrate was 9 percent wrong. With the scaled step the same gradient is
within 4e-5 at the default tolerances and within 4e-9 with `atol = 1e-12 mol/L`.
Without settings the default scales are `1e-10 / 1e-8 = 1e-2`, the ratio of
the `SolverSettings` defaults. `CompiledModel.summary()` records
`finite_difference_scales` and `finite_difference_relative_step`.

### Thermodynamically constrained processes

A process bound to a dynamic Gibbs constraint evaluates `v = v_num * phi`,
where `phi` is the blocking indicator `1[dG < -tol]` (or, where a constraint
compiles a rate factor, that factor). Its gradient follows the product rule

```text
grad v = phi * grad v_num + v_num * grad phi      (grad phi = 0 when not offered)
```

and `grad v_num` is the numeric kernel's own gradient (analytic if offered,
finite differences of the unblocked kernel otherwise). The indicator is never
differenced: before this change the Jacobian of the showcase constraint carried
a spike of 25000 on the switching surface, and Radau with the compiled Jacobian
needed 4.2 million right-hand-side evaluations against 670 for the backend.
Now the Jacobian equals the one-sided limit on each side of the surface and
the compiled Jacobian costs no more than the backend's finite differences
(`tests/test_compiled_jacobian.py`). The rule is recorded as
`constraint_gradient_rule` in the kernel summary.

A constraint that compiles neither a rate factor nor a feasibility kernel can
only be evaluated through its unit-aware `enforce`. Its process is recorded
with the Jacobian kind `refused_constraint_without_numeric_factor`, and
evaluating the compiled Jacobian raises instead of differencing the
constraint. The right-hand side is unaffected. No shipped constraint takes
this path.

## What is recorded

`solver_metadata["kernel"]` (also `ProcessODESolver.kernel_summary(request)`)
carries `jacobian` (`finite_difference_by_backend` or
`compiled_process_gradients`, according to the settings and the method),
`jacobian_kernels`, `analytic_jacobian_count`, `finite_difference_scales`,
`finite_difference_relative_step`, `constraint_gradient_rule` and the
unchanged kernel and negativity-policy entries. One helper,
`fungal_model.solvers.process_ode.integrate_compiled`, turns the settings into
`solve_ivp` options for both `ProcessODESolver.run` and the calibration
predictor, so a requested compiled Jacobian is never dropped silently.

## Limitations

- No event location at depletion or at a thermodynamic switch; the trajectory
  may overshoot zero within tolerance and the validators report it.
- No forward parameter sensitivities; calibration gradients still use
  finite differences of trajectories.
- No automatic check that a scalar `atol` is tight enough for the declared
  state units; declare per-state tolerances when in doubt.
- Surface catalysis and modifier-wrapped processes still use finite-difference
  gradients.
