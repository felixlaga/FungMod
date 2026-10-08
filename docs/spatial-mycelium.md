# Spatial mycelium on the compiled core

`fungal_model.mycelium` is the first slice of step 6 of the state document:
a fungus that occupies space. It is a continuum (density) model of a
mycelium on a uniform one-, two- or three-dimensional grid, compiled once
to numpy kernels like the well-mixed process core, and verified against
analytic and conservation results. It is **exploratory**: every process is
generic and provenance-labelled, but no organism record parameterises it
yet and no comparison with colony data has been run. The colony-expansion
dataset it is meant to meet is ingested (De Ligne et al. 2019, see below). A
result from this module carries that label and its limitations.

## What it models

Fields are densities per unit length, area or volume of the grid:

| Field role | Meaning | Example units |
| --- | --- | --- |
| tips | hyphal tip density (count per measure) | `1 / millimeter ** 2` |
| hyphae | active hyphal length density (length per measure) | `1 / millimeter` |
| inactive hyphae | hyphal length no longer growing or taking up | `1 / millimeter` |
| internal substrate | substrate carried inside the mycelium | `microgram / millimeter ** 2` |
| external substrate, enzyme, product | fields in the medium | `microgram / millimeter ** 2` |

The processes are the continuum laws first written for fungal colonies by
Edelstein (1982) and extended with substrate by Boswell et al. (2003);
every functional form is this implementation's declared choice, and the
process carries it as an assumption with its limitations:

| Process type | Law (per cell) | Fields changed |
| --- | --- | --- |
| `tip_extension` | hyphae gain `v * n`, with `v` constant or `v_max s / (K + s)` in the internal substrate; an optional cost `c * v * n` is drawn from that same substrate, so it cannot overdraw | hyphae, cost field |
| `tip_motion` | tip flux `-D grad(n) + n * (+/-) mobility * grad(g)`: random-walk diffusion and a drift up or down a declared field (towards substrate, away from dense hyphae) | tips |
| `lateral_branching` | tips gain `b * rho` or `b * rho * s` | tips |
| `dichotomous_branching` | tips gain `alpha * n` | tips |
| `anastomosis` | tips lose `a * n * rho` | tips |
| `first_order_field_loss` | a field loses `k * f`, optionally into a product field of compatible units (tip death, hyphal inactivation, decay of inactive hyphae) | field, product |
| `local_uptake` | external substrate moves to the internal field at `c * rho * s_e` or `c * rho * s_e / (K + s_e)` | external, internal |
| `translocation` | internal substrate diffuses (`-D_i grad(s)`) and is carried up the tip-density gradient (`D_a s grad(n)`) | internal |
| `local_secretion` | a product field gains `k * rho`, saturating in an internal substrate when declared, at an optional cost drawn from that substrate | product, cost field |
| `field_diffusion` | Fickian diffusion of any field | field |

Transport terms are conservative finite-volume fluxes (central gradients,
first-order upwind drift) under `no_flux` or `periodic` boundaries declared
per axis. Translocation acts on the internal substrate density itself and
is not gated by the hyphal density: a first version that gated the flux
with the harmonic face mean of the hyphal density starved the tip zone, so
a substrate-limited extension could never leave the inoculum, and the
process records that choice as a limitation. Kernels are evaluated at `max(field, 0)` and the integrated
fields are never clipped, the policy of the well-mixed compiled core.

Two grid geometries exist. A `cartesian` grid has one to three axes with
equal cells. An `axisymmetric` grid (`SpatialGrid.axisymmetric(radius,
cells)`, SPATIAL-002) has one axis, the radius of a colony with circular
symmetry: a cell is the annulus between two radii, its measure is
`2 pi r dr`, the divergence weights each face by `r_face / (r_centre dr)`,
the face on the axis carries no flux, and every integral is an area
integral (`measure_dimension` is two). The same processes run unchanged on
either geometry; the radial grid resolves a centred colony at a small
fraction of the cost of the two-dimensional one and is the calibration
grid of the colony comparison plan (`docs/colony-comparison.md`).

## Colony observables

`fungal_model.mycelium.observation` evaluates image-derived colony measures
on a result, for a square scan window and an inoculum disc declared by the
caller: `colony_count_outside_disc` (a per-area field integrated over the
window outside the disc, as a tip count is read after the inoculum is
removed from the images), `colony_hull_radius` (the farthest detected cell
centre at a declared detection density, never inside the disc) and
`colony_hull_area` (the window-truncated disc of that radius on an
axisymmetric grid, the convex hull of the detected cells and the disc
boundary on a cartesian one), with the closed forms `disc_area_in_square`
and `circle_length_in_square`. They are geometry, not biology: the
detection density and the disc are declared constants of a plan.

