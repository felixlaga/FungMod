# Solver accuracy and thermodynamic networks

The October 2026 solver pass adds physical-law constraints and numerical
controls. It does not establish a perfect or empirically validated fungal model.

## Numerical controls

`SolverSettings` supports LSODA, BDF, Radau, DOP853, RK45 and RK23. The native
process solver, low-level reaction engine, 1D/2D/3D spatial engines, and joint
culture research API accept explicit per-state absolute tolerances and optional
unit-bearing first/maximum steps. Scalar tolerances retain their existing
meaning. For example:

```python
from fungal_model import SolverSettings
from fungal_model.core.units import Q_

settings = SolverSettings(
    method="BDF",
    rtol=1e-9,
    atol={"substrate": Q_(1e-12, "mol/L"), "enzyme": Q_(1e-18, "mol/L")},
    first_step=Q_(1e-3, "s"),
    max_step=Q_(1, "s"),
)
```

The tolerance mapping must exactly cover the model's actual state names, with
compatible units. Each spatial field's tolerance repeats over its cells. Local
error control uses `atol_i + rtol * abs(y_i)`; it is neither experimental
uncertainty nor a global accuracy guarantee. Controls are recorded with results.
Impossible, nonfinite and sub-machine-precision controls fail before a run.
The supported range for relative tolerance is `[100 * machine_epsilon, 1)`.

The shared integration boundary rejects nonfinite derivatives, incomplete or
failed trajectories, and malformed evaluation times. It never changes solver,
relaxes tolerances or clips returned states. Callers previously inspecting a
failed partial result must now catch `fungal_model.core.numerics.IntegrationError`
(a `ValueError`). Successful existing runs retain their equations and settings.
Research APIs preserve their existing domain error types.

BDF/Radau use a conservative sparse Cartesian Jacobian pattern for the cell-local
1D solver and pure diffusion in 2D/3D. The ND callable reaction API can access an
entire field, so locality is not inferred for arbitrary ND reactions. Those keep
the backend's dense default. This changes numerical work, not transport physics.

`simulate_candidate(..., solver_settings=settings)` exposes the same controls
for the joint culture study. It is exclusive with nondefault legacy
`method/rtol/atol` arguments. Names are `biomass`, `substrate`, optionally
`retained_mass` or dimensionless `induction`, and the named activity assays.
Returned tiny negative roundoff remains visible in both states and metadata;
values below minus ten times the relevant state tolerance still fail.

## A fundamental coupled thermodynamic model

`fungal_model.chemistry` now exports `DetailedBalanceReaction`,
`DetailedBalanceNetwork`, and `DetailedBalanceTrajectory`. This additive API
builds on the existing `MacrochemicalBalance` and its explicitly sourced species
compositions, charges, formation Gibbs energies and common conditions.

For an elementary reaction with reactant orders alpha and product orders beta,
the network implements:

```text
a_i = c_i / c_standard
nu = beta - alpha
delta_G_standard = nu.T @ mu_standard
j_forward = forward_scale * product(a_i ** alpha_i)
j_reverse = forward_scale * exp(delta_G_standard / RT) * product(a_i ** beta_i)
j = j_forward - j_reverse
dc/dt = nu @ j
delta_G = delta_G_standard + RT * nu.T @ ln(a)
sigma = sum(-j * delta_G / T)
f = sum(c_i * [mu_standard_i + RT * (ln(a_i) - 1)])
df/dt = -T * sigma
```

Every reverse rate derives from the same species chemical potentials. Closed
reaction cycles therefore cannot be assigned inconsistent equilibrium constants.
Element and charge balance are checked before execution. Integer-order reactions
can include explicit catalysts on both sides; supplied kinetic scales remain
necessary because thermodynamics does not predict activation barriers or rates.

The network provides an analytic Jacobian for stiff integration and a separate
equilibrium solver. Equilibrium satisfies zero reaction affinities and every
stoichiometric conservation law, including disconnected pools, in logarithmic
concentrations. It finds the stationary minimum of the convex dilute free energy
for an interior compatibility class, independently of kinetic scales.

