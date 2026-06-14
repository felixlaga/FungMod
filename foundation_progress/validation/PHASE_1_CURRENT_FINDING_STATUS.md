# Phase 1 Current Finding Status

Reviewed commit: `3538d303c5fbeb1697c584b11d4b6b1109374223`

Verified at: `2026-06-14T11:31:47Z`

This report summarizes the P1.2 reconciled critical/high audit claims. Detailed
P1.2 evidence is in `findings.yaml`. Later Phase 1 task reports may supersede
individual rows; for example, P1.4 resolved the process-to-`Reaction` adapter
debt recorded here.

## Summary Table

| ID | Original severity | Current status | Current severity | Evidence summary | Remaining scientific risk | Recommended next phase or task |
| --- | --- | --- | --- | --- | --- | --- |
| P1-AUDIT-NATIVE-001 | critical | stale | none | Configured workflow calls `AssembledModel.run`, which delegates to `ProcessODESolver`. | Native execution does not validate biology. | P1.3 execution-path mapping. |
| P1-AUDIT-LEGACY-REACTION-001 | high | partially_resolved at P1.2; adapter debt resolved in P1.4 | medium at P1.2 | Public configured paths avoided direct legacy solver construction; P1.4 removed process-to-`Reaction` adapters. | Low-level `Reaction` APIs remain intentionally supported and must stay clearly separated from configured workflows. | See `PHASE_1_LEGACY_ADAPTER_RETIREMENT.md`. |
| P1-AUDIT-VALIDATORS-001 | high | resolved | none | Configured validators are loaded, attached, executed, and strict failures are tested. | Validators are software checks, not empirical validation. | Preserve guardrails in P1.3. |
| P1-AUDIT-CONFIGURED-API-001 | high | resolved | none | `run_configured_model` is public, tested, and writes configured bundles. | Benchmark configs are not scientific biology. | No P1.2 action. |
| P1-AUDIT-QA-001 | high | partially_resolved | informational | CI, Ruff, Pyright, and 80% coverage gate exist; Pyright optional-member debt remains. | Quality gates do not validate science. | Track FD-005. |
| P1-AUDIT-THERMO-001 | critical | confirmed | critical | Gibbs metadata exists, but solver thermodynamic feasibility is not enforced. | Thermodynamic overclaiming remains possible. | Future thermodynamic enforcement task. |
| P1-AUDIT-BALANCE-001 | high | partially_resolved | medium | Carbon/oxygen validators and stoichiometry metadata exist; redox/global enforcement absent. | Balance only holds where validators and weights are configured. | Future scientific validator hardening. |
| P1-AUDIT-ENV-001 | high | partially_resolved | medium | Environment modifiers and metadata-only grid guards exist. | No validated general environmental response model. | Future ENV response task. |
| P1-AUDIT-SUBSTRATE-001 | high | stale | medium | Non-PET substrates and BIO-001/BIO-002 paths exist. | Breadth is not empirical validation. | Keep maturity labels. |
| P1-AUDIT-BIO001-001 | high | partially_resolved | medium | Product amount naming and proxy labelling are fixed. | BIO-001 remains exploratory and unvalidated. | Future validation-data task. |
| P1-AUDIT-BIO002-001 | high | partially_resolved | medium | Two-step chain genericity is tested with an unrelated fixture. | Not arbitrary pathway biology. | Future chain-topology design. |
| P1-AUDIT-CHAIN-001 | high | confirmed | high | Current chain support is scoped two-step, not arbitrary-length/branching. | Complex pathway claims remain unsupported. | Future chain-topology task. |
| V001-PC001 | critical | partially_resolved | high | Versioned schema and data dictionary exist; some standard outputs remain absent. | Schema does not validate predictions. | Later schema/output task. |
| V001-PC002 | high | resolved | none | Public scientific simulation exists and rejects inappropriate inputs. | Scientific means exact/unvalidated. | Preserve output labels. |
| V001-PC003 | critical | resolved | none | BIO-001 no longer emits mass-valued concentration wording. | BIO-001 remains exploratory. | Preserve tests. |
| V001-PC004 | high | partially_resolved | medium | Accessibility is now labelled as a proxy. | No true accessibility mechanism. | Future mechanism proposal if needed. |
| V001-PC005 | high | resolved | none | `missing_parameters.csv` and `suggested_experiments.csv` are standard outputs. | Suggestions may need richer future content. | No P1.2 action. |
| V001-PC006 | high | resolved | informational | Metadata-only environment grids disable ranking and response plotting. | Active response models remain limited. | Future ENV task. |
| V001-PC011 | high | partially_resolved | medium | BIO readiness template, validator, CLI, and tests exist. | Future work must consistently use the gate. | Possible CI/process hardening. |
| V001-PC012 | high | resolved | informational | Range scope, interpretation, and allowed-use fields exist in records and outputs. | Users can still ignore them. | Keep fields prominent. |
| V001-R001 | high | partially_resolved | medium | Exploratory priors are labelled in sampled/provenance outputs. | No publication-export acknowledgement gate. | Later output-governance task. |
| V001-R013 | high | confirmed | critical | BIO-001 still has no empirical validation data. | Empirical cellulose claims remain unsupported. | Future validation-data task. |
| P1-AUDIT-CALIBRATION-001 | high | partially_resolved | high | Synthetic least-squares calibration, Monte Carlo, and local sensitivity exist; Bayesian/Sobol absent. | No empirical validation or global sensitivity. | Future validation/inference milestones. |
| P1-AUDIT-PROVENANCE-001 | high | partially_resolved | medium | Maturity, provenance, scientific/exploratory mode, and output labelling exist. | Users can misuse exported tables out of context. | Later export/maturity acknowledgement. |

## Resolved Or Stale Audit Claims

- Native configured workflow execution is no longer a current critical blocker.
- Public `VirtualExperiment.simulate(mode="scientific")` now exists for exact
  modelable cases.
- BIO-001 no longer reports a kilogram-valued product as a concentration.
- First-class missing-parameter and suggested-experiment tables now exist.
- Metadata-only environment grids now block ranking/response-plot semantics.
- The technical claim that only PET has implemented paths is stale.

## Confirmed Engineering Blockers

- Arbitrary-length and branching process chains are not implemented.
- Full execution-path mapping was completed in P1.3; adapter retirement was
  completed in P1.4.
- Bayesian calibration and Sobol/global sensitivity remain absent.

## Confirmed Scientific Blockers

- Thermodynamic feasibility is not enforced by the solver.
- BIO-001 has no empirical validation data.
- Broad substrate support, BIO-001, and BIO-002 are not publication-grade
  validation of arbitrary fungus/substrate/environment combinations.

## Findings Requiring Manual Verification

None. The current catalogue did not use `needs_manual_verification`; absent
repository audit inputs are recorded in catalogue notes instead.

## Audit Methodology Limitations

- `findings.yaml` and `priority_findings.txt` were not present before this
  reconciliation, so IDs were preserved from available VALIDATION-001 artifacts
  where possible and new `P1-AUDIT-*` IDs were assigned to Phase 1 audit-scope
  claims.
- Documentation was used only as secondary evidence for implementation claims.
- Passing tests show current software contracts execute; they do not prove
  empirical biology, environmental response, thermodynamic feasibility, or
  publication readiness.