## How a model is built and run

```python
from fungal_model.mycelium.benchmarks import artificial_colony_model, central_inoculum
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.units import Q_
import numpy as np

model = artificial_colony_model(cells=40)          # grid, fields, processes, parameters
compiled = model.compile()                          # units resolved once, kernels built
result = compiled.simulate(
    initial_fields=central_inoculum(model.grid),
    t_span=(Q_(0, "hour"), Q_(24, "hour")),
    t_eval=Q_(np.linspace(0, 24, 7), "hour"),
    solver_settings=SolverSettings(method="LSODA", rtol=1e-6, atol=1e-9),
)
result.spatial_integral("hyphae")                   # total hyphal length over time
result.occupied_measure("hyphae", Q_(0.05, "1 / millimeter"))   # colony area above a declared threshold
result.front_position("hyphae", Q_(0.05, "1 / millimeter"))     # colony edge along an axis
result.results_summary()                            # maturity, assumptions, limitations, solver record
```

`MyceliumModel.compile()` refuses a process whose fields the model lacks or
whose units are incompatible, a missing or unknown parameter, and a
negative rate or non-positive half-saturation, before any kernel runs.
`SolverSettings` is the shared one: the implicit methods take the model's
analytic Jacobian (BDF and Radau as a sparse matrix, LSODA in band storage)
and explicit methods work for mildly stiff colonies (see
[Jacobians](#jacobians)).
The `benchmarks` module holds two artificial models whose parameters are
round framework-benchmark numbers with `testing` confidence, refused by
scientific mode.

## Verification

`tests/test_mycelium_core.py` and `tests/test_mycelium_colony.py`:

- the diffusive tendency matches the transport engines' finite-volume
  Laplacian in two and three dimensions and conserves the integral under
  no-flux boundaries; upwind drift conserves mass, keeps a top-hat
  non-negative and carries it the right way; no-flux outer faces carry no
  flux;
- the one-dimensional Edelstein system (`n_t = D n_xx + alpha n - a n rho`,
  `rho_t = v n`) spreads as a pulled front whose measured speed approaches
  the analytic `2 sqrt(D alpha)` from below and reaches it within 5 percent
  at 80 hours on 800 cells;
- the artificial two-dimensional colony conserves substrate across uptake,
  extension cost and translocation to 1e-7 relative, expands monotonically
  and stays symmetric to 1e-10 under transposition and reflection;
- LSODA, BDF with the analytic sparse Jacobian and RK45 agree to 2e-4
  relative;
- the same physics declared in millimetres and in centimetres gives the
  same trajectory to 1e-8, and the per-cell hyphal growth matches the
  closed form `v n_0 (e^{alpha t} - 1) / alpha`;
- every mechanism's tendency is checked numerically against its law in its
  declared units, including a cost declared in a different mass unit;
- the right-hand side of a 50 x 50 grid with four fields takes well under
  a millisecond per evaluation (about 0.4 ms on the development container,
  against 66 ms per evaluation at 200 cells for the unit-aware engines);
- on the axisymmetric grid the cells are annuli whose measures sum to the
  disc area, the axis face carries no flux, diffusion conserves the integral
  and matches the time derivative of the planar Gaussian to 2e-3 of its
  peak, a model's integrals carry area units, and the artificial colony on
  the radial grid agrees with the two-dimensional colony on the window
  count and hull area within the cartesian discretisation
  (`tests/test_mycelium_colony.py`);
- the colony observables reproduce their closed forms, agree between the
  two geometries for a uniform density, and follow the outermost detected
  cell (`tests/test_colony_observation.py`);
- the analytic Jacobian equals centred differences of the right-hand side on
  every grid geometry and boundary kind, has no dependency outside its
  declared stencil, gives the trajectories of the finite-difference paths and
  reproduces the previous default results (`tests/test_mycelium_jacobian.py`;
  numbers under [Jacobians](#jacobians)).

## Jacobians

The implicit methods need the Jacobian `d rhs / d state`. Every shipped
process offers it analytically (SPATIAL-003): `FieldProcess.compile_jacobian`
returns a `FieldJacobianKernel`, the blocks of the stencil the process
couples (`StencilBlock`: which field row depends on which field, in the same
cell or one step along an axis) and a kernel for their coefficients,
evaluated at `max(field, 0)` like the right-hand side. The local laws are
differentiated in closed form (for a saturating extension `v s / (K + s)`
with respect to the tips and `v n K / (K + s)^2` with respect to the
substrate, the cost row the same times `-c`; uptake, secretion, branching,
anastomosis and losses likewise). The transport terms differentiate the
finite-volume operators themselves: diffusion has the constant coefficients
`w D / dx` of the geometry's face weights (`1 / dx` on a cartesian grid,
`r_face / (r_centre dr)` on the radial one, nothing on a no-flux outer face,
the wrapped neighbour on a periodic one); an upwind drift `v q_up` with
`v = mobility grad(g)` contributes `max(v, 0)` and `min(v, 0)` with respect
to the carried field and `mobility q_up / dx` with respect to the steering
field, with the upwind side held fixed (where a face velocity is exactly
zero this is the derivative of the side the kernel uses). The model maps the
union of every process's blocks once onto a compressed-sparse-column
pattern; `CompiledMyceliumModel.analytic_jacobian` only scatters the
coefficient arrays into its data vector and multiplies each column by the
derivative of the projection (zero for a negative state, the right
derivative at zero). No dense matrix is formed. A process that offers no
kernel (a third-party one) is assumed nearest-neighbour like the rest and
puts every pair of its fields on the pattern; such a model falls back to
finite differences, which `summary()["jacobian_kernels"]` and the run's
`jacobian_structure` record.

The declared stencil is the nearest-neighbour pattern plus the cross-field
neighbour couplings of a drift (tips steered by the hyphae) and of active
translocation (internal substrate steered by the tips), which the pattern
before SPATIAL-003 left out. The coloured finite-difference Jacobian uses the
same stencil since SPATIAL-003, and its colouring (`stencil_colours`) gives
the cells after the last whole triple of a periodic axis colours of their
own. Before, three defects made it inexact: the pattern held wrap entries on
no-flux axes, and where an axis length was not a multiple of three the
colouring put that wrap column in the colour of a real neighbour, so the
entry copied a real coupling (`J[0, 799] = J[0, 1] = 16` per hour on the
800-cell front); on a periodic axis of such a length two columns of one row
shared a colour and their entries were mixed; and the cross-field neighbour
couplings were missing. A Jacobian only steers Newton's iteration, but these
slowed it (the front took 398 Jacobians and 1488 factorisations for 80 hours)
and on the front left the 80-hour tip integral 7.2e-4 relative from the
converged value at `rtol` 1e-8, while the front position was right.

Which Jacobian each method gets is recorded in
`solver_metadata["jacobian_structure"]`; `simulate(..., jacobian=...)` makes
the choice explicit:

| Method | Default | `jacobian="analytic"` or `SolverSettings(jacobian="compiled")` | `jacobian="finite_difference"` |
| --- | --- | --- | --- |
| BDF, Radau | analytic sparse (`analytic_sparse_on_the_nearest_neighbour_stencil`) | the same; refused when a process offers no kernel | coloured finite differences on the declared stencil (`coloured_finite_difference_on_the_nearest_neighbour_pattern`) |
| LSODA | analytic, in band storage of the cell-major state (`analytic_banded_cell_major`); dense (`analytic_dense`) where the band would hold more, on grids of two cells along the first axis | the same; refused when a process offers no kernel | LSODA's own differences, unchanged: banded in cell-major order with half-bandwidth `2 F - 1` for `F` fields on a one-axis grid (`one_axis_banded_cell_major`), dense otherwise (`backend_default`) |
| RK45, RK23, DOP853 | none | ignored | ignored |

A model with a process that offers no kernel gets the last column by
default; `SolverSettings(jacobian="compiled")` with
`jacobian="finite_difference"` is refused as a contradiction. LSODA accepts
only dense or banded matrices. Its band holds every coupling between cells at
most one slice of the first axis apart: half-bandwidths at most `F` times
the cells of a slice plus `F - 1` (`jacobian_bandwidths` in the metadata;
`[2, 2]` on the two-field front, `[162, 161]` on the 40 x 40 colony). The
couplings across the wrap of a periodic first axis lie outside any band; they
are left out and counted (`jacobian_entries_outside_band`), and LSODA's own
banded differences cannot represent them either, so on such a grid the
matrix LSODA factorises is exact but for those entries. Keeping them made the
matrix dense: 394 s instead of 0.45 s for 40 hours of an 800-cell periodic
line. On a one-axis grid LSODA's own banded differences, kept as the
finite-difference path, cost a few right-hand sides per Jacobian instead of
one per state: the radial colony comparison model (283 cells, four fields,
62 hours) went from about 220 s to 4 s with the same trajectory (SPATIAL-002).

Verification (`tests/test_mycelium_jacobian.py`), before any default
changed:

- on a model with every shipped process type in every declared option
  (saturating and linear forms, costs, products, drift up and down, a field
  steering itself, fields in two unit systems) on eight grids (one axis
  no-flux, periodic of seven and of two cells; two axes no-flux and periodic
  by no-flux; three axes periodic of 3 x 4 x 5 cells and mixed; the radial
  grid) at random states with some negative values, the analytic matrix
  equals centred differences of the right-hand side to 7.9e-11 of its
  largest entry at worst (entries above 1e-6 of the largest to 5.9e-8
  relative; the tests require 1e-8 and 1e-6), and so does the artificial
  colony at a simulated state;
- no dependency lies outside the declared stencil: perturbing a state
  outside a row's stencil leaves the row bit for bit unchanged, and the
  matrix is stored on exactly that pattern;
- negative states give zero columns and a state at zero the right
  derivative; the band storage holds the same matrix in cell-major order
  except the counted wrap of a periodic first axis;
- the corrected coloured differences agree with the analytic matrix to the
  `sqrt(eps)` accuracy of forward differences, including on periodic axes of
  four, five and seven cells, and put nothing across a no-flux wall;
- on the 16 x 16 colony and the 60-cell radial colony, BDF on the analytic
  and on the finite-difference path, LSODA on the analytic band and Radau
  agree with LSODA's own differences to 2e-4 relative (`atol` 1e-7); on a
  periodic line LSODA's band without the wrap, BDF on both paths and Radau
  agree with DOP853;
- the new defaults reproduce the defaults before SPATIAL-003 (stored
  values). BDF: the colony's integrals to 8.2e-10 relative and its diagonal
  profiles to 1.7e-9 of their scale, the radial colony's integrals to 3.1e-8,
  the colony comparison plan's check solve (450 radial cells, 62 hours, the
  artificial stage 0 check values) to 5.5e-9 in the tip count with an
  identical area, and the front's position to 2.7e-7 and hyphae to 3.5e-5;
  its tip integral, which the old default had 7.2e-4 off at 80 hours, now
  agrees with DOP853 at `rtol` 1e-11 to 4.7e-7. LSODA: the front to 6e-15
  and the plan's primary solve to 9.8e-9 in the tip count with an identical
  area. Every analytic front-speed, conservation and symmetry test above
  passes unchanged.

Measured on the development container, which other jobs shared throughout
(load average 8 to 25 on four cores), so absolute times are noisy and only
ratios within one session mean much; medians of three interleaved runs, at
the tolerances of the tests (`rtol` 1e-6 for the colony, the plan's 1e-6 for
LSODA and 1e-7 for BDF and Radau on the radial model, 1e-8 for the front);
"before" is main before SPATIAL-003 (LSODA's own differences, whose code is
unchanged, timed beside "now"), "differences" the corrected finite-difference
path, and the two Radau colony runs alternated in one process:

| Problem | LSODA before | LSODA now | BDF before | BDF now | BDF differences | Radau now | Radau differences |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 40 x 40 colony, 4 fields, 24 h | 48 s | 28 s | 6.8 s | 0.88 s | 0.85 s | 37 s | 32 s |
| radial plan model, 450 cells, 62 h | 0.89 s | 0.51 s | 4.4 s | 0.81 s | 2.8 s | 29 s | 86 s |
| Edelstein front, 800 cells, 80 h | 0.63 s | 0.39 s | 7.1 s | 0.62 s | 0.50 s | 41 s | 43 s |

One Jacobian of the 40 x 40 colony costs 1.9 ms analytic against 33 ms by
coloured differences (70 ms before their vectorisation; one right-hand side
is 0.8 ms), and of a 160 x 160 colony 21 ms against 278 ms (660 ms before).
The colony comparison plan's stage 0 cartesian reference (160 x 160 cells of
0.25 mm, 102 400 states, hours 1 to 12, BDF at `rtol` 1e-7, the artificial
check values) took 231 s with the analytic default (969 right-hand sides, 3
Jacobians, 75 factorisations) against the 4.1 hours and 18 074 right-hand
sides recorded for it, and its window observables equal the recorded ones to
1.9e-8 in tip count and exactly in area; this was a timing and regression
check, not a new stage 0 record. The earlier figures on this page (19 s for LSODA and 39 s for BDF on the 40 x
40 colony) were taken on a quieter container, BDF then with scipy's own
sparse differences.

The analytic Jacobian is the default of every implicit method because it is
verified and faster where the Jacobian matters. BDF is 5 to 11 times faster
than the default it replaces, as fast as the corrected differences where
Newton needs one Jacobian per run (alternating the two in one process on the
front gave medians of 0.55 s analytic and 0.69 s by differences) and 3.5
times faster on the radial plan model, where it needs many (5 Jacobians
against 134). LSODA is 1.6 to 1.8 times faster than with its own differences
on the colony, the radial plan model and the front, and 1.35 times on the
periodic line (0.45 s against 0.61 s). Radau is 3 times faster on the radial
plan model (12 Jacobians against 251) and as fast on the front, but 15
percent slower on the 40 x 40 colony, the one measured case where the
analytic matrix lost: both paths there take two Jacobians and the same
number of factorisations, and Radau's time is SuperLU's complex
factorisation (one took 13.5 s with the analytic matrix and 12.1 s with the
differences at a 12-hour state, with 3 percent less fill, against 0.06 s for
the real one), a cost of the factorisation's sensitivity to the values, not
of the Jacobian. Radau keeps the analytic default for its exactness and its
gain on the stiff plan model; `jacobian="finite_difference"` is the choice
for such a case, and BDF is 35 to 65 times faster than Radau on all three
problems.

The change moves the frozen colony comparison plan's solvers (LSODA its
primary, BDF its check solver and cartesian reference) by at most 2e-8
relative in the observables at the stage 0 check values, far inside the
plan's thresholds (0.005 between solvers, 0.02 between grids); the stage 0
record was not re-run and remains the record of its run, and
`jacobian="finite_difference"` keeps LSODA's earlier path unchanged. On two-
and three-dimensional grids BDF with the sparse matrix is the fast choice:
LSODA's band there spans a whole slice of cells.