Scope is closed, ideal-dilute, fixed-solvent-volume, isothermal chemistry. The
reported `f` omits the constant solvent reference; it is not the full Gibbs energy
of an arbitrary concentrated or variable-volume solution. Formation energies
must match the declared temperature, pressure, species and standard state. No pH,
ionic-strength, phase, heat-balance, open-culture physiology or maximum-entropy
selection model is inferred. These restrictions follow the implemented model;
see [Rao and Esposito's reaction-network thermodynamics](https://doi.org/10.1103/PhysRevX.6.041064).

At zero concentration, the exact `c*ln(c) -> 0` limit keeps free energy finite and
polynomial reaction rates can still create missing products. Chemical potentials
are singular there: entropy/Gibbs diagnostics explicitly return unavailable,
rather than using an invented activity floor. Equilibrium currently requires
strictly positive initial concentrations. Negative simulation outputs reject the
network trajectory; they are never clipped. The older single-reaction API retains
its explicit floor contract and now uses `expm1` for accurate near-equilibrium
net fluxes.

## Reproducible data comparison

Run from the repository with an empty output directory:

```bash
MPLCONFIGDIR=/tmp/fungmod-mpl .venv/bin/python scripts/run_solver_thermodynamic_audit.py \
  --output outputs/solver-thermodynamic-audit
```

The runner reuses the [Gelain 2020 source archive](https://doi.org/10.17632/shd3wcczsr.2)
and existing reviewed extracts. It replays all 33 frozen model/condition/scenario
holdouts against 144 unique published means, without refitting parameters. It
preserves training/holdout separation, raw prediction arrays, initial failed
attempts, explicit refinement controls, input/implementation hashes and software
versions. Synthetic thermodynamic verification is recorded separately and clearly
labelled in its figure. No new experimental observations are claimed.

The run on 2026-10-03 made 264 scored integration attempts: 132 with uniform
absolute tolerance, followed by 132 with named tolerances and a maximum step of
0.1 h. One initial BDF attempt failed the existing negativity guard (substrate
minimum `-4.80e-11 g/L`). Explicit `1e-14 g/L` substrate tolerance and the step
bound reduced this to `-2.48e-15 g/L`; all 132 refined attempts passed. The raw
roundoff and first failure remain in the results. The reference DOP853 trajectory
is a cross-method check, not exact ground truth.

Maximum solver disagreement was `5.114e-9` in training-scale units; the maximum
difference from historical frozen predictions was `2.249e-7`. Data errors remained
substantially larger. The best primary candidate among the existing models
(published equations) retained these pooled held-condition RMSEs:

| Family | Biomass (g/L) | Substrate (g/L) | Cellulase (FPU/L) | Beta-glucosidase (pNPG U/L) |
| --- | ---: | ---: | ---: | ---: |
| Glycerol | 0.4583 | 1.0047 | Not measured | Not measured |
| Cellulose | 0.7617 | 1.1615 | 83.82 | 149.72 |

The artificial cyclic network conserved elements to `2.7e-15 mol/L` and matched
the independent equilibrium solve (scaled residual `1.95e-16`). Free energy fell
monotonically and entropy production remained positive at every sampled point.
Tests additionally cover charged association with a catalyst, analytic solutions,
Jacobian derivatives, trace-state accuracy, boundaries and source rejection.

Scientific behavior: new opt-in thermodynamic physics and improved numerical
controls; existing culture equations, fitted parameters, observations, maturity
labels and registry records remain unchanged. This pass resolves a numerical
failure but does not materially reduce culture model–data error. Missing raw
replicates, measurement uncertainty, matched thermochemistry and independent
experiments remain unresolved. Software risk is moderate because integration
failure semantics tighten; scientific interpretation risk is moderate because
physical-law verification cannot establish biological validity.

Recommended next task: collect or curate preparation-matched formation energies,
oxygen/CO2 exchange and calorimetry, then preregister a reduced coupled culture
model and test it on new cultures with raw replicates. The existing cellulose
model's parameter identifiability still needs attention; adding unsupported
parameters would not resolve it.
