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
`SolverSettings` is the shared one: implicit methods other than LSODA get
the nearest-neighbour sparsity pattern; explicit methods work for mildly
stiff colonies. The `benchmarks` module holds two artificial models whose
parameters are round framework-benchmark numbers with `testing`
confidence, refused by scientific mode.

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
- LSODA, BDF with the sparse pattern and RK45 agree to 2e-4 relative;
- the same physics declared in millimetres and in centimetres gives the
  same trajectory to 1e-8, and the per-cell hyphal growth matches the
  closed form `v n_0 (e^{alpha t} - 1) / alpha`;
- every mechanism's tendency is checked numerically against its law in its
  declared units, including a cost declared in a different mass unit;
- the right-hand side of a 50 x 50 grid with four fields takes well under
  a millisecond per evaluation (about 0.4 ms on the development container,
  against 66 ms per evaluation at 200 cells for the unit-aware engines).

Measured on the development container (one core): the 40 x 40 artificial
colony over 24 hours takes about 19 s with LSODA (20 000 right-hand sides,
dense backend Jacobian) and 39 s with BDF on the sparse pattern; the
right-hand side itself is 7 s of that. A compiled sparse Jacobian for the
spatial core is the next performance step.

## What it is not

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
  (`scripts/digitize_de_ligne_2019_figures.py`). Before any comparison is a
  result, an observation operator from the model's hyphal length and tip
  density fields to the scanned mycelial area and graph-derived tip count
  must be declared, and a frozen plan must name the conditions used for
  calibration and those held out.
- The existing 1D and N-D reaction-diffusion engines are unchanged; they
  remain the `Reaction`-based path recorded under `FD-009`.
