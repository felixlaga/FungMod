# Definition of Done and Review Checklist

## A. Hardcoding removal

- [ ] PET-specific code exists only in plugin/substrate/example/data/test paths.
- [ ] Generic workflow contains no PET strings.
- [ ] Generic loaders use registries.
- [ ] State names are config-driven.
- [ ] Product maps are config-driven.
- [ ] Validators are config-driven.
- [ ] Guardrail tests enforce all of this.

## B. Native execution

- [ ] `AssembledModel.run()` works.
- [ ] It returns `SimulationResult`.
- [ ] Workflows call `model.run`.
- [ ] Process rates are recorded automatically.
- [ ] Solver metadata is saved.
- [ ] Unsupported geometry fails honestly.
- [ ] No public execution placeholder remains.

## C. Generic configured workflow

- [ ] `load_model_config` exists.
- [ ] `run_configured_model` exists.
- [ ] Homogeneous benchmark runs.
- [ ] PET plugin benchmark runs.
- [ ] Non-PET dummy surface benchmark runs.
- [ ] Same code path for all.
- [ ] Missing config fields fail clearly.
- [ ] Missing parameters fail clearly.

## D. Process factories

- [ ] `ProcessFactory` exists.
- [ ] `BuildDecision` exists.
- [ ] `ProcessLibrary` exists.
- [ ] First-order factory works.
- [ ] Homogeneous factory works.
- [ ] Surface factory works.
- [ ] Factories explain failures.
- [ ] Factories do not hardcode PET.

## E. Results and validation

- [ ] `SimulationResult` includes states, rates, parameters, assumptions, validation, warnings, solver metadata, and assembly report.
- [ ] `save()` writes a full output folder.
- [ ] plots are created from result object.
- [ ] validation report is saved.
- [ ] mode/maturity is visible.
- [ ] toy/scientific distinction is enforced at foundation level.

## F. Tests

- [ ] full pytest passes.
- [ ] guardrail tests exist.
- [ ] failure tests exist.
- [ ] non-PET mirror tests exist.
- [ ] native execution tests exist.
- [ ] config workflow tests exist.
- [ ] no public placeholder tests exist.

## G. Notebooks/docs/CI

- [ ] generic quickstart notebook.
- [ ] notebooks do not implement core logic.
- [ ] docs explain architecture.
- [ ] GitHub Actions CI exists.
- [ ] branch protection enabled.
- [ ] ruff introduced.
- [ ] pyright introduced.
- [ ] coverage measured.
- [ ] README reflects reality.

## H. Start-biology gate

The foundation is ready for biology only if yes:

1. Can a new dummy substrate run without editing core code?
2. Can state names change without breaking workflows?
3. Can a model run without PET-specific workflow code?
4. Can unsupported configs fail with structured reports?
5. Can a user inspect assumptions/provenance/output without reading source?
6. Can Codex no longer sneak hardcoding into core without tests failing?
7. Can `model.run()` produce a result directly?

If not, keep building foundation.
