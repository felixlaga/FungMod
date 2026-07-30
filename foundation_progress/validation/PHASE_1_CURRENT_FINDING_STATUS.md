# Phase 1 Current Finding Status

Reviewed baseline commit: `95253b838afdd645be67e9e6ebceab6f703cd9e3`

Current implementation branch: `agent/pr-57-dynamic-thermodynamic-enforcement`

Verified at: `2026-07-30`

This report summarizes the Phase 1 reconciled critical/high audit claims.
Detailed current evidence is in `findings.yaml`; P1.3 and P1.4 superseded the
initial P1.2 execution-path and process-to-`Reaction` adapter rows.

## Summary Table

| ID | Original severity | Current status | Current severity | Evidence summary | Remaining scientific risk | Recommended next phase or task |
| --- | --- | --- | --- | --- | --- | --- |
| P1-AUDIT-NATIVE-001 | critical | stale | none | Configured workflow calls `AssembledModel.run`, which delegates to `ProcessODESolver`. | Native execution does not validate biology. | P1.3 execution-path mapping. |
| P1-AUDIT-LEGACY-REACTION-001 | high | resolved | none | Public configured paths avoid direct legacy solver construction; P1.3 mapped retained low-level APIs; P1.4 removed process-to-`Reaction` adapters. | Low-level `Reaction` APIs remain intentionally supported and must stay clearly separated from configured workflows. | Preserve native execution and adapter-retirement guardrails. |
| P1-AUDIT-VALIDATORS-001 | high | resolved | none | Configured validators are loaded, attached, executed, and strict failures are tested. | Validators are software checks, not empirical validation. | Preserve guardrails in P1.3. |
| P1-AUDIT-CONFIGURED-API-001 | high | resolved | none | `run_configured_model` is public, tested, and writes configured bundles. | Benchmark configs are not scientific biology. | No P1.2 action. |
| P1-AUDIT-QA-001 | high | resolved | none | CI, Ruff, Pyright, and the 80% coverage gate exist; PR-41 enabled Pyright optional-member access and resolved FD-005. | Quality gates do not validate science. | Preserve the stricter quality-config guardrail. |
| P1-AUDIT-THERMO-001 | critical | partially_resolved | medium | Optional configured constraints now derive ideal-dilute molar activities/Q and dynamic Gibbs energy from explicit sourced inputs and block unfavorable nonnegative forward rates at every native solver RHS call. | Nonideal activities, reverse rates, coupled-network thermodynamics, electrochemical gradients, and empirical validity remain unsupported. | Preserve fail-closed binding/provenance guardrails; extend only through explicit generic contracts. |
| P1-AUDIT-BALANCE-001 | high | partially_resolved | medium | Dynamic constraints require a passing process/reaction-bound electron/redox check; carbon/oxygen and stoichiometry validators remain available. | Electron checks depend on supplied species metadata, and no global coupled-network balance is inferred. | Preserve explicit balance bindings; add broader enforcement only with complete chemistry. |
| P1-AUDIT-ENV-001 | high | partially_resolved | medium | Environment modifiers and metadata-only grid guards exist. | No validated general environmental response model. | Future ENV response task. |
| P1-AUDIT-SUBSTRATE-001 | high | stale | medium | Non-PET substrates and BIO-001/BIO-002 paths exist. | Breadth is not empirical validation. | Keep maturity labels. |
| P1-AUDIT-BIO001-001 | high | partially_resolved | medium | Product amount naming and proxy labelling are fixed. | BIO-001 remains exploratory and unvalidated. | Future validation-data task. |
| P1-AUDIT-BIO002-001 | high | partially_resolved | medium | Linear, branching, and cyclic graph genericity is tested with unrelated artificial conserved framework fixtures; existing two-step behavior is preserved. | Not empirical validation or broad provenance-backed pathway biology. | Preserve template-specific claims and topology guardrails; add biology only through the active evidence rule. |
| P1-AUDIT-CHAIN-001 | high | resolved | none | Explicit linear, branching, and cyclic graphs over existing process laws validate directed process/map edges, connectivity, substrate reachability, declared graph shape, state identity, and conservation before execution. | Graph support does not validate biology or implement unsupported rate laws. | Preserve graph and conservation guardrails. |
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

- Linear, branching, and cyclic enzyme-pathway graphs are implemented over
  supported process laws; arbitrary new process laws remain explicit work.
- Full execution-path mapping was completed in P1.3; adapter retirement was
  completed in P1.4.
- Bayesian calibration and Sobol/global sensitivity remain absent.

## Confirmed Scientific Blockers

- Dynamic thermodynamic feasibility is enforced only for explicitly configured
  single-process forward-rate constraints; broader coupled-network,
  reverse-flux, and nonideal thermodynamics remain unsupported.
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
  empirical biology, environmental response, empirical thermodynamic validity,
  or publication readiness.
