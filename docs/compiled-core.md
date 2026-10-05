# Compiled model core

Since CORE-001 the well-mixed process solver no longer evaluates unit-bearing
quantities inside the right-hand side. `ProcessODESolver` compiles the
assembled model once per run (`fungal_model.solvers.compile_assembled_model`)
into

```text
dy/dt = N v(t, y)
```

where `y` is the numeric state vector in the model's declared state units, `N`
is a stoichiometric matrix (states x processes) and `v` is the vector of
process rates, each in its process's own rate units. Every unit conversion
between rate units, state units and the integration time unit is resolved at
build time. The integrator then calls plain numpy code.

This is a numerical change only. No rate law, parameter, default, threshold or
biological claim was added; the compiled path reproduces the unit-aware
evaluation and is tested against it on every packaged model config.

## How a model is compiled

1. **State vector.** `resolve_state_units` orders the model's state variables
   and fails on conflicting units, exactly as before.
2. **Stoichiometry.** `Process.contributions` is probed at rates 0, 1 and 2 in
   the process's rate units. Each contribution is converted to
   `state units / time unit`, and the probe must be linear in the rate;
   otherwise compilation fails explicitly. A contribution to an unknown state
   fails with the same message the solver raised before.
3. **Rate kernels.** Each process is asked for a numeric kernel through
   `Process.compile_rate(context)`. The `KernelContext` carries the state
   index, state units, time unit, parameters, environment and geometry; it
   resolves parameter values and state conversion factors once. Rate modifiers
   compile their activity through `compile_activity`; environment-only
   modifiers (temperature, pH, oxygen, water activity) fold to a constant
   evaluated with the modifier's own `activity` method, so a source-range
   warning now fires once per run instead of at every evaluation.
4. **Thermodynamic blocking.** A process bound to a dynamic Gibbs constraint
   uses `DynamicThermodynamicConstraint.compile_feasibility`, a float
   re-implementation of `evaluate`; the kernel returns zero when the forward
   reaction is unfavorable. Activities, reaction quotients and Gibbs energies
   are still recorded at the returned time points through the unit-aware
   `enforce`, so the diagnostics are unchanged.

## Kernel kinds are recorded, never silent

`solver_metadata["kernel"]` records, for every process, which path evaluated
it:

| Kind | Meaning |
| --- | --- |
| `numeric` | Closure from `compile_rate`, plain floats. |
| `numeric_thermodynamic` | Numeric kernel plus compiled feasibility blocking. |
| `quantity_wrapped` | The process offered no kernel; its unit-aware `rate` runs on a reconstructed state. Exact, slow. |
| `quantity_wrapped_thermodynamic` | Wrapped evaluation followed by the constraint's unit-aware `enforce`. |

All five shipped process classes (`FirstOrderDecayProcess`,
`MassActionProcess`, `HomogeneousMichaelisMentenProcess`,
`SurfaceCatalysisProcess`, `SubstrateTransglycosylationProcess`) and all eight
modifiers compile to numeric kernels; `tests/test_compiled_process_models.py`
fails if any shipped mechanism falls back. A third-party `Process` that only
implements `rate`/`contributions` keeps working through the wrapped path.

Kernels raise the same parameter errors as the unit-aware path (a non-positive
`Km`, a negative rate constant). Solver trial iterates are a different matter:
constitutive laws are defined on the non-negative orthant, and an implicit or
multistep solver evaluates the right-hand side at predicted states that can sit
slightly below zero when a pool approaches depletion. The compiled model
therefore evaluates every rate at `max(state, 0)` and records
`negative_state_policy` in `solver_metadata["kernel"]`. This is the standard
non-negativity projection (Shampine et al., 2005) and the same zero extension
the culture classes use. The integrated state is never clipped: the returned
trajectory is whatever the solver accepted, and the `non_negative` validator
reports any accepted state below its tolerance. A caller that passes a negative
state to a process's unit-aware `rate` still receives a `ValueError`.
`SolverSettings`, `solve_checked`, tolerances and failure semantics are
unchanged.

## Measured effect

On the packaged configs, with identical trajectories and identical numbers of
right-hand-side evaluations (`nfev`) between the compiled and the unit-aware
evaluation:

| Config | Unit-aware solve | Compiled solve |
| --- | ---: | ---: |
| `alvarez_gonzalez_2022_free_beta_glucosidase_comparison` | 252 ms | 19 ms |
| `phanerochaete_bgl1b_cellobiose_transglycosylation` | 198 ms | 5 ms |
| `showcase_dynamic_thermodynamics` | 478 ms | 8 ms |
| `toy_homogeneous_competitive_inhibition` | 65 ms | 2 ms |
| `toy_surface_dummy_non_pet_product_inhibition` | 17 ms | 1 ms |

The per-sample cost of a registry ensemble is now dominated by writing the
per-sample output bundle, chiefly three matplotlib figures per sample
(about 0.55 s), not by integration. Reducing that is a separate, non-numerical
change to the screening output policy.