## What it is not

- The active translocation term (`Translocation` with a tip field) is not
  well posed in general: carrying substrate up the tip-density gradient
  while a branching process makes tips where the substrate is forms a
  chemotaxis-like positive feedback that can concentrate tips into a spike
  whose height grows without bound under grid refinement (COLONY-001 stage
  0: the 24 hour tip count doubled with each halving of the cell at
  `D_a = 1`). The process declares this failure mode; any result that uses
  the term needs a grid-convergence check, and the colony comparison plan
  dropped the term.
- No individual hyphae, orientation, septa or diameter: densities only.
- No colony boundary as a moving interface; the "extent" is the measure of
  cells above a threshold the caller declares.
- No three-dimensional morphology validated against microscopy; no
  substrate accessibility or solid-substrate structure.
- Not reachable from the registry, the configured workflow or
  `VirtualExperiment`; the Python API and the benchmark builders are the
  entry points.
- No organism parameters: a registry record for a mycelium must still be
  authored from the literature (Boswell et al. 2003 for *Rhizoctonia
  solani* is the candidate source).
- No comparison with colony data yet. The colony-expansion dataset is
  ingested: `data/experiments/literature/de_ligne_2019_colony_growth/`
  holds the hourly mycelial area and tip count of *R. solani* and
  *Coniophora puteana* under sixteen temperature-humidity conditions from
  De Ligne et al. 2019 (IMA Fungus 10:7, CC BY 4.0), digitized from the
  supplementary figures with every reading limitation flagged
  (`scripts/digitize_de_ligne_2019_figures.py`). The observation operators
  from the model's hyphal length and tip density fields to the scanned
  mycelial area and graph-derived tip count are declared (above), and a frozen
  plan names the conditions used for calibration and those held out
  ([colony comparison plan](colony-comparison.md)); its stage 0 checks
  (grid, solver, symmetry) are recorded and passed under amendment 3, and no
  fit has been run.
- The existing 1D and N-D reaction-diffusion engines are unchanged; they
  remain the `Reaction`-based path recorded under `FD-009`.
