# Native Model Execution Plan

## Objective

Make `AssembledModel.run()` the central execution path.

## Stage N1: run interface

Implement a `RunRequest` or equivalent:

```python
initial_state: Mapping[str, Quantity]
t_span: tuple[Quantity, Quantity]
t_eval: Quantity | None
validators: tuple[ValidatorSpec, ...]
mode: toy | scientific | strict
label: str
```

`AssembledModel.run()` must accept this and return `SimulationResult`.

## Stage N2: RHS construction

For well-mixed ODEs:

1. order state variables;
2. convert initial quantities to canonical units;
3. reconstruct quantity state inside RHS;
4. evaluate process rates;
5. evaluate process contributions;
6. sum derivatives;
7. return numerical vector.

Tests: first-order analytic solution, A->B conservation, zero-rate process, unit conversion.

## Stage N3: solver layer isolation

It is acceptable initially for solver layer to adapt to existing `SimulationEngine`, but workflows must not call it directly.

Allowed:

```text
src/fungal_model/solvers/process_ode.py
```

Forbidden:

```text
workflows/configured_model.py imports SimulationEngine
```

## Stage N4: process rate recording

Every process rate trajectory must be recorded automatically in `SimulationResult.process_rates`.

## Stage N5: validation integration

Validators from model/config/run request attach to the result. Strict mode can raise on severe validation failures.

## Stage N6: solver metadata

Record method, tolerances, success, message, evaluations, backend, and warnings.

## Stage N7: geometry routing

Well-mixed routes to ODE. Unsupported geometry fails. No silent well-mixed fallback.

## Stage N8: remove workflow direct solvers

Once `model.run()` works, delete workflow-level solver construction.

## Done when

1. `AssembledModel.run()` no longer raises placeholder errors.
2. Generic configured workflow uses `model.run`.
3. PET and non-PET examples run through `model.run`.
4. Rates and validation are automatic.
5. Unsupported cases fail honestly.
