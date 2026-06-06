# Solver Backend and Numerics Plan

## Objective

Make numerical execution reliable and backend-clean before adding biology.

## Principles

1. Correctness before speed.
2. Units/provenance outside inner numerical loop.
3. Pure numerical RHS inside solver.
4. Structured errors on invalid states/units.
5. JAX optional later, not required now.

## Stage S1: canonical units

Every state variable has canonical units. Initial states are converted. Process contributions are checked.

## Stage S2: ProcessODESolver

Receive processes, parameters, state specs, environment, geometry, and solver settings. Build `rhs(t, y)` with no domain-specific logic.

Tests: analytic first-order solution, A->B conservation, multiple processes contributing to same state, zero-rate process.

## Stage S3: solver settings

Expose method, rtol, atol, max_step. Record in result. Solver settings are numerical, not physical.

## Stage S4: rate trajectory reconstruction

Compute and store all process rates after solving.

## Stage S5: backend interface later

Initial backend: SciPy/NumPy. Future backend: JAX. Do not require JAX now.

Potential later API:

```python
compiled = model.compile_numeric(backend="jax")
result = compiled.run(...)
```

## Stage S6: JAX-ready code style

Even without JAX: keep rate math pure, avoid mutation, separate quantities from arrays, avoid object-heavy logic inside RHS, and compile a numeric representation.

## Stage S7: spatial policy

Spatial models either work through `AssembledModel.run()` or fail as unsupported. No silent fallback.

## Done when

1. `AssembledModel.run()` uses solver layer;
2. solver has no PET logic;
3. solver returns `SimulationResult`;
4. process rates are recorded;
5. units are checked;
6. errors are structured;
7. workflows do not directly call low-level solvers.