## Culture physiology on the compiled core

The well-mixed Pirt/Monod closure of the opt-in physiology classes and the
chemostat boundary exchanges are generic processes
(`fungal_model.processes.culture`), each with a numeric kernel, a factory and
config support:

| Process type | Rate (extent per volume and time) | Parameters |
| --- | --- | --- |
| `resource_limited_growth` | `(1 - f) Y max(q S/(K_S+S) O/(K_O+O) - m, 0) N/(K_N+N) X` | yield, maintenance demand, uptake capacity, three half-saturations, optional allocation fraction `f` |
| `resource_limited_maintenance` | `min(m, q S/(K_S+S) O/(K_O+O)) X` | the same closure constants |
| `costed_secretion` | `f max(capacity - m, 0) N/(K_N+N) y X` | the closure constants, `f`, the secretion yield `y` |
| `dilution_exchange` | `D (c_feed - c)` | dilution rate, feed concentration |
| `gas_transfer` | `k_La (c_sat - c)` | transfer coefficient, saturation concentration |

Every extent changes the pools through an explicit `stoichiometry` (formula
units per unit extent, supplied from a macrochemical balance; reservoir
species that are not states stay out of it) and may feed an `extent` ledger;
exchanges may feed a boundary `ledger`. The packaged
`data/model_configs/toy_resource_limited_chemostat.yml` runs the five types on
abstract pools. `ResourceLimitedCulture.simulate_compiled` and
`DegradingCulture.simulate_compiled` build these processes from the classes'
own parameters and balances (`compiled_processes`, `compiled_parameters`) and
return the same trajectory types as `simulate`; the parity tests agree to
1e-7 relative at tight tolerances, and each trajectory names its engine in
`diagnostics["engine"]`. The five types are not SBML-exportable yet; the
exporter refuses them explicitly rather than guessing a kinetic law.

`FungalCouplingModel`, the third opt-in whole-fungus class, composes
`mass_action` (now with catalysts: species that enter the rate law without
being consumed, exported to SBML as modifiers), `first_order_decay` and
`proportional_synthesis` processes through `compiled_processes(degradation)`,
where the caller supplies the extracellular degradation as processes;
`simulate_compiled` runs them on the compiled core and the parity test pins
the result to the legacy `build_engine().simulate` to 1e-7 relative. The
secretion cost needs one derived rate constant (`alpha_E_c_E`, the product
of the secretion coefficient and the secretion cost), carried by
`compiled_parameters` with its provenance.

## The compiled Jacobian

A compiled model can assemble `d(dy/dt)/dy` itself:
`CompiledModel.jacobian(t, y)` sums, over processes, the stoichiometric
column times the gradient of the process rate with respect to the state
vector. A process may offer that gradient analytically through
`Process.compile_jacobian`; `first_order_decay`, `mass_action` (with
catalysts), `homogeneous_michaelis_menten`, `proportional_synthesis`, the
three resource-limited closure processes and the two exchanges do. Every
other process (and any process behind a rate modifier or a dynamic
thermodynamic constraint) is differentiated by central finite differences of
its own rate kernel over the states it declares, and the kind of every
process is recorded in the kernel summary under `jacobian_kernels` with
`analytic_jacobian_count`. Gradients are evaluated at the same projected
state as the rates and multiplied by the projection's derivative, so the
matrix is the exact derivative of the right-hand side wherever it is
differentiable; at the closure's kink the one-sided derivative the classes
use applies.

`SolverSettings(jacobian="compiled")` makes the implicit methods (`LSODA`,
`BDF`, `Radau`) take that matrix instead of differentiating the right-hand
side themselves; explicit methods ignore the option. The default stays
`"finite_difference_by_backend"`, so no recorded result changes unless a
run declares otherwise; the run's `solver_metadata["kernel"]["jacobian"]`
says which was used, and `SolverSettings.to_dict()` records the option only
when it is set. `tests/test_compiled_jacobian.py` checks the assembled
matrix against finite differences of the compiled right-hand side on every
packaged config and reproduces the backend-difference trajectories and the
culture classes' analytic-Jacobian trajectories with it.

## What is not on the compiled core yet

- The legacy `Reaction`/`SimulationEngine` path, the 1D and N-D
  reaction-diffusion engines and the research culture models still integrate
  their own right-hand sides. `ResourceLimitedCulture.simulate` and
  `DegradingCulture.simulate` keep their native right-hand side for its
  analytic piecewise Jacobian, and `FungalCouplingModel.reactions()` keeps
  `Reaction` objects for caller-supplied Python rate laws, which cannot be
  compiled; `simulate_compiled` is the compiled path of all three classes.
  They are tracked as `FD-009` in `ARCHITECTURE_DEBT.md`.
- By default stiff methods still use the backend's finite differences,
  recorded as `"jacobian": "finite_difference_by_backend"`; the compiled
  Jacobian below is opt-in so that recorded results stay byte-stable.

## Reproduce

```bash
python -m pytest tests/test_compiled_process_models.py
```
