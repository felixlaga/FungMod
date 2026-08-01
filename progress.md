# FungMod Progress

This is the active progress ledger for the virtual-experiment directive in
`foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`.

Historical foundation-first and long-term roadmap notes are archived under
`old_progress/`; they are context, not the active starting point.

Older dated entries in this ledger preserve the project state and wording from
the time they were written. They do not override `AGENTS.md` or the current
biology rule.

Update this file whenever a feature, test, example, notebook, or architectural
milestone changes. The goal is that a future reader can quickly answer:

- what FungMod can do today;
- what is still only a roadmap item;
- what scientific assumptions are implemented;
- what failure modes are tested;
- which examples and tests prove the current behavior.

Status key:

- `complete`: implemented and tested for the stated scope.
- `partial`: useful infrastructure exists, but the roadmap stage is not fully complete.
- `not started`: no new long-term-roadmap implementation exists yet.
- `blocked`: implementation needs a decision, dependency, or sourced data.

## VALIDATION-DATA-001 First Literature Time Course Ingestion

Date: 2026-08-01

Status: `partial`; first source-backed dataset ingested, provenance-matched
model comparison pending.

Completed in this pass:

- Added a nine-point literature-raw cellobiose concentration time course from
  Alvarez-Gonzalez et al. (2022), DOI `10.3390/catal12010080`, Supplementary
  Figure S1A's 20 g/L filled-square free-enzyme series.
- Recorded the source PDF checksum, exact figure/series, sampling times, assay
  conditions, rendered axis calibration, marker-centre pixels, conversion,
  extraction software/date, exclusions, and a conservative 0.6 mM
  digitization-resolution estimate.
- Kept the commercial preparation's organism unknown because the 2022 source
  does not state it directly, and separated digitization error from unavailable
  experimental uncertainty.
- Updated the active data contract and validation status from blocked
  ingestion to partial comparison work.

Tests added or modified:

- Added `tests/test_literature_time_course_dataset.py` for both literature and
  runtime dataset schemas, exact observations, scope labels, reproducible pixel
  conversion, and packaged-resource identity.
- Updated literature-directory and active-status contract tests.

What did not change: no process law, parameter, solver behavior, calibration,
model comparison, residual table, validation report, organism identity, or
whole-fungus claim was added.

Scientific behavior impact: none. This is observation ingestion only. The
dataset may support a bounded no-calibration comparison after the paper's
combined inhibition law is implemented exactly.

Backward compatibility: additive dataset, documentation, and tests only.

Remaining ambiguity: source error bars are visible but their statistic is not
defined, and the commercial formulation's biological source is unstated. The
stored uncertainty is digitization resolution only.

Risk level: moderate scientific-interpretation risk, contained by raw maturity,
unknown organism metadata, explicit extraction provenance, and no validation
claim.

Recommended next task: implement the publication's exact combined substrate
and double product-inhibition law, then generate a provenance-matched
comparison bundle without fitting.

## SHOWCASE-001 Five Purified Fungal Beta-Glucosidases On Cellobiose

Date: 2026-07-31

Status: `complete` in the current checkout for one in-depth, installed-package
notebook covering five literature-reported purified-enzyme source cases.

Completed in this pass:

- Added
  `data/showcases/five_fungal_beta_glucosidases.yml` with five matched 50 °C,
  pH 5 parameter rows attributed to Bohlin et al. (2010) through the open
  Teugjas and Väljamäe (2013) Table 5 transcription.
- Added the deterministic
  `notebooks/examples/22_five_fungal_beta_glucosidases.ipynb`.
- The notebook generates inspectable configured models for purified
  beta-glucosidases sourced from *Aspergillus fumigatus*,
  *Chaetomium globosum*, *Emericella nidulans*, *Neurospora crassa*, and
  *Penicillium brasilianum* on dissolved cellobiose.
- Every case uses the same generic homogeneous Michaelis-Menten process,
  provenance-bound competitive glucose-inhibition modifier, explicit 2:1
  glucose stoichiometry, assay context, 10 mM starting cellobiose, and
  explicitly assumed 10 nM standardized enzyme dose.
- Added matched no-inhibition counterfactuals, conditional trajectory and
  threshold summaries, figures, validation/conservation/solver audits, normal
  per-run manifests, and a cross-case showcase manifest.
- Added docs and release-note coverage that distinguishes purified-enzyme
  source labels from whole-fungus models and blocks organism ranking.

Tests added or modified:

- Added `tests/test_fungal_beta_glucosidase_showcase.py` for exact five-row
  parameter transcription, source identity, units, maturity, stoichiometry,
  scenario assumptions, and limitation wording.
- Extended `tests/test_release_notebooks.py` for deterministic generation,
  public configured-workflow use, full execution, counterfactual coverage,
  provenance, and no-shortcut/no-whole-fungus guardrails.

What did not change: no generic/core equation, solver, output schema,
scientific-mode admission rule, production registry record, whole-fungus
physiology, culture protocol, empirical time-course dataset, calibration, or
validation claim was added.

Scientific behavior impact: five new exploratory configured scenarios expose
existing homogeneous Michaelis-Menten, competitive inhibition, and
stoichiometric product behavior with literature-reported parameters.
Transglycosylation, enzyme inactivation, preparation effects, secretion,
uptake, growth, transport, and model discrepancy remain unrepresented.
Parameter uncertainty remains explicit as unavailable.

Backward compatibility: additive packaged data, notebook, tests, and
documentation only; existing APIs, configs, registry resolution, output
schemas, and numerical behavior are unchanged.

Remaining ambiguity: the open transcription attributes the selected rows to
the primary comparative study, but no uncertainty values were transcribed.
Conditional scenario comparisons are allowed under the matched setup;
organism or real-preparation ranking remains blocked.

Risk level: low-to-moderate. Existing numerical laws are unchanged; the main
risk is overinterpreting reduced purified-enzyme trajectories as organism
performance, which the data, notebook, tests, and docs explicitly prohibit.

Recommended next task: ingest empirical cellobiose/glucose time courses for
one purified enzyme through the existing validation-data review workflow, or
implement and source a generic transglycosylation mechanism before expanding
the comparative claim.

## PUBLIC-RELEASE-001 Installable Package, Documentation, And Full Notebooks

Date: 2026-07-30

Status: `complete` in the current checkout for the first public alpha
distribution and documentation surface.

Completed in this pass:

- Renamed the unpublished distribution from `fungal-model` to the available
  PyPI project name `fungmod` at version `0.1.0`, while retaining the
  `fungal_model` implementation namespace and adding a `fungmod` convenience
  namespace.
- Added complete Python package metadata, MIT license text, project URLs,
  supported Python classifiers, notebook/docs extras, and build/twine tooling.
- Added immutable wheel-packaged mirrors of the registry, frozen SABIO-RK
  source evidence, and example data/configs, plus public bounded path helpers
  and installed-wheel path resolution.
- Added an artificial, framework-labelled configured example that exercises
  dynamic reaction quotient/Gibbs evaluation, required electron-balance
  binding, native solver-time forward-rate blocking, conservation,
  static-condition entropy-rate diagnostics, solver metadata, and output
  manifests without adding biological evidence.
- Added deterministic full notebooks
  `20_zero_to_complete_virtual_experiment.ipynb` and
  `21_advanced_capabilities.ipynb`, covering zero-to-report and
  provenance-to-thermodynamics workflows through public APIs.
- Added a strict MkDocs Material site and Read the Docs v2 configuration with
  install, quickstart, concepts, output reference, notebooks, configured-model
  tutorial, capability map, scientific-integrity guidance, API reference, and
  release notes.
- Added CI/release contracts for notebook execution, documentation builds,
  wheel/sdist checks, isolated installation smoke, and PyPI Trusted
  Publishing.

Tests added or modified:

- Added `tests/test_packaged_distribution.py` for namespace/version,
  resource-drift, path-containment, non-checkout registry/config execution,
  and frozen-source discovery contracts.
- Added `tests/test_release_notebooks.py` for deterministic notebook
  generation, public-API/no-shortcut guardrails, scientific-scope wording, and
  full cell execution.
- Added release/docs/package contract assertions and CI jobs.

What did not change: no production biological record, mechanism law, solver
equation, empirical dataset, calibration result, scientific-mode eligibility,
or validation claim was added. The dynamic thermodynamic showcase uses
artificial testing inputs and existing implemented behavior only.

Scientific behavior impact: no existing scientific behavior changed. The
default registry and example assets can now be located after wheel
installation; advanced examples expose already implemented mechanics under
explicit framework-benchmark labels.

Backward compatibility: the `fungal_model` import namespace remains supported.
The distribution name change affects only installation metadata and is safe
because neither `fungmod` nor `fungal-model` had an existing PyPI release at
the audited time. Relative repository data paths retain their current
behavior; packaged fallback occurs only for known shipped `data/` and
`data_registry/` assets when the relative path does not exist.

Remaining ambiguity and risk: Read the Docs project import and first PyPI
Trusted Publisher registration are provider-owned setup gates. The package
resource mirror is byte-checked against repository data and recorded as
contained debt in `ARCHITECTURE_DEBT.md`.

Risk level: medium release/process risk, low scientific-behavior risk.

Recommended next task: after the release artifacts, PyPI installation, and
hosted documentation are verified, select a new roadmap slice only by explicit
user direction.

## PR-59 Final PRODUCT-001 Integration

Date: 2026-07-30

Status: `complete` in the current checkout for the final scoped integration of
already implemented simulator evidence into standard researcher-facing
outputs.

Completed in this pass:

- Bumped the additive standard output contract to schema version `1.8.0`.
- Added explicit `process_rate.<process_id>` rows to
  `time_series_long.csv`, preserving every process identity in multi-process
  models while retaining the legacy `degradation_rate` and
  `product_release_rate` presentation aliases.
- Copied persisted `derived_quantities.csv` trajectories into namespaced
  `derived_quantity.<name>` rows with explicit thermodynamic activity,
  reaction-quotient, Gibbs-energy, and enforcement-flag roles.
- Extended `thermodynamic_diagnostics.csv` with the configured dynamic-Q,
  redox-energy, electron-balance, solver-enforcement, binding, evaluation
  count, blocking count, and Gibbs-extrema evidence already written by PR-57.
- Updated the Markdown/HTML report text and row detail rendering so it can
  display copied dynamic thermodynamic evidence without claiming to infer,
  recompute, revalidate, or apply enforcement.
- Synchronized the active README, roadmap, status, next-step, validation-gate,
  and machine-checkable status contracts. No further PR is selected for the
  user-scoped queue after PR-59.

Tests added or modified:

- Extended virtual-experiment API tests for every newly copied thermodynamic
  summary/row field and each derived-quantity semantic role.
- Added a multi-process registry-chain test proving all process rates retain
  explicit identity in the standard long table while legacy aliases remain.
- Updated schema-version, report guardrail, and active-status contract tests.

What did not change: no equation, modifier, process law, solver RHS behavior,
thermodynamic evaluation, registry record, biological identity, parameter,
validation dataset, calibration result, empirical comparison, or simulation
authorization changed. Missing configured artifacts still produce no invented
rows or values.

Scientific behavior impact: none. This slice copies and labels evidence already
persisted by configured simulation. It does not independently calculate or
enforce thermodynamics and does not add a biological claim.

Backward compatibility: existing columns and legacy rate aliases remain.
Schema `1.8.0` adds rows and columns, so consumers that incorrectly assume
fixed row counts should select by `state`, `state_role`, or `source`. New
namespaces prevent collisions with simulated state names.

Remaining ambiguity and risk: legacy `degradation_rate` and
`product_release_rate` remain compatibility presentation aliases and cannot
identify every process in a multi-process system; the new
`process_rate.<process_id>` rows are authoritative for that purpose. Derived
quantities are trusted only as copied simulation artifacts and are not
recomputed by the PRODUCT table writer.

Risk level: low-to-medium output-contract risk, bounded by an additive schema
minor version, collision-resistant namespaces, retained legacy rows, focused
multi-process/thermodynamic tests, and no numerical-behavior change.

Recommended next task: none in the user-scoped queue. After PR-59 is reviewed,
verified, and merged, stop rather than inventing another roadmap item.

Verification:

- Focused thermodynamic bridge and multi-process rate-identity tests:
  `2 passed in 9.90s`.
- Focused output, thermodynamic, and status regression initially reached
  `90 passed, 2 failed in 21.17s`; both failures were stale status-text
  assertions. The corrected status/API/report subset passed
  `14 passed in 11.70s`.
- Canonical pytest with coverage: `1216 passed in 452.84s`; total coverage
  `83.95%`, above the required `80%`.
- Ruff over `src tests`: passed.
- Pyright with the venv interpreter: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## PR-58 Broader Provenance-Backed Biological Laws

Date: 2026-07-30

Status: `complete` after PR #73 merged as `68c715b` for competitive and
Haldane substrate-inhibition laws on explicitly matched homogeneous
Michaelis-Menten processes.

Completed in this pass:

- Added `CompetitiveInhibitionModifier` using
  `v = Vmax*S / (Km*(1 + I/Ki) + S)`.
- Added `SubstrateInhibitionModifier` using the Haldane form
  `v = Vmax*S / (Km + S + S^2/Ki)`.
- Required exact base-process type, substrate-state, and Michaelis-constant
  ownership plus finite nonnegative states and positive unit-compatible
  parameters.
- Required a nonblank primary-law source and the explicit
  `literature_backed_software_tested` maturity label for both laws.
- Added assumptions, limitations, parameter/state requirements, failure modes,
  serialization, configured metadata, and fail-closed rejection of unsupported
  combined inhibition.
- Added BIO-readiness proposals and two materially different artificial
  configured benchmarks.

Tests added or modified:

- Added direct equation tests for competitive and Haldane factors.
- Added configured solver/output tests for both artificial benchmark systems.
- Added failure tests for missing primary provenance, nonpositive parameters,
  non-Michaelis-Menten base processes, and mismatched substrate/Km ownership.
- Added machine-checkable proposal and active-status coverage.

What did not change: no production registry record, production biological
identity, case applicability, whole-fungus growth, secretion, uptake, toxicity,
parameter inference, validation dataset, calibration, empirical comparison, or
simulation authorization changed. The existing reversible product-inhibition
modifier and all existing configs retain their behavior.

Scientific behavior impact: only configs that explicitly select one of the new
complete modifier contracts change numerical rates. The cited primary studies
support the selected equation in their study systems; they do not support the
artificial fixture parameters or establish applicability to a FungMod
production case.

Backward compatibility: existing modifier types and configs remain unchanged.
The new modifier types are additive and opt-in. Unsupported composition fails
before execution instead of silently multiplying mechanistically incomplete
rate laws.

Remaining ambiguity and risk: these are reduced single-substrate rate laws.
Competitive inhibition supports one inhibitor; the Haldane law does not
identify a molecular inhibitory complex. Mixed, uncompetitive, irreversible,
time-dependent, allosteric, multiple-inhibitor, transport, and whole-organism
effects remain unsupported. Production use requires separately curated
parameter and applicability evidence.

Risk level: medium scientific risk, bounded by primary-law citations, mandatory
maturity/provenance, exact base-law ownership, unit and positivity checks,
closed composition, artificial labels, and no production records.

Recommended next task: PR-59, integrate already implemented solver diagnostics
and trajectories into standard PRODUCT-001 researcher outputs without adding a
new mechanism or scientific claim.

Verification:

- PR-58 implementation/factory focused suite: `31 passed in 9.80s`.
- Final PR-58 biological-law/factory/roadmap focused suite: `41 passed in
  10.23s`.
- Both new BIO-003 proposals: readiness validation passed.
- Broad full pytest regression: `1215 passed in 219.92s`.
- Canonical pytest with coverage: `1215 passed in 431.91s`; total coverage
  `83.94%`, above the required `80%`.
- Ruff over `src tests`: passed.
- Pyright with the venv interpreter: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## PR-57 Dynamic Thermodynamic Feasibility And Solver Enforcement

Date: 2026-07-30

Status: `complete` after PR #72 merged as `ae8a5a3` for optional explicit
single-reaction ideal-dilute activity/Q evaluation and native forward-rate
enforcement.

Completed in this pass:

- Added a structured optional `thermodynamic_constraints` model-config section
  that binds one constraint to one assembled process, one explicit reaction,
  and one required passing electron/redox balance check.
- Added immutable activity participant, dynamic constraint, and evaluation
  contracts for molar state activities, reaction quotient, standard and
  state-specific Gibbs energy, favorability, and blocking evidence.
- Required exact sourced scalar parameters for temperature, gas constant,
  standard concentration, explicit positive activity floor, nonnegative Gibbs
  tolerance, and either direct standard Gibbs energy or the complete
  `delta_g_standard = -n*F*E_standard` redox input set.
- Required explicit reaction-participant state names, exact verified
  state/species binding, compatible molar concentration units, positive
  stoichiometric coefficients, unique IDs, nonblank provenance references,
  and the sole supported `block_unfavorable_forward_rate` enforcement mode.
- Applied the constraint after the native process rate is evaluated and before
  its contributions are accumulated at every internal
  `ProcessODESolver` RHS call. The same enforced rate is recorded in
  `process_rates`.
- Added standard derived trajectories for per-constraint activities, Q,
  `ln(Q)`, dynamic Gibbs energy, favorability, and rate-blocking flags.
- Added assembly-report ownership, solver metadata, a
  `dynamic_thermodynamic_feasibility` validation row, and configured
  thermodynamic JSON/CSV summary flags/fields for direct or redox-derived
  energy, electron binding, and solver enforcement.

Tests added or modified:

- Added an artificial first-order `A -> B` molar framework fixture whose zero
  standard Gibbs energy stops the forward process near equal activities,
  while the otherwise identical unconstrained model continues converting.
- Exercised both direct standard-Gibbs and redox-derived standard-energy paths
  through configured assembly, native solver execution, derived trajectories,
  assembly/solver metadata, validation results, and output artifacts.
- Added fail-closed tests for an unsupported activity model, missing parameter
  provenance, unknown process ownership, non-concentration state units, and a
  failed bound electron balance.
- Preserved existing configured/native/static-thermodynamic regression
  coverage for models that do not declare a dynamic constraint.

What did not change: no production case template, registry biology, parameter
record, organism/substrate identity, existing process rate law, default solver
setting, validation dataset, calibration, empirical comparison, or simulation
authorization changed. No thermodynamic constraint is inferred for an
existing config.

Scientific behavior impact: only configs that explicitly opt into the complete
constraint contract change numerical behavior. For those configs, an
unfavorable nonnegative forward process rate is set to zero at solver time.
The artificial equilibrium fixture is software evidence only, not a measured
or validated biological reaction.

Backward compatibility: existing configs omit `thermodynamic_constraints` and
retain their prior assembly, solver, process-rate, validation, and output
behavior. Existing configured thermodynamic metadata diagnostics remain
supported; dynamic rows and derived quantities are additive when configured.

Remaining ambiguity and risk: the activity model is ideal dilute and uses one
explicit common standard concentration plus explicit numerical floor. Reverse
rates, nonideal activity coefficients, coupled-network optimization,
electrochemical gradients, environmental-temperature trajectories,
multi-constraint ownership per process, and empirical validity are
unsupported. A hard forward-rate boundary is numerically discontinuous and is
bounded here by native solver regression and explicit returned blocking
evidence.

Risk level: medium scientific/numerical risk, bounded by opt-in ownership,
complete sourced inputs, passing static electron/binding evidence, closed
methods, exact unit checks, no defaults, artificial tests, and unchanged
existing configurations.

Recommended next task: PR-58, implement broader biological laws only after
selecting mechanisms with primary provenance, explicit parameter and maturity
contracts, assumptions, limitations, and materially different generic tests.

Verification:

- Dynamic/configured/native/static-thermodynamic/roadmap focused regression:
  `130 passed in 16.15s`.
- Broad full pytest regression: `1202 passed in 222.76s`.
- Ruff over the repository's documented `src` and `tests` gate: `All checks
  passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1202 passed in 531.22s`; total coverage
  `83.91%`, above the required `80%`.
- `git diff --check`: passed.

## PR-56 Branching And Cyclic Enzyme-Pathway Assembly

Date: 2026-07-30

Status: `complete` after PR #71 merged as `caa0a17` for explicit linear,
branching, and cyclic graphs over already implemented configured process laws.

Completed in this pass:

- Replaced the linear-only topology parser with an explicit registry-owned
  `topology_type` contract admitting only `linear`, `branching`, or `cyclic`.
- Derived directed state-role edges from each distinct process-owned
  stoichiometric map while retaining one explicit implemented rate-law input
  and allowing one or more explicit product edges.
- Added fail-closed validation for graph connectivity, substrate reachability,
  distinct runtime topology states, process/map role agreement, declared
  branch/cycle shape, map ownership, endpoints, and conservation.
- Preserved stricter ordered, contiguous, acyclic, one-product semantics for
  templates that declare `linear`.
- Emitted process/map-owned edges, entry roles, terminal roles, and actual
  branch/cycle flags in inspectable `case_template.chain_topology` metadata.
- Kept the production BIO-002 template explicitly linear and unchanged in its
  processes, scientific metadata, parameters, state names, stoichiometry,
  outputs, and numerical behavior.

Tests added or modified:

- Added a test-local artificial branching graph with one process producing two
  conserved downstream states; it assembles and runs through the standard
  configured solver.
- Added a test-local artificial cyclic graph with an explicit conserved return
  edge and terminal product edge; it assembles and runs through the same path.
- Added fail-closed tests for missing topology type, a declared branching graph
  without a branch, and a declared cyclic graph without a cycle.
- Updated the existing artificial three-step and production two-step topology
  assertions for explicit edges and entry/terminal roles while preserving
  existing malformed-linear rejection coverage.

What did not change: no production biological identity, production parameter,
source record, process rate law, numerical equation, solver setting, output
table schema, validation data, calibration, empirical comparison, or
simulation authorization changed. Graph fixtures are artificial software
evidence only.

Scientific behavior impact: existing production runs are unchanged. New graph
execution occurs only when templates explicitly own every process, map, state,
coefficient, parameter, topology type, and conservation weight and the process
laws already exist.

Backward compatibility: the existing BIO-002 helper signatures, production
linear configuration, process/state IDs, outputs, and two-step behavior remain
supported. `case_template.chain_topology` gains additive edge and
entry/terminal metadata. Enzyme-pathway templates must now declare their
topology type explicitly instead of receiving an implicit linear default.

Remaining ambiguity and risk: graph execution does not make a pathway
biologically supported. Multi-reactant rate-law semantics, broader pathway
laws, whole-fungus physiology, and empirical validity remain separate
provenance-backed work. Dynamic thermodynamic feasibility is not yet enforced
by the solver.

Risk level: medium architecture risk, bounded by explicit topology ownership,
pre-execution graph/conservation checks, executable conserved branch/cycle
fixtures, preserved linear regressions, and no production biology changes.

Recommended next task: PR-57, implement explicit provenance-bound activity or
reaction-quotient inputs, dynamic Gibbs feasibility, redox/electron balance,
and solver-time process enforcement without inferred chemistry or silent
constants.

Verification:

- Focused BIO-002 linear/branching/cyclic and roadmap suite: `39 passed in
  16.37s`.
- Broader pathway/configuration/registry/roadmap regression suite: `198 passed
  in 28.14s`.
- Ruff over the repository's documented `src` and `tests` gate: `All checks
  passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1192 passed in 485.32s`; total coverage
  `83.99%`, above the required `80%`.
- `git diff --check`: passed.

## PR-55 Arbitrary Reaction Onboarding And Assembly

Date: 2026-07-30

Status: `complete` after PR #70 merged as `6b3d275` for arbitrary reactions
using the already implemented homogeneous Michaelis-Menten process law.
Unsupported process laws remain explicit blockers.

Completed in this pass:

- Removed all Reaction 618, SABIO-RK, cellobiose, and beta-glucosidase tokens
  from the generic registry case builder.
- Moved homogeneous config name/mode/maturity, process ID, parameter-set ID,
  product-map name, state roles, initial conditions, yields, time grid,
  provenance, enzyme/substrate metadata, parameters, and output roles to
  explicit registry/template ownership.
- Preserved the public `RegistryProcessAssembler.deterministic_mode` contract
  while adding explicit supported-request modes. Homogeneous templates may be
  toy or scientific, but the request must match the template's declared mode.
- Required canonical process/config/parameter-set/product-map identity and
  explicit provenance source/confidence. Missing identities, malformed
  provenance, request/template mode mismatch, incomplete parameters, and
  unsupported process laws fail without fallback.
- Added a materially different artificial homogeneous reaction that assembles
  and simulates through the standard public registry case path. It is labelled
  throughout as software-test-only and is not production registry data.

Tests added or modified:

- Added assembly/simulation coverage for the second artificial reaction,
  template-owned IDs/states/product yield/provenance, and no Reaction 618
  leakage.
- Added fail-closed coverage for missing process identity and
  request/template mode mismatch.
- Added a generic-source guard that prevents Reaction 618, SABIO-RK,
  cellobiose, or beta-glucosidase display tokens from returning to
  `case_builder.py`.
- Kept Reaction 618, BIO-001, registry template, registry builder, and
  configured execution regressions in the focused gate.

What did not change: no production biology, production parameter, source
record, numerical rate law, stoichiometric contribution behavior, solver,
output schema, validation dataset, calibration, empirical comparison,
scientific-validation status, or simulation authorization changed. The
artificial fixture is test-local.

Scientific behavior impact: none for existing cases. Reaction 618 continues to
use its existing explicit template, process/product-map identities,
parameters, provenance, states, yield, and time grid. New reactions run only
when every required record is explicit and the selected process law is already
implemented.

Backward compatibility: existing `deterministic_mode` inspection and Reaction
618 scientific assembly remain supported. Homogeneous assembly additionally
admits explicit toy templates. Requests whose mode disagrees with template
mode now fail rather than returning a config whose declared mode differs from
the request.

Remaining ambiguity and risk: registry generality does not imply mechanism
generality. A new rate law still requires its own provenance-backed,
maturity-labelled implementation and tests. Branching and cyclic pathway
topology remains unsupported until PR-56.

Risk level: low-to-medium architecture risk, bounded by unchanged implemented
rate laws, explicit template ownership, a materially different test case,
hardcoding guardrails, mode matching, no production-data additions, and
existing-case regression coverage.

Recommended next task: PR-56, extend registry-owned enzyme-pathway topology
from ordered linear chains to explicit branching and cyclic graphs while
preserving component ownership, supported-law checks, stoichiometry,
conservation, parameters, limitations, and honest failure states.

Verification:

- Focused assembly/registry/Reaction 618/hardcoding suite: `101 passed in
  16.80s`.
- Ruff over `src` and `tests`: `All checks passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1186 passed in 415.03s`; total coverage
  `83.95%` (required `80%`).
- `git diff --check`: passed.

## PR-54 CURATION-001 Authenticated Curator Signatures

Date: 2026-07-30

Status: `complete` after PR #69 merged as `35a3ecb`. This completes
CURATION-001 for its defined review, authoring, authentication,
promotion-planning, and transactional-apply workflow. It does not complete
scientific validation or authorize simulation.

Completed in this pass:

- Added a closed versioned Ed25519 signature contract for exact
  `curation_manifest.json` bytes. The signature is written atomically as a
  deterministic sibling sidecar so the curation bundle's closed internal
  inventory remains unchanged; the manifest continues to bind every owned
  artifact checksum.
- Added explicit `TrustedCuratorKey` bindings and
  `load_authenticated_curation_bundle(...)`. Trust is caller-owned and binds
  one key ID, Ed25519 public key, and curator identity. The signature envelope,
  public-key digest, exact manifest digest, signature bytes, and every explicit
  decision curator must agree.
- Added `AuthenticatedCurationBundle.reload()` and revalidation at
  `author_parameter_record(...)`, `author_registry_records(...)`, and
  `plan_registry_promotion(...)` use boundaries.
- Kept SHA-256 scoped to consistency checking. The signature result explicitly
  records `production_registry_mutated`, `scientific_validation_claimed`, and
  `simulation_authorized` as false; true or malformed envelope values fail
  closed.
- Kept unsigned `LoadedCurationBundle` use backward compatible and
  distinguishable. A detached promotion plan remains digest-confirmed
  review/apply evidence and does not independently prove curator
  authentication.

Tests added or modified:

- Added signature coverage for the authenticated authoring-to-planning path,
  exact-manifest byte binding, tampered signatures, untrusted keys, forbidden
  validation/authorization claims, mismatched decision-curator identity,
  reload stability, and package-root exports.
- Updated the active roadmap status contract to mark CURATION-001 complete for
  its defined workflow and select PR-55 arbitrary reaction onboarding and
  assembly.

What did not change: no private-key storage, global trust registry, certificate
authority, key revocation, registry mutation, plan/apply schema, scientific
field, parameter, mechanism, process law, numerical method, solver, configured
model, output schema, validation data, calibration, empirical comparison, or
automatic simulation authorization changed.

Scientific behavior impact: none. Signature verification authenticates exact
manifest authorship against caller-supplied trust. It does not establish that
the signed biology, parameters, decisions, or promoted records are
scientifically valid.

Backward compatibility: `LoadedCurationBundle`, in-memory curation results,
existing authored bundles, promotion plans, and apply behavior remain
supported. Authenticated loading is opt-in. The only new runtime dependency is
`cryptography>=42.0`.

Remaining ambiguity and risk: callers own curator identity, public-key
distribution, key rotation, and revocation policy; FungMod deliberately does
not invent a PKI or global curator authority. A signature sibling must remain
available with the bundle for later authentication. Downstream detached plans
retain their existing digest contract but not independent signature evidence.

Risk level: medium security/workflow risk, bounded by Ed25519-only key types,
domain-separated exact-byte signing, closed sidecar fields, explicit caller
trust, exact curator matching, fail-closed verification, and use-boundary
reloads.

Recommended next task: PR-55, generalize arbitrary reaction onboarding and
assembly through explicit generic source, registry, template, and supported
mechanism contracts without reaction-specific branches or silent fallback
values.

Verification:

- Focused curation/signature/authoring/promotion/roadmap suite: `233 passed in
  114.45s`.
- Ruff over `src` and `tests`: `All checks passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1181 passed in 431.38s`; total coverage
  `83.95%`, above the required `80.0%`.
- `git diff --check`: passed.

## PR-53 CURATION-001 Product-Map Registry Ownership

Date: 2026-07-30

Status: `complete` after PR #68 merged as `19baedd`. At that checkpoint,
CURATION-001 remained `partial` only for authenticated curator signatures.

Completed in this pass:

- Added the index-owned `data_registry/product_maps/product_maps.yml`
  destination and a strict `ProductMapRecord` schema owned by
  `FungModRegistry`.
- Added production loading and exact single-record loader support for explicit
  `one_to_one` and `stoichiometric` maps. Reactant/product state names and
  finite positive float coefficients are required exactly; integers, booleans,
  missing mappings, unsupported types, and invalid coefficients fail closed.
- Added explicit conversion from a validated storage record to the existing
  runtime `ProductReleaseMap` without translating participant identities or
  coefficients.
- Extended `author_registry_records(...)`, promotion planning, written-plan
  validation, and transactional apply to the index-declared `product_maps`
  destination through the existing source-identity, reserved audit/digest,
  loader-fidelity, no-overwrite, drift, staging, rollback, and no-mutation
  controls.

Tests added or modified:

- Extended registry loading, record-authoring, promotion-plan, and
  transactional-apply coverage for product-map storage ownership, explicit
  coefficient typing, exact destination resolution, runtime conversion, and
  copied-registry apply.
- Updated the active roadmap status contract to select PR-54 authenticated
  curator signatures.

What did not change: the indexed product-map file contains no scientific
records. No source participant is automatically mapped to a runtime state, no
stoichiometry is inferred or converted, and no process law, solver, configured
model, output schema, validation data, calibration, empirical comparison,
scientific-validation status, or automatic simulation authorization changed.

Scientific behavior impact: none until a caller explicitly selects a valid
promoted map and converts it to the existing runtime type. The conversion
preserves the exact stored states and coefficients.

Backward compatibility: registry indexes without a `product_maps` key still
load with an empty product-map mapping. Existing file-backed and inline config
product-map loaders retain their behavior. Promotion into product maps is now
available only where the current index explicitly declares the destination.

Remaining ambiguity and risk: exact schema and loader fidelity do not prove
that curator-supplied state identities or stoichiometry are scientifically
correct. SHA-256 still proves internal consistency only and does not
authenticate the curator.

Risk level: medium scientific-metadata risk, bounded by explicit float-only
coefficients, no participant conversion, strict loader round trips, reserved
integrity evidence, no overwrite, full staged-registry validation, and copied
registry apply tests.

Recommended next task: PR-54, add an authenticated curator-signature and
trusted-public-key verification contract while keeping checksums scoped to
internal consistency.

Verification:

- Focused registry/authoring/promotion/apply/roadmap suites: `164 passed`.
- Ruff over `src` and `tests`: `All checks passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1172 passed in 513.75s`; total coverage
  `83.96%`, above the required `80.0%`.
- `git diff --check`: passed.

## PR-52 CURATION-001 Non-Parameter Registry-Record Authoring

Date: 2026-07-30

Status: `complete` after PR #67 merged as `5da611b` for the five index-backed
non-parameter record families. PR-51 is `complete` after PR #66 merged as
`bef938f`. At that checkpoint CURATION-001 remained `partial` for product-map destination
ownership and curator authentication/signatures.

Completed in this pass:

- Added public `author_registry_records(...)`,
  `CuratorAuthoredRegistryResult`, and a versioned
  `fungmod_registry_record_authoring` audit contract for `fungi`,
  `substrates`, `enzyme_classes`, `process_compatibility`, and
  `case_templates`.
- Required one explicitly accepted source record per complete curator-authored
  production target, preserved nonconflicting source identity, rejected
  pre-populated reserved provenance, and bound the source, target, curation,
  result provenance, destination family, safety flags, and record/result
  digests.
- Restricted target maturity to the explicit `exploratory_metadata` and
  `literature_metadata` labels; authoring cannot claim validated or unrestricted
  maturity.
- Added a public single-record production-loader entry point and required exact
  loader round-trip fidelity. Fields that would be dropped, synthesized,
  defaulted, or type-changed fail before promotion planning.
- Extended in-memory, checksum-written, promotion-plan, and transactional-apply
  validation so generic `CurationResult` objects cannot spoof the specialized
  authoring namespace and every authored record is independently revalidated.
- Kept product maps outside this bridge because the production registry index
  still has no declared product-map owner or destination.

Tests added or modified:

- `tests/test_registry_record_authoring.py` covers all five supported families,
  checksum-loaded written sources, source reload and checksum failure, raw-path
  rejection, product-map rejection, source-identity conflicts, dropped-field
  rejection, in-memory tamper detection, namespace-spoof rejection, public
  exports, promotion planning, and transactional apply against a copied
  registry.
- Existing curation review, parameter authoring, promotion plan/apply, registry
  loading, configured workflow, biology, numerical, and no-shortcut tests
  remain applicable.

What did not change: no production registry file, registry version, package
version, source evidence, scientific field, parameter, process law, solver,
simulation admission policy, output schema, notebook, validation data,
calibration, or empirical comparison changed. Authoring and planning do not
apply a registry mutation, and no record is called scientifically validated or
automatically simulation-authorized.

Scientific behavior impact: none. This is an administrative source-to-loader
bridge for complete curator-supplied metadata. It does not infer biological
capabilities, substrate structure, process compatibility, case behavior, or
missing values.

Backward compatibility: existing ordinary curation, ParameterRecord authoring,
written bundle loading, promotion planning, and apply contracts retain their
public behavior. The new reserved provenance namespace only rejects attempts
to pre-populate or spoof the new specialized contract.

Remaining ambiguity and risk: a production loader can prove schema and
round-trip fidelity, not biological truth. Curators remain responsible for
every authored scientific field. Product maps remain blocked until ownership,
storage schema, loader, and index destination are explicit. SHA-256 digests
prove internal consistency only; curator authentication is still absent.

Risk level: medium administrative/scientific-metadata risk, bounded by explicit
acceptance, source identity, closed supported types, reserved provenance,
deterministic digests, exact loader fidelity, full prospective-registry
validation, no overwrite, copied-registry apply tests, and no mutation during
authoring or planning.

Recommended next task: PR-53, define production product-map record ownership,
an index-declared destination and loader schema, then admit curator-authored
product maps through the same source identity, integrity, planning, and
transactional-apply controls.

Verification:

- Focused authoring suite: `13 passed`.
- Authoring plus promotion plan/apply suites: `120 passed`.
- Ruff over the repository's configured gate, `src` and `tests`: `All checks
  passed!`. A broader ad hoc scan also reports 17 existing E402 import-order
  violations in notebooks and `scripts/propose_sabiork_source_records.py`;
  those unrelated files were not changed in this slice.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1171 passed in 411.07s`; total coverage
  `83.95%`, above the required `80.0%`.
- `git diff --check`: passed.

## PR-51 CURATION-001 Versioned Nonidentity Parameter Conversion Registry

Date: 2026-07-30

Status: `complete` after PR #66 merged as `bef938f` for the bounded nonidentity
ParameterRecord conversion slice. PR-50 is `complete` after PR #65 merged as
`933d2c8`. At that point CURATION-001 remained `partial` for
non-parameter authoring, product-map destination ownership, and curator
authentication.

Completed in this pass:

- Added public immutable `ParameterConversionMethod` and
  `ParameterConversionRegistry` contracts with an exact registry schema
  version and unique named methods.
- Added the registered
  `pint_unit_conversion_decimal_places_half_even_12_v1` method. It accepts
  finite floats only, parses explicit source and target units with Pint,
  rejects identical unit text and incompatible dimensionality, converts
  deterministically, and applies 12-decimal-place half-even rounding.
- Extended `author_parameter_record(...)` so an explicitly accepted source may
  use that registered nonidentity method. Original/source/normalized values and
  units remain type-exact; converted and target values/units must match the
  registered-method recomputation type-exactly.
- Bound the method identifier, version, rounding policy, input value/unit,
  converted value/unit, target value/unit, and conversion policy into the
  existing authoring audit and digest. In-memory and written promotion planning
  independently revalidate the conversion.
- Preserved `identity_no_conversion` behavior and its existing written bundle
  summary contract.

Tests added or modified:

- `tests/test_parameter_conversion.py` covers public exports, registry version,
  the named method policy, deterministic conversion, unknown and duplicate
  methods, nonfinite values, unparseable units, incompatible dimensions, and
  identical unit text.
- `tests/test_parameter_record_authoring.py` covers registered conversion
  authoring, audit content, in-memory and written promotion planning, exact
  recomputation, dimensional rejection, identical-unit rejection, and
  unregistered-method rejection.
- Existing identity, authored-bundle, adversarial mutation, apply, storage-only,
  loader, selector, provenance, and no-mutation tests remain applicable.

What did not change: no registry record, source evidence, production
parameter, registry version, package version, curation decision, promotion
transaction, process law, solver, biology, validation data, calibration,
empirical comparison, output table, or notebook behavior. No conversion is
selected implicitly and no live source access occurs.

Scientific behavior impact: additive administrative unit transcription only.
The registered method performs dimensionally compatible unit conversion; it
does not validate the source value, improve evidence quality, infer a
parameter, fit a model, make a value transferable, or authorize simulation.

Backward compatibility: existing identity authoring retains its exact method
identifier, audit policy, summary flag, and result behavior. Previously
unsupported nonidentity methods continue to fail unless they exactly match a
registered versioned method and recomputation.

Remaining ambiguity and risk: Pint unit parsing defines dimensional
compatibility but not biological comparability. The fixed rounding policy is
explicit and deterministic, not a statement about measurement precision.
Non-parameter authoring, product-map promotion, and curator authentication
remain unsupported.

Risk level: medium administrative/scientific-transcription risk, bounded by a
closed method registry, explicit units, dimensional checks, deterministic
recomputation, exact audit/digest binding, storage-only output, promotion
revalidation, and no registry mutation during authoring.

Recommended next task: PR-52, a non-parameter curator-authored registry-record
bridge for the index-backed record families. Preserve exact source identity,
closed record schemas, destination ownership, loader fidelity, conservative
allowed-use/maturity policy, and no mutation; keep product maps separate until
their destination contract exists.

Verification:

- Full conversion and parameter-authoring suites:
  `119 passed in 113.85s`.
- Ruff: `All checks passed!`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Canonical pytest with coverage:
  `1158 passed in 534.68s`; total coverage `84.08%`, above the required
  `80.0%`.
- `git diff --check`: passed.

## PR-50 CURATION-001 Checksum-Loaded Written Source Authoring

Date: 2026-07-30

Status: `complete` in the current checkout for the bounded loaded-source
authoring slice. PR-49 is `complete` after PR #64 merged as `bbe2ee6`.
CURATION-001 remains `partial` for nonidentity conversion, non-parameter
authoring, product-map destination ownership, and curator authentication.

Completed in this pass:

- Extended `author_parameter_record(...)` to accept either its existing
  validated in-memory `CurationResult` or a public `LoadedCurationBundle`.
- Re-loads the owned manifest through `load_curation_bundle(...)` at authoring
  time and uses only the freshly reconstructed `CurationResult`. This rechecks
  exact inventory, checksums, path/symlink containment, and deterministic
  shared semantics after loading and before authoring.
- Kept raw bundle and manifest paths unsupported at the authoring boundary so
  callers cannot skip the explicit public loading step.
- Preserved every PR-48 source, curator, frozen snapshot, ordered URL,
  identity-only value/unit, closed provenance, storage-only allowed-use,
  registry-context, selector, loader-fidelity, authoring-digest, and
  no-mutation constraint.

Tests added or modified:

- `tests/test_parameter_record_authoring.py` proves loaded written input
  authors the exact same deterministic result and digest as its in-memory
  source, leaves the copied registry unchanged, and still rejects raw paths.
- The same suite proves a bundle modified after loading is revalidated and
  rejected at authoring time.
- `tests/test_roadmap_orchestration_status.py` synchronizes PR-49 merge,
  PR-50 completion and scope, remaining CURATION-001 limits, and the PR-51
  follow-up.

What did not change: no source value, converted value, target value, unit,
parameter policy, registry record, registry version, package version,
promotion classification, apply transaction, process law, solver, biology,
validation data, calibration, empirical comparison, output table, or notebook
behavior. No live source access occurs.

Scientific behavior impact: none. Written-source authoring reconstructs the
same administrative identity transcription already supported in memory. It
does not infer or convert values, validate science, authorize simulation, or
make a parameter transferable.

Backward compatibility: additive accepted input type. Existing in-memory
`CurationResult` callers retain their exact behavior. Raw paths continue to
fail, now with an error that directs callers to the checksum-loaded bundle
contract.

Remaining ambiguity and risk: `LoadedCurationBundle` is not proof of curator
identity; checksums prove internal consistency only. Nonidentity conversion
requires an explicit versioned method registry, parseable units, dimensional
compatibility, deterministic recomputation, and a closed rounding policy.
Non-parameter authoring and product-map promotion remain unsupported.

Risk level: low-to-medium administrative integrity. The only new path is
reduced to the already validated in-memory result after a second public-loader
pass and retains all downstream authoring validation and no-mutation behavior.

Recommended next task: PR-51, a versioned nonidentity ParameterRecord
conversion registry. Admit only explicit named conversions with parseable
source/target units, compatible dimensions, deterministic recomputation from
the source value, and an explicit rounding policy. Add no guessed conversion,
registry mutation, validation claim, or broader record support.

Verification:

- Focused authoring, curation, and roadmap suites:
  `162 passed in 105.19s`.
- Ruff: `All checks passed!`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Canonical pytest with coverage:
  `1148 passed in 396.78s`; total coverage `84.10%`, above the required
  `80.0%`.
- `git diff --check`: passed.

## PR-49 CURATION-001 Reusable Public Curation-Bundle Loader

Date: 2026-07-30

Status: `complete` in the current checkout for the bounded public-loader
slice. PR-48 is `complete` after PR #63 merged as `764d1e4`. CURATION-001
remains `partial` for direct written input to specialized authoring,
nonidentity conversion, non-parameter authoring, and product-map destination
ownership.

Completed in this pass:

- Added top-level `load_curation_bundle(...)` and
  `LoadedCurationBundle`. The loader accepts an owned curation directory or
  its exact `curation_manifest.json`, returns the reconstructed
  `CurationResult`, and exposes the already-read manifest, verified artifact
  paths, parsed YAML/CSV payloads, report text, and accepted records for
  workflow-specific validation.
- Centralized the written curation manifest, schema, exact artifact inventory,
  SHA-256, path traversal, symlink, containment, JSON/YAML/CSV/text parsing,
  summary-count, shared record-envelope, cross-artifact, and deterministic
  report checks in `fungal_model.api.curation`.
- Rewired `plan_registry_promotion(...)` to reuse that loader for every written
  curation input. Parameter-authoring bundles continue through their stronger
  closed workflow validator after the shared integrity pass; the loader does
  not replace the independent authoring digest, audit-schema, frozen-source,
  registry-context, selector, or apply-time checks.
- Kept the trust boundary explicit: manifest checksums prove internal
  consistency and detect changes relative to the manifest. They do not
  authenticate a curator or establish cryptographic authorship.
- Rejected undeclared bundle files in addition to missing or unexpected
  manifest declarations, and preserved rejection of path traversal and any
  symlink component before bundle content is trusted.

Tests added or modified:

- `tests/test_curation_review.py` now covers public directory and manifest
  loading, deterministic reconstruction/rewrite, top-level exports,
  checksum failure, checksum-refreshed cross-artifact semantic drift,
  undeclared artifacts, and symlinked inputs.
- Existing curation, promotion-plan, promotion-apply, and parameter-authoring
  tests continue to exercise the shared loader through the planner, including
  adversarial checksum-valid authored-bundle mutations that must reach the
  stronger specialized validator.
- `tests/test_roadmap_orchestration_status.py` synchronizes PR-48 completion,
  PR-49 completion and scope, remaining CURATION-001 limits, and the PR-50
  follow-up.

What did not change: no registry record, parameter value, unit, maturity,
allowed-use policy, registry version, package version, curation decision
semantics, promotion classification, apply transaction, process law, solver,
biology, validation data, calibration, empirical comparison, output table, or
notebook behavior. No live source access occurs.

Scientific behavior impact: none. Loading a bundle reconstructs administrative
review artifacts only. It does not make their contents current or correct
science, validation evidence, calibration evidence, transferable parameters,
or simulation-authorized inputs.

Backward compatibility: additive public API. Written promotion inputs now pass
through the shared loader and newly reject undeclared sibling artifacts or
cross-artifact disagreement even when an attacker refreshes manifest
checksums. Valid generic and specialized curation bundles retain their
existing promotion behavior and error boundaries.

Remaining ambiguity and risk: `author_parameter_record(...)` still accepts
only an in-memory `CurationResult`; direct written source input needs a
separate explicit API contract. Checksums remain unauthenticated. Nonidentity
conversion requires a closed conversion-method registry, unit parsing,
dimensional compatibility, exact recomputation, and rounding policy.
Non-parameter records and product-map promotion remain unsupported or blocked
as documented.

Risk level: medium for administrative bundle integrity, bounded by exact owned
inventory, checksum, path/symlink, shared semantic reconstruction, existing
specialized authoring validation, and no mutation/apply behavior in the
loader.

Recommended next task: PR-50, a bounded written-source input path for
identity-only parameter authoring that accepts only a successfully
`load_curation_bundle(...)`-validated source result and preserves every PR-48
authoring constraint. Add no conversion, registry mutation, scientific
transformation, validation claim, or broader record support.

Verification:

- Focused documentation and roadmap synchronization suites:
  `15 passed in 0.06s`.
- Ruff: `All checks passed!`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Canonical pytest with coverage:
  `1147 passed in 395.49s`; total coverage `84.10%`, above the required
  `80.0%`.
- `git diff --check`: passed.

## PR-48 CURATION-001 Identity-Only Curator-Authored ParameterRecord Bridge

Date: 2026-07-14

Status: `current` for the bounded PARAMETER-only identity-authoring slice.
PR-47 is `complete` after PR #62 merged as `b1ebb860`. CURATION-001 remains
`partial` for nonidentity conversions and non-parameter source records.

Completed in this pass:

- Added top-level `author_parameter_record(...)` for a validated in-memory
  `CurationResult`, one explicitly selected accepted PARAMETER source record,
  one complete curator-authored production mapping, and an explicit registry
  index. It returns `CuratorAuthoredParameterResult` without registry mutation
  or apply.
- Restricted conversion to `identity_no_conversion`. Original, source,
  normalized, converted, and target values must be finite floats and
  type-exactly equal; their units must be identical nonblank strings. Bools,
  integers, numeric strings, nonfinite values, unknown/range/distribution
  `ValueSpec` forms, and nonidentity methods fail closed.
- Required complete accepted-curation evidence and exact source identity:
  proposal record id, database, entry/reaction ids, query, source field,
  snapshot path, exact one-URL or ordered multi-page `source_url`/`source_urls`
  cardinality from frozen fetch metadata,
  frozen snapshot SHA256, curator, date, reason, limitations, and
  pending-promotion decision policy. Snapshot bytes and frozen URL evidence are
  revalidated before authoring and planning.
- Required every loader-emitted production field, all explicit null selectors,
  every exact `ValueSpec` field, closed maturity/allowed-use/range policies,
  a closed non-validation confidence label, exact source parameter
  symbol/value/units, and full outer source/curator
  provenance. Loader-dropped, synthesized, defaulted, or type-coerced mappings
  are rejected by exact production-loader round-trip comparison.
- Resolved effective enzyme/substrate classes from every non-null entity id,
  rejected class/entity disagreements, and required exactly one process
  compatibility record matching the effective combination and the explicit
  source/curator runtime parameter-role key. The authored result records the
  registry index identity, a complete registry-tree digest, resolved classes,
  compatibility record id, and role key; it isolates
  itself from later input mutation, and revalidates its authoring digest,
  selectors, and planning registry when passed to `plan_registry_promotion(...)`.
- Preserved the dual representation: accepted source/curation evidence is
  durable `fungmod_parameter_bridge` audit metadata, while only the complete
  curator-authored `ParameterRecord` is the loader and promotion target. The
  specialized result reuses `CurationResult.write()` for deterministic,
  checksummed output already consumable by promotion planning.
- Persisted result-level proposal limitations in manifest, summary, all three
  decision YAML payloads, both decision CSV tables, bridge audit, and the
  deterministic full report. Specialized planning reconstructs every semantic
  artifact from the authored result and requires exact headers, keys, and
  values. Public SHA256 checksums prove internal bundle consistency, not
  external curator identity or cryptographic authorship.
- Closed the full authored summary key/value schema, including every mutation,
  validation, simulation, provenance, and limitation claim, and compare it
  against manifest, accepted payload, bridge audit, and report representations.
  Removing removable workflow labels cannot downgrade a parameter candidate
  whose intrinsic target/curation provenance still has the authoring shape;
  planning rejects it, apply independently rejects a legacy/reconstructed
  generic plan lacking the bridge audit, and the shared runtime authorization
  predicate blocks an externally installed relabelled record.
- Reconciled frozen SABIO metadata as one offline structure: page/request/URL
  cardinality and immutable raw-page order, page numbers, URLs, regular files,
  unique exact `raw/page_NNNN.json` identities, byte sizes, and checksums must
  agree. Collapsed or path-aliased multi-page metadata fails.
- Bound source query, source snapshot path, proposal limitations, every
  original/source/normalized/converted/target value and unit representation,
  singular and plural source aliases, acceptance evidence, and every closed
  policy field into exact-key audit schemas and the result digest. Both
  authoring-owned provenance keys and outer mutation/validation/simulation
  safety claims are rejected on input. Curator-authored outer provenance now
  uses a closed identity-only field set, so validation, calibration,
  empirical-status, simulation-readiness, authorization, or nested claim
  aliases cannot be added alongside the owned false safety audit.
- Made simulation admission one centralized authorization-and-mode predicate
  used by modelability and every simulation parameter resolution path.
  `registry_storage_only_no_simulation_authorization` and reserved authoring
  evidence remain mode-independent blockers. Scientific mode accepts only the
  exact canonical scientific permission; exploratory and toy modes use closed
  explicit permission sets. Empty, unknown, negative, and near-match strings
  fail closed before ranking.
- Centralized mode-aware parameter eligibility and the complete dynamic ranking
  key across modelability, ensemble sampling/runtime, deterministic case
  assembly, and result-table/mechanism reconstruction. Ineligible records are
  filtered before ranking; explicit records are rejected rather than silently
  substituted. Exploratory and scientific value-kind preferences remain
  mode-specific, while selector, exploratory-prior, and calibrated-maturity
  tie-breaks now agree for identical admitted candidates; authorization is no
  longer a ranking preference because unauthorized records cannot enter a
  candidate set.
- Added one neutral exact-template role resolver used by modelability/preflight,
  ensemble/public runtime, deterministic assembly, direct chain assembly, and
  result reconstruction. CASE-001 consumes its exact role-to-record IDs without
  fallback and rejects mapping, symbol, nonnegative/exact-or-sampleable value,
  selector/component-identity, environment, authorization, mode, and process
  drift.
  The outer process compatibility binds every ordered process-template ID to a
  unique exact component compatibility record. Structural process `state_roles`
  resolve through canonical `state_species` enzyme-entity or substrate IDs;
  registry entities, enzyme capabilities, and the bound compatibility determine
  each component's class pair, process, bond, and role-symbol authority.
  Role/record selectors are assertions only, and `component_selectors` shadow
  metadata is rejected. Process parameters and parameter-backed catalyst/
  substrate initial states must match that independently resolved owning slot.
  This rejects a coherent whole-role-group rewrite even when contracts, records,
  and selector assertions are changed together.
  Kinetic role ownership is derived from component `process_templates` and
  conflicting metadata is rejected. Initial-state roles instead use an honest
  per-role record-scope contract; they do not claim a kinetic process owner.
  The BIO-002 cellulase initial-state record retains its declared surface-process
  scope because it initializes the surface-release component; BIO-001 uses the
  separate `bio001_cellulase_initial_concentration_prior` record. That storage/
  applicability scope does not make the initial condition a surface-kinetic
  parameter.
- Added intrinsic `component_only` scope for component process compatibilities
  and one registry-level authority graph validated at load and again on every
  compatibility query. Component records require exactly one ordered outer
  owner, complete unique semantic role content, canonical non-whitespace IDs,
  no nesting or standalone case-template claim, and exact process-template
  coverage. Standalone records keep their existing omitted/default scope in
  serialization; corrupt or removed incoming bindings cannot reclassify a
  marked component as an authoring or simulation candidate.
- Cross-bound the configured outer template substrate entity ID to the exact
  registry substrate identity consumed by the outer process's canonical
  `state_species` slot; the same-class alternate-ID attack cannot pass by
  parking the configured ID on an unused state.
  Component compatibility now requires exact semantic key-to-symbol mappings
  for parameter-backed catalyst/substrate initial states and nested modifiers,
  rather than accepting symbol membership under a renamed key. The same shared
  resolver rejects these drifts in modelability, ensemble/public simulation,
  deterministic/direct assembly, and result reconstruction; a materially
  different copied-registry three-step chain covers both initial-state and
  nested product-inhibition role rewrites.
- Preserved caller-supplied required roles when compatibility is present and
  anchored implemented direct process parameters to process-type-owned
  canonical fields. Explicit templates reject missing direct roles, coherent
  semantic-key renames, and duplicate role reuse before modelability or
  assembly. Every initial-state `parameter_role` and `units_from_role` must also
  retain an explicit parameter record, so coherent outer-compatibility and
  template truncation fails during preflight instead of later assembly. Optional
  nested modifiers and dynamic fallback retain their existing contracts.
  Malformed list-valued compatibility roles and component binding IDs now
  produce `RegistryValidationError` instead of raw `TypeError`.
- Centralized one parameter-provenance classifier across planning, apply, and
  runtime. A reserved `fungmod_parameter_bridge` namespace always requires full
  independent bridge schema/digest/policy validation at apply; the reserved
  `fungmod_curation` namespace and distinctive nested source evidence remain
  mode-independently non-simulatable even when malformed. Ordinary outer
  `curator`, `curation_date`, and `parameter_role` metadata alone remain generic.
- Kept written source curation input out of scope. Shared canonicalization,
  type-exact comparison, round-trip difference, SHA256, full-tree hashing, and
  symlink helpers live in one internal integrity module and are reused by
  registry promotion; provenance classification lives in one neutral shared
  module used by plan, apply, and runtime. No parallel curation-bundle parser
  was added.
- The frozen SABIO-RK test completes explicit identity curation in a test-owned
  proposal copy, re-authors canonical EntryID 35622 kcat using the existing
  canonical record id, removes that target only from a copied temporary
  registry, and produces one ADDABLE plan. Production `data_registry/` is
  byte-checked as unchanged and no apply occurs.

Tests added or modified: `tests/test_parameter_record_authoring.py` covers the
real frozen SABIO path, in-memory and written-result planning, deterministic
checksums, rechecksummed authored-bundle tampering, post-result mutation,
unsupported written input, source acceptance/blocker/type failures, exact
identity conversion, bool/int/string/nonfinite values, blank fields, source
identity and snapshot digest conflicts, conservative policies, complete
`ValueSpec` and loader fidelity, selector compatibility, malformed and nested
bridge evidence at plan/apply/runtime, exact written-envelope/report closure,
ordinary curator-metadata compatibility, aliased raw pages, unsafe output paths,
planning-registry revalidation, and public exports.
`tests/test_roadmap_orchestration_status.py` synchronizes PR-47 completion,
PR-48 current scope, remaining CURATION-001 limits, and the PR-49 follow-up.

What did not change: no production registry parameter record, value, unit,
maturity, allowed-use policy, or version; no package version,
curation decision semantics, valid generic promotion transaction behavior, process law, solver,
biology, validation data,
calibration, or empirical comparison. The SABIO source adapter performs no
network access here. Its proposal payload now adds explicit `parameter_role`
and normalizes the SABIO `Km` role to runtime key `km`, alongside exact frozen
URL provenance; source values and units are unchanged.

Scientific behavior impact: no new scientific result. The frozen SABIO case
proves deterministic extraction, explicit identity mapping, provenance,
loader fidelity, and copied-registry planning only. It is not current/correct
science, validation, calibration, prediction, transferability evidence, or
simulation authorization.

Backward compatibility: the public API and result/error types are additive,
but behavior is not purely additive. SABIO proposal payloads gain explicit
`parameter_role`, with `Km` normalized to runtime role key `km`; malformed
multi-page frozen metadata is newly rejected. Parameter candidates with the
intrinsic authoring provenance shape require the specialized contract even if
labels are removed, and outer provenance safety claims are rejected. Existing
generic curation, planning, and apply inputs without that shape retain their
contracts. Deliberate safety change: parameters retaining either reserved
authoring/curation provenance namespace are mode-independently non-simulatable;
ordinary outer curator/date/role metadata alone remains generic. An exact
`registry_storage_only_no_simulation_authorization` parameter is now rejected
by modelability/preflight in every mode. Parameter simulation admission now uses
closed exact `allowed_use` sets, so prior ad hoc, empty, negative, or near-match
strings no longer authorize a mode. Explicit chain templates with
`parameter_record_ids` must also provide complete `parameter_role_contracts`;
the outer compatibility must provide exact ordered component-compatibility
bindings, component compatibilities must carry intrinsic `component_only` scope
with exactly one registry-validated owner, each configured substrate and
the configured outer substrate and each parameter-backed component state must
resolve through the exact structurally consumed canonical registry ID,
initial-state/modifier symbols require exact semantic compatibility keys,
direct process fields must satisfy the implemented process-type schema without
omission, renaming, or role aliasing, role/record selectors are assertions only,
and the old
ownership-like `parameter_role_process_types` shape is rejected.
CASE-001 initial-state records declare exact storage/reuse process scope, while
kinetic owners are derived only from component process templates.

Remaining ambiguity and risk: nonidentity conversions require a separate
closed conversion-method registry, unit parsing, dimensional compatibility,
exact recomputation, and rounding policy; they are rejected here. Written
curation input remains deferred until the existing private bundle parser can be
made reusable without duplication. Non-parameter curation records remain
unsupported. Registry locks remain relevant only at apply, which this API does
not invoke.

Risk level: high for scientific provenance and schema integrity, bounded by an
identity-only policy, exact type checks, frozen-byte digest verification,
loader and selector revalidation, immutable result copies, adversarial tests,
and no mutation/apply path.

Recommended next task after PR-48 merges: PR-49, a reusable public
checksum-validated curation-bundle loader that centralizes the existing
manifest/checksum/path contract before any specialized authoring API accepts a
written source bundle. Add no scientific transformation or registry mutation.

Verification:

- Focused authoring, source-provider, promotion-apply, direct chain, and roadmap
  status suite: 171 passed in 28.59s.
- Broader authoring, source, curation, promotion, modelability, ensemble,
  case-builder, chain, and VirtualExperiment suite: 320 passed in 49.74s before
  the final apply-time regression; the canonical suite below includes that
  regression and all focused coverage.
- Final-review authoring/resolver/registry/status regression suite: 230 passed
  in 126.33s; the complete explicit CASE-001 malformation matrix passed 35
  tests in 10.37s after its expected diagnostics were aligned with the stronger
  exact process-role and consumed-substrate checks.
- Canonical full pytest: 1144 passed in 249.30s on the final code.
- Focused Ruff: passed.
- Full Ruff: passed for `src` and `tests`.
- Full Pyright with the shared venv interpreter selected explicitly: 0 errors,
  0 warnings, 0 informations. The bare worktree invocation could not resolve
  `pint` because isolated worktrees do not contain the main checkout's
  `.venv`; the repository-documented `--pythonpath` equivalent passed.
- `git diff --check`: passed.

## PR-47 CURATION-001 Digest-Confirmed Transactional Apply

Date: 2026-07-13

Status: `complete` for the bounded transactional apply slice after PR #62
merged as `b1ebb860`; PR-46 is complete after PR #61 merged as `2b6c639`.
CURATION-001 remains `partial`, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added top-level `apply_registry_promotion(...)` for an in-memory
  `RegistryPromotionPlan` or its owned written bundle. Written apply requires
  an explicit current registry index and never uses manifest absolute paths as
  write destinations.
- Intentionally advanced the promotion-plan schema from `1.0.0` to `2.0.0`.
  Planning now inserts deterministic non-scientific
  `provenance.fungmod_curation` audit metadata into each addable prospective
  record and binds every regular registry-root file into before/prospective
  digests. Pre-PR-47 written `1.0.0` bundles are rejected at apply rather than
  silently reinterpreted.
- Revalidates the exact plan/confirmation digest, candidate and prospective
  consistency, accepted curation metadata, ISO date, source provenance,
  source-identity consistency between target and curator provenance, blockers,
  loader fidelity, current index SHA, full before-root digest, every
  target before hash, index destinations, path/root/symlink/shared-target
  safety, no-overwrite state, and `load_registry(...)` immediately before the
  transaction.
- Requires a strict numeric current `MAJOR.MINOR.PATCH` version and exactly the
  next patch version. Apply changes only the index version and exact planned
  target bytes; package version and all scientific fields remain unchanged.
- Copies the complete registry root into a same-filesystem sibling stage,
  preserves unrelated regular files, rejects unsafe symlinks/special entries,
  validates the full staged registry, verifies promoted runtime records
  type-exactly, and records exact changed-file before/after hashes.
- Uses an atomic exclusive sibling lock for cooperating single-writer and
  reentrant exclusion. The directory-level swap retains a byte-exact backup
  through installed version/digest/runtime verification, rolls back
  deterministically on injected failure or interruption, reconciles source,
  backup, and stage state from validated on-disk digests, verifies rollback
  digest/loader state, preserves recovery copies when rollback is unproven, and
  reports committed cleanup failures without implying rollback.
- Added `RegistryPromotionApplyResult` with old/new versions, confirmed
  `plan_digest`/`confirmation_digest`, before/planned/applied registry digests,
  exact changed files/hashes, applied and exact-duplicate IDs, transaction,
  rollback, and backup-cleanup status, plus explicit
  `production_registry_mutated: true`,
  `scientific_validation_claimed: false`, and
  `simulation_authorized: false`.
- Kept product maps blocked pending a destination contract, conflicts and
  blocked candidates non-applicable, exact duplicates no-op only, and at least
  one addable record mandatory. Plan summaries/manifests now report
  `apply_available: true` only for at least one addable with no conflict or
  blocked candidate. No receipt is written to a hidden location.

Tests added or modified: `tests/test_registry_promotion_apply.py` exercises
in-memory and written-bundle success on copied registries, parameter and fungus
record types, exact confirmation, plan and artifact tampering, schema
compatibility, index/target/unrelated drift, conflict/blocked/no-addable plans,
strict patch versions, unsafe destinations, untrusted manifest absolute paths,
durable audit provenance, unchanged scientific fields and target allowed-use,
complete staged loading, byte-exact commit rollback, rollback failure,
`KeyboardInterrupt`/`SystemExit` after backup rename, before install rename,
and during installed-runtime verification, committed backup/lock cleanup
failure truthfulness, concurrent/reentrant lock refusal, debris cleanup, and
public exports. The repository's real
`data_registry/` is never an apply target in tests.
`tests/test_registry_promotion_plan.py` now covers schema `2.0.0`, deterministic
audit metadata, source-identity contradiction blocking, candidate-derived
applicability, and unchanged raw exact-duplicate semantics.
`tests/test_roadmap_orchestration_status.py` keeps PR-46 completion, PR-47
current status, partial CURATION-001 status, PR-48 curation bridge follow-up,
and deferred validation wording synchronized.

What did not change: no repository `data_registry/` record or version, package
version, source-provider/curation decision, simulation eligibility, process
law, solver, thermodynamic behavior, biology, parameter value/unit/maturity,
validation data, calibration, or empirical comparison changed.

Scientific behavior impact: none. This is an administrative production
registry mutation contract over exact reviewed bytes. Promotion is not
scientific validation and does not authorize simulation.

Backward compatibility: the public apply API/result types are additive, but
promotion-plan schema `2.0.0` intentionally supersedes preview-only written
schema `1.0.0`. Existing `1.0.0` bundles remain readable review artifacts but
must be regenerated before apply. Planning now includes audit metadata in
addable prospective YAML and full-root digests; exact-duplicate raw-content
classification remains unchanged.

Remaining ambiguity and risk: the lock is cooperative between callers using
this API; external filesystem writers cannot be forced to honor it, so source
digests are rechecked immediately before swap. Directory swaps assume local
same-filesystem rename semantics. Rollback failure is fail-closed and reports
the exact backup/stage paths and preserves the stage container because
automatic recovery cannot then be proven.
Product-map destination ownership remains undefined and blocked. Exact
duplicates remain no-op and therefore do not rewrite an existing production
record solely to attach this plan's curation audit.

Risk level: high for filesystem integrity, bounded by copied-registry
adversarial tests, full-tree staging, digest rechecks, locking, installed-state
verification, deterministic rollback, and explicit cleanup-state reporting;
scientific risk is low because no scientific content is inferred or changed.

Recommended next task after PR-47 merges: PR-48, a bounded CURATION-001
curator-authored source-to-production registry-record bridge/schema workflow.
Make an explicit frozen source record transformable into the exact existing
production loader schema through curator-authored fields and conversion
metadata only. Add no guessed conversion, fallback/default, invented science,
automatic promotion, simulation authorization, validation data, calibration,
or empirical claim.

Verification:

- Focused registry-promotion plan/apply and roadmap-status suite: 109 passed in
  22.71s.
- Broad registry, curation, source-provider, researcher-API, and status suite:
  273 passed in 40.93s.
- Full suite from scratch with coverage: 904 passed in 179.71s; total coverage
  84.52% against the required 80% gate, with
  `src/fungal_model/api/registry_promotion.py` at 80%.
- Full Ruff: passed for `src` and `tests`.
- Full Pyright: 0 errors, 0 warnings, 0 informations.
- Unstaged and staged diff checks: passed.

## PR-46 CURATION-001 Registry-Promotion Preview Plan

Date: 2026-07-13

Status: `complete` for the bounded registry-promotion preview/plan after PR #61
merged as `2b6c639`; PR-45 is complete after PR #60 merged as `5ac7864`.

Completed in this pass:

- Added top-level `plan_registry_promotion(...)` support for an in-memory
  `CurationResult` or a written owned curation bundle. Written inputs verify the
  curation manifest kind/schema and every declared artifact checksum before
  accepted records are read.
- Limited consideration to explicit accepted decisions. Rejected, deferred,
  omitted, blocked, malformed, and non-owned inputs cannot enter a plan.
- Mapped curation `parameter_records` only to the registry index's `parameters`
  key and resolved every supported destination solely from the supplied
  `registry_index.yml` records mapping. Traversal, absolute/out-of-root paths,
  symlink components, shared target files, malformed record files, and missing
  destinations fail or remain explicitly blocked.
- Added deterministic per-record `addable`, `exact_duplicate`, `conflict`, and
  `blocked_unsupported` classifications. Existing IDs are never overwritten;
  product maps are blocked as `unsupported_pending_destination_contract`
  because they remain outside the registry index.
- Preserved accepted target-record fields without scientific inference or
  transformation while keeping curator-decision metadata separately visible in
  the plan. Each addable candidate is validated through the actual
  `load_registry(...)` path in a temporary copied registry and must round-trip
  to the exact candidate mapping through the loaded record's existing
  `to_dict()` schema. Unknown fields that loaders would silently drop and
  omitted fields they would synthesize/default are blocked. Scalar comparisons
  are recursively type-exact, so booleans, integers, and floats cannot silently
  compare equal after loader conversion. Exact duplicates remain raw
  stored-content comparisons with the same scalar-type fidelity before this
  addable-only fidelity gate.
- Revalidated every accepted record against the existing CURATION-001 contract:
  unresolved `missing_fields` or `reasons` and incomplete source provenance are
  rejected for both in-memory and checksum-valid written bundles.
- Added exact prospective YAML content, target paths, before/post SHA-256
  values, an unchanged-registry digest, a prospective full-registry digest, and
  a deterministic plan digest. The complete combined prospective registry is
  loaded and validated again before a plan is returned.
- Added optional deterministic `promotion_plan.json`,
  `candidate_classifications.yml`, `promotion_report.md`, and
  `prospective_registry/` review artifacts with transactional replacement only
  for an existing folder carrying the owned plan manifest kind/version. Output
  paths that equal, descend from, or contain a registry root are rejected before
  replacement, and write-time digest verification rejects mutated nested plan
  payloads before creating output.
- Kept the API preview-only: there is no `apply()` path, production registry
  mutation, record overwrite, simulation promotion, version bump policy,
  scientific validation claim, live API behavior, biology, solver, calibration,
  or validation-data change. Digest-confirmed transactional apply and version
  policy remain PR-47 concerns.

Tests added or modified: `tests/test_registry_promotion_plan.py` covers a
schema-valid addable parameter, byte-for-byte registry immutability, exact
duplicate/no-op, same-ID conflict, unsupported product maps, reject/defer
exclusion, valid and checksum-tampered written bundles, malformed/non-owned
bundles, index traversal/symlink/out-of-root destinations, target-schema and
loader-fidelity failures for unknown and omitted/defaulted fields, prospective
full-registry validation failures, type-exact boolean/integer-versus-float
comparisons, accepted-record blocker and provenance revalidation for memory and
checksum-valid written bundles, shared ISO-date validation for accepted records
from both input forms, deterministic digests/artifacts, refusal after plan
mutation, safe owned output replacement, bidirectional registry-root overlap
refusal with byte-preservation proof, and public exports.
`tests/test_roadmap_orchestration_status.py` keeps the PR-45/PR-46/PR-47 queue,
partial CURATION-001 status, and deferred validation wording synchronized.

What did not change: `data_registry/`, registry versions, source proposal or
curation-decision behavior, simulation eligibility, live-source behavior,
process laws, solver and thermodynamic behavior, biology, parameters, units,
validation data, calibration, and empirical comparison are unchanged.

Scientific behavior impact: none. This slice validates and previews exact file
content only; it does not establish scientific validity or authorize any record
for simulation.

Backward compatibility: all existing source-provider, curation, registry, and
simulation APIs remain unchanged. The preview API, result types, and artifacts
are additive, and no apply method exists.

Remaining ambiguity and risk: registry version policy and the exact
digest-confirmed transactional apply authorization remain intentionally
undefined until PR-47. Product-map destination ownership also remains undefined
and therefore blocked. Human curator decisions remain outside software
validation.

Risk level: moderate. The runtime scope is isolated from production mutation,
but it introduces security-sensitive path/checksum handling and exact
prospective file/digest contracts that PR-47 may later consume.

Recommended next task: review and merge PR-46, then implement PR-47 as a
separately reviewed digest-confirmed transactional apply operation with an
explicit version policy, rollback behavior, and unchanged no-overwrite/path
boundaries. Keep validation deferred until source-backed observations satisfy
its evidence gate.

Verification:

- Focused registry-promotion plan suite: 34 passed.
- Focused promotion/curation/orchestration suite: 84 passed.
- Combined promotion/curation/registry-loading/public/status suite: 104 passed.
- Broad curation, registry, public-API, instruction, hygiene, source-provider,
  virtual-experiment, and roadmap suite: 223 passed.
- `MPLCONFIGDIR=/private/tmp/fungmod-mpl-cache PYTHONPATH=src /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
  - Result: 838 passed in 127.10 seconds; total coverage 84.74%, above
    the required 80%; `registry_promotion.py` coverage 80%.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache PYTHONPATH=src /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m ruff check src tests`
  - Result: all checks passed. The main checkout interpreter is used because
    ignored virtual environments are not copied into git worktrees.
- `PYTHONPATH=src /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m pyright --pythonpath /Users/felix/Documents/GitHub/FungMod/.venv/bin/python`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## PR-45 CURATION-001 Source-Proposal Review And Decision Bundle

Date: 2026-07-13

Status: `complete` for the bounded proposal-review and curator-decision bundle
after PR #60 merged as `5ac7864`; PR-44 is complete after PR #59,
CURATION-001 remains `partial`, and
VALIDATION-DATA-001 remains `deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added top-level `review_source_proposal(...)` support for either an in-memory
  `RegistryProposal` or its written `proposal_manifest.json` bundle through one
  normalization and validation path.
- Added per-record `eligible_for_review` versus `blocked_excluded`
  classification with exact missing fields and typed record-specific schema
  reasons. Unknown biology, parameters, units, and review-required fields
  remain explicit and are never filled or inferred.
- Required every proposed product-map substrate/product participant
  stoichiometry to parse as a finite positive number. Product yields must be
  finite positive numerics, map unambiguously to product participant names or
  ids through the existing SABIO token normalization, and match participant
  stoichiometry within `1e-12` relative tolerance and zero absolute tolerance.
  Float-conversion overflow from oversized JSON integers is classified as
  malformed rather than aborting review. No stoichiometric conversion or
  fallback is performed.
- Added explicit `accept`, `reject`, and `defer` decisions requiring curator
  identity, reason, ISO curation date, closed review-only/pending-promotion
  allowed use, and limitations. Acceptance additionally requires complete
  source database, snapshot-or-URL, entry provenance, and explicit original
  and converted parameter values/units/conversion method. Reject/defer may
  preserve provenance blockers. Every omitted decision remains deferred, and
  blocked records cannot be accepted.
- Added deterministic `curation_report.md`, `eligible_records.csv`,
  `excluded_records.csv`, `proposed_registry_records.yml`,
  `accepted_registry_records.yml`, `rejected_registry_records.yml`, and
  checksummed `curation_manifest.json` artifacts with canonical serialization
  and transactional repeated-write replacement only for directories carrying
  the expected owned curation manifest kind/version.
- Preserved proposed record values and metadata verbatim, including source and
  normalized values/units plus conversion metadata when present. Accepted
  artifacts add a curator decision block but retain review-only separation.
- Rejected malformed manifests, duplicate record IDs, unknown decisions,
  incomplete decision metadata, unknown decision record IDs, path traversal,
  symlinks in every existing input/output path component, unowned output
  directories, and writes beneath `data_registry/`.
- Exported the concise API at top level and added a README example with the
  explicit non-promotion boundary.

Tests added or modified: `tests/test_curation_review.py` covers normal frozen
SABIO-RK review, all-deferred default behavior, explicit accepted/rejected
decisions, exact blockers, provenance, value/unit/conversion preservation,
registry immutability, deterministic transactional outputs and checksums,
malformed/duplicate/path/decision failures, owned output replacement, canonical
serialization, full path-component symlink rejection, strict product-map
participant/yield stoichiometry and consistency, and offline socket
containment. Oversized participant stoichiometry and yield integers are covered
as blocked records that cannot be accepted but can be explicitly rejected or
deferred.
`tests/test_roadmap_orchestration_status.py` keeps PR-44/PR-45, partial
CURATION-001, future promotion, and deferred validation wording synchronized.

What did not change: `data_registry/`, simulation eligibility, source proposal
generation, live-source behavior, parser behavior, process laws, solver and
thermodynamic behavior, biology, parameters, units, validation data,
calibration, and empirical comparison are unchanged.

Scientific behavior impact: none. This slice validates proposal structure and
records human decisions only. It does not establish scientific validity or
authorize simulation.

Backward compatibility: all existing source-provider, proposal, registry, and
simulation APIs remain unchanged. The curation API and artifacts are additive.

Remaining ambiguity and risk: curator decisions still require human scientific
judgment. Acceptance in this bundle is not production registry promotion, and
CURATION-001 remains partial until a separate explicit promotion operation is
implemented and reviewed.

Risk level: low to moderate. Runtime scope is isolated from simulation and the
production registry, while file/bundle validation and replacement behavior are
new public surfaces.

Recommended next task after this completed slice: implement PR-46 as a bounded
registry-promotion preview plan with explicit destination control and
registry-schema validation, leaving digest-confirmed transactional apply and
version policy to PR-47. Keep validation deferred until source-backed
observations satisfy its evidence gate.

Verification:

- Focused curation, source-provider, and discovery suite: 75 passed.
- Broad curation, SABIO-RK source/discovery/parser/fetch, Reaction 618,
  registry, public-API, instruction-hierarchy, and roadmap suite: 169 passed.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache .venv/bin/python -m ruff check src tests`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.
- Unfiltered full coverage gate: 773 passed, 1 failed; total coverage 84.85%.
  The sole failure was the unrelated repository-hygiene assertion because the
  ignored pre-existing
  `notebooks/examples/.ipynb_checkpoints/10_virtual_experiment_product_tour-checkpoint.ipynb`
  remains in the shared workspace with a 2026-06-20 timestamp. PR-45 did not
  create, modify, delete, or stage it.
- Review-correction full coverage gate before the final product-map P1,
  excluding only that unrelated workspace-hygiene assertion: 783 passed,
  1 deselected; total coverage 84.93%. The curation module had 88%
  branch-aware coverage at that checkpoint. The final product-map P1 then ran
  the focused, broad, Ruff, Pyright, and diff gates requested above.
- One initial broad-suite command named nonexistent
  `tests/test_active_instruction_docs.py` and collected no tests; it was
  corrected to `tests/test_active_instruction_hierarchy.py` in the green broad
  run. A module-targeted coverage command also hit a NumPy collection error;
  the repository-standard `--cov=fungal_model` commands collected and ran
  normally.

## PR-44 Researcher Source-Provider Onboarding UX

Date: 2026-07-12

Status: `complete` after PR #59 merged for the bounded public SABIO-RK provider
UX slice; PR-43 is complete after PR #58, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added top-level `source_proposal(provider="sabiork", ...)` onboarding that
  requires only one friendly scientific selector and returns the existing
  review-only `RegistryProposal`.
- Reused existing `SabioRKSource` discovery, parsing, filtering, and proposal
  generation. Common `reaction_id`, EC number, enzyme, substrate,
  organism/source, and entry identifiers derive the source query without
  exposing raw Solr syntax in the new API.
- Moved the existing SABIO-RK HTTP/freeze implementation into the package and
  kept the fetch CLI as a thin wrapper, so explicit `refresh=True` freezes the
  raw response plus fetch metadata through one implementation.
- Hardened the review follow-up so every refresh writes a unique query-specific
  snapshot bundle. Exact HTTP page bodies remain separate under `raw/`, the
  parser reads `derived/combined_export.json`, and `fetch_metadata.json` binds
  every artifact with SHA-256 checksums instead of sharing or overwriting files.
- Applied the official SABIO-RK query semantics: all text terms are quoted,
  embedded quotes/backslashes are escaped, boolean/operator text remains
  literal inside quotes, the documented `Enzymename` field is used, and SABIO
  reaction/entry IDs accept only positive unquoted decimal forms.
- Removed `live_fetcher` from the new top-level `source_proposal(...)`
  signature so public refresh cannot bypass shared freeze/provenance handling.
  The legacy `SabioRKSource(live_fetcher=...)` hook remains backward compatible.
- Kept SABIO-RK keyless: no credential is required, read, used, stored, or
  included in query/cache/proposal artifacts. A supplied credential fails with
  a redacted provider-specific error before any filesystem or transport action.
- Unknown providers list only `sabiork`; no BRENDA, CAZy, or other provider is
  claimed.

Tests added or modified: `tests/test_source_provider_api.py` covers the minimal
no-key call, injected fake transport refresh/freeze, friendly query derivation,
official quote/backslash/operator escaping, strict numeric IDs, two-query
immutable bundle/metadata pairing, multi-page raw preservation and checksums,
secret redaction and non-persistence, review-only proposal gate, production
registry immutability, unknown provider, missing selector, public-signature
containment, and refresh failure. Existing SABIO-RK adapter/discovery/fetch and
public-API guardrails remain covered.

What did not change: existing `SabioRKSource` and `live_fetcher` signatures,
source parsing/proposal schemas, production registry records, simulation and
test network behavior, biology, solver behavior, thermodynamics, validation
data, calibration, and empirical comparison are unchanged.

Scientific behavior impact: none. Source records remain review-only proposals
and are never trusted or promoted into simulation automatically. Live refresh
is explicit and outside simulation/tests.

Backward compatibility: the existing `SabioRKSource` constructor,
`live_fetcher` hook, parser/proposal behavior, and fetch CLI command remain
available. The fetch CLI now writes its returned export and metadata inside a
unique nested bundle instead of shared output filenames. The unmerged new
top-level API intentionally removes its custom-fetcher bypass before release.

Remaining ambiguity and risk: SABIO-RK source completeness and scientific
suitability still require human review. Only SABIO-RK is implemented, and live
service behavior remains external to offline verification.

Recommended next task: implement PR-45 as a bounded CURATION-001
source-proposal review and explicit decision bundle without production registry
promotion.

Verification:

- Focused source/public/status suite after the review follow-up: 64 passed.
- Broad SABIO-RK, Reaction 618, notebook, registry, public-API, virtual-
  experiment, active-instruction, repository-hygiene, and roadmap suite after
  the review follow-up: 140 passed.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache .venv/bin/python -m ruff check src tests scripts/fetch_sabiork_kinlaw_entries.py`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## PR-43 Process-Bound Entropy-Production-Rate Timeseries

Date: 2026-07-12

Status: `complete` after PR #58 merged for the bounded THERMO-003
configured-output diagnostics slice; PR-42 is complete after PR #57, and
broader THERMO-003 remains `partial`.

Completed in this pass:

- Added a typed optional
  `outputs.entropy_production_rate_timeseries` configured contract that binds a
  known process id to explicit sourced condition-specific delta Gibbs,
  positive temperature, reaction-extent-rate interpretation, target
  extent-rate units, provenance refs, and an optional sourced unit-bearing
  native-rate conversion.
- Derived `entropy_production_rate(t) = -DeltaG * extent_rate(t) / T` after the
  solver finishes, from the native `SimulationResult.process_rates` trajectory
  only. Direct molar extent-rate trajectories and explicitly converted mass
  rates are covered by artificial framework benchmarks.
- Added configured `entropy_production_rate_timeseries.json` and `.csv`
  artifacts with process/time/value/units/provenance/status/guardrail fields,
  automatic output-manifest inclusion, and Markdown/HTML/index report
  visibility.
- Added explicit failures for unknown configured processes, absent native
  trajectories, incompatible or undefined units, nonpositive temperature,
  non-finite or misaligned trajectories, and unsupported metadata. No default
  conversion or inferred value is used.

Tests added or modified: `tests/test_configured_model_workflow.py` covers the
converted-rate path, direct molar-rate path, artifact schema and values,
manifest/report visibility, and each required failure boundary.

What did not change: the ODE right-hand side, process rate laws, solver
settings, state trajectories, native process-rate trajectories, existing
scalar `entropy_production_rate_metadata` validator and thermodynamic-summary
row contract, validation/calibration behavior, and biology are unchanged.

Scientific behavior impact: additive diagnostics only. Delta G remains a
caller-supplied condition-specific constant for each configured diagnostic;
there is no inferred Q/activity/concentration/redox/electron balance, dynamic
Delta G, energy gate, or solver-time thermodynamic enforcement.

Backward compatibility: existing configs emit no new artifact and follow the
same result/output behavior. Existing scalar entropy metadata remains
supported unchanged. The new contract is opt-in and rejects incomplete or
dimensionally dishonest metadata.

Remaining ambiguity and risk: callers remain responsible for the scientific
meaning and provenance of the declared process-rate-to-reaction-extent mapping.
The software verifies units and explicit metadata, not empirical validity or
whether a constant condition-specific Delta G is appropriate across a run.

Recommended next task: review and merge PR-43 as the bounded process-rate
diagnostics slice while keeping THERMO-003 partial. Then take the requested
provider UX as a separately scoped PR-44 rather than adding it to this
thermodynamics slice.

Verification:

- Focused configured-workflow suite: 44 passed.

## PR-42 Arbitrary-Length Linear Enzyme-Chain Assembly

Date: 2026-07-12

Status: `complete` after PR #57 merged for the bounded arbitrary-length linear
enzyme-chain assembly slice.

Completed in this pass:

- Replaced the exactly-two-process guard in the registry/template-driven
  extracellular enzyme-chain assembler with explicit ordered linear-topology
  validation for two or more process templates.
- Added bounded indexed intermediate/catalyst/enzyme state-role support while
  preserving every existing case-template role and schema version.
- Require one unique one-reactant/one-product stoichiometric map per ordered
  process, exact process/map state-role agreement, contiguous step order,
  unique topology states, and `substrate`/`product` endpoints.
- Emit the validated process, product-map, role, and state sequences as
  inspectable `case_template.chain_topology` config metadata.
- Reject fewer than two steps, process/map count mismatches, repeated process
  or product-map IDs, disconnected/reordered steps, branching maps, cycles,
  repeated states, and process/map role mismatches before model execution.
- Extended the unrelated copied-registry framework benchmark to three process
  steps, four topology states, three catalyst states, explicit conservation
  weights, an existing product-inhibition modifier on the third step, and the
  existing configured execution/standard-table path. The fixture is artificial
  software evidence only, not scientific or validation data.
- Preserved the existing BIO-002 two-step template, configured process/state
  IDs, researcher-facing CASE-001 API path, conservation semantics, modifiers,
  provenance, maturity, assumptions, limitations, and standard output labels.
- Updated README capability text, BIO-002 documentation, roadmap/status queue,
  validation-gate wording, and Phase 1 finding status so arbitrary-length
  linear support is explicit while branching and cycles remain unsupported.

Tests added or modified: expanded
`tests/test_bio002_generic_chain_assembly.py` for three-step assembly/execution,
conservation and output semantics, third-step modifier mapping, minimum-length,
disconnected, branching, cyclic, and malformed topology rejection; preserved
the existing BIO-002 and researcher API regression suites.

No new rate law, production constant, empirical record, validation data,
calibration claim, inferred parameter, hidden notebook science,
substrate/fungus-specific generic branch, or scientific validation claim was
added. Existing two-step scientific/numerical behavior and public helper
signatures are backward compatible. The new behavior is limited to templates
that previously failed solely because they declared more than two valid linear
steps.

Remaining ambiguity and risk: the schema intentionally supports only ordered
acyclic linear topology. Branching, converging multi-reactant steps, cycles,
and general pathway graphs remain unsupported and must not be claimed.

Recommended next task: implement PR-43 as a bounded process-bound
entropy-production-rate configured-output diagnostic from native process-rate
trajectories only when explicit dimensionally compatible metadata are present.

Verification:

- Focused chain baseline before edits: 21 passed.
- Focused chain/registry/API/modifier suite: 54 passed.
- Broad relevant suite spanning chain assembly, modifier mapping, registry
  templates, BIO readiness, modelability, ensembles, public APIs, environment
  grids, hardcoding guardrails, roadmap status, and findings: 130 passed.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache .venv/bin/python -m ruff check src tests`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath "$(.venv/bin/python -c 'import sys; print(sys.executable)')"`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.
- Unfiltered full coverage gate before the final additional malformed-topology
  test: 700 passed, 1 failed, total coverage 84.63%. The sole failure was
  `test_no_notebook_checkpoints_remain_in_working_tree` because the ignored
  pre-existing file
  `notebooks/examples/.ipynb_checkpoints/10_virtual_experiment_product_tour-checkpoint.ipynb`
  remains in the shared workspace. Its filesystem timestamp is 2026-06-20 and
  PR-42 did not create, modify, delete, or stage it.
- Final-tree full coverage gate excluding only that unrelated workspace-hygiene
  assertion: 701 passed, 1 deselected; total coverage 84.64%.
- One initial broad-suite command named nonexistent `tests/test_modelability.py`
  and collected no tests; it was corrected to `tests/test_modelability_report.py`
  in the 130-test green run above.

## PR-41 Pyright Optional-Member-Access Ratchet

Date: 2026-07-11

Status: `complete` for the global optional-member-access typing ratchet once
merged; PR-40 is complete after PR #55, FD-005 is resolved, and
VALIDATION-DATA-001 remains `deferred; blocked/partial` for ingestion.

Completed in this pass:

- Enabled Pyright `reportOptionalMemberAccess` globally in
  `pyrightconfig.json` without disabling or weakening another diagnostic.
- Quantified the pre-change baseline at 35 optional-member-access errors across
  11 modules: configured calibration, calibration fitting, stoichiometry, core
  validators, Gaussian pH kinetics, PET substrate metadata, diffusion,
  transport geometry, Monte Carlo uncertainty, local sensitivity, and static
  balance workflow helpers.
- Narrowed nullable `Parameter.quantity` and optional uncertainty parameters
  with precise local `Quantity`/`Parameter` annotations after existing
  validation contracts. No value was defaulted, guessed, ignored, or cast to
  `Any`.
- Updated the README quality-gate text, architecture-debt register, Phase 1 QA
  finding, active roadmap/status queue, validation gate, and focused quality
  and roadmap guardrail tests.
- Recorded PR-40 complete after PR #55 and made PR-41 the current-next PR while
  keeping validation deferred behind its evidence gate.

No scientific equation, parameter value, quantity conversion, numerical
tolerance, solver path, model output, validation data, calibration result,
biology record, notebook behavior, public API, or output schema changed. The
narrowing uses runtime-neutral precise annotations where existing validation
already establishes non-null state, so no reachable control-flow boundary was
changed and no new behavioral test was warranted.

Recommended next task: add the bounded public-API conservation diagnostics
example notebook previously identified after PR-40, using only the standard
table/accessor and header-only guardrail without changing configured-output
artifacts or scientific behavior.

## PR-40 Virtual-Experiment Conservation Diagnostics Bridge

Date: 2026-07-11

Status: `complete` for the scoped PR-40 standard-table/accessor bridge after PR
#55 merged; PR-39 is complete after PR #54, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added `conservation_diagnostics.csv` as a standard virtual-experiment output
  table with schema/data-dictionary coverage in output schema version `1.7.0`.
- Added `DegradationScreenResult.conservation_diagnostics()` for loading the
  standard table without rerunning simulations.
- The table is populated only by reading existing per-sample configured-output
  `conservation_diagnostics.json` and `conservation_diagnostics.csv` artifacts
  from sample bundle directories.
- Rows copy artifact-presence flags, top-level configured conservation
  diagnostics fields, configured row fields, and explicit interpretation
  guardrails.
- If no configured conservation diagnostics artifacts exist, the standard
  table is written header-only rather than inferring conservation metadata.
- Added Markdown, HTML, report-folder index, and output-manifest visibility
  while preserving configured-output conservation artifact generation and row
  behavior unchanged.
- Added focused virtual-experiment tests for package-generated artifact-field
  copying, the header-only no-artifact case, accessor/schema/report visibility,
  and queue/status contracts.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-39 is complete after
  PR #54 and PR-40 is the current conservation diagnostics bridge slice.

No conserved quantity, tolerance, pass/fail threshold, validation rule,
validation evidence, chemistry, thermodynamics, calibration, empirical
comparison, biology record, solver behavior, scientific numerical behavior,
configured-output conservation artifact schema, or hidden notebook science
changed.

Recommended next task: add a bounded public-API conservation diagnostics
example notebook over the standard table/accessor and its header-only guardrail,
without changing configured-output artifacts or scientific behavior.

## PR-39 Virtual-Experiment Solver Diagnostics Bridge

Date: 2026-07-10

Status: `complete` for the scoped PR-39 standard-table/accessor bridge after PR
#54 merged; PR-38 is complete after PR #53, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added `solver_diagnostics.csv` as a standard virtual-experiment output table
  with schema/data-dictionary coverage in output schema version `1.6.0`.
- Added `DegradationScreenResult.solver_diagnostics()` for loading the standard
  table without rerunning simulations.
- The table is populated only by reading existing per-sample configured-output
  `solver_diagnostics.json` and `solver_diagnostics.csv` artifacts from sample
  bundle directories.
- Rows copy artifact-presence flags, top-level configured solver diagnostics
  metadata, configured row fields, and explicit allowed-use/interpretation
  guardrails.
- If no configured solver diagnostics artifacts exist, the standard table is
  written header-only rather than inferring solver metadata.
- Added report/index standard-table visibility while preserving the existing
  configured-output report links for configured `solver_diagnostics.json` and
  `solver_diagnostics.csv` artifacts.
- Updated focused virtual-experiment tests to prove both the header-only
  no-artifact case and the artifact-derived row case.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-38 is complete after
  PR #53 and PR-39 is the current solver diagnostics bridge slice.

No solver behavior, numerical quality threshold, validation rule, calibration
routine, empirical comparison claim, validation data, biology record,
thermodynamic enforcement, hidden notebook science, silent fallback constant,
scientific inference, configured-output row schema, or notebook behavior
changed.

Recommended next task: continue build-first simulator capability work,
preferably with a bounded mechanism, thermodynamic inspectability, or
table-derived output ergonomics slice, rather than validation ingestion.

## PR-38 Solver Diagnostics Example Notebook

Date: 2026-07-10

Status: `complete` for the scoped PR-38 solver diagnostics example notebook
after PR #53 merged; PR-37 is complete after PR #52, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added `notebooks/examples/19_solver_diagnostics_example.ipynb` as a public
  configured-workflow example over package-generated configured solver
  diagnostics artifacts.
- The notebook runs the existing configured workflow to inspect
  `solver_diagnostics.json`, `solver_diagnostics.csv`, and report/index links
  for the normal metadata path.
- The notebook also demonstrates the explicit header-only/no-metadata
  guardrail by using package workflow helpers to write a bundle whose JSON
  reports `status: unavailable` and whose CSV keeps headers without row-level
  diagnostics.
- Updated notebook inventory/smoke tests so the new notebook remains
  package-output-driven, does not define hidden solver/rate-law logic, and
  verifies normal metadata, no-metadata, and report/index visibility paths.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-37 is complete after
  PR #52 and PR-38 is the current solver diagnostics example-notebook slice.

No solver behavior, numerical threshold, validation rule, calibration routine,
empirical comparison claim, validation data, biology record, thermodynamic
enforcement, hidden notebook science, silent fallback constant, scientific
inference, configured-output row schema, or report-generation behavior changed.

Recommended next task: choose another small build-first simulator capability
slice, preferably a bounded generic mechanism, thermodynamic inspectability, or
table-derived output ergonomics follow-up, rather than validation ingestion.

## PR-37 Solver Diagnostics Visibility Follow-Up

Date: 2026-07-10

Status: `complete` for the scoped PR-37 solver diagnostics visibility
follow-up after PR #52 merged; the current next task is PR-38 solver
diagnostics example notebook, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added Markdown report visibility for existing configured-output
  `solver_diagnostics.json` and `solver_diagnostics.csv` artifacts when
  `write_report(...)` is pointed at a configured-output folder.
- Added optional HTML report and report-folder index links for those existing
  solver diagnostics artifacts, matching the established configured-output
  artifact navigation pattern.
- Kept the section presentation-only and metadata-derived: it summarizes the
  existing JSON status, metadata-availability state, missing solver-metadata
  fields, and existing CSV rows without interpreting numerical quality.
- Added focused configured-output tests for the available-metadata and
  header-only/no-metadata solver diagnostics visibility paths.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-36 is complete after
  PR #51 and PR-37 is the selected visibility follow-up.

No solver behavior, numerical threshold, validation rule, calibration routine,
empirical comparison claim, validation data, biology record, thermodynamic
enforcement, hidden notebook science, silent fallback constant, scientific
inference, output generation behavior, or configured-output row schema changed.

Recommended next task: choose another small build-first simulator capability
slice, preferably the PR-38 solver diagnostics example notebook, rather than
validation ingestion.

## PR-36 Configured-Output Solver Diagnostics

Date: 2026-07-06

Status: `complete` for the scoped PR-36 configured-output solver diagnostics
slice after PR #51 merged; the current next task is PR-37 solver diagnostics
visibility follow-up, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added `solver_diagnostics.json` and `solver_diagnostics.csv` to configured
  result bundles.
- Derived diagnostics only from existing configured run metadata, solver
  settings, solver metadata, time-grid/evaluation counts, state counts, and
  process counts already available on the configured workflow result/model.
- Recorded config/run identity, model version, state/process counts, configured
  time-grid bounds and evaluation count, result time-point count, solver
  backend, method, success/status/message, nfev/njev/nlu, tolerances, optional
  max step, allowed-use text, and interpretation guardrails where solver
  metadata exists.
- Wrote deterministic header-only CSV plus JSON `status: unavailable` behavior
  when solver metadata is absent.
- Updated configured-output tests, manifest expectations, active README
  capability text, roadmap/status docs, validation-gate current-next wording,
  and roadmap orchestration status tests.

No solver behavior, numerical threshold, validation rule, calibration routine,
empirical comparison claim, validation data, biology record, thermodynamic
enforcement, hidden notebook science, silent fallback constant, or scientific
inference was added.

Recommended next task: complete PR-37 as a small simulator diagnostics
visibility follow-up that remains metadata/table-derived and improves
configured bundle navigation without changing solver or scientific behavior.

## PR-35 Repository Hygiene Guardrail Extension

Date: 2026-07-06

Status: `complete` for the scoped PR-35 repository hygiene guardrail extension
after PR #50 merged; PR-36 configured-output solver diagnostics is the current
next build-first simulator diagnostics slice, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added a `.gitignore` rule for generated
  `foundation_progress/FUNGMOD_PROGRESS_REPORT_*.html` snapshots while leaving
  the tracked final-goal HTML plan allowed.
- Extended the git-backed repository hygiene test to reject tracked generated
  artifacts already covered by `.gitignore`, including Python/tool caches,
  coverage artifacts, build/dist/htmlcov/output folders, egg-info metadata,
  bytecode, logs, temporary files, `.DS_Store`, notebook checkpoints, and
  generated progress-report HTML snapshots.
- Added explicit guardrail assertions that generated progress-report HTML
  snapshots are ignored and that
  `foundation_progress/FUNGMOD_FINAL_GOAL_PR_PLAN_2026_06_20.html` remains
  tracked and allowed.
- Updated active roadmap/status docs and roadmap orchestration tests so PR-34
  is complete after PR #49, PR-35 is the current hygiene guardrail extension,
  and the recommended next task is a simulator-building diagnostics follow-up.

No code behavior, solver behavior, validation rule, calibration routine,
notebook output, validation data, biology record, thermodynamics, empirical
comparison claim, scientific output schema, or numerical behavior changed.

Recommended next task: complete PR-36 configured-output solver diagnostics as
a focused simulator diagnostics slice that improves inspectability without
changing scientific or numerical behavior unless explicitly tested.

## PR-34 Configured-Output Conservation/Drift Diagnostics

Date: 2026-07-06

Status: `complete` for the scoped PR-34 configured-output conservation/drift
diagnostics slice after PR #49 merged; broader solver diagnostics remain a
follow-up, and VALIDATION-DATA-001 remains `deferred; blocked/partial` for
ingestion.

Completed in this pass:

- Added `conservation_diagnostics.json` and `conservation_diagnostics.csv` to
  configured result bundles.
- Derived diagnostics only from existing `SimulationResult` state trajectories
  and explicit configured `mass_balance` validators that declare
  `conserved_weights`.
- Recorded validator id, optional `closed_system`, weighted state metadata,
  initial and final conserved totals, final drift, maximum absolute drift,
  relative maximum drift when the initial total is finite and nonzero, units,
  row status/reason, and allowed-use text.
- Wrote deterministic header-only CSV plus JSON `evaluated_count: 0` behavior
  when no explicit configured mass-balance weights are present.
- Kept missing-state and incompatible-unit behavior explicit rather than
  silently coercing diagnostics.
- Updated configured-output tests, manifest expectations, active README
  capability text, roadmap/status docs, validation-gate current-next wording,
  and roadmap orchestration status tests.

No validation data, calibration routine, empirical comparison claim, fitted
curve, new validation rule, solver equation, threshold change, thermodynamic
enforcement, biology record, hidden notebook science, or silent fallback
constant was added.

Recommended next task: after PR-34 merged, complete the focused PR-35
repository hygiene guardrail extension, then choose a simulator-building
diagnostics follow-up that improves inspectability without changing scientific
or numerical behavior unless explicitly tested.

## PR-33 Chain-Template Explicit Environment Modifier Assembly

Date: 2026-07-05

Status: `complete` for the scoped PR-33 chain-template explicit environment
modifier assembly slice once merged; broader environment-response biology
remains explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Extended BIO-002-style chain process-template assembly so explicit
  per-process `modifiers` records can emit configured
  `temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
  `water_activity_threshold` modifiers using the same existing configured
  modifier field names as PR-31.
- Added explicit chain environment context handling through an optional
  `environment_id` builder argument and the researcher-facing registry case
  environment id. Chain templates with environment modifiers now fail if no
  explicit environment id is supplied by the caller or template metadata.
- Added package-generated configured environment entities for chain configs
  when environment modifiers require runtime environment values, sourced only
  from exact registry environment conditions.
- Shared the registry-template environment modifier assembly helper between
  one-process case-template assembly and chain process-template assembly so the
  same explicit role, exact ValueSpec, oxygen-units, and environment-source
  guardrails apply.
- Added copied-registry tests proving chain process templates emit
  temperature/pH and oxygen/water-activity modifiers, expose exact environment
  snapshots and configured metadata, change process-rate inspection outputs,
  and fail clearly for missing role fields, unresolved roles, missing
  environment context, missing environment conditions, non-exact environment
  values, and missing oxygen units.

No validation data, calibration routine, empirical comparison claim, fitted
temperature, pH, oxygen, or water-activity response curve, organism-specific
physiology, inferred environment response, oxygen consumption state, gas
transfer, redox balance, anaerobic metabolism, substrate water-binding model,
EnvironmentGrid behavior change, new response law, solver-time thermodynamic
enforcement, hidden notebook science, or silent fallback constant was added.

Recommended next task: choose a focused PR-34 simulator diagnostics slice, such
as solver diagnostics or conservation/drift diagnostics, unless review finds a
smaller follow-up in the chain-template modifier path.

## PR-32 Repository Hygiene Cleanup

Date: 2026-07-05

Status: `complete` for the scoped repository hygiene cleanup after PR #47
merged; no scientific, numerical, solver, notebook-output, validation-data,
calibration, or biology behavior changed.

Completed in this pass:

- Removed the tracked generated macOS metadata files `.DS_Store`,
  `data/.DS_Store`, `data/experiments/.DS_Store`,
  `data/experiments/synthetic/.DS_Store`,
  `foundation_progress/.DS_Store`, `notebooks/.DS_Store`,
  `notebooks/examples/.DS_Store`, `old_progress/.DS_Store`, and
  `src/.DS_Store`.
- Updated `.gitignore` so `.DS_Store` files and notebook checkpoint
  directories remain untracked in future worktrees.
- Added `tests/test_repository_hygiene.py` to assert that generated metadata
  files such as `.DS_Store`, `.pyc`, `__pycache__`, and
  `.ipynb_checkpoints` are not tracked by git.
- Updated the active roadmap/status current-next wording after PR #46 so
  PR-31 was treated as merged and the cleanup slice became the
  machine-checkable PR-32 current next item until PR #47 merged.

No `old_progress/` content, scientific fixtures, validation datasets, notebook
outputs, solver behavior, response-law behavior, calibration path, or biology
records were changed or deleted beyond the tracked `.DS_Store` metadata file.

Recommended next task: after PR-32 merges, choose a scoped PR-33 simulator
building slice such as chain-template explicit environment modifier assembly,
or a focused solver diagnostics slice. Revisit VALIDATION-DATA-001 only if
source-backed numeric time-course observations satisfying the active evidence
gate are available.

## PR-30 Configured Oxygen And Water-Activity Modifier Example Notebook

Date: 2026-07-05

Status: `complete` for the scoped PR-30 public configured-workflow example
notebook slice after PR #45 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added
  `notebooks/examples/18_configured_oxygen_water_modifiers_example.ipynb` to
  demonstrate configured `oxygen_monod` and `water_activity_threshold` rate
  modifiers through `run_configured_model(...)` and package-generated
  configured outputs.
- The notebook creates a temporary artificial framework-benchmark config from
  the existing homogeneous software-test benchmark, adds explicit artificial
  oxygen half-saturation and minimum water-activity parameter records, and
  keeps the source labelled as non-biological software-test data.
- The notebook inspects `configured_metadata.json`, `assumptions.json`,
  `merged_parameters.json`, `entity_snapshots/`, `input_model_config.json`,
  and `process_rates.csv` so explicit modifier parameters, oxygen units, and
  explicit environment oxygen/water-activity values are visible from
  configured workflow outputs.
- Updated notebook inventory/smoke tests so the new notebook remains
  JSON-valid, public-API/configured-runner only, free of hidden rate laws or
  solver logic, and executable with temporary outputs.
- Updated active README and roadmap/status docs so PR-29 is complete after
  PR #44, PR-30 is the build-first oxygen/water-activity configured modifier
  example notebook slice selected after PR #44, and VALIDATION-DATA-001
  remains deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, fitted
oxygen or water-activity response curve, organism-specific physiology, inferred
environment response, oxygen consumption state, gas transfer, redox balance,
anaerobic metabolism, substrate water-binding model, EnvironmentGrid behavior
change, solver/model behavior, registry biology record, hidden notebook
science, thermodynamic enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## PR-31 Registry-Backed Explicit Environment Modifier Assembly

Date: 2026-07-05

Status: `complete` for the scoped PR-31 registry-backed explicit environment
modifier assembly slice after PR #46 merged; broader environment-response
biology remains explicit-config only, chain-template environment modifier
support remains a follow-up, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Extended one-process registry case-template assembly so explicit
  `process_modifiers` records can emit configured
  `temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
  `water_activity_threshold` modifiers using existing configured modifier
  field names.
- Added builder checks that modifier records must supply required role fields,
  roles must resolve to explicit parameter records, oxygen modifiers must
  declare `oxygen_units`, and required registry environment conditions must be
  present and exact before a model config is emitted.
- Added package-generated environment config references for one-process
  registry configs when explicit environment modifiers require runtime
  environment values, sourced only from the registry environment record.
- Allowed configured input loading to consume inline environment config data,
  matching the existing inline entity pattern for other configured entities.
- Added copied-registry tests proving temperature/pH and oxygen/water-activity
  one-process template modifiers emit configured metadata, environment entity
  snapshots, and inspectable process-rate changes, plus clear builder failures
  for unresolved roles, missing environment conditions, non-exact environment
  values, and missing oxygen units.
- Inspected `src/fungal_model/screening/enzyme_chain.py`; chain templates
  still support explicit product-inhibition modifiers only. Extending the same
  environment modifier records to chain templates needs a follow-up slice so
  chain-specific environment record selection and entity emission can stay
  explicit and tested.

No validation data, calibration routine, empirical comparison claim, fitted
temperature, pH, oxygen, or water-activity response curve, organism-specific
physiology, inferred environment response, oxygen consumption state, gas
transfer, redox balance, anaerobic metabolism, substrate water-binding model,
EnvironmentGrid behavior change, new response law, solver-time thermodynamic
enforcement, hidden notebook science, or silent fallback constant was added.

Recommended next task: complete the scoped PR-32 repository hygiene cleanup,
then choose a scoped follow-up such as chain-template explicit environment
modifier assembly, or revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available.

## PR-29 Explicit Oxygen And Water-Activity Configured Modifiers

Date: 2026-07-04

Status: `complete` for the scoped PR-29 configured oxygen and water-activity
modifier slice after PR #44 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Wired existing `OxygenModifier` and `WaterActivityModifier` response laws
  into configured process modifier construction through `oxygen_monod` and
  `water_activity_threshold` process modifiers.
- Configured generic processes now expose explicit parameter requirements for
  positive oxygen half-saturation symbols and minimum water-activity threshold
  symbols, using caller-supplied oxygen concentration units rather than inferred
  defaults.
- Configured output metadata now records explicit oxygen and water-activity
  modifier rows with maturity labels and limitations, while preserving existing
  product-inhibition and pH/temperature metadata.
- Added focused process-factory and configured-workflow tests proving explicit
  oxygen and water-activity modifiers change configured generic process rates
  when explicit parameters and environment values are supplied.
- Added guardrail tests for missing configured modifier fields, missing required
  parameters, missing environment oxygen/water-activity values, missing
  environment entities, non-positive oxygen half-saturation, and unsupported
  modifier types.
- Updated active README and roadmap/status docs so PR-28 is complete after
  PR #43, PR-29 is the build-first explicit oxygen/water-activity configured
  modifier slice selected after PR #43, and VALIDATION-DATA-001 remains
  deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, fitted
oxygen or water-activity response curve, organism-specific physiology, inferred
environment response, oxygen consumption state, gas transfer, redox balance,
anaerobic metabolism, substrate water-binding model, EnvironmentGrid behavior
change, registry biology record, hidden notebook science, solver-time
thermodynamic enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## PR-28 Configured Environment Modifier Example Notebook

Date: 2026-07-04

Status: `complete` for the scoped PR-28 public configured-workflow example
notebook slice after PR #43 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added `notebooks/examples/17_configured_environment_modifiers_example.ipynb`
  to demonstrate configured `temperature_arrhenius_reference` and
  `ph_gaussian` rate modifiers through `run_configured_model(...)` and
  package-generated configured outputs.
- The notebook creates a temporary artificial framework-benchmark config from
  the existing homogeneous software-test benchmark, adds explicit artificial
  Arrhenius and Gaussian pH parameter records, and keeps the source labelled as
  non-biological software-test data.
- The notebook inspects `configured_metadata.json`, `assumptions.json`,
  `merged_parameters.json`, `entity_snapshots/`, `input_model_config.json`,
  and `process_rates.csv` so explicit modifier parameters and explicit
  environment temperature/pH values are visible from configured workflow
  outputs.
- Updated notebook inventory/smoke tests so the new notebook remains
  JSON-valid, public-API/configured-runner only, free of hidden rate laws or
  solver logic, and executable with temporary outputs.
- Updated active README and roadmap/status docs so PR-27 is complete after
  PR #42, PR-28 is the current build-first environment-modifier example
  notebook slice, and VALIDATION-DATA-001 remains deferred behind the evidence
  gate.

No validation data, calibration routine, empirical comparison claim, fitted
pH/temperature response curve, organism-specific physiology, inferred
environment response, runtime EnvironmentGrid behavior change, solver/model
behavior, registry biology record, hidden notebook science, oxygen/redox
behavior, thermodynamic enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## PR-27 Explicit Configured Environmental Rate Modifiers

Date: 2026-07-04

Status: `complete` for the scoped PR-27 configured environment-modifier slice
after PR #42 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Wired existing `TemperatureModifier` and `PHModifier` response laws into
  configured process modifier construction through
  `temperature_arrhenius_reference` and `ph_gaussian` process modifiers.
- Configured generic processes now expose explicit parameter requirements for
  Arrhenius activation/reference temperature symbols and Gaussian pH
  optimum/width symbols, including optional configured validity-bound symbols.
- Configured output metadata now records explicit pH/temperature modifier rows
  with maturity labels and limitations, while preserving existing
  product-inhibition metadata.
- Added focused process-factory and configured-workflow tests proving explicit
  pH/temperature modifiers change configured generic process rates when
  explicit parameters and environment values are supplied.
- Added guardrail tests for missing configured modifier symbols, missing
  required parameters, missing environment pH/temperature values, and
  unsupported modifier types.
- Updated active README and roadmap/status docs so PR-26 is complete after
  PR #41, PR-27 is the build-first explicit environment-modifier slice, and
  VALIDATION-DATA-001 remains deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, fitted
pH/temperature response curve, organism-specific physiology, inferred
environment response, runtime EnvironmentGrid behavior change, solver law,
registry biology record, hidden notebook science, solver-time thermodynamic
enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## THERMO-003 Virtual-Experiment Thermodynamic Diagnostics Example Notebook

Date: 2026-07-01

Status: `complete` for the scoped PR-26 example-notebook slice once merged;
broader THERMO-003 remains `partial` for dynamic thermodynamic and entropy
constraints, and VALIDATION-DATA-001 remains `deferred; blocked/partial` for
ingestion.

Completed in this pass:

- Added `notebooks/examples/16_thermodynamic_diagnostics_example.ipynb` as a
  public-API example for the standard `thermodynamic_diagnostics.csv` table and
  `DegradationScreenResult.thermodynamic_diagnostics()` accessor.
- The notebook demonstrates the normal header-only/no-artifact case for
  virtual-experiment samples that have no configured thermodynamic summary
  artifacts.
- The notebook then uses `run_configured_model(...)` to generate package-owned
  `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts from
  explicit configured metadata, copies only those artifacts into a
  virtual-experiment sample bundle, and reruns the standard table writer.
- Updated notebook smoke tests so the new example remains public-API-only,
  executable with temporary outputs, and bounded to existing configured
  artifacts plus standard result-table/report access.
- Updated active README and roadmap/status docs so PR-25 is complete, PR-26 is
  the current build-first notebook slice, and VALIDATION-DATA-001 remains
  deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, inferred
activity model, inferred reaction quotient, inferred concentration, redox
potential model, electron-balance model, solver-time thermodynamic
enforcement, biological mechanism, numerical model, solver behavior, registry
record, hidden notebook science, schema change, CSV row-contract change, or
silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting, digitizing, or fabricating validation data.

## THERMO-003 Virtual-Experiment Thermodynamic Diagnostics Bridge

Date: 2026-07-01

Status: `complete` for the scoped PR-25 standard-table/accessor bridge after
PR #40 merged; broader THERMO-003 remains `partial` for dynamic thermodynamic and
entropy constraints, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added `thermodynamic_diagnostics.csv` as a standard virtual-experiment
  output table with schema/data-dictionary coverage in output schema version
  `1.5.0`.
- Added `DegradationScreenResult.thermodynamic_diagnostics()` for loading the
  standard table without rerunning simulations.
- The table is populated only by reading existing per-sample configured-output
  `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts from
  sample bundle directories.
- Rows copy artifact-presence flags, configured row names/statuses, residual
  and equation fields, entropy-budget summary fields when present, and explicit
  allowed-use/interpretation guardrails.
- If no configured thermodynamic artifacts exist, the standard table is written
  header-only rather than failing validation or inventing diagnostics.
- Added report/index standard-table link visibility through the existing table
  link pattern.
- Updated focused virtual-experiment tests to prove both the header-only
  no-artifact case and the artifact-derived row case.

No validation data, calibration routine, empirical comparison claim, inferred
activity model, inferred reaction quotient, inferred concentration, redox
potential model, electron-balance model, solver-time thermodynamic
enforcement, biological mechanism, numerical model, solver behavior, registry
record, hidden notebook science, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting, digitizing, or fabricating validation data.

## BIO-003 Non-PET Product-Inhibition Genericity Hardening

Date: 2026-07-01

Status: `complete` for the scoped PR-24 build-first genericity-hardening slice
after PR #39 merged; broad BIO-003 remains `partial/software-tested`, and
VALIDATION-DATA-001 remains `deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added
  `data/model_configs/toy_surface_dummy_non_pet_product_inhibition.yml`, a
  `mode: toy`, `maturity: framework_benchmark` configured model derived from
  the generic non-PET surface benchmark.
- The fixture adds an explicit artificial product-state `K_i` parameter and a
  `product_inhibition` modifier on the existing dummy surface-catalysis
  process, labelled as software benchmark/testing coverage rather than
  biological evidence.
- Updated configured workflow tests so `run_configured_model(...)` executes
  the non-PET product-inhibition fixture and verifies configured modifier
  metadata, the reversible product-inhibition assumption surface, artificial
  `K_i` labelling, mode/maturity labels, and successful validation output.
- Updated active README, BIO-003 notes, roadmap/status docs, validation gate
  docs, and queue-status tests so PR-24 is the selected build-first BIO-003
  slice because the validation evidence gate remains blocked.

No new biology, validation data, calibration routine, empirical comparison
claim, solver law, numerical behavior change, registry biology record,
researcher-facing API change, live API call, silent fallback constant,
scientific `K_i` claim, toxicity, uptake, secretion, biomass, physiology, or
multi-product inhibition support was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting, digitizing, or fabricating validation data.

## PRODUCT-001 Provenance/Limitations Report Example Notebook

Date: 2026-07-01

Status: `complete` for the scoped PR-23 example-notebook slice once merged;
PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added `notebooks/examples/15_provenance_limitations_report_example.ipynb`
  as a public-API example that runs an existing supported exploratory virtual
  experiment, writes the Markdown report plus optional HTML sidecar and
  report-folder index, and inspects the provenance/limitation decision summary.
- The notebook loads existing decision-support rows through public
  `DegradationScreenResult` accessors for assumptions, limitations, missing
  parameters, suggested experiments, and provenance.
- The notebook checks existing report/index links for
  `assumption_summary.csv`, `limitations_table.csv`,
  `missing_parameters.csv`, `suggested_experiments.csv`, and
  `provenance_table.csv` without adding notebook-only scientific logic.
- Updated notebook smoke tests so the new example remains researcher-facing,
  unvalidated, public-API-only, and executable with temporary outputs.
- Updated active README and roadmap/status docs so PR-23 is complete for the
  scoped provenance/limitations report example-notebook slice, while
  VALIDATION-DATA-001 remains deferred and evidence-gated before any ingestion
  or empirical-comparison work.

No biological mechanism, numerical model, solver behavior, registry record,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, schema version change, CSV
row contract change, silent fallback constant, report utility behavior, or
hidden notebook science was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting or fabricating validation data.

## PRODUCT-001 Provenance/Limitations Report Ergonomics

Date: 2026-07-01

Status: `complete` for the scoped PR-22 report-inspection slice once merged;
PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added a provenance and limitation decision-summary section to the
  deterministic Markdown report, derived only from existing
  `assumption_summary.csv`, `limitations_table.csv`, `missing_parameters.csv`,
  `suggested_experiments.csv`, and `provenance_table.csv` rows.
- Expanded the report renderers for assumptions, limitations, missing
  parameters, suggested follow-up experiments, and provenance so row types,
  categories, severities, sources, missing statuses, suggested resolutions,
  allowed-use labels, and provenance record details are easier to inspect.
- Added optional HTML sidecar and report-folder index links for those existing
  decision-support tables while preserving the Markdown report as the primary
  contract.
- Updated focused report tests so real generated reports and small
  table-derived fixtures prove the new decision summary and richer row
  renderers without changing simulation behavior.
- Updated active README and roadmap/status docs so PR-22 is complete for the
  scoped provenance/limitations report ergonomics slice, PR-23 is the next
  build-first PRODUCT-001 provenance/limitations report example-notebook
  target, and VALIDATION-DATA-001 remains deferred to PR-24 or later.

No biological mechanism, numerical model, solver behavior, registry record,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, schema version change, CSV
row contract change, silent fallback constant, or hidden notebook science was
added.

Recommended next task: implement PR-23 as a small build-first PRODUCT-001
example-notebook slice that uses the public API to write reports and inspect
the provenance/limitation decision summary and decision-support table links,
without validation data, calibration, empirical comparison, inferred
environment responses, hidden notebook science, schema changes, or solver/model
changes.

## THERMO-003 Explicit Thermodynamic-Summary Report Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-21 report-inspection slice once merged;
THERMO-003 remains `partial` for broader dynamic thermodynamic and entropy
constraints.

Completed in this pass:

- Added an explicit thermodynamic-diagnostics section to the deterministic
  Markdown report when the report utility is pointed at a configured-output
  folder containing existing `thermodynamic_summary.json` and
  `thermodynamic_summary.csv` artifacts.
- Added optional HTML sidecar and report-folder index links for those existing
  thermodynamic summary artifacts without adding them to the virtual-experiment
  standard table schema.
- Kept the report section bounded to existing configured-output diagnostics:
  summary counts, explicit-Q/entropy-rate flags, entropy-budget fields,
  supported/unsupported-scope text, and row-level residual/equation fields.
- Updated focused configured-output/report tests so a real
  `run_configured_model(...)` explicit-Q Gibbs run proves Markdown, HTML, and
  index visibility for `thermodynamic_summary.json` and
  `thermodynamic_summary.csv`.
- Updated active README and roadmap/status docs so PR-21 is complete for the
  scoped thermodynamic-summary report ergonomics slice, PR-22 is the next
  build-first PRODUCT-001 provenance/limitations report ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-23 or later.

No inferred activities, inferred reaction quotients, inferred concentrations,
redox-potential model, electron-balance model, biological mechanism, numerical
model, solver behavior, registry record, validation data, calibration routine,
empirical comparison claim, schema version change, CSV row contract change,
silent fallback constant, or hidden notebook science was added.

Recommended next task: implement PR-22 as a small build-first PRODUCT-001
slice that improves provenance, limitation, missing-parameter, or
suggested-experiment inspection in existing report/index paths, without
validation data, calibration, empirical comparison, inferred environment
responses, hidden notebook science, schema changes, or solver/model changes.

## PRODUCT-001 Threshold-Time Inspection And Report Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-20 report-inspection slice once merged;
PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added `summary_metrics.csv` to the report/index standard-table links so
  aggregate threshold quantiles are easier to inspect beside per-sample
  threshold rows.
- Expanded the deterministic Markdown report's threshold-time section to show
  existing `threshold_times.csv` rows and existing `summary_metrics.csv`
  threshold quantiles with explicit guardrails.
- Updated report tests so Markdown, HTML, and index outputs expose the
  threshold-time guardrails and `summary_metrics.csv` links.
- Updated active README and roadmap/status docs so PR-20 is complete for the
  scoped threshold-time inspection slice, PR-21 is the next build-first
  THERMO-003 explicit thermodynamic-summary report ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-22 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant,
CSV row contract change, schema version change, or notebook-only scientific
implementation was added.

Recommended next task: implement PR-21 as a small build-first THERMO-003 slice
that improves explicit thermodynamic-summary report or inspection ergonomics
from existing configured-output diagnostics only, without inferred
thermodynamics, validation data, calibration, empirical comparison, hidden
notebook science, or solver/model changes.

## PRODUCT-001 Degradation-Rate Quicklook And Report Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-19 quicklook/report inspection slice
once merged; PRODUCT-001 remains `partial` for broader researcher-facing
output ergonomics.

Completed in this pass:

- Added a presentation-only `degradation_rate_vs_time.png` quicklook figure
  generated from existing `time_series_long.csv` `degradation_rate` rows.
- Added a bounded degradation-rate inspection section to the deterministic
  Markdown report, with optional HTML/index visibility flowing through the
  existing report paths and standard table links.
- Updated virtual-experiment API and report tests so the quicklook figure,
  manifest entry, report guardrails, and `time_series_long.csv` report links
  are exercised.
- Updated active README and roadmap/status docs so PR-19 is complete for the
  scoped degradation-rate inspection slice, PR-20 is the next build-first
  PRODUCT-001 threshold-time inspection/report ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-21 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant,
CSV row contract change, or notebook-only scientific implementation was added.

Recommended next task: implement PR-20 as a small build-first PRODUCT-001
slice that improves threshold-time inspection/report ergonomics from existing
`threshold_times.csv`, `summary_metrics.csv`, and report/index paths with
explicit guardrails, without validation data, calibration, empirical
comparison, inferred environment responses, hidden notebook science, or
solver/model changes.

## PRODUCT-001 Trajectory-Quantile Example And Quicklook Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-18 example/quicklook inspection slice
once merged; PRODUCT-001 remains `partial` for broader researcher-facing
output ergonomics.

Completed in this pass:

- Added `notebooks/examples/14_trajectory_quantiles_example.ipynb` as a
  public-API example that runs an existing exploratory virtual experiment,
  writes standard outputs and reports, loads `trajectory_quantiles.csv` through
  `DegradationScreenResult.trajectory_quantiles()`, and verifies trajectory
  guardrails.
- Added a presentation-only `trajectory_quantile_bands.png` quicklook figure
  generated from existing `trajectory_quantiles.csv` rows.
- Updated notebook and virtual-experiment API tests so the example, quicklook
  figure, report links, and guardrail columns are exercised.
- Updated active README and roadmap/status docs so PR-18 is complete for the
  scoped trajectory-quantile inspection slice, PR-19 is the next build-first
  PRODUCT-001 degradation-rate quicklook/report ergonomics target, and
  VALIDATION-DATA-001 remained deferred behind build-first simulator work.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant,
CSV row contract change, or notebook-only scientific implementation was added.

Recommended next task: implement PR-19 as a small build-first PRODUCT-001
slice that improves degradation-rate inspection and report/quicklook
ergonomics from existing standard output tables with explicit guardrails,
without validation data, calibration, empirical comparison, inferred
environment responses, hidden notebook science, or solver/model changes.

## PRODUCT-001 Trajectory-Quantile Output Ergonomics

Date: 2026-06-29

Status: `complete` for the scoped PR-17 derived-output/report ergonomics
slice once merged; PRODUCT-001 remains `partial` for broader
researcher-facing output ergonomics.

Completed in this pass:

- Added `trajectory_quantiles.csv` as a standard virtual-experiment output
  table derived from existing `time_series_long.csv` sample rows.
- Added `DegradationScreenResult.trajectory_quantiles()` for loading
  trajectory bands without rerunning simulations.
- Updated the Markdown report, optional HTML sidecar, and report-folder index
  so the new standard table is visible while preserving explicit
  interpretation guardrails.
- Updated the versioned output schema and data dictionary to `1.4.0`,
  including machine-readable allowed-use, trajectory-band status, and
  interpretation-guardrail columns.
- Updated active README and roadmap/status docs so PR-17 is complete for the
  scoped trajectory-quantile output ergonomics slice, PR-18 is the next
  build-first PRODUCT-001 trajectory-quantile example and quicklook ergonomics
  target, and VALIDATION-DATA-001 remains deferred to PR-19 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant, or
notebook-only scientific implementation was added.

Recommended next task: implement PR-18 as a small build-first PRODUCT-001 slice
that improves trajectory-quantile inspection and quicklook ergonomics from
existing standard output tables with explicit guardrails, without validation
data, calibration, empirical comparison, inferred environment responses,
hidden notebook science, or solver/model changes.

## PRODUCT-001 Uncertainty-Band Output Ergonomics

Date: 2026-06-29

Status: `complete` for the scoped PR-16 derived-output/report ergonomics
slice once merged; PRODUCT-001 remains `partial` for broader
researcher-facing output ergonomics.

Completed in this pass:

- Added `uncertainty_summary.csv` as a standard virtual-experiment output
  table derived from existing sampled-parameter rows and per-case
  `summary_metrics.csv` quantiles.
- Added `DegradationScreenResult.uncertainty_summary()` for loading the
  uncertainty/range summary without rerunning simulations.
- Updated the Markdown report, optional HTML sidecar, and report-folder index
  so the new standard table is visible while preserving explicit
  interpretation guardrails.
- Updated the versioned output schema and data dictionary to `1.3.0`, including
  machine-readable allowed-use and uncertainty-band status columns.
- Updated active README and roadmap/status docs so PR-16 is complete for the
  scoped uncertainty-output ergonomics slice, PR-17 is the next build-first
  PRODUCT-001 trajectory-quantile output ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-18 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant, or
notebook-only scientific implementation was added.

Recommended next task: implement PR-17 as a small build-first PRODUCT-001 slice
that derives trajectory-level quantile or band outputs from existing
`time_series_long.csv` sample rows with explicit guardrails, without validation
data, calibration, empirical comparison, inferred environment responses, or
solver/model changes.

## THERMO-003 Entropy-Budget Notebook Inspection

Date: 2026-06-29

Status: `complete` for the scoped PR-15 notebook-inspection slice once merged;
THERMO-003 remains `partial` for broader dynamic thermodynamic and entropy
constraints.

Completed in this pass:

- Extended `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`
  so it inspects the package-generated entropy-budget fields in
  `thermodynamic_summary.json`.
- The notebook now displays `has_entropy_budget`, `entropy_budget_status`,
  evaluated and negative counts, units, total, and limitations from the JSON
  summary while confirming CSV output remains row-level diagnostics.
- Updated notebook tests so the static notebook contract and execution smoke
  path both prove the entropy-budget fields are visible and remain JSON-only.
- Updated active README and roadmap/status docs so PR-15 is complete for the
  scoped notebook-inspection slice, PR-16 is the next build-first PRODUCT-001
  uncertainty-band output ergonomics target, and VALIDATION-DATA-001 remains
  deferred to PR-17.

No source code, numerical model, solver behavior, biological mechanism,
registry record, validation dataset, calibration routine, empirical comparison
claim, inferred thermodynamics, inferred activity/reaction-quotient model,
solver-time thermodynamic enforcement, or output schema was added.

Recommended next task: implement PR-16 as a small PRODUCT-001 slice that
surfaces existing explicit uncertainty/range metadata more clearly in standard
outputs or reports without validation data, calibration, empirical comparison,
inferred environment responses, or silent fallback constants.

## PR-14 Post-Merge Current-Next Rollover

Date: 2026-06-29

Status: `complete` for the scoped docs/tests-only rollover once merged.

Completed in this pass:

- Marked the merged PR-14 configured entropy-budget summary as complete in the
  active orchestrator queue.
- Advanced the machine-checkable current-next target to PR-15 THERMO-003
  entropy-budget output notebook inspection so the next build-first slice makes
  the new JSON budget fields visible in a researcher-facing diagnostics path.
- Kept VALIDATION-DATA-001 deferred and moved its future queue slot to PR-16;
  validation still requires source-backed numeric time-course observations and
  must not be presented as complete by this rollover.
- Updated the roadmap/status contract tests so active docs and the validation
  gate agree on the current-next line and do not point back to completed PR-14
  in current-next wording.

No source code, numerical behavior, solver behavior, notebook behavior,
biological mechanism, registry record, validation dataset, calibration routine,
empirical comparison claim, inferred thermodynamics, or output schema was
changed.

Recommended next task: implement PR-15 as a small notebook/report-output slice
that inspects the configured entropy-budget JSON fields from explicit metadata
only, with no new equations, inferred thermodynamics, validation data, or
solver-time enforcement.

## THERMO-003 Configured Entropy-Budget Summary

Date: 2026-06-23

Status: `complete` for the scoped PR-14 configured entropy-budget summary
slice; THERMO-003 remains `partial` for broader dynamic thermodynamic and
entropy constraints.

Completed in this pass:

- Extended configured `thermodynamic_summary.json` with a top-level
  explicit-metadata-only entropy-production budget over existing
  `entropy_production_rate_metadata` validation rows.
- The budget includes only numeric `entropy_production_rate` values whose
  units are exactly `joule / second / kelvin`; missing, non-numeric, non-finite,
  or differently unitized rows remain unevaluated and are not treated as zero.
- Added focused configured-output tests for a single positive entropy-rate row
  and a mixed positive/negative/missing entropy-rate run, including aggregate
  total, minimum, evaluated count, negative count, status, and unchanged CSV
  row schema.
- Updated active README and roadmap/status docs so PR-13 is complete for the
  entropy-production-rate notebook coverage, this slice is PR-14 THERMO-003
  configured entropy-budget summary, and VALIDATION-DATA-001 is deferred to
  PR-15.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, inferred
thermodynamics, inferred activities, inferred reaction quotients, inferred
concentrations, redox-potential model, electron-balance model, solver-time
thermodynamic enforcement, notebook-only scientific implementation, or CSV row
schema change was added.

Recommended next task: after this configured entropy-budget summary slice is
reviewed and merged, either continue build-first simulator capability with a
small explicit-metadata-only THERMO/PRODUCT slice, or start PR-15
VALIDATION-DATA-001 only if a source-backed numeric time-course dataset
satisfies the active ingestion gate.

## THERMO-003 Entropy-Production-Rate Notebook Coverage

Date: 2026-06-23

Status: `complete` for the scoped PR-13 notebook-coverage slice;
THERMO-003 remains `partial` for broader dynamic thermodynamic and entropy
constraints.

Completed in this pass:

- Extended `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`
  so the configured-output fixture demonstrates both existing explicit
  reaction-quotient Gibbs metadata and existing entropy-production-rate
  metadata.
- The notebook still uses public configured workflow APIs and package-written
  `thermodynamic_summary.json` / `thermodynamic_summary.csv` outputs; it does
  not implement thermodynamic equations inside notebook cells.
- Added notebook smoke assertions proving the configured summary reports
  `has_entropy_production_rate`, the entropy-rate equation, positive explicit
  entropy-production-rate values, `joule / second / kelvin` units, and
  `solver_time_enforcement == not_evaluated`.
- Updated active README and roadmap/status docs so PR-12 is complete for the
  PRODUCT-001 comparison/report-output notebook, this slice is PR-13
  THERMO-003 entropy-production-rate notebook coverage, and
  the next build-first THERMO-003 slice is PR-14 before
  VALIDATION-DATA-001.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, inferred
thermodynamics, inferred activities, inferred reaction quotients, inferred
concentrations, redox-potential model, electron-balance model, solver-time
thermodynamic enforcement, or notebook-only scientific implementation was
added.

Recommended next task: after this notebook-coverage slice is reviewed and
merged, continue THERMO-003 only with another small generic constraint or
output slice that uses explicit configured metadata and tests, continue
PRODUCT-001 if the slice improves researcher-facing simulator capability from
existing outputs, or start validation-data work only when a source-backed
numeric time-course dataset satisfies the active ingestion gate.

## PRODUCT-001 Screen Comparison Summary Example Notebook

Date: 2026-06-23

Status: `complete` for the scoped PR-12 example-notebook slice;
PRODUCT-001 remains `partial` for broader researcher-facing output ergonomics.

Completed in this pass:

- Added `notebooks/examples/13_screen_comparison_summary_example.ipynb` as a
  public-API example for running an existing virtual experiment, writing
  standard outputs, writing Markdown/HTML/index report artifacts, and
  inspecting `comparison_summary.csv`.
- The notebook demonstrates metadata-only runtime environment-grid guardrails
  through `comparison_allowed`, `ranking_allowed`,
  `ranking_blocking_reason`, and `recommended_next_action` columns rather than
  ranking cases or plotting environmental response.
- Added notebook smoke coverage proving the example writes
  `comparison_summary.csv`, `output_manifest.json`,
  `virtual_experiment_report.md`, `virtual_experiment_report.html`, and
  `report/index.html`, and that metadata-only rows remain blocked from
  comparison/ranking use.
- Updated active README and roadmap/status docs so PR-11 is complete for
  screen-comparison summary ergonomics, this example notebook is PR-12
  PRODUCT-001 comparison/report-output example notebook, and
  VALIDATION-DATA-001 remains deferred behind the next build-first THERMO-003
  entropy-rate slices.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook-only
scientific implementation, inferred science, environment response law, ranking
of metadata-only environment cases, or hidden report logic was added.

Recommended next task: after this example-notebook slice is reviewed and
merged, continue PR-13 THERMO-003 entropy-production-rate notebook coverage
without adding new thermodynamic behavior, continue build-first PRODUCT-001
only if the next slice improves researcher-facing simulator capability from
existing outputs, or start validation-data work only when a source-backed
numeric time-course dataset satisfies the active ingestion gate.

## PRODUCT-001 Report-Folder Index Navigation

Date: 2026-06-22

Status: `complete` for the scoped PR-10 report-folder index/navigation slice;
PRODUCT-001 remains `partial` for broader researcher-facing output ergonomics.

Completed in this pass:

- Extended `DegradationScreenResult.write_report(..., include_index=True)` so it
  still writes and returns the deterministic Markdown report while optionally
  writing `report/index.html` navigation for the output folder.
- Added a deterministic stdlib HTML index that links existing report artifacts,
  standard CSV tables, `output_manifest.json`, and optional quicklook figures
  when present.
- Added focused tests proving default Markdown and HTML-sidecar behavior remain
  unchanged, the index is opt-in, HTML is escaped, relative links work for
  absolute and relative output directories, and no validation or calibration
  claims are introduced.
- Updated active README and roadmap/status docs so the current-next slice moves
  from the merged PR-09 HTML wrapper to PR-10 PRODUCT-001 report-folder
  index/navigation, with validation-data ingestion deferred behind the next
  build-first output ergonomics slice.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, inferred science, or hidden report logic was added.

Recommended next task: after this presentation-only index slice is reviewed and
merged, continue PR-11 PRODUCT-001 screen-comparison ergonomics if it remains
derived from standard outputs, or start PR-12 validation-data work only when a
source-backed numeric time-course dataset satisfies the active ingestion gate.

## PRODUCT-001 Screen Comparison Summary

Date: 2026-06-22

Status: `complete` for the scoped PR-11 screen-comparison summary ergonomics
slice; PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added `comparison_summary.csv` as a standard virtual-experiment output table
  derived from existing `final_metrics.csv`, `threshold_times.csv`, and
  environment guardrail rows.
- Added `DegradationScreenResult.comparison_summary()` for loading the guarded
  comparison summary without rerunning simulations.
- Added machine-readable comparison and ranking guardrail columns including
  `comparison_allowed`, `ranking_allowed`, `ranking_blocking_reason`, and
  `recommended_next_action`.
- Preserved existing standard-output units and metadata-only environment
  guardrails; runtime environment grids that are metadata-only remain blocked
  from ranking or environmental-response plot interpretation.
- Updated the versioned output schema and data dictionary to `1.2.0`, and
  included `comparison_summary.csv` in report-folder table links.
- Updated active README and roadmap/status docs so PR-10 is complete for
  report-folder index/navigation, this slice is PR-11 PRODUCT-001
  screen-comparison summary ergonomics, and VALIDATION-DATA-001 remains
  deferred behind the next build-first slice.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, inferred science, environment response law, ranking of metadata-only
environment cases, or hidden report logic was added.

Recommended next task: after this derived-output ergonomics slice is reviewed
and merged, continue PR-12 PRODUCT-001 comparison/report-output example
notebook work if it remains derived from existing standard outputs, or start
validation-data work only when a source-backed numeric time-course dataset
satisfies the active ingestion gate.

## PRODUCT-001 HTML Virtual-Experiment Report Wrapper

Date: 2026-06-22

Status: `partial` for researcher-facing report/output ergonomics.

Completed in this pass:

- Extended `DegradationScreenResult.write_report(..., include_html=True)` so it
  still writes and returns the deterministic Markdown report while also writing
  `virtual_experiment_report.html` beside it when requested.
- Added a small stdlib HTML renderer derived from the Markdown report and the
  same standard table/quicklook paths, with HTML escaping and relative links to
  existing CSV tables and optional quicklook figures.
- Added focused tests proving Markdown output remains the primary report,
  HTML output is opt-in, table-derived content is escaped deterministically,
  standard table and quicklook links are present, and no validation or
  calibration claims are introduced.
- Updated active README and roadmap/status docs so the current-next slice moves
  from the merged Markdown writer to this PRODUCT-001 HTML wrapper.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, or inferred science was added.

Recommended next task: continue PRODUCT-001 report-folder navigation or
screen-comparison ergonomics only if it remains a presentation layer over
standard output tables; otherwise keep validation-data ingestion deferred until
source-backed observations exist.

## BIO-003 Researcher-Facing Product Inhibition Example

Date: 2026-06-21

Status: `partial/software-tested` for broad BIO-003; complete for the scoped
researcher-facing example gap on the selected reversible-product-inhibition
target once this PR is merged.

Completed in this pass:

- Added `notebooks/examples/12_reversible_product_inhibition_example.ipynb`.
- Added `fungal_model.examples.prepare_reversible_product_inhibition_example_registry(...)`
  to prepare an explicit copied example registry fixture with a
  provenance-labelled exploratory `K_i`.
- The notebook compares inhibited and uninhibited exploratory virtual
  experiments through `virtual_experiment(...)`, then inspects
  `mechanism_summary.csv`, configured metadata, limitations, and final metrics.
- Added focused tests proving the example runs offline through public
  researcher-facing names, exposes the active `product_inhibition` rate
  modifier, records the example as non-validation data, and reduces final
  product concentration relative to the uninhibited deterministic run.
- Extended notebook smoke tests so the new example executes under
  `FUNGMOD_NOTEBOOK_OUTPUT_ROOT`.

No generic/core process behavior, numerical solver behavior, organism-specific
inhibition behavior, substrate-specific shortcut, competitive/uncompetitive/
mixed/multi-product inhibition, toxicity, uptake, secretion, biomass,
physiology, validation data, calibration routine, empirical comparison claim,
or fallback inhibition constant was added.

Recommended next task: after this PR is reviewed and merged, select the next
small BIO-003 mechanism-family candidate only if it can be implemented with
explicit provenance, maturity labels, tests, and honest limitations; otherwise
return to PRODUCT-001 output ergonomics or deferred validation-data gate work.

## PRODUCT-001 Virtual-Experiment Report Writer

Date: 2026-06-22

Status: `partial` for researcher-facing report/output ergonomics.

Completed in this pass:

- Added `DegradationScreenResult.write_report(...)` as a public result method
  that writes a deterministic Markdown report under `report/` by default.
- Added an internal report renderer that reads existing standard output tables:
  preflight/modelability, case summary, final metrics, threshold times,
  sampled parameters, mechanism summary, assumption summary, provenance,
  limitations, missing parameters, suggested experiments, and optional
  quicklook figure paths.
- Added focused Reaction 618 API coverage proving the report is written,
  includes table-derived facts and limitation language, exposes exploratory
  parameter assumptions, and does not make positive validation or calibration
  claims.
- Updated active roadmap/status docs to move the current next PR from the
  merged PR-07 BIO-003 example to this scoped PRODUCT-001 report-writer slice.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, or inferred science was added.

Recommended next task: continue PRODUCT-001 report/output ergonomics only if it
remains a presentation layer over standard tables; otherwise continue toward
researcher screen comparison reports.

## THERMO-003 Configured Entropy-Production-Rate Diagnostic

Date: 2026-06-21

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `validate_entropy_production_rate(...)`, a generic configured metadata
  diagnostic for
  `entropy_production_rate = -condition_specific_delta_gibbs * reaction_extent_rate / temperature`.
- Required explicit provenance-backed `Parameter` inputs for
  condition-specific delta G, reaction extent rate, and temperature, with unit
  checks for energy per mole, mole per time, and kelvin.
- Added configured-validator registry support through
  `entropy_production_rate_metadata`.
- Extended configured `thermodynamic_summary.json` and
  `thermodynamic_summary.csv` rows with entropy-production-rate fields while
  preserving existing reaction-quotient Gibbs fields.
- Added focused synthetic tests for positive and negative entropy-production
  rate cases, invalid temperature and units, missing quantities, registry
  loading, and configured JSON/CSV outputs.

No new biology, substrate-specific mechanism, fungus-specific branch, inferred
activity model, inferred reaction quotient, concentration model,
redox-potential model, electron-balance model, solver-time thermodynamic
enforcement, validation data, calibration routine, or empirical validation
claim was added.

Recommended next task: continue THERMO-003 only if another small generic
first-principles diagnostic has explicit configured inputs and tests, or move
to BIO-003 registry-backed case assembly for the already software-tested
product inhibition mechanism.

## BIO-003 Registry-Backed Product Inhibition Assembly

Date: 2026-06-21

Status: `partial/software-tested` for registry-backed assembly of the first
BIO-003 generic mechanism family where explicit records exist.

Completed in this pass:

- Extended registry-backed case-template assembly so explicit product
  inhibition modifier metadata maps into configured process `modifiers`.
- Supported chain process-template modifiers with explicit
  `product_state_role` and `inhibition_constant_role`, and one-process
  registry templates through `process_state_metadata.process_modifiers`.
- Added `mechanism_summary.csv` rate-modifier rows for active assembled
  product-inhibition modifiers in virtual-experiment outputs.
- Added focused copied-registry tests proving explicit registry template
  records emit configured modifiers, configured outputs expose modifier
  metadata, standard mechanism summaries show the active rate modifier, missing
  K_i records fail explicitly, non-positive K_i fails without fallback, and an
  unrelated non-specific chain remains unaffected.

No organism-specific inhibition behavior, substrate-specific shortcut,
competitive/uncompetitive/mixed inhibition, toxicity, uptake, secretion,
biomass, physiology, validation data, calibration routine, empirical
comparison claim, or fallback inhibition constant was added.

Recommended next task: add a public BIO-003 example or notebook that compares
explicit inhibited and uninhibited exploratory runs while preserving the
configured-mechanics and no-validation limitations.

## THERMO-003 Thermodynamics And Entropy Diagnostics Notebook

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`.
- The notebook builds a tiny configured software-test model from the existing
  toy homogeneous benchmark, adds an explicit
  `reaction_quotient_thermodynamic_metadata` validator, runs
  `run_configured_model(...)`, and inspects `thermodynamic_summary.json` and
  `thermodynamic_summary.csv`.
- Added notebook tests proving the file exists, imports public package code,
  avoids thermodynamics/core implementation internals, executes under
  `FUNGMOD_NOTEBOOK_OUTPUT_ROOT`, and writes both thermodynamic summary files.
- Reconciled active README and roadmap-status docs so THERMO-003 example
  coverage is visible in the current queue.

No scientific or numerical behavior, new biology, inferred activity model,
inferred reaction quotient, redox-potential model, solver-time thermodynamic
enforcement, validation data, calibration routine, or empirical validation
claim was added.

Recommended next task: continue THERMO-003 only with another small generic
constraint that has explicit configured inputs and tests, or return to BIO-003
registry-backed case assembly for the already software-tested product
inhibition mechanism.

## PRODUCT-001 Public Virtual-Experiment Product Tour Notebook

Date: 2026-06-20

Status: `partial` for examples and notebooks.

Completed in this pass:

- Added `notebooks/examples/10_virtual_experiment_product_tour.ipynb`.
- The notebook uses public APIs only: `virtual_experiment(...)`,
  `environment_grid(...)`, `preflight(...)`, `simulate(...)`, and standard
  table accessors.
- The notebook inspects `mechanism_summary`, `assumption_summary`,
  `limitations`, `final_metrics`, and `sampled_parameters`.
- Added smoke tests proving the notebook executes with
  `FUNGMOD_NOTEBOOK_OUTPUT_ROOT` and writes expected standard output tables.

No scientific or numerical behavior, new biology, registry records,
calibration routine, validation data, or empirical validation claim was added.

Recommended next task: add a BIO-003-specific notebook after registry-backed
product-inhibition case assembly exists, or add a thermodynamics/entropy
notebook using configured explicit-Q Gibbs outputs.

## PRODUCT-001 Mechanism Summary Output Table

Date: 2026-06-20

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `mechanism_summary.csv` as a standard virtual-experiment output table.
- Added the table to the versioned output schema and data dictionary, bumping
  the virtual-experiment output schema to `1.1.0`.
- Added `DegradationScreenResult.mechanism_summary()` to load the table through
  the public API.
- Populated one active process-law row per simulated case with mechanism kind,
  family, maturity, configured-by source, equation/law summary, state-variable
  roles, parameter roles/symbols, assumptions, limitations, and provenance.
- Added tests for homogeneous Michaelis-Menten and BIO-002 enzyme-chain virtual
  experiments.

No scientific or numerical behavior, registry records, new biology,
calibration routine, validation data, or empirical validation claim was added.

Recommended next task: add a product-tour notebook or expose BIO-003 product
inhibition through registry-backed case assembly so `mechanism_summary.csv`
can show active rate modifiers as well as process laws.

## BIO-003 Configured Reversible Product Inhibition

Date: 2026-06-20

Status: `partial/software-tested` for the first BIO-003 generic mechanism
family.

Completed in this pass:

- Added a generic `RateModifierProcess` wrapper that scales any configured
  process rate with explicit reusable modifiers.
- Added configured process `modifiers` support for `type: product_inhibition`
  with explicit `product_state` and `inhibition_constant`.
- Required the product state to exist and required `K_i` as a positive,
  unit-compatible parameter through the existing assembly/solver checks.
- Added configured output metadata for active process modifiers, including
  maturity and limitation text.
- Added non-specific tests for homogeneous first-order and generic surface
  configured processes, plus full configured-run tests proving active
  assumptions/output metadata, missing-`K_i`, and non-positive-`K_i` failure
  behavior.
- Updated the BIO-003 proposal from `proposed` to `software_tested`.

No organism-specific inhibition behavior, substrate-specific shortcut,
registry-backed case assembly, validation data, calibration routine, empirical
validation claim, or fallback inhibition constant was added.

Recommended next task: expose configured product inhibition through
registry-backed case assembly or add the first public API/notebook example that
shows outputs with and without the modifier while preserving limitations.

## BIO-003 Reversible Product Inhibition Scope Selection

Date: 2026-06-20

Status: `selected/proposed` for the first BIO-003 generic mechanism-family
target.

Completed in this pass:

- Added `foundation_progress/BIO_003_GENERIC_PROCESS_LAWS.md` to record the
  selected first BIO-003 target.
- Added the machine-checkable
  `foundation_progress/proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml`
  proposal.
- Selected generic reversible product inhibition as the next implementation
  target because the low-level `ProductInhibitionModifier` already exists, but
  configured/registry-backed virtual-experiment integration is not complete.
- Added the final-goal HTML PR plan as an active planning artifact:
  `foundation_progress/FUNGMOD_FINAL_GOAL_PR_PLAN_2026_06_20.html`.

No scientific or numerical behavior, configured workflow behavior, registry
records, simulation outputs, biology implementation, validation data,
calibration routine, or empirical validation claim was added.

Recommended next task: implement BIO-003 reversible product inhibition
integration as a small code PR with explicit product-state mapping, positive
unit-compatible `K_i`, output limitations, and at least two materially
different non-specific tests.

## THERMO-003 Configured Thermodynamic Summary CSV

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `thermodynamic_summary.csv` beside `thermodynamic_summary.json` for
  configured runs with thermodynamic validation results.
- Populated the CSV from the same summary rows as the JSON output so explicit
  Gibbs and entropy-production diagnostics are spreadsheet-friendly without a
  second source of truth.
- Added tests proving the CSV is written, contains the explicit-Q Gibbs
  equation and entropy diagnostic, and appears in `output_manifest.json`.

No new biology, substrate-specific mechanism, fungus-specific branch, activity
model, inferred reaction quotient, redox-potential model, solver-time
thermodynamic enforcement, validation data, calibration routine, or empirical
validation claim was added.

Recommended next task: move to BIO-003 with a small generic process-law
expansion, or continue THERMO-003 by adding carefully scoped configured
examples that exercise explicit thermodynamic metadata.

## THERMO-003 Configured Thermodynamic Summary Output

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `thermodynamic_summary.json` to configured-model output bundles when
  thermodynamic validation results are present.
- Summarized explicit reaction-quotient Gibbs rows, delta-G diagnostics,
  entropy-production-per-mole diagnostics, provenance refs, and the supported
  versus unsupported thermodynamic scope.
- Added a configured workflow test proving an explicit-Q Gibbs validator writes
  the summary and records it in the output manifest.

No new biology, substrate-specific mechanism, fungus-specific branch, activity
model, inferred reaction quotient, redox-potential model, solver-time
thermodynamic enforcement, validation data, calibration routine, or empirical
validation claim was added.

Recommended next task: continue THERMO-003 by adding first-class CSV/standard
table summaries for configured thermodynamics, or move to BIO-003 for a small
generic process-law expansion.

## THERMO-003 Reaction-Quotient Gibbs Feasibility

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `validate_reaction_quotient_gibbs_feasibility(...)`, a generic
  equation-backed validator for explicitly supplied reaction quotient metadata:
  `delta_g = delta_g_standard + R*T*ln(Q)`.
- Added entropy-production-per-mole reporting as `-delta_g / T`.
- Added a named, sourced ideal-gas constant parameter rather than a silent
  fallback constant.
- Added configured-validator registry support through
  `reaction_quotient_thermodynamic_metadata`.
- Added tests for favorable, unfavorable, invalid, and config-loaded synthetic
  reaction-quotient Gibbs cases.

No new biology, substrate-specific mechanism, fungus-specific branch, activity
model, inferred reaction quotient, redox-potential model, solver-time
thermodynamic enforcement, validation data, calibration routine, or empirical
validation claim was added.

Recommended next task: continue THERMO-003 by connecting explicit
reaction-quotient checks to configured output bundles, or return to
PRODUCT-001/BIO-003 for broader generic mechanism coverage.

## PRODUCT-001 Preflight Policy Columns

Date: 2026-06-20

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added explicit `mode` storage and serialization to `ModelabilityReport`.
- Added `assessment_mode`, `simulation_allowed_for_mode`,
  `blocking_reason`, and `recommended_next_action` columns to
  `modelability_preflight.csv`.
- Added versioned output-schema/data-dictionary coverage for the new columns.
- Added tests proving exploratory cases advertise simulation eligibility and
  blocked scientific preflight reports point to missing-input curation.

No new biology, validation data, simulation behavior, calibration routine,
thermodynamic equation, entropy calculation, environmental response law, or
empirical validation claim was added.

Recommended next task: continue PRODUCT-001 with richer researcher-facing input
coverage or start THERMO-003 with a small generic feasibility equation and
tests.

## PRODUCT-001 Preflight Report Writer

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `VirtualExperiment.write_preflight_report(...)` so researcher-facing
  inputs can write diagnostic modelability tables without assembling or running
  a model.
- Added `write_preflight_tables(...)` for preflight-only
  `modelability_preflight.csv`, `modelability_items.csv`, and the versioned
  data dictionary/schema.
- Marked preflight-only rows with `environment_effect_status=preflight_only`
  so they are not confused with simulated environment-response outputs.
- Added tests proving a scientific-mode case that would be blocked by
  `simulate(...)` still writes diagnostic preflight CSVs.

No new biology, validation data, simulation fallback, calibration routine,
thermodynamic equation, entropy calculation, environmental response law, or
empirical validation claim was added. Blocked cases still do not simulate.

Recommended next task: continue PRODUCT-001 with richer researcher-facing
input coverage or start a generic THERMO-003 feasibility slice with explicit
equations and tests.

## PRODUCT-001 Modelability Items Output

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `modelability_items.csv` to the standard virtual-experiment output
  bundle.
- Added `DegradationScreenResult.modelability_items()` for loading the table
  without rerunning simulation.
- Added versioned output-schema/data-dictionary coverage for the new table.
- Populated the table with every per-case preflight fact: known, uncertain,
  missing, and incompatible modelability items, including JSON details and
  machine-readable allowed-use policy.
- Added tests proving known process-compatibility facts and uncertain
  exploratory parameter facts are inspectable from standard outputs.

No new biology, validation data, calibration routine, thermodynamic equation,
entropy calculation, environmental response law, unsupported-case simulation
path, or empirical validation claim was added.

Recommended next task: continue PRODUCT-001 with a report-writing path for
blocked/unsupported preflight cases, or proceed to a generic THERMO-003
feasibility slice if a small equation-backed scope is clear.

## PRODUCT-001 Environment Grid Helper

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added the top-level researcher-facing `environment_grid(...)` helper as a
  convenience wrapper around `EnvironmentGrid`.
- Exported the helper from `fungal_model.api` and top-level `fungal_model`.
- Updated the README target workflow so researchers can pass runtime
  temperature, pH, and oxygen grids directly into `virtual_experiment(...)`.
- Added tests proving the helper works through the top-level API, standard
  outputs still write, runtime environment cases remain `metadata_only`, and
  the public API documentation/export guardrail includes the new helper.
- Updated active roadmap/status docs to keep PRODUCT-001 partial and current.

No new biology, validation data, pH response law, temperature response law,
oxygen response law, thermodynamic equation, entropy calculation, numerical
method, dataset, calibration routine, or empirical validation claim was added.
Runtime environment-grid values remain metadata unless an explicit response law
or condition-specific parameter record is active.

Recommended next task: continue PRODUCT-001 with a small code PR that improves
exploratory output usefulness, such as richer assumption/range summaries,
clearer missing-mechanism reporting, or broader generic mechanism selection
without fungus-specific branches.

## PRODUCT-001 Assumption Summary Output

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `assumption_summary.csv` to the standard virtual-experiment output
  bundle.
- Added `DegradationScreenResult.assumption_summary()` for loading the table
  without rerunning simulation.
- Added versioned output-schema/data-dictionary coverage for the new table.
- Populated the table with per-case modelability assumptions, uncertain inputs,
  missing inputs, incompatibilities, and suggested follow-up experiments.
- Added tests proving exploratory assumptions and uncertain parameter policies
  are inspectable from standard outputs.

No new biology, validation data, calibration routine, thermodynamic equation,
entropy calculation, environmental response law, or empirical validation claim
was added.

Recommended next task: continue PRODUCT-001 by improving missing-mechanism and
unsupported-case reporting for researcher-facing inputs, or proceed to a
generic THERMO-003 feasibility slice if a small equation-backed scope is clear.

## PR-04 Build-First Roadmap Reframe

Date: 2026-06-19

Status: `complete` once merged for documentation and guardrail-test scope.

Completed in this pass:

- Reframed VALIDATION-DATA-001 as deferred validation/calibration work rather
  than the blocker for all further repository progress.
- Kept validation in the roadmap and preserved the ingestion gate: real
  observations remain required before making validation, calibration, or
  empirical comparison claims.
- Set the current next PR to PRODUCT-001: build-first exploratory
  virtual-experiment expansion.
- Queued THERMO-003 for dynamic thermodynamic and entropy constraints and
  BIO-003 for generic mechanism expansion through implemented, tested process
  laws.
- Added guardrail tests so active docs keep validation deferred, keep
  PRODUCT-001 current, and require build-first work to preserve explicit
  assumptions, uncertainty, provenance, limitations, and missing-mechanism
  reporting.

No scientific model, numerical method, runtime behavior, output schema, public
API, dataset, validation observation, calibration routine, thermodynamic
equation, entropy calculation, or biology implementation was added in this
documentation reframe.

Recommended next task: implement PRODUCT-001 as a small code PR that expands
researcher-facing exploratory virtual experiments while keeping all assumptions
and unsupported biology explicit.

## PR-03 VALIDATION-DATA-001 Ingestion Gate

Date: 2026-06-19

Status: `blocked/partial` for real-data ingestion.

Completed in this pass:

- Expanded `foundation_progress/VALIDATION_DATA_001_FIRST_TIMECOURSE.md` from
  a stub into an active ingestion-gate/status document.
- Recorded that the existing Resa/Buckin 2011 candidate review remains blocked
  because no ingestable observation rows, observation CSV, extraction metadata,
  uncertainty policy, or preprocessing/conversion record is present.
- Recorded that the existing Ariaeenejad 2020 PersiBGL1 Frontiers candidate
  remains blocked because no machine-readable time-course table exists locally
  and the time axis has an unresolved source-text conflict between hour-based
  evidence and one sentence saying 380 min.
- Recorded the required evidence for a future ingestion PR: exact
  figure/table/supplement identifier, observation rows, units,
  extraction/transcription method, extractor/date, preprocessing/conversion
  notes, uncertainty policy, and explicit limitations.
- Updated the active orchestration and next-steps docs so PR-03 remains the
  current next PR and PR-04 is not advanced.
- Added focused tests proving the two real candidate reviews remain blocked and
  data-free, `data/experiments/literature/` contains no real data files, and
  active docs do not mark VALIDATION-DATA-001 complete or advance beyond PR-03.

No dataset, `raw_data.csv`, `curated_data.csv`, `model_comparison.csv`,
`residuals.csv`, `validation_report.md`, observation rows, literature CSV,
scientific model, parameter, numerical method, runtime behavior, output schema,
public API, external API call, or biology was added.

Recommended next task: find or obtain source-backed numeric time-course
observations satisfying the gate, then open a separate VALIDATION-DATA-001
ingestion PR with dataset files, model-comparison artifacts, limitations, and
tests.

## PR-02 CASE-001 Researcher-Facing Enzyme-Chain Virtual Experiment

Date: 2026-06-19

Status: `complete` for the scoped CASE-001 researcher-facing API path once
PR-02 is merged.

Completed in this pass:

- Exposed the existing BIO-002 extracellular enzyme-chain template through the
  top-level researcher-facing `virtual_experiment(...)` / `VirtualExperiment`
  API using names and aliases for the generic cellulase source, cellulose film,
  and 30 C pH 5 assay context.
- Added registry compatibility metadata for the existing BIO-002 chain so the
  CASE-001 path selects `extracellular_enzyme_chain` without requiring users to
  call `run_extracellular_enzyme_chain_demo(...)` directly.
- Taught modelability to choose the best supported implemented process path
  when the same source/substrate class has multiple scoped alternatives, so
  BIO-001 surface-catalysis metadata does not block the BIO-002 chain path.
- Taught exploratory ensemble simulation and standard result tables to use the
  BIO-002 template-owned parameter records and template suggested experiments.
- Added CASE-001 coverage proving alias resolution, standard output files,
  limitations, suggested experiments, no live socket use, and no unsupported
  whole-fungus/PET/lignin output states or metrics.
- Updated CASE-001 and orchestration docs to mark PR-02 complete once merged
  and set PR-03 VALIDATION-DATA-001 as the next PR.

No new biological mechanism, validation dataset, live external source call,
invented parameter, whole-fungus growth, secretion, uptake, biomass, PET,
lignin, full lignocellulose, organism-specific physiology, or empirical
validation claim was added.

## PR-01 Roadmap Orchestration And Phase Status Tracker

Date: 2026-06-19

Status: `complete` for the scoped documentation/status guardrail once PR-01 is
merged.

Completed in this pass:

- Added `foundation_progress/ROADMAP_ORCHESTRATION_STATUS.md` as the active
  orchestrated-PR workflow and phase-status tracker.
- Recorded the maker/reviewer/comment-loop/merge/next-PR workflow.
- Recorded the PR queue with PR-02 CASE-001 as the current next slice and
  VALIDATION-DATA-001 queued after it.
- Reconciled scoped completion/partial status for SOURCE-002, RESOLVE-001,
  ASSEMBLY-001 case-template basics, API-003, BIO-READINESS-LITE, BIO-002, and
  Phase 2 static balance checks.
- Added completion rules requiring tests, active-doc updates, `progress.md`
  updates, honest scope/limitations, no live external APIs in tests or
  simulation, no unsupported biology, and no silent fallback constants.
- Updated the active roadmap and next-steps document so future agents do not
  rebuild already completed scoped slices or treat `old_progress/` as binding.

No scientific models, parameters, numerical methods, public APIs, runtime
behavior, output schemas, source adapters, registry records, or biology changed.

## Phase 2 Task 4b Process-Reaction Binding For Static Balance Checks

Date: 2026-06-18

Status: `complete` for the corrective P2.4b binding gate. Static balance
checks can no longer pass merely because an unrelated declared reaction is
balanced; requested checks must now bind explicit reaction metadata to the
actual assembled process contributions through explicit process-state to
chemical-species mappings.

Completed in this pass:

- Added explicit `process_id` and state-to-species binding support for
  `balance_checks`.
- Verified each requested assembly-time balance check against the assembled
  process contribution signs and coefficients before running the chemical
  residual validator.
- Included process/reaction binding evidence, mapped process stoichiometry,
  reaction stoichiometry, role checks, product-map evidence, tolerance, and
  failure reasons in validation details.
- Added static balance check evidence to successful `AssemblyReport` payloads.
- Made required scientific/strict balance checks block on missing, unknown,
  duplicated, contradictory, coefficient-mismatched, or unrelated bindings.
- Kept configs without `balance_checks` unchanged.
- Added adversarial tests proving a process `A -> B` cannot pass with
  unrelated balanced metadata `X2 -> 2X`, plus missing/unknown/duplicated/
  contradictory binding tests and a product-map-backed
  homogeneous-Michaelis-Menten binding test.

No trajectory-level balance validation, dynamic Gibbs calculation, activity
model, redox potential, biological data, literature value, process rate
equation, solver equation, or real registry chemistry was added.

## Phase 2 Tasks 3-4 Static Metadata Schema And Assembly-Time Balance Checks

Date: 2026-06-16

Status: `complete` for the scoped P2.3/P2.4 static metadata and
assembly-time balance enforcement foundation. The full thermodynamic
feasibility blocker remains unresolved because dynamic reaction quotients,
activities, activity coefficients, redox potentials, and solver-time
thermodynamic constraints are still not implemented.

Completed in this pass:

- Added optional model-config schema surfaces for `chemistry_metadata`,
  `reaction_metadata`, and `balance_checks` while preserving existing config
  compatibility and raw passthrough.
- Added assembly-time static balance parsing for explicit configured species,
  reaction participant, and reaction metadata.
- Wired optional assembly-time elemental, charge, and electron/redox balance
  checks into configured model assembly.
- Made scientific and strict modes block required assembly-time static checks
  that fail, are unsupported, or are inconclusive because metadata are absent.
- Kept toy and exploratory runs non-blocking for these optional checks while
  recording `failed` or `inconclusive` validation results in the existing
  result/output validation path.
- Added tests proving schema recognition, passing metadata-backed elemental,
  charge, and electron-equivalent checks, exploratory inconclusive metadata
  output, scientific blocking on failed balance, strict blocking on missing
  reaction metadata, and unchanged existing configured-workflow behavior.

No dynamic thermodynamic validation, reaction-quotient calculation, activity
model, activity coefficient, redox potential, biological data, literature
value, process rate equation, solver equation, or real registry chemistry was
added.

## Phase 2 Task 2 Static Elemental and Thermodynamic Validator Foundation

Date: 2026-06-15

Status: `complete` for the scoped static validator foundation. The full
thermodynamic feasibility blocker remains unresolved because dynamic reaction
quotients, activities, activity coefficients, and solver-time thermodynamic
constraints are still not implemented.

Completed in this pass:

- Extended `ValidationResult` with backward-compatible `status`, `severity`,
  and `required` fields.
- Added explicit metadata residual primitives for elemental, charge, and
  electron-equivalent balance.
- Added static validators for elemental balance, charge balance,
  electron/redox balance, and condition-specific Gibbs feasibility.
- Made missing composition, charge, electron-equivalent metadata, unknown
  condition values, and unknown Gibbs values report `inconclusive` rather than
  passed.
- Made provenance failures report structured failed validation results.
- Registered the new static validators through `ValidatorRegistry` for
  explicit inline model-config use.
- Extended configured-output validation summaries with status and severity
  counts while preserving existing boolean `passed` behavior.
- Preserved strict-mode rejection of confirmed failures and added handling for
  required inconclusive/unsupported validation statuses.
- Added tests for balanced/unbalanced synthetic reactions, missing metadata,
  charge/electron checks, favorable/unfavorable/unknown Gibbs metadata,
  provenance failure, config registry integration, exploratory versus strict
  behavior, serialization, and existing validator compatibility.

No dynamic thermodynamic validation, reaction-quotient calculation, activity
model, activity coefficient, redox potential, biological data, literature
value, process rate equation, solver equation, or real registry chemistry was
added.

## Phase 2 Task 1 Thermodynamic and Balance Enforcement Design

Date: 2026-06-15

Status: `complete` for the scoped implementation plan only. The confirmed
thermodynamic feasibility and complete stoichiometric/redox enforcement
blockers remain unresolved.

Completed in this pass:

- Added `FUNGMOD_PHASE_2_THERMODYNAMIC_AND_BALANCE_ENFORCEMENT.md` as the
  staged design for thermodynamic and balance enforcement.
- Defined standard Gibbs energy, condition-specific Gibbs energy, and dynamic
  reaction Gibbs energy as separate concepts.
- Documented what FungMod can honestly enforce with current metadata and what
  remains unsupported.
- Specified elemental, charge, electron/redox, residual, tolerance, unit,
  provenance, mode, assembly-time, post-simulation, schema, API, output,
  migration, test, and milestone requirements.
- Updated `findings.yaml` only to point `P1-AUDIT-THERMO-001` and
  `P1-AUDIT-BALANCE-001` to the Phase 2 plan.

No production thermodynamic enforcement, redox enforcement, formulas, charges,
activity models, Gibbs values, biological data, solver behavior, public APIs,
output schemas, numerical methods, or scientific claims changed.

## Phase 1 Task 5 Documentation and Quality-Gate Synchronization

Date: 2026-06-15

Status: `complete` for the scoped documentation, audit-status, and Phase 1
quality-gate synchronization.

Completed in this pass:

- Reconciled active README capability claims, public API documentation,
  roadmap status notes, Phase 1 reports, and the machine-readable audit
  catalogue with the post-P1.4 repository state.
- Marked Phase 1 complete in
  `FUNGMOD_PHASE_1_REPOSITORY_TRUTH_AND_EXECUTION_HARDENING.md` only after
  verifying the instruction hierarchy, audit catalogue, native execution
  guardrails, adapter retirement, Ruff, Pyright, full tests, and coverage gate.
- Clarified that BIO-001/BIO-002 cellulose-related paths are implemented and
  technically verified only for scoped exploratory pilots, not scientifically
  validated default cellulose degradation.
- Added a migration note for former `process.as_reaction()` users: use native
  process execution or construct an explicit low-level `Reaction`.
- Removed the unsupported tracked notebook checkpoint artifact.
- Added focused documentation synchronization tests for public API docs,
  capability labels, adapter-retirement wording, audit status, checkpoint
  cleanup, and Phase 1 completion status.

No scientific models, parameters, numerical methods, public APIs, runtime
behavior, output schemas, or biology changed.

## Phase 1 Task 1 Instruction-Hierarchy Cleanup

Date: 2026-06-14

Status: `complete` for the scoped instruction/documentation guardrail cleanup.

Completed in this pass:

- Added root `AGENTS.md` as the binding Codex/contributor instruction
  hierarchy.
- Marked `old_progress/` as historical and non-binding while retaining the
  archived restrictions as context.
- Replaced active blanket biology-gate wording with the current rule: no
  unsupported or invented biology, not no biology.
- Added tests that protect the active instruction hierarchy without scanning
  archived files as active instructions.

No scientific or numerical behavior changed. No biology was added.

## Phase 1 Task 2 Audit Finding Reconciliation

Date: 2026-06-14

Status: `complete` for the scoped current-state finding catalogue.

Completed in this pass:

- Added `findings.yaml` as the machine-readable current finding-status
  catalogue for critical/high audit claims.
- Added `foundation_progress/validation/PHASE_1_CURRENT_FINDING_STATUS.md` as
  the concise human-readable status matrix.
- Classified stale and resolved technical audit claims separately from
  confirmed scientific limitations.
- Added `tests/test_findings_catalogue.py` to ensure the catalogue parses,
  finding IDs remain unique, status/severity values are valid, required
  evidence sections exist, and historical claims remain preserved.

No production, scientific, numerical, or public API behavior changed. No audit
finding resolutions were implemented in this task.

## Phase 1 Task 3 Native Execution Path Verification

Date: 2026-06-14

Status: `complete` for the scoped native execution path verification.

Completed in this pass:

- Added `foundation_progress/validation/PHASE_1_NATIVE_EXECUTION_PATHS.md`
  with the current execution-path matrix for configured workflows,
  VirtualExperiment, plugin helpers, notebooks, calibration/uncertainty
  wrappers, reaction-diffusion, and direct low-level solver APIs.
- Strengthened `tests/test_guardrails_native_execution.py` so supported
  configured well-mixed workflows fail if they instantiate the legacy
  `SimulationEngine`, construct `Reaction` objects, or call concrete
  `as_reaction()` adapters.
- Added a configured validator trace proving validators loaded through
  `ValidatorRegistry` execute after the native process solver returns a result.
- Added a configured unsupported-geometry regression proving `film_1d`
  configured geometry fails explicitly instead of silently changing solver
  paths.
- Recorded active process-to-Reaction compatibility adapters as `FD-006` in
  `ARCHITECTURE_DEBT.md` for the P1.4 retirement/containment decision.

No production, scientific, numerical, public API, or output semantics changed.
The low-level `Reaction`, `SimulationEngine`, and `ReactionDiffusionEngine1D`
APIs remain intentionally supported low-level surfaces.

## Phase 1 Task 4 Legacy Adapter Retirement

Date: 2026-06-14

Status: `complete` for the scoped process-to-`Reaction` adapter retirement.

Completed in this pass:

- Removed concrete `as_reaction()` compatibility adapters from homogeneous and
  surface process classes.
- Removed the shared `_reaction_from_process` helper that existed only to build
  legacy `Reaction` objects from `Process` objects.
- Rewrote adapter-dependent process tests so they verify process execution
  through native `ModelBuilder` / `AssembledModel.run()` instead of the legacy
  `SimulationEngine`.
- Kept direct low-level `Reaction`, `SimulationEngine`, and
  `ReactionDiffusionEngine1D` APIs intact where they are intentionally
  supported and tested.
- Added `foundation_progress/validation/PHASE_1_LEGACY_ADAPTER_RETIREMENT.md`
  and marked `FD-006` resolved in `ARCHITECTURE_DEBT.md`.
- Strengthened native-execution guardrails so process modules cannot silently
  reintroduce `as_reaction()` or `_reaction_from_process`.

No supported configured numerical outputs, scientific assumptions, model
parameters, solver settings, public configured APIs, or output schemas changed.

## CLEANUP-001 / SCHEMA-001 Researcher Output Semantics

Date: 2026-06-07

Status: `complete` for the scoped cleanup/schema hardening pass.

Completed in this pass:

- Made the central virtual-experiment directive the active README/progress
  entry point.
- Relabeled toy/synthetic configured assets and notebooks as software-test or
  example fixtures, not scientific records.
- Added versioned virtual-experiment output schema files:
  `virtual_experiment_output_schema.json` and
  `virtual_experiment_output_data_dictionary.csv`.
- Added standard `missing_parameters.csv` and `suggested_experiments.csv`
  tables to virtual-experiment output bundles.
- Added `range_scope`, `range_interpretation`, and `allowed_use` semantics to
  registry parameter records and sampled/provenance output tables without
  removing exact, range, distribution, unknown, or exploratory-prior support.
- Renamed BIO-001 mass-valued product output from concentration wording to
  amount wording.
- Marked BIO-001 accessible-site fraction as a derived proxy rather than a
  modeled accessibility state.
- Added metadata-only environment-grid guardrails so environment summaries are
  explicitly non-rankable and non-plottable as response models unless an
  active response model or condition-specific parameter status is present.

No new data, new biology, or scientific-value edits were added.

## BIO-001 Cellulose Surface Degradation

Date: 2026-06-07

Status: `complete` for a first exploratory insoluble cellulose-like
surface-degradation virtual experiment.

Completed in this pass:

- Added BIO-001 registry records for a generic cellulase enzyme source,
  cellulase-like enzyme class, insoluble cellulose-film substrate, pilot assay
  environment, and surface-catalysis process compatibility.
- Added explicitly marked `exploratory_prior` parameter records for surface
  catalytic rate, adsorption constant, accessible surface area, initial
  cellulose-film mass, and initial cellulase concentration.
- Reused the existing generic `SurfaceCatalysisProcess` and
  `SurfaceCatalysisFactory`; no duplicate surface process was introduced.
- Added exploratory configured-model mode support so sampled BIO-001 runs do
  not need to masquerade as toy runs.
- Extended virtual-experiment output tables with surface-specific degradation
  metrics: solid substrate remaining/degraded fraction, accessible-site
  fraction proxy, soluble product amount, and final product yield.
- Added BIO-001 limitations stating that this is enzyme-mediated surface
  degradation, not whole-fungus growth, secretion, uptake, biomass, oxygen
  limitation, or full lignocellulose modeling.
- Added the executable notebook
  `notebooks/07_bio001_cellulose_surface_virtual_experiment.ipynb`.

See `foundation_progress/BIO_001_CELLULOSE_SURFACE_DEGRADATION.md` for scope,
parameters, output tables, and limitations.

## DATA-002 SABIO-RK Reaction 618 Parameter Ranges

Date: 2026-06-07

Status: `complete` for local Reaction 618 multi-entry parameter-range curation.

Completed in this pass:

- Hardened the local SABIO-RK Reaction 618 beta-glucosidase/cellobiose curation
  into eligible/excluded CSV tables plus JSON and Markdown parameter-range
  summaries.
- Preserved EntryID, organism, enzyme type, pH, temperature, buffer,
  publication/PubMed metadata, source fields, and explicit exclusion reasons.
- Added scoped Km/kcat ranges for all eligible entries, organism, exact pH,
  exact temperature, organism+pH, wildtype-only, and mutant-only groups.
- Marked sparse groups as `insufficient_n` instead of presenting them as robust
  ranges.
- Clarified registry provenance for the all-eligible `literature_range` Km and
  kcat records without overwriting selected exact EntryID 35622 values, the
  unknown enzyme concentration record, or the exploratory enzyme prior.
- Extended virtual-experiment sampled-parameter tables with
  `parameter_source_class` so outputs can distinguish selected exact values,
  literature ranges, user-supplied exploratory priors, and unknown sources.

See `foundation_progress/DATA_002_REACTION_618_PARAMETER_RANGES.md` for scope,
limitations, curated outputs, and interpretation.

## ENV-001 Environment Grids for Virtual Experiments

Date: 2026-06-07

Status: `complete` for runtime environment-grid virtual-experiment support.

Completed in this pass:

- Added concrete `EnvironmentGrid` case generation for temperature, pH, and
  oxygen labels.
- Added runtime in-memory environment records and parameter-record overlay for
  metadata-only environment grid simulations.
- Extended virtual-experiment output tables with `environment_source` and
  `environment_effect_status`.
- Added `final_states.csv` and `environment_summary.csv`.
- Documented that Reaction 618 grid runs do not apply a temperature or pH
  response law; kinetics are reused as metadata-only context unless a future
  response model or condition-specific parameters are active.

See `foundation_progress/ENV_001_ENVIRONMENT_GRIDS.md` for scope,
limitations, and output-table details.

## BIO-002-GENERICITY Extracellular Enzyme-Chain Hardening

Date: 2026-06-13

Status: `complete` for reusable two-step chain assembly and software
verification.

Completed in this pass:

- Refactored `src/fungal_model/screening/enzyme_chain.py` so the generic
  assembler reads entity definitions, loaders, state roles, state units,
  initial states, catalyst states, process sequence, parameter-record IDs,
  product-map IDs, stoichiometric coefficients, conservation weights, output
  labels, limitations, and suggested experiments from registry/template data.
- Moved the current cellulose-equivalent demonstration entity metadata,
  conserved-equivalent definition, and standard-table output labels into
  `data_registry/case_templates/case_templates.yml`.
- Removed hardcoded product-yield and conserved-weight fallbacks from the
  enzyme-chain table writer.
- Added validation for malformed chain templates, including non-positive or
  non-finite coefficients, empty required maps, unknown roles, missing units,
  legacy product-state conflicts, missing conservation metadata, inconsistent
  conservation weights, and invalid output references.
- Added `tests/test_bio002_generic_chain_assembly.py`, with an unrelated
  `polymer_X -> oligomer_Y -> monomer_Z` fixture using different entities,
  states, catalyst names, parameters, output labels, yields `1.5` and `3.0`,
  and conserved weights `1`, `2/3`, and `2/9`.
- Added the machine-readable real mechanism proposal
  `foundation_progress/proposals/BIO_002_EXTRACELLULAR_ENZYME_CHAIN.yml` and
  a readiness test that validates the actual file.
- Preserved the Reaction 618 behavior where beta-D-glucose formed is
  approximately two times cellobiose consumed.

Verification:

- `.venv/bin/python -m pytest tests/test_pre_bio001_stoichiometry_and_assembly.py`
  - Result: 4 passed.
- `.venv/bin/python -m pytest tests/test_bio_readiness_lite.py`
  - Result: 8 passed.
- `.venv/bin/python -m pytest tests/test_bio002_extracellular_enzyme_chain.py`
  - Result: 3 passed.
- `.venv/bin/python -m pytest tests/test_bio002_generic_chain_assembly.py`
  - Result: 11 passed.
- `.venv/bin/python -m ruff check src tests`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath "$(.venv/bin/python -c 'import sys; print(sys.executable)')"`
  - Result: 0 errors, 0 warnings, 0 informations.
- `.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing`
  - Result: 540 passed; total coverage 84.30%, above the 80% gate.

See `foundation_progress/BIO_002_ENZYME_CHAIN_DEGRADATION.md` for the generic
contract, demonstration-specific data, failure modes, and limitations.

## Foundation-First Reset: Milestone 1 Governance Gate

Date: 2026-05-27

Status: `complete` for the initial governance and architecture guardrail scope.

Completed in this foundation-first pass:

- Added `ARCHITECTURE_DEBT.md` as the required containment register for
  temporary architecture compromises.
- Documented the current narrow transitional debts:
  - `FD-001`: legacy PET workflow still exported from generic workflows;
  - `FD-002`: PET-only substrate branch in YAML loading;
  - `FD-003`: `AssembledModel.run()` is still non-native execution debt.
- Added guardrail tests for:
  - PET/product hardcoding in generic source paths;
  - shortcut/fallback patterns in high-risk modules;
  - current and next-milestone public API expectations.
- Added a GitHub PR template requiring scope, tests, limitations, shortcut
  removal, architecture debt, and progress-doc updates.
- Added a minimal GitHub Actions CI workflow that installs `.[dev]` and runs
  `pytest`.
- Updated the notebook test path to the actual `notebooks/examples/` location
  so notebook smoke checks execute rather than failing on discovery.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 160 passed.

Next foundation milestone: Milestone 2, generic public API names
(`run_configured_model`, `load_model_config`, and future `ProcessLibrary`)
without faking runnable implementation.

## Foundation-First Reset: Milestone 2 Generic Public API

Date: 2026-05-27

Status: `complete` for generic-first public API introduction.

Completed in this foundation-first pass:

- Added `src/fungal_model/io/model_config.py` with a real `ModelConfig`,
  `load_model_config`, and top-level generic model-config validation.
- Added `src/fungal_model/workflows/configured_model.py` with
  `run_configured_model`.
- Made `run_configured_model` load the generic config and fail with a
  structured `ConfiguredModelRunReport` until registry loading, process
  factories, native `AssembledModel.run()`, and configured output bundles exist.
- Added `ProcessLibrary` as the public foundation process-library name over
  current already-built process objects.
- Exposed `load_model_config`, `run_configured_model`, `ProcessLibrary`,
  `ModelConfig`, `ConfiguredModelExecutionError`, and
  `ConfiguredModelRunReport` from top-level `fungal_model`.
- Removed `run_pet_surface_integration` and `PETSurfaceWorkflowConfig` from
  top-level `fungal_model` exports.
- Kept the legacy PET workflow available from `fungal_model.workflows` and made
  it emit a `DeprecationWarning`.
- Updated README workflow guidance to point at the generic configured-model API.
- Updated `ARCHITECTURE_DEBT.md` with `FD-004` for the structural preflight
  runner boundary.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_full_integration_workflow.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 162 passed.

Next foundation milestone: Milestone 3, registry-based loading for substrates,
geometries, product maps, and validators.

## Foundation-First Reset: Milestone 3 Registry-Based Loading

Date: 2026-05-27

Status: `complete` for the initial registry-based loader boundary.

Completed in this foundation-first pass:

- Added neutral config parameter parsing in `src/fungal_model/io/parameters.py`.
- Added `src/fungal_model/io/registries.py` with:
  - `SubstrateLoaderRegistry`;
  - `GeometryLoaderRegistry`;
  - `ProductMapRegistry`;
  - `ValidatorRegistry`;
  - `RegistryLookupError`.
- Changed `load_substrate` to delegate through `SubstrateLoaderRegistry`.
- Changed `load_geometry` to delegate through `GeometryLoaderRegistry`.
- Added default non-PET substrate loaders for `generic_solid` and
  `generic_dissolved` foundation benchmark configs.
- Added default geometry loaders for `well_mixed` and `film_1d`.
- Added default product-map loaders for `one_to_one` and `stoichiometric`
  configured state mappings.
- Added default validator loaders for `non_negative` and `mass_balance`.
- Added `src/fungal_model/plugins/pet/` with explicit PET substrate loader
  registration.
- Migrated the legacy PET integration workflow and PET config tests to use the
  explicit PET plugin registry.
- Resolved architecture debt `FD-002`: the generic YAML substrate loader no
  longer imports PET or branches on PET.
- Updated README loader guidance to describe the registry boundary.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_registry_based_loading.py tests/test_config_io.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_full_integration_workflow.py`
- Result: 24 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 168 passed.

Next foundation milestone: Milestone 4, model config object expansion for
homogeneous, PET plugin, and dummy non-PET configs.

## Foundation-First Reset: Milestone 4 Model Config Objects

Date: 2026-05-27

Status: `complete` for generic model-config object loading.

Completed in this foundation-first pass:

- Expanded `src/fungal_model/io/model_config.py` from top-level validation into
  structured config objects:
  - `ConfigReference`;
  - `EntityConfigRefs`;
  - `ParameterSetConfig`;
  - `ProcessConfig`;
  - `InitialStateConfig`;
  - `TimeConfig`;
  - `ValidatorConfig`;
  - `OutputConfig`.
- Kept `load_model_config` generic and made it return structured sections
  without executing loaders, factories, or solvers.
- Added canonical foundation model-config shells:
  - `data/model_configs/toy_homogeneous_ab.yml`;
  - `data/model_configs/toy_surface_pet_plugin.yml`;
  - `data/model_configs/toy_surface_dummy_non_pet.yml`.
- The plugin surface config and dummy non-PET surface config use the same
  `surface_catalysis` process shape and configured state mappings.
- Updated schema validation so `model_config` records are treated as
  config-of-configs rather than raw parameter-set files.
- Added `tests/test_model_config_loading.py`.
- Updated README data/config guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_config_loading.py tests/test_config_io.py tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 174 passed.

Next foundation milestone: Milestone 5, product-map configs and loader path
for configured product-state mappings.

## Foundation-First Reset: Milestone 5 Product-Map Configs

Date: 2026-05-27

Status: `complete` for file-backed product-map config loading.

Completed in this foundation-first pass:

- Added `src/fungal_model/io/product_maps.py` with `load_product_map`.
- Extended `ProductReleaseMap` with optional `name`, `maturity`, and `source`
  metadata while preserving existing process compatibility.
- Updated `ProductMapRegistry` loaders to preserve product-map metadata from
  config files.
- Added canonical product-map configs:
  - `data/product_maps/toy_surface_plugin_mass_equivalent.yml`;
  - `data/product_maps/toy_surface_dummy_mass_equivalent.yml`.
- Updated the plugin surface and dummy non-PET surface model configs to
  reference product-map files instead of embedding product maps inline.
- Added tests proving product maps load from files, preserve arbitrary state
  names, fail on unknown map types, and are referenced from surface model
  configs.
- Updated README data/config guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_product_map_configs.py tests/test_model_config_loading.py tests/test_registry_based_loading.py tests/test_config_io.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 31 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 178 passed.

Next foundation milestone: Milestone 6, process factory library foundation.

## Foundation-First Reset: Milestone 6 Process Factory Library

Date: 2026-05-27

Status: `complete` for the foundation process-factory layer.

Completed in this foundation-first pass:

- Added `src/fungal_model/processes/factories.py` with:
  - `BuildDecision`;
  - `ProcessBuildContext`;
  - `ProcessFactory`;
  - `FirstOrderFactory`;
  - `MassActionFactory`;
  - `HomogeneousMichaelisMentenFactory`;
  - `SurfaceCatalysisFactory`;
  - `default_foundation_factories`.
- Extended `ProcessLibrary` so it can register factories, reject duplicate
  factories, return a factory by process type, build decisions, and build
  process objects from structured `ProcessConfig` entries.
- Kept existing `ProcessRegistry` behavior intact for already-built process
  objects.
- Verified that:
  - homogeneous `toy_homogeneous_ab.yml` builds through the first-order factory;
  - plugin surface and dummy non-PET surface configs build through the same
    generic surface factory;
  - mass-action and homogeneous Michaelis-Menten factories build generic process
    objects;
  - missing state units/product maps produce structured `BuildDecision`
    failures;
  - the factory module contains no plugin imports or domain names.
- Updated `run_configured_model` preflight reporting so it now names missing
  process-factory wiring, not a missing process-factory library.
- Updated README process-library guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_process_factory_library.py tests/test_model_config_loading.py tests/test_product_map_configs.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 29 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 188 passed.

Next foundation milestone: Milestone 7, native `AssembledModel.run()`.

## Current Roadmap Slice

Current active milestone: **Milestones 1-10 complete for the first roadmap
implementation slice**.

Status: `complete` for the tested scope documented below. Remaining work is
future expansion beyond the first long-term architecture pass.

Completed milestone: **Milestone 2: Generic result object**.

Milestone 2 status: `complete` for the first standardized result/export scope.

Completed in Milestone 2:

- Added `src/fungal_model/results/result.py`.
- Added `src/fungal_model/results/__init__.py`.
- Exposed roadmap `SimulationResult` from top-level `fungal_model`.
- Added a standard result wrapper that can be built from:
  - existing well-mixed ODE results;
  - existing 1D reaction-diffusion results.
- Added state and rate accessors:
  - `state(name)`
  - `rate(name)`
- Added validation attachment and validation report export.
- Added plot methods:
  - `plot_state`
  - `plot_states`
  - `plot_rates`
  - `plot_mass_balance`
- Added standardized output saving:
  - `record.json`
  - `model_assembly_report.json`
  - `assumptions.json`
  - `parameters.csv`
  - `validation_report.json`
  - `solver_report.json`
  - `state_trajectories.csv`
  - `process_rates.csv`
  - `derived_quantities.csv`
  - `figures/state_trajectories.png`
  - `figures/process_rates.png`
  - optional `figures/mass_balance.png`
  - `logs/warnings.txt`
  - `logs/provenance_report.md`
- Updated examples 01-06 to save standardized result outputs while preserving
  their existing legacy files and plots.
- Added `tests/test_results.py`.

Milestone 2 verification:

- `./.venv/bin/python -m pytest tests/test_results.py tests/test_simulation_record.py`
- Result: 4 passed.
- Re-ran examples 01-06 successfully.

Completed milestone: **Milestone 3: Generic homogeneous kinetics**.

Milestone 3 status: `complete` for the first generic homogeneous process scope.

Completed in Milestone 3:

- Added `src/fungal_model/processes/homogeneous.py`.
- Added generic homogeneous process classes:
  - `FirstOrderDecayProcess`
  - `MassActionProcess`
  - `HomogeneousMichaelisMentenProcess`
- Added `homogeneous_process_assumption`.
- Added `as_reaction()` adapters so the new process classes can run through the
  existing ODE `SimulationEngine` before the future process solver exists.
- Updated process and top-level package exports.
- Migrated examples 01 and 02 to build reactions from generic homogeneous
  process classes.
- Added `tests/test_homogeneous_processes.py`.

Milestone 3 behavior now available:

- First-order homogeneous decay/product formation can be declared as a generic
  process and converted into a runnable `Reaction`.
- Generic mass-action processes check state units and rate units.
- Generic homogeneous Michaelis-Menten processes support:
  - classic `Vmax * S / (Km + S)`;
  - enzyme-explicit `kcat * E * S / (Km + S)`;
  - required parameter declarations for model assembly.
- Homogeneous process assumptions stay generic and do not mention PET.

Milestone 3 verification:

- `./.venv/bin/python -m pytest tests/test_homogeneous_processes.py tests/test_michaelis_menten.py tests/test_reaction_engine.py`
- Result: 16 passed.
- Re-ran examples 01 and 02 successfully after migration.

Completed milestone: **Milestone 4: Generic surface process refactor**.

Milestone 4 status: `complete` for the first generic surface-process scope.

Completed in Milestone 4:

- Added `src/fungal_model/processes/surface.py`.
- Added generic surface process components:
  - `AccessibleSitePool`
  - `AccessibleSurfaceAreaModel`
  - `LangmuirAdsorptionModel`
  - `EquilibriumSurfaceCoverageModel`
  - `SurfaceCatalysisModel`
  - `ProductReleaseMap`
  - `SurfaceCatalysisProcess`
  - `BondCleavageProcess` alias
  - `surface_catalysis_rate`
- Added `PETAccessibleSurfaceAreaModel` to `src/fungal_model/substrates/pet.py`.
- Added `pet_product_release_map` for the current mass-equivalent PET benchmark.
- Refactored `PETSurfaceHydrolysisRateLaw` so no-modifier PET surface
  hydrolysis delegates to a generic `SurfaceCatalysisProcess`.
- Kept environmental PET scaling working by applying temperature/pH modifiers
  around the generic `surface_catalysis_rate`.
- Updated process, substrate, and top-level exports.
- Added `tests/test_generic_surface_processes.py`.
- Updated `README.md` with the new roadmap capabilities and limitations.

Milestone 4 behavior now available:

- A generic surface catalysis process can run a dummy non-PET solid substrate.
- Generic surface modules do not import PET-specific modules.
- PET exposes accessibility and product-release composition pieces instead of
  making the generic surface machinery live inside PET.
- PET can still run through the existing `PETSurfaceHydrolysisRateLaw` API.
- PET can also expose its generic composed process through
  `PETSurfaceHydrolysisRateLaw.as_generic_process()`.
- Missing PET accessible surface area still fails honestly.
- The PET mass-equivalent benchmark product map can be checked for mass
  conservation.

Milestone 4 verification:

- `./.venv/bin/python -m pytest tests/test_generic_surface_processes.py tests/test_surface_pet.py tests/test_environmental_modifiers.py`
- Result: 26 passed.
- Re-ran examples 03-06 successfully after the generic surface refactor.

Completed milestone: **Milestone 5: Environment object and modifiers**.

Milestone 5 status: `complete` for the first environment/modifier scope.

Completed in Milestone 5:

- Added `src/fungal_model/entities/environment.py`.
- Added `src/fungal_model/entities/__init__.py`.
- Added `Environment` with temperature, pH, oxygen, water activity, nutrient,
  ionic-strength, pressure, boundary-condition, validity-label, source, notes,
  and assumptions fields.
- Added environment validation and unit checks.
- Added `src/fungal_model/modifiers/`.
- Added environment-driven modifiers:
  - `TemperatureModifier`
  - `PHModifier`
  - `WaterActivityModifier`
  - `OxygenModifier`
  - `ProductInhibitionModifier`
- Added explicit assumptions for water activity, oxygen limitation, and product
  inhibition modifiers.
- Exposed environment and modifiers from top-level `fungal_model`.
- Added `tests/test_environment_modifiers.py`.

Milestone 5 behavior now available:

- Modifiers read environmental values from an `Environment` object rather than
  loose parameters.
- Temperature and pH modifiers reuse the existing Arrhenius and Gaussian pH
  implementations.
- Water activity can explicitly block rates below a sourced threshold.
- Oxygen can explicitly limit rates through a Monod-style activity.
- Product inhibition can explicitly reduce rates from a named product state.

Milestone 5 verification:

- `./.venv/bin/python -m pytest tests/test_environment_modifiers.py tests/test_environmental_modifiers.py`
- Result: 16 passed.

Completed milestone: **Milestone 6: Geometry abstraction**.

Milestone 6 status: `complete` for the first geometry abstraction scope.

Completed in Milestone 6:

- Added `src/fungal_model/geometry/`.
- Added base `Geometry` metadata object.
- Added functional `WellMixedGeometry`.
- Added functional `Film1DGeometry` wrapping the existing `UniformGrid1D`.
- Added explicit metadata placeholders:
  - `ParticleGeometry`
  - `SlabGeometry`
  - `PorousMediumGeometry`
- Added geometry assumptions and provenance/source checks.
- Exposed geometry classes from top-level `fungal_model`.
- Added `tests/test_geometry_abstractions.py`.

Milestone 6 behavior now available:

- Well-mixed models can carry explicit volume, optional surface area, and
  area/volume ratio metadata.
- 1D film models can carry explicit grid and boundary-condition metadata.
- Particle, slab, and porous-medium objects record metadata honestly without
  pretending solver support exists.

Milestone 6 verification:

- `./.venv/bin/python -m pytest tests/test_geometry_abstractions.py tests/test_reaction_diffusion.py`
- Result: 11 passed.

Completed milestone: **Milestone 7: Fungus/enzyme/process compatibility**.

Milestone 7 status: `complete` for the first compatibility-matching scope.

Completed in Milestone 7:

- Added `src/fungal_model/entities/enzyme.py`.
- Added explicit `Enzyme` entity with:
  - enzyme class;
  - target bond types;
  - target substrate names/classes;
  - catalytic and adsorption parameter sets;
  - pH/temperature profile placeholders;
  - validity labels;
  - assumptions, source, and notes.
- Added `Enzyme.compatible_with_substrate`.
- Extended `EnzymeProfile` with `compatible_capabilities`.
- Extended `Fungus` with explicit `uptake_capabilities` and
  `can_assimilate_product`.
- Extended `ModelBuilder` and `ModelAssemblyContext` with `enzymes`.
- Added `CompatibilityIssue` to assembly reports.
- Added assembly failure for incompatible mechanisms through
  `InvalidMechanismError`.
- Added compatibility checks for generic surface-catalysis processes:
  - missing catalyst entity;
  - incompatible enzyme/substrate/bond pairing;
  - fungus lacking a matching enzyme capability.
- Exposed `Enzyme` and `CompatibilityIssue` from package exports.
- Added `tests/test_enzyme_compatibility.py`.
- Updated `README.md`.

Milestone 7 behavior now available:

- Isolated enzyme surface systems can assemble without a fungus when a
  compatible enzyme entity is supplied.
- Living-fungus surface systems require the fungus to declare a compatible
  enzyme capability.
- Incompatible enzyme, substrate, and target-bond pairings fail with structured
  assembly reports.
- Product uptake/assimilation capability is explicit on the fungus.
- Living-fungus process assembly can block on unknown secretion parameters.

Milestone 7 verification:

- `./.venv/bin/python -m pytest tests/test_enzyme_compatibility.py tests/test_process_assembly.py tests/test_fungal_dynamics.py`
- Result: 24 passed.

Completed in this slice:

- Added structured assembly errors in `src/fungal_model/core/errors.py`:
  - `ModelAssemblyError`
  - `MissingProcessError`
  - `MissingParameterError`
  - `IncompatibleUnitsError`
  - `InvalidMechanismError`
- Added generic process contracts in `src/fungal_model/processes/base.py`:
  - `Process`
  - `StateVariableSpec`
  - `ParameterRequirement`
  - `ValidityDomain`
- Added a generic registry in `src/fungal_model/processes/registry.py`:
  - `ProcessRegistry`
  - `MissingProcessIssue`
  - empty `ProcessRegistry.default()` for the current milestone
- Added model assembly scaffolding in `src/fungal_model/processes/assembly.py`:
  - `ModelAssemblyContext`
  - `ProcessMatch`
  - `ParameterIssue`
  - `AssemblyReport`
  - `AssembledModel`
  - `ModelBuilder`
- Added `src/fungal_model/processes/__init__.py` exports.
- Updated top-level package exports in `src/fungal_model/__init__.py`.
- Updated core exports in `src/fungal_model/core/__init__.py`.
- Added assembly tests in `tests/test_process_assembly.py`.

Milestone 1 behavior now available:

- A model can request named process types.
- A `ProcessRegistry` can match registered generic processes.
- Missing mechanisms fail with `MissingProcessError`.
- Missing parameters fail with `MissingParameterError`.
- Explicitly unknown parameters fail instead of receiving fallback constants.
- Missing provenance fails in scientific mode.
- Unsourced parameters are allowed only with `allow_unsourced_for_testing=True`.
- Incompatible parameter units fail separately with `IncompatibleUnitsError`.
- Assembly reports are both machine-readable (`to_dict`) and human-readable
  (`human_readable`).
- A successful assembly produces an `AssembledModel` containing matched
  processes, state variables, parameters, assumptions, validators, solver
  settings, and the assembly report.

Important deliberate limitation:

- `AssembledModel.run()` is a placeholder. Solver-backed execution through the
  process architecture belongs to later milestones. Current runnable models
  still use the existing `SimulationEngine` and `ReactionDiffusionEngine1D`.

Milestone 1 tests added:

- missing process gives a structured report;
- matched process with absent parameter gives a structured missing-parameter
  report;
- unknown parameter value blocks assembly;
- missing parameter provenance blocks assembly;
- testing escape hatch for unsourced parameters is explicit;
- incompatible units are reported separately;
- successful assembly exports state variables, assumptions, solver settings,
  and report data;
- generic process modules do not import PET-specific modules.

Verification:

- `./.venv/bin/python -m pytest tests/test_process_assembly.py`
- Result: 8 passed.

Full-suite verification for this slice:

- `./.venv/bin/python -m pytest`
- Result: 108 passed.

## Current Codebase Capability Inventory

### Scientific Governance

Status: `complete` for the existing foundation.

FungMod can:

- represent scientific parameters with names, symbols, values, units,
  uncertainties, sources, confidence levels, notes, and measurement methods;
- represent unknown parameters explicitly with `value=None`;
- require provenance before scientific runs;
- allow unsourced values only through explicit testing escape hatches;
- serialize parameter sets to JSON and YAML;
- represent modelling assumptions separately from parameters;
- enforce unit-bearing quantities through a shared `pint` registry.

Core files:

- `src/fungal_model/core/parameters.py`
- `src/fungal_model/core/provenance.py`
- `src/fungal_model/core/assumptions.py`
- `src/fungal_model/core/units.py`
- `src/fungal_model/core/errors.py`

### Existing Well-Mixed Solver

Status: `complete` for deterministic ODE reaction systems.

FungMod can:

- run deterministic well-mixed ODE models through `SimulationEngine`;
- use generic `Reaction` objects with unit-checked rate laws;
- validate reaction provenance before scientific execution;
- require unit-bearing initial states and simulation times;
- record solver settings and solver metadata;
- return unit-bearing `SimulationResult` objects;
- create reproducible `SimulationRecord` JSON outputs.

Current limitation:

- This solver works with `Reaction` objects, not yet with the new
  process-centered `AssembledModel`.

Core files:

- `src/fungal_model/chemistry/reactions.py`
- `src/fungal_model/core/simulation.py`

### Validation

Status: `partial` relative to the long-term roadmap; substantial existing
foundation is implemented.

FungMod can validate:

- non-negativity;
- weighted mass balance;
- carbon conservation;
- oxygen limitation;
- biomass yield bounds;
- limiting-case suites;
- selected spatial checks for 1D diffusion and reaction-diffusion models.

Current limitations:

- Validation results do not yet use the roadmap's richer severity/residual
  schema everywhere.
- Validators are not yet automatically attached by the new `ModelBuilder`.
- Thermodynamic feasibility is metadata-supported but not solver-enforced.

Core files:

- `src/fungal_model/core/validators.py`
- `src/fungal_model/validation/`

### Homogeneous Kinetics

Status: `complete` for the existing dissolved-substrate benchmark layer;
`partial` relative to the future process architecture.

FungMod can:

- compute homogeneous Michaelis-Menten rates;
- compute enzyme-explicit Michaelis-Menten rates;
- wrap homogeneous kinetics as `Reaction` rate laws;
- check low-substrate, high-substrate, zero-substrate, zero-enzyme, and unit
  limiting cases.

Current limitations:

- Homogeneous process classes can adapt to the existing ODE `Reaction` engine,
  but `AssembledModel.run()` is still a future native process solver.
- PET is explicitly not treated as a valid dissolved-substrate default.

Core files:

- `src/fungal_model/kinetics/michaelis_menten.py`

### Surface and PET Kinetics

Status: `partial`.

FungMod can:

- represent PET as a solid polyester substrate with explicit unknown material
  parameters by default;
- derive accessible PET surface area from supplied surface area, roughness, and
  amorphous fraction/crystallinity metadata;
- compute Langmuir equilibrium surface coverage;
- run a PET-specific surface hydrolysis rate law through the existing
  `Reaction` engine;
- apply Arrhenius temperature and Gaussian pH modifiers to the PET surface
  hydrolysis rate law.

Current limitations:

- Generic surface catalysis exists and PET composes it through
  `PETAccessibleSurfaceAreaModel`, but the workflow still executes through the
  current ODE reaction adapter rather than a native process solver.
- PET product release is still represented in examples and the integration
  workflow as a simplified lumped mass-equivalent hydrolysate where noted.
- Dynamic adsorption/desorption states, evolving morphology, and resolved
  MHET/BHET/TPA/EG product stoichiometry remain future work.

Core files:

- `src/fungal_model/substrates/pet.py`
- `src/fungal_model/kinetics/langmuir.py`
- `src/fungal_model/kinetics/surface_kinetics.py`
- `src/fungal_model/kinetics/arrhenius.py`
- `src/fungal_model/kinetics/ph.py`

### Universal Substrate Metadata

Status: `partial`.

FungMod can:

- represent generic substrate metadata through `Substrate`;
- represent degradation products without assuming assimilation;
- create explicit unknown parameter sets for substrate metadata;
- expose placeholder metadata classes for cellulose, lignin, starch, and
  chitin;
- keep PET marked as the only currently partial substrate with an implemented
  process path.

Current limitations:

- Placeholder substrates do not yet assemble into scientific kinetic models.
- Substrate maturity levels from the roadmap are conceptually present through
  `completeness`, but not yet enforced by the new process registry.

Core files:

- `src/fungal_model/substrates/base.py`
- `src/fungal_model/substrates/pet.py`
- `src/fungal_model/substrates/cellulose.py`
- `src/fungal_model/substrates/lignin.py`
- `src/fungal_model/substrates/starch.py`
- `src/fungal_model/substrates/chitin.py`

### Fungal Dynamics

Status: `partial`.

FungMod can:

- represent basic fungus metadata;
- represent enzyme capabilities and enzyme profiles;
- model enzyme secretion from active biomass;
- model enzyme production cost;
- model enzyme decay;
- model active-biomass maintenance loss;
- gate product uptake and growth through explicit product-assimilation
  evidence;
- prevent non-assimilable products from causing biomass growth.

Current limitations:

- Fungi and enzymes now participate in model-builder compatibility matching,
  but the builder does not yet auto-generate full living-fungus ODE systems.
- Living-fungus simulations still use existing `Reaction` rate laws rather than
  native process-registry solver execution.

Core files:

- `src/fungal_model/fungi/base.py`
- `src/fungal_model/fungi/enzyme_profile.py`
- `src/fungal_model/fungi/growth.py`
- `src/fungal_model/fungi/metabolism.py`

### Stoichiometry and Thermodynamics

Status: `partial`.

FungMod can:

- parse elemental formula strings;
- represent stoichiometric reaction metadata;
- detect balanced and unbalanced stoichiometry;
- represent carbon-content metadata for state variables;
- represent oxygen-demand metadata;
- represent Gibbs free energy estimates with provenance.

Current limitations:

- Gibbs free energy is not yet enforced as a thermodynamic feasibility
  constraint during solving.
- Redox balance is not yet implemented as a process or validator beyond the
  current oxygen-demand checks.

Core files:

- `src/fungal_model/chemistry/stoichiometry.py`
- `src/fungal_model/chemistry/thermodynamics.py`

### Spatial Transport

Status: `partial`.

FungMod can:

- represent a uniform 1D finite-volume grid;
- represent no-flux, fixed-value, and periodic boundary conditions;
- compute a 1D finite-volume diffusion operator;
- run a 1D method-of-lines reaction-diffusion model;
- validate no-flux conservation, gradient smoothing, and high-diffusion
  well-mixed behavior.

Current limitations:

- Geometry metadata is now exposed through the roadmap `Geometry` hierarchy,
  but transport is not yet a `DiffusionProcess` assembled by `ModelBuilder`.
- 2D/3D, porous media, advection, and dynamic surface/volume coupling are not
  implemented.

Core files:

- `src/fungal_model/transport/geometry.py`
- `src/fungal_model/transport/diffusion.py`
- `src/fungal_model/transport/reaction_diffusion.py`

### Calibration

Status: `partial`.

FungMod can:

- compute unit-aware residuals;
- split sequential train/validation data;
- fit selected parameters with bounded least squares;
- report failed optimizer/model runs without hiding them;
- serialize fit results, residuals, covariance diagnostics, approximate
  confidence intervals where valid, and warnings.

Current limitations:

- Bayesian calibration is a placeholder.
- Calibration is generic but not yet integrated into the future result/output
  system.

Core files:

- `src/fungal_model/calibration/residuals.py`
- `src/fungal_model/calibration/fitting.py`
- `src/fungal_model/calibration/bayesian.py`

### Uncertainty and Sensitivity

Status: `partial`.

FungMod can:

- run Monte Carlo uncertainty propagation for normal, uniform, and lognormal
  parameter uncertainty specifications;
- preserve sample provenance;
- summarize output quantiles;
- run local finite-difference sensitivity analysis with dimensional and
  normalized sensitivities.

Current limitations:

- Global sensitivity is not implemented.
- Uncertainty bands are not yet integrated with a first-class roadmap
  `SimulationResult` plotting system.

Core files:

- `src/fungal_model/uncertainty/monte_carlo.py`
- `src/fungal_model/uncertainty/sensitivity.py`

### Examples

Status: `complete` for the current runnable example set.

Current examples demonstrate:

- first-order well-mixed reaction;
- homogeneous Michaelis-Menten dissolved-substrate benchmark;
- PET surface hydrolysis;
- PET surface hydrolysis with temperature and pH modifiers;
- fungal enzyme secretion and product-coupled growth;
- 1D PET film enzyme diffusion and local hydrolysis;
- Stage 12 wrapper examples for the current canonical examples.

Current limitations:

- Examples now save standardized result outputs, but most still use the
  existing solver/rate-law architecture rather than native process-centered
  solver execution.

Core files:

- `examples/`

### Notebooks

Status: `complete` for the first required notebook/smoke-test scope.

Implemented notebooks:

- `notebooks/00_quickstart.ipynb`
- `notebooks/01_process_library_demo.ipynb`
- `notebooks/02_surface_hydrolysis_demo.ipynb`
- `notebooks/03_fungus_on_pet_demo.ipynb`
- `notebooks/04_reaction_diffusion_demo.ipynb`
- `notebooks/05_calibration_and_uncertainty_demo.ipynb`

Important rule:

- Notebooks must import package code and demonstrate workflows. They must not
  contain core model implementation.
- `tests/test_notebooks.py` enforces that notebooks import `fungal_model`, do
  not define core classes/rate laws, and the quickstart notebook can execute as
  a smoke test.

### Data and Configuration

Status: `complete` for the first YAML schema/loader scope.

Implemented top-level folders:

- `data/fungi/`
- `data/substrates/`
- `data/enzymes/`
- `data/environments/`
- `data/geometries/`
- `data/parameters/`
- `data/experiments/`

Current behavior:

- YAML configs load into `Environment`, `Enzyme`, `Fungus`, `Substrate`,
  `Geometry`, and `ParameterSet` objects.
- Configs require top-level provenance and parameter-level source,
  measurement-method, confidence, notes, validity-range, units, and value
  fields.
- Unknown values remain explicit `value: null` inputs and become unknown
  `Parameter` objects instead of guessed numbers.

## Long-Term Roadmap Status

### Milestone 1: Process base classes

Status: `complete` for the skeleton scope.

Done:

- Process contracts.
- Process registry.
- Model builder skeleton.
- Structured assembly report.
- Structured assembly errors.
- Missing process and missing parameter tests.

Remaining future expansion:

- Entity-aware compatibility matching.
- Process-to-solver execution.
- Automatic validator selection.

### Milestone 2: Generic result object

Status: `complete` for the first standardized result/export scope.

Implemented:

- `src/fungal_model/results/result.py`
- `src/fungal_model/results/__init__.py`
- standardized `results.SimulationResult`
- ODE and reaction-diffusion wrapper constructors
- report/table/log/figure export
- result-generated plots
- tests in `tests/test_results.py`

Still required:

- make the roadmap result object the native output of all solvers rather than
  a wrapper around current solver results;
- add specialized plots for carbon, oxygen, spatial profiles, uncertainty
  bands, and calibration diagnostics.

### Milestone 3: Generic homogeneous kinetics

Status: `complete` for the first generic homogeneous process scope.

Implemented:

- `HomogeneousMichaelisMentenProcess`
- `MassActionProcess`
- `FirstOrderDecayProcess`
- `as_reaction()` adapters for current ODE engine execution
- examples 01 and 02 migrated to generic process classes
- tests in `tests/test_homogeneous_processes.py`

Still required:

- native process solver execution through `AssembledModel.run()`;
- richer process-rate recording from homogeneous processes.

### Milestone 4: Generic surface process refactor

Status: `complete` for the first generic surface-process scope.

Implemented:

- generic adsorption model in process form;
- generic surface catalysis/bond cleavage process;
- accessible site/surface model;
- product release map;
- PET accessibility adapter;
- PET migration to generic process composition;
- dummy non-PET substrate surface test.

Still required:

- dynamic adsorption/desorption states;
- resolved PET product maps beyond the current mass-equivalent benchmark;
- dynamic morphology/accessibility evolution;
- full entity compatibility matching for enzyme class, target bond, substrate,
  environment, and geometry.

### Milestone 5: Environment object and modifiers

Status: `complete` for the first environment/modifier scope.

Implemented:

- `Environment` entity.
- Temperature, pH, water activity, oxygen, and product inhibition modifiers.
- Tests in `tests/test_environment_modifiers.py`.

Still required:

- richer modifier plots and automatic modifier selection during assembly.

### Milestone 6: Geometry abstraction

Status: `complete` for the first geometry abstraction scope.

Implemented:

- roadmap `Geometry` hierarchy;
- functional well-mixed and 1D film geometry wrappers;
- particle, slab, and porous-medium metadata placeholders;
- tests in `tests/test_geometry_abstractions.py`.

Still required:

- process-native diffusion assembly and richer geometry-specific solvers.

### Milestone 7: Fungus/enzyme/process compatibility

Status: `complete` for the first compatibility-matching scope.

Implemented:

- explicit enzyme entities;
- compatibility matching between fungus, enzyme, substrate bond, and surface
  catalysis processes;
- clear assembly failures for missing biological capability;
- tests in `tests/test_enzyme_compatibility.py`.

Still required:

- broader environment and geometry compatibility rules for every process type.

### Milestone 8: Notebooks

Status: `complete` for the first required notebook/smoke-test scope.

Implemented:

- `/notebooks`;
- required six notebooks;
- notebook structure and smoke tests in `tests/test_notebooks.py`.

Still required:

- richer executed notebook snapshots as workflows mature.

### Milestone 9: Data/config schemas

Status: `complete` for the first YAML schema/loader scope.

Implemented:

- YAML loaders;
- JSON export helper;
- schema validation;
- example configs with provenance;
- unknown-value handling in config files;
- tests in `tests/test_config_io.py`.

Still required:

- full versioned schemas and broader literature-backed config libraries.

### Milestone 10: First full integration workflow

Status: `complete` for the first config-driven PET surface integration scope.

Implemented:

- `src/fungal_model/workflows/pet_surface_integration.py`;
- one fungus/enzyme/PET/environment/geometry workflow assembled through the
  registry and model builder;
- standardized output folder with reports, tables, logs, figures, input
  configs, and entity JSON snapshots;
- validation and process-rate plots;
- honest failure when accessible PET surface area is missing;
- honest failure when enzyme/substrate metadata are incompatible;
- tests in `tests/test_full_integration_workflow.py`.

Still required:

- native execution through `AssembledModel.run()`;
- resolved PET product chemistry;
- broader living-fungus dynamics assembled from configs.

## Anti-Cheating Checklist Status

Implemented in current tests:

- missing process fails with `MissingProcessError`;
- missing parameter fails with `MissingParameterError`;
- missing provenance fails in scientific assembly mode;
- incompatible units fail with `IncompatibleUnitsError`;
- generic process modules do not import PET-specific modules;
- generic surface hydrolysis works with PET and a dummy non-PET substrate;
- PET composes generic surface processes through a PET accessibility adapter;
- incompatible fungus/substrate/enzyme pairings fail in model assembly;
- non-assimilable product cannot cause biomass growth;
- roadmap result object saves standardized files, plots, logs, and reports;
- notebooks import from `fungal_model` and do not define core rate laws/classes;
- zero enzyme, zero accessible surface, zero substrate, and zero PET mass checks
  exist for current PET rate-law tests;
- high diffusion approaches well-mixed behavior in existing spatial tests.

Still required:

- oxygen cannot be consumed if oxygen process is absent or unavailable;
- native process-solver execution through `AssembledModel.run()`;
- resolved product stoichiometry for PET surface hydrolysis.

## How To Verify

Focused Milestone 1 tests:

```bash
.venv/bin/python -m pytest tests/test_process_assembly.py
```

Full test suite:

```bash
.venv/bin/python -m pytest
```

Current focused verification:

- 2026-05-26: `tests/test_process_assembly.py` passed with 8 tests.

Current full-suite verification:

- 2026-05-26: full test suite passed with 141 tests after Milestones 5-7.
- 2026-05-26: full test suite passed with 153 tests after Milestones 8-10.

Completed milestone: **Milestone 8: Notebooks**.

Milestone 8 status: `complete` for the first required notebook/smoke-test scope.

Completed in Milestone 8:

- Added top-level `/notebooks`.
- Added required notebooks:
  - `notebooks/00_quickstart.ipynb`
  - `notebooks/01_process_library_demo.ipynb`
  - `notebooks/02_surface_hydrolysis_demo.ipynb`
  - `notebooks/03_fungus_on_pet_demo.ipynb`
  - `notebooks/04_reaction_diffusion_demo.ipynb`
  - `notebooks/05_calibration_and_uncertainty_demo.ipynb`
- The quickstart notebook creates entities, assembles a generic PET surface
  process, runs through the current ODE engine, validates, plots, and saves
  standardized outputs.
- Added `tests/test_notebooks.py`.

Milestone 8 verification:

- `./.venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.

Completed milestone: **Milestone 9: Data/config schemas**.

Milestone 9 status: `complete` for the first YAML schema/loader scope.

Completed in Milestone 9:

- Added top-level data folders:
  - `data/fungi/`
  - `data/substrates/`
  - `data/enzymes/`
  - `data/environments/`
  - `data/geometries/`
  - `data/parameters/`
  - `data/experiments/`
- Added example configs:
  - `data/substrates/pet_film.yml`
  - `data/substrates/cellulose_powder.yml`
  - `data/fungi/toy_pet_fungus.yml`
  - `data/fungi/pleurotus_ostreatus.yml`
  - `data/enzymes/petase_like.yml`
  - `data/environments/lab_30C_pH7.yml`
  - `data/geometries/well_mixed_100ml.yml`
  - `data/geometries/pet_film_1d.yml`
  - `data/parameters/pet_surface_benchmark.yml`
  - `data/experiments/synthetic_pet_surface.yml`
- Added `src/fungal_model/io/`.
- Added schema validation in `src/fungal_model/io/schema.py`.
- Added YAML loaders in `src/fungal_model/io/yaml_loader.py`.
- Added JSON export helper in `src/fungal_model/io/json_export.py`.
- Exposed loaders from top-level `fungal_model`.
- Added `tests/test_config_io.py`.

Milestone 9 behavior now available:

- YAML configs must include top-level provenance fields.
- Parameter entries must include source, measurement method, confidence level,
  notes, validity range, units, and value.
- Unknown values remain `value: null` and load as explicit unknown parameters.
- Example configs can load into `Environment`, `Enzyme`, `PETSubstrate`,
  `Fungus`, `WellMixedGeometry`, `Film1DGeometry`, and `ParameterSet`.

Milestone 9 verification:

- `./.venv/bin/python -m pytest tests/test_config_io.py`
- Result: 6 passed.

Most recently completed milestone: **Milestone 10: First full integration workflow**.

Milestone 10 status: `complete` for the first config-driven PET surface
integration scope.

Completed in Milestone 10:

- Added `src/fungal_model/workflows/pet_surface_integration.py`.
- Added `src/fungal_model/workflows/__init__.py`.
- Exposed `PETSurfaceWorkflowConfig` and `run_pet_surface_integration` from
  top-level `fungal_model`.
- The workflow loads the example configs for:
  - PET film substrate;
  - PETase-like enzyme;
  - toy PET-capable fungus;
  - lab temperature/pH environment;
  - well-mixed geometry;
  - PET surface benchmark parameters.
- The workflow assembles generic surface catalysis through `ModelBuilder` and
  `ProcessRegistry`.
- The workflow runs the assembled process through the current ODE adapter,
  validates non-negativity and mass balance, records process-rate trajectories,
  and wraps the run in standardized `results.SimulationResult`.
- The workflow saves the full standardized output folder plus:
  - `input_configs.json`
  - `substrate.json`
  - `enzyme.json`
  - `fungus.json`
  - `environment.json`
  - `geometry.json`
- Added `tests/test_full_integration_workflow.py`.

Milestone 10 behavior now available:

- A complete config-driven PET surface run can be launched from
  `run_pet_surface_integration(output_dir)`.
- Missing accessible PET surface area fails before simulation with
  `MissingParameterError` and a structured assembly report.
- Incompatible enzyme/substrate metadata fails before simulation with
  `InvalidMechanismError` and structured compatibility issues.
- The saved output folder contains reports, tables, figures, logs, provenance,
  input config references, and entity snapshots.

Milestone 10 verification:

- `./.venv/bin/python -m pytest tests/test_full_integration_workflow.py`
- Result: 3 passed.

## Foundation-First Reset: Milestone 7 Native AssembledModel.run

Date: 2026-05-27

Milestone 7 status: `complete` for the first native assembled-model execution
scope.

Completed in Milestone 7:

- Added `src/fungal_model/solvers/process_ode.py`.
- Added `RunRequest` and `ProcessODESolver`.
- Implemented `AssembledModel.run()` as a real public execution method.
- `AssembledModel.run()` now delegates to the process ODE solver and returns a
  standardized `SimulationResult`.
- The solver builds derivatives from registered process `rate()` and
  `contributions()` methods.
- Process-rate trajectories are recorded into `SimulationResult.process_rates`.
- Model-level and request-level validators are run against the result.
- Unsupported geometry and mismatched initial states fail before simulation
  with structural `ValueError` messages.
- Resolved architecture debt `FD-003`; the shortcut guardrail no longer
  allowlists public `NotImplementedError` in `AssembledModel.run()`.

Milestone 7 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_native_assembled_model_run.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_public_api.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 192 passed.

Next milestone:

- Milestone 8: wire the generic `run_configured_model` workflow into config
  loading, registries, process factories, `AssembledModel.run()`, result
  validation, and output-bundle saving.

## Foundation-First Reset: Milestone 8 Generic run_configured_model

Date: 2026-05-27

Milestone 8 status: `complete` for the first generic configured-model
execution scope.

Completed in Milestone 8:

- Implemented `run_configured_model` as the generic workflow orchestrator.
- Configured runs now load substrates, geometries, product maps, validators,
  fungi, enzymes, environments, and parameter sets from the config contract.
- Plugin-backed substrate loading remains explicit through caller-supplied
  registries; the generic workflow does not import plugin loaders.
- Added `merge_parameter_sets` with duplicate-identical acceptance and
  duplicate-conflict rejection.
- Configured process entries build through `ProcessLibrary` factories and then
  assemble through `ModelBuilder`.
- Configured execution calls `AssembledModel.run()` and returns
  `SimulationResult`.
- Output saving uses the standard `SimulationResult.save()` bundle and adds
  `input_model_config.json` plus `configured_model_run.json`.
- Added a toy generic surface catalyst config so the dummy non-plugin surface
  benchmark exercises entity compatibility without substrate-specific biology.
- Resolved architecture debt `FD-004`.

Milestone 8 behavior now available:

- `run_configured_model("data/model_configs/toy_homogeneous_ab.yml")` runs the
  homogeneous benchmark through the generic workflow.
- `run_configured_model("data/model_configs/toy_surface_dummy_non_pet.yml")`
  runs the dummy non-plugin surface benchmark through the same workflow.
- `run_configured_model("data/model_configs/toy_surface_pet_plugin.yml",
  substrate_registry=pet_substrate_loader_registry())` runs the explicit plugin
  benchmark through the same workflow.
- Running the plugin config without the explicit registry fails structurally at
  input loading instead of creating a generic substrate-specific branch.

Milestone 8 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_model_config_loading.py tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 198 passed.
- `rg -n "SimulationEngine|ReactionDiffusionEngine|solve_ivp" src/fungal_model/workflows src/fungal_model/plugins/pet`
- Result: no matches.
- Generic PET-hardcoding scan over core/process/results/modifiers/io/workflows
  source paths.
- Result: no matches.

Next milestone:

- Milestone 9: remove or relocate the deprecated direct PET workflow path so
  workflows no longer call lower-level solvers directly.

## Foundation-First Reset: Milestone 9 Workflow Solver Isolation

Date: 2026-05-28

Milestone 9 status: `complete` for workflow-level solver isolation.

Completed in Milestone 9:

- Removed `src/fungal_model/workflows/pet_surface_integration.py`.
- Removed `PETSurfaceWorkflowConfig` and `run_pet_surface_integration` from
  `fungal_model.workflows`.
- Added `src/fungal_model/plugins/pet/workflows.py` as the plugin-local
  compatibility helper.
- The PET plugin helper materializes a generic model config and delegates to
  `run_configured_model` with `pet_substrate_loader_registry()`.
- The plugin helper no longer constructs processes, reactions, or low-level
  solvers directly.
- Tightened `tests/test_guardrails_no_hardcoding.py` by removing the legacy
  PET allowlist for generic workflow paths.
- Resolved architecture debt `FD-001`.

Milestone 9 behavior now available:

- `fungal_model.workflows` exports only generic configured-model workflow
  names.
- PET-specific convenience execution lives under `fungal_model.plugins.pet`.
- Generic workflow source paths no longer contain PET-specific workflow names,
  hardcoded PET states, or direct low-level solver imports.

Milestone 9 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_full_integration_workflow.py tests/test_configured_model_workflow.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_public_api.py tests/test_guardrails_no_shortcuts.py`
- Result: 16 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 198 passed.

Next milestone:

- Milestone 10: harden the result/output foundation for configured runs,
  including complete output metadata and snapshots for generic configs.

## Foundation-First Reset: Milestone 10 Result/Output Foundation

Date: 2026-05-28

Milestone 10 status: `complete` for configured-run output bundles.

Completed in Milestone 10:

- Hardened configured-run output saving around `SimulationResult.save()`.
- Added `configured_metadata.json` with config name, mode, maturity, result
  label, model version, state count, process-rate count, and validation
  summary.
- Expanded `configured_model_run.json` with state names, process-rate names,
  validation summary, and solver metadata.
- Added `process_build_decisions.json` so factory decisions are inspectable.
- Added `initial_state.json`, `time_grid.json`, `validators.json`, and
  `merged_parameters.json`.
- Added `entity_snapshots/` with snapshots for configured fungi, substrates,
  enzymes, environments, geometries, and product maps.
- Added `output_manifest.json` listing the complete saved bundle.
- Updated configured workflow tests so homogeneous, plugin, and non-plugin
  foundation configs all prove the complete output bundle exists.

Milestone 10 behavior now available:

- Every configured foundation benchmark saves a complete output folder.
- Mode and maturity are visible without opening the source config.
- Users can inspect config, entity, parameter, process-build, validation, solver,
  trajectory, plot, and provenance artifacts from the output directory.

Milestone 10 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_full_integration_workflow.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 17 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 199 passed.
- Notebook JSON validation for all four foundation notebooks.
- Result: passed.
- Notebook direct-solver/core-implementation scan.
- Result: no matches.

Next milestone:

- Milestone 11: notebook foundation for generic quickstart, config/entity
  inspection, failure reports, and configured output inspection.

## Foundation-First Reset: Milestone 11 Notebook Foundation

Date: 2026-05-28

Milestone 11 status: `complete` for foundation notebook smoke coverage.

Completed in Milestone 11:

- Replaced the old roadmap notebooks with foundation-first notebooks under
  `notebooks/examples/`.
- Added a generic quickstart notebook that runs
  `data/model_configs/toy_homogeneous_ab.yml` through `run_configured_model`.
- Added a config/entity inspection notebook for the dummy non-plugin surface
  benchmark.
- Added a structured failure-report notebook that captures the expected plugin
  registry failure as a `ConfiguredModelRunReport`.
- Added a configured-output inspection notebook that reads the manifest,
  metadata, build decisions, validators, and result state names.
- Tightened notebook tests so required notebooks import package code, call the
  generic configured workflow, avoid core class/rate-law/solver definitions,
  and execute every foundation notebook smoke path.

Milestone 11 behavior now available:

- Notebooks demonstrate the generic workflow instead of constructing low-level
  solvers.
- Failure handling and output inspection are documented as runnable examples.
- Notebook smoke tests create quickstart, failure-report, and output-inspection
  artifacts under `outputs/`.

Milestone 11 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 199 passed.

Next milestone:

- Milestone 12: package quality and CI discipline, including initial linting,
  type-checking, coverage, and README/CI alignment.

## Foundation-First Reset: Milestone 12 Package Quality And CI

Date: 2026-05-28

Milestone 12 status: `complete` for the first executable package-quality
baseline.

Completed in Milestone 12:

- Added `ruff`, `pyright`, and `pytest-cov` to the `dev` extra.
- Added Ruff configuration for correctness-oriented linting over `src` and
  `tests`.
- Added `pyrightconfig.json` as an explicit initial type-checking baseline.
- Added coverage configuration with branch coverage and a starting
  `fail_under = 60` gate.
- Updated GitHub Actions CI to run lint, type check, and coverage-backed tests.
- Added `.github/BRANCH_PROTECTION.md` documenting the default-branch
  protection expectation for the CI workflow.
- Added `tests/test_quality_config.py` to protect declared dev dependencies,
  quality-tool configuration, and CI commands.
- Updated the PR template to require Ruff, Pyright, coverage, and pytest status.
- Cleaned up unused imports surfaced by Ruff without broad style churn.
- Updated `.gitignore` for local coverage artifacts.

Milestone 12 type-checking note:

- The Pyright gate is intentionally permissive around Pint quantity typing and
  optional-state inference. It is active and passing, but the stricter quantity
  typing cleanup remains a future package-quality milestone and is documented
  as `FD-005` in `ARCHITECTURE_DEBT.md`.

Milestone 12 verification:

- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 203 passed, total coverage 84.92%, required coverage 60% reached.

Next milestone:

- Milestone 13: tighten foundation review/readiness, including explicit
  remaining architecture debt and the next realistic type/coverage ratchet.

## Foundation-First Reset: Milestone 13 Foundation Review

Date: 2026-05-28

Milestone 13 status: `complete` for the foundation review/readiness gate.

Completed in Milestone 13:

- Added `FOUNDATION_READINESS.md` with the current foundation gate result,
  active architecture debt, deferred biology scope, and review commands.
- Added `tests/test_guardrails_config_generality.py` to prove the homogeneous,
  explicit PET plugin, and dummy non-PET surface configs all run through
  `run_configured_model`.
- Added `tests/test_guardrails_config_generality.py` coverage for arbitrary
  state names and explicit plugin registry failure.
- Added `tests/test_guardrails_native_execution.py` to prove the configured
  workflow calls `AssembledModel.run()` and high-level workflows do not import
  low-level solver backends.
- Replaced the stale README example-script section with the current
  configured-model benchmark workflow.
- Raised the coverage gate from 60% to 80%.
- Updated branch-protection and quality-config docs/tests for the new coverage
  floor.
- Clarified that `FD-005` remains active and should be removed in a dedicated
  quantity-typing package-quality ratchet.

Milestone 13 behavior now available:

- The required foundation benchmark trio is protected by explicit guardrail
  tests.
- Output bundles are inspected as part of the generic-config guardrail.
- The package now has a more serious coverage gate while preserving the
  documented Pyright quantity-typing baseline.

Milestone 13 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 6 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 19 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 209 passed, total coverage 84.92%, required coverage 80% reached.

Next milestone:

- Quantity-typing package-quality ratchet: reduce `FD-005` by tightening
  Pyright diagnostics around Pint quantity aliases and optional-state handling.

## Foundation-First Reset: Milestone 14 Pyright Quantity-Typing Ratchet

Date: 2026-05-28

Milestone 14 status: `complete` for the first Pyright quantity/type diagnostic
ratchet.

Completed in Milestone 14:

- Made `fungal_model.core.units.Quantity` a static `TypeAlias` while preserving
  the runtime Pint class export.
- Marked the runtime `Q_` constructor alias as `Any` so Pyright does not treat
  it as a type alias.
- Re-enabled these Pyright diagnostics:
  - `reportInvalidTypeForm`;
  - `reportReturnType`;
  - `reportAssignmentType`;
  - `reportArgumentType`;
  - `reportAttributeAccessIssue`;
  - `reportCallIssue`;
  - `reportOperatorIssue`;
  - `reportOptionalOperand`;
  - `reportGeneralTypeIssues`.
- Tightened process factory protocol typing and product-map defaults.
- Added explicit casts/guards for quantity arithmetic, mass-balance totals,
  local sensitivity perturbations, spatial grid cell width, registry literal
  loading, and result assembly-report summaries.
- Reworked product inhibition activity calculation to avoid ambiguous
  dimensionless quantity operators.
- Updated `ARCHITECTURE_DEBT.md` so `FD-005` now tracks only the remaining
  optional-member-access cleanup.

Milestone 14 verification:

- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_units.py tests/test_process_factory_library.py tests/test_results.py tests/test_configured_model_workflow.py tests/test_registry_based_loading.py tests/test_uncertainty_sensitivity.py tests/test_reaction_diffusion.py tests/test_environment_modifiers.py tests/test_calibration.py`
- Result: 55 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 209 passed, total coverage 84.83%, required coverage 80% reached.

Next milestone:

- Optional-member-access package-quality ratchet: re-enable
  `reportOptionalMemberAccess` by narrowing optional quantities in calibration,
  transport, uncertainty, pH kinetics, and plugin substrate modules.

## Foundation 10/10 Push: F10.2 Centralized Mode/Maturity Enforcement

Date: 2026-05-28

F10.2 status: `complete` for centralized toy/scientific/strict run-mode
preflight enforcement.

Completed in F10.2:

- Added `fungal_model.validation.maturity` as the central maturity-policy
  module for configured runs.
- Added structured `MaturityIssue` records and `InvalidDataMaturityError`
  failures with object type, object id, field, requested mode, reason, and fix.
- Wired `run_configured_model` to enforce the maturity policy after generic
  config/entity/parameter/product-map loading and before process factories,
  model assembly, or solving.
- Preserved toy benchmark execution while preventing framework benchmark
  parameters, toy-only provenance, unknown required parameter values, missing
  required parameter metadata, and toy/framework product maps from running in
  scientific or strict modes.
- Made strict mode reject missing uncertainty metadata for required
  parameters, which scientific mode still allows.
- Added `validity_range` to parameter parsing/serialization so required
  parameter validity metadata can be enforced centrally.
- Moved example notebook outputs from root-level `outputs/` paths to
  `notebooks/examples/Outputs/<notebook-name>/`, with notebook smoke tests
  updated to protect that layout.

Architecture debt:

- No new architecture debt was added for F10.2.

F10.2 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_maturity_policy.py`
- Result: 10 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py`
- Result: 5 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py`
- Result: 2 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_shortcuts.py`
- Result: 2 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 219 passed.

Next milestone:

- F10.1: decompose the generic configured workflow into separately testable
  input loading, process assembly, orchestration, and output writing
  responsibilities.

## Foundation 10/10 Push: F10.1 Configured Workflow Decomposition

Date: 2026-05-28

F10.1 status: `complete` for decomposing the generic configured workflow into
separately testable responsibilities.

Completed in F10.1:

- Kept `run_configured_model(config_path, output_dir=None, ...)` as the stable
  public entry point.
- Added `ConfiguredModelRunner` for orchestration of config loading, maturity
  preflight, process assembly, model execution, and output writing.
- Added `ConfiguredInputLoader` and `ConfiguredInputs` for resolving entity
  registries, product maps, merged parameter sets, validators, initial state,
  and time grids.
- Added `ConfiguredProcessAssembler` and `ConfiguredProcessAssembly` for
  process-factory decisions, process construction, and `ModelBuilder`
  assembly.
- Added `ConfiguredOutputWriter` for configured output bundle persistence.
- Moved configured workflow error/report helpers into a shared internal module
  so loader, assembler, and runner can all raise the same structured
  execution error without import cycles.
- Exported the new workflow components from `fungal_model.workflows` and the
  top-level package.

Architecture debt:

- No new architecture debt was added for F10.1.

F10.1 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_workflow_components.py`
- Result: 8 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py`
- Result: 5 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_config_loading.py`
- Result: 8 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 15 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_maturity_policy.py tests/test_notebooks.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 227 passed.

Next milestone:

- F10.3: strengthen generic workflow failure-path tests with structured
  exception-stage assertions and no false-success output.

## Foundation 10/10 Push: F10.3 Generic Workflow Failure-Path Tests

Date: 2026-05-28

F10.3 status: `complete` for structured generic workflow failure-path coverage.

Completed in F10.3:

- Added `tests/test_configured_workflow_failures.py` with all required generic
  workflow failure-path cases.
- Wrapped model-config loading failures at the public configured workflow
  boundary with `ConfiguredModelExecutionError` stage `model_config_loading`.
- Wrapped process-factory lookup failures, model-assembly failures, and
  model-execution failures with structured configured-run reports.
- Added strict-mode result-validation enforcement: strict configured runs now
  raise before output writing if any configured validator fails.
- Kept non-strict failed validation behavior record-oriented: failed
  validators are saved in result metadata and output bundles instead of being
  hidden or treated as success.
- Updated PET plugin integration tests to assert the generic configured
  workflow error boundary while preserving plugin delegation to
  `run_configured_model`.

F10.3 failure cases now covered:

- missing config file;
- invalid top-level config kind;
- missing configured processes;
- missing configured initial state;
- unknown substrate loader;
- plugin config without explicit plugin registry;
- unknown product-map loader;
- unknown validator type;
- unknown process type;
- missing product map;
- missing state unit;
- missing required parameter;
- conflicting duplicate parameters;
- incompatible initial-state units;
- unsupported geometry;
- failed validation recorded in non-strict mode;
- failed validation raises in strict mode.

Architecture debt:

- No new architecture debt was added for F10.3.

F10.3 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_workflow_failures.py`
- Result: 17 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_full_integration_workflow.py tests/test_configured_workflow_failures.py`
- Result: 20 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_workflow_components.py tests/test_configured_model_workflow.py tests/test_model_config_loading.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 36 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_maturity_policy.py tests/test_notebooks.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 244 passed.

Next milestone:

- F10.4: make configured output bundles reproducibility-grade by adding run
  environment, package version, source revision, and solver settings metadata.

## Foundation 10/10 Push: F10.4 Reproducibility-Grade Output Bundles

Date: 2026-05-28

F10.4 status: `complete` for configured-run output bundle reproducibility
metadata.

Completed in F10.4:

- Added `run_environment.json` to each configured output bundle with UTC run
  timestamp, Python runtime details, platform details, executable path, and
  working directory.
- Added `package_versions.json` with the FungMod model version and installed
  package versions for core runtime dependencies.
- Added `source_revision.json` with truthful Git metadata when available:
  repository root, commit, branch, dirty state, and an error field when Git
  metadata cannot be resolved.
- Added `solver_settings.json` with both configured solver settings and solver
  backend metadata.
- Ensured the output manifest includes the new files and still includes
  itself.
- Added reproducibility tests that assert every manifest-listed file exists,
  mode/maturity are recorded, solver metadata is present, package version
  metadata is present, and process-build decisions are included.

Architecture debt:

- No new architecture debt was added for F10.4.

F10.4 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_output_bundle_reproducibility.py tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py`
- Result: 31 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 15 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py tests/test_full_integration_workflow.py`
- Result: 6 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 245 passed.

Next milestone:

- F10.5: make the public API intentionally stable and documented, while
  keeping PET-specific helpers contained in `fungal_model.plugins.pet`.

## Foundation 10/10 Push: F10.5 Stable Foundation Public API

Date: 2026-05-28

F10.5 status: `complete` for a documented, generic-first foundation public API.

Completed in F10.5:

- Added a `Foundation Public API` section to `README.md` documenting the stable
  top-level foundation names for configured execution, loaders, model assembly,
  solvers, results, and parameter containers.
- Strengthened `tests/test_guardrails_public_api.py` so the required
  foundation API names must be exported from `fungal_model.__all__` and must
  resolve to the expected objects.
- Added explicit plugin containment checks proving PET helper names are absent
  from top-level `fungal_model` and `fungal_model.workflows`.
- Added explicit plugin availability checks proving PET helper names remain
  available only from `fungal_model.plugins.pet`.
- Expanded public API cleanliness checks across the documented foundation
  primitives so they contain no `TODO`, `placeholder`, or public
  `NotImplementedError` markers.
- Added README documentation coverage checks for every required foundation API
  name and for the PET plugin containment path.

Architecture debt:

- No new architecture debt was added for F10.5.

F10.5 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_public_api.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_quality_config.py`
- Result: 14 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py tests/test_configured_output_bundle_reproducibility.py tests/test_full_integration_workflow.py tests/test_notebooks.py`
- Result: 37 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 247 passed.

Next milestone:

- F10.6: harden notebook smoke tests so foundation notebooks demonstrate only
  public APIs and do not hide implementation in notebook cells.

## Foundation 10/10 Push: F10.6 Notebook Public-API Smoke Tests

Date: 2026-05-28

F10.6 status: `complete` for notebook public-API and smoke-test guardrails.

Completed in F10.6:

- Added a `FUNGMOD_NOTEBOOK_OUTPUT_ROOT` output-root override to every
  foundation example notebook while preserving the default
  `notebooks/examples/Outputs/<notebook-name>/` location for normal use.
- Updated notebook smoke tests to redirect outputs to `tmp_path` so test runs
  do not write generated files into the repository.
- Strengthened notebook import checks so every foundation notebook must import
  or use public `fungal_model` APIs and call `run_configured_model`.
- Strengthened hidden-implementation guardrails so notebooks cannot define
  process classes, solver classes, process factories, rate-law functions,
  solver functions, direct SciPy solver calls, core simulation-engine imports,
  solver imports, process-internal imports, or legacy rate-law classes.
- Added an explicit quickstart smoke test that executes
  `00_quickstart.ipynb` with temporary outputs and verifies the expected
  result bundle files.
- Kept the full foundation notebook smoke path so the complete example set
  still executes through package APIs.

Architecture debt:

- No new architecture debt was added for F10.6.

F10.6 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 4 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_quality_config.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py tests/test_configured_output_bundle_reproducibility.py tests/test_full_integration_workflow.py`
- Result: 34 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 248 passed.

Next milestone:

- F10.7: harden CI and branch-protection documentation around lint, type,
  coverage, and merge requirements.

## Foundation 10/10 Push: F10.7 CI And Branch Protection Gate

Date: 2026-05-28

F10.7 status: `complete` for documented CI and merge-quality policy.

Completed in F10.7:

- Confirmed `.github/workflows/ci.yml` runs the required package-quality gates:
  Ruff, Pyright, and pytest with coverage XML output.
- Strengthened `.github/BRANCH_PROTECTION.md` so default-branch policy requires
  pull requests, the `CI / tests` status check, up-to-date branches, no force
  pushes, and no unaudited direct bypass.
- Updated `README.md` to state that CI is required before merging and to
  summarize the protected-branch requirements.
- Expanded `tests/test_quality_config.py` so the CI commands, coverage gate,
  branch-protection policy, and README merge policy stay mechanically checked.

Architecture debt:

- No new architecture debt was added for F10.7.
- `FD-005` remains active as a documented package-quality typing ratchet, not
  foundation-blocking architecture debt.

F10.7 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_foundation_complete_gate.py`
- Result: 8 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 252 passed; coverage 85.35%, above the 80% gate.

Next milestone:

- F10.8: add and test the formal foundation-complete gate before biology may
  begin.

## Foundation 10/10 Push: F10.8 Foundation Complete Gate

Date: 2026-05-28

F10.8 status: `complete` for the formal foundation-complete gate.

Completed in F10.8:

- Added `FOUNDATION_COMPLETE.md` with `Status: complete` for the software
  foundation only.
- Recorded the completion criteria required before biology may begin:
  guardrails, configured workflows, failure paths, maturity modes,
  reproducibility outputs, CI, coverage, plugin containment, notebook public
  API usage, README limitations, and all three foundation configured runs.
- Explicitly stated that the completion gate does not approve real fungal
  biology, PETase mechanisms, literature parameters, metabolism, growth
  physiology, or substrate-specific scientific mechanisms.
- Documented active non-blocking architecture debt `FD-005` as a typing
  ratchet only, not foundation-blocking architecture debt.
- Added `tests/test_foundation_complete_gate.py` so a complete foundation gate
  requires all evidence and cannot coexist with undocumented active
  architecture debt.

Architecture debt:

- No new architecture debt was added for F10.8.

F10.8 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py tests/test_maturity_policy.py tests/test_configured_output_bundle_reproducibility.py tests/test_notebooks.py tests/test_quality_config.py tests/test_foundation_complete_gate.py`
- Result: 70 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 252 passed; coverage 85.35%, above the 80% gate.

Next milestone:

- Foundation F10.1-F10.8 is complete. The next work should start the
  post-foundation biology-readiness path from
  `foundation_progress/FUNG_MOD_FOUNDATION_8_TO_10_MILESTONES.md`: literature
  dataset schema, provenance templates, experiment dataset object, and
  calibration workflow on synthetic data before any real biology is added.

## Data Infrastructure: D1 ExperimentDataset Loader

Date: 2026-05-29

D1 status: `complete` for the first strict experiment-dataset schema and
loader.

Completed in D1:

- Added the `fungal_model.data` package with explicit dataset objects:
  `ExperimentDataset`, `DataSource`, `ExperimentalSystem`,
  `ExperimentalConditions`, `MeasurementSeries`, `MeasurementPoint`, and
  `PreprocessingRecord`.
- Added `load_experiment_dataset` for YAML-backed datasets with CSV
  measurement loading, relative CSV resolution, explicit maturity validation,
  required source metadata, required time/value units, uncertainty-unit checks,
  expected-column validation, and optional missing-uncertainty handling only
  when configured.
- Added a synthetic first-order A to B dataset fixture under
  `data/experiments/synthetic/first_order_ab/` with YAML metadata,
  observation CSV, and a generation record.
- Added experiment dataset documentation for maturity labels, toy versus
  synthetic data, provenance, unit requirements, uncertainty behavior, and the
  current no-literature-data boundary.
- Added loader tests covering valid synthetic loading, maturity preservation,
  measurement units and uncertainty, missing kind, invalid maturity, missing
  source, missing CSV files, missing value columns, missing uncertainty
  columns, explicitly allowed missing uncertainty, JSON-safe `to_dict()`, and
  `validate()` success.

Architecture debt:

- No new architecture debt was added for D1.

D1 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py`
- Result: 11 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_maturity_policy.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 263 passed.

Next milestone:

- D2 should add the explicit observable mapping and model-dataset comparison
  layer before any calibration or real literature data work begins.

## Data Infrastructure: D2 Observable Mapping And Comparison

Date: 2026-05-29

D2 status: `complete` for explicit model-dataset comparison on synthetic data.

Completed in D2:

- Added `src/fungal_model/data/comparison.py` with `ObservableMapping`,
  `ResidualPoint`, `ResidualSeries`, `ModelDatasetComparison`, and
  `evaluate_model_against_dataset`.
- Required explicit dataset-measurement to model-observable mappings; no fuzzy
  matching or automatic biological interpretation is used.
- Implemented state, process-rate, and derived-observable lookup against
  `SimulationResult`.
- Implemented unit-aware identity and unit-conversion comparisons, plus a
  guarded fractional-conversion path that requires an explicit initial value
  and units.
- Implemented linear interpolation to dataset times and structural rejection
  of extrapolation beyond the model time range.
- Implemented raw residuals, standardized residuals when uncertainty exists,
  RMSE, mean absolute residual, chi-square, and reduced chi-square metrics.
- Implemented comparison output bundles with comparison record, dataset
  snapshot, observable mapping, residuals CSV, metrics, validation report, and
  observed-vs-predicted and residual figures.
- Updated the synthetic first-order fixture so it aligns with the existing
  `toy_homogeneous_ab.yml` benchmark time window and rate constant.
- Exposed comparison names from `fungal_model.data` without adding unstable
  data APIs to top-level `fungal_model`.
- Updated data documentation to describe explicit observable mappings and the
  comparison output bundle.

Architecture debt:

- No new architecture debt was added for D2.

D2 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_model_dataset_comparison.py`
- Result: 23 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py`
- Result: 14 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_dataset_comparison.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 275 passed.

Next milestone:

- D3 should add synthetic dataset generation from `SimulationResult`, including
  Gaussian noise options, generation records, reproducibility tests, and
  reloadability checks. No calibration or real literature data yet.

## Data Infrastructure: D3 Synthetic Dataset Generation

Date: 2026-05-29

D3 status: `complete` for synthetic dataset generation from existing
`SimulationResult` objects.

Completed in D3:

- Added `src/fungal_model/data/synthetic.py` with `GaussianNoise`,
  `SyntheticDatasetGenerationError`, and
  `generate_synthetic_dataset_from_result`.
- Implemented generation from explicit `ObservableMapping` entries or a simple
  measurement-to-state mapping, using existing `SimulationResult` states,
  process rates, or derived quantities.
- Wrote reloadable dataset bundles containing:
  - dataset YAML;
  - observations CSV;
  - `generation_record.json`.
- Recorded seed, noise model, source result metadata, optional source config,
  observable mappings, output file names, and true values in the generation
  record.
- Enforced unit compatibility for Gaussian noise and generated measurement
  units.
- Added fixed-seed reproducibility tests, changed-seed tests, reloadability
  tests, comparison-back-to-source tests, generation-record metadata tests,
  incompatible-noise-unit tests, and missing-model-observable tests.
- Updated synthetic-data documentation to describe generation from
  `SimulationResult` and the required generation record.

Architecture debt:

- No new architecture debt was added for D3.

D3 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_model_dataset_comparison.py tests/test_synthetic_dataset_generation.py`
- Result: 30 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py`
- Result: 14 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_synthetic_dataset_generation.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 282 passed.

Next milestone:

- D4 should add synthetic-only calibration that can recover a known first-order
  parameter from generated synthetic data. Do not add real literature data or
  biological mechanisms.

## Data Infrastructure: D4-D6 Synthetic Calibration And Literature Contract

Date: 2026-05-29

D4-D6 status: `complete` for synthetic-only calibration, train/validation
splits, literature schema guardrails, and the remaining data-validation rules.

Completed in D4-D6:

- Added `calibrate_configured_model` and `CalibrationResult` in
  `src/fungal_model/calibration/configured.py` for synthetic configured-model
  calibration.
- Kept calibration synthetic-only: non-synthetic datasets are rejected, source
  model configs are copied through temporary configured runs, and source config
  files are not mutated in place.
- Added a synthetic first-order calibration model config and calibration
  contract fixture under `data/model_configs/` and `data/calibration/`.
- Wrote inspectable calibration bundles with calibration records, source model
  snapshots, dataset snapshots, fitted parameter files, optimizer metadata,
  train/validation residual CSVs, metrics, assumptions, warnings, and figures.
- Added deterministic train/validation split support by time, with separate
  train and validation residuals/metrics and a clear warning when no
  validation split is supplied.
- Added dataset validation rules for known units, finite numeric values,
  nonnegative time, strictly increasing time per series, nonnegative
  uncertainty, duplicate measurement IDs, source/provenance, preprocessing
  status, and preprocessing notes.
- Added `data/experiments/literature/README.md` as the literature extraction
  metadata contract while keeping the literature directory free of real paper
  data.
- Added `data/experiments/validation/README.md`, `data/calibration/README.md`,
  and `data/README.md` to document maturity labels, synthetic-only calibration,
  and the current no-real-literature boundary.

Architecture debt:

- No new architecture debt was added for D4-D6.

D4-D6 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_synthetic_calibration.py tests/test_calibration_config_contract.py tests/test_experiment_dataset_validation_rules.py tests/test_literature_schema_contract.py`
- Result: 18 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_experiment_dataset_validation_rules.py tests/test_model_dataset_comparison.py tests/test_synthetic_dataset_generation.py tests/test_configured_synthetic_calibration.py tests/test_calibration_config_contract.py tests/test_literature_schema_contract.py`
- Result: 48 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py tests/test_config_io.py`
- Result: 20 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 300 passed.

Data infrastructure roadmap status:

- D1-D6 and the roadmap definition-of-done items are complete for the
  synthetic/no-real-biology scope. Real literature extraction and real fungal
  biology remain explicitly out of scope until schema-compliant data curation
  work is requested and reviewed.

## Data Infrastructure Finalization: D4-D6 Hardening Before Real Data

Date: 2026-05-31

Status: `complete` for the final pre-real-data hardening pass.

Completed in this pass:

- Finalized configured synthetic calibration behavior:
  - fitted `k_ab` still recovers the synthetic first-order target near
    `0.1 1 / second`;
  - fitted parameter provenance now records synthetic-only calibration,
    dataset ID, least-squares fitting, and not-empirical-validation status;
  - source model configs are not mutated;
  - missing parameter symbols, missing initial guesses, bad bounds,
    non-synthetic datasets, and parameters absent from the configured model
    fail structurally.
- Hardened calibration path resolution:
  - calibration now resolves model-config references against the source config
    path and its ancestors before writing temporary configured runs;
  - synthetic calibration works when invoked from outside the repository root.
- Fixed D5 split semantics with explicit train/validation/holdout behavior:
  - `train_fraction` selects the first time-ordered block;
  - `validation_fraction` selects the next time-ordered block;
  - remaining points become holdout/unused data for future workflows;
  - train, validation, and holdout indices are disjoint and reported in
    `CalibrationSplit.to_dict()`;
  - validation metrics are reported only when validation indices exist.
- Upgraded D6 from README-only to machine-readable literature metadata schema:
  - added `validate_literature_dataset_metadata`;
  - added fake schema-only metadata under
    `data/experiments/literature_schema_examples/`;
  - preserved the rule that `data/experiments/literature/` contains no real
    paper-derived data files.
- Updated the literature README to state that future literature datasets must
  pass machine-readable schema validation and include provenance, units,
  extraction notes, preprocessing, uncertainty status, and source metadata.

Architecture/data debt:

- No architecture or data debt was added.
- No real literature data or real biological mechanisms were inserted.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_synthetic_calibration.py`
- Result: 15 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_literature_schema_contract.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_model_dataset_comparison.py tests/test_synthetic_dataset_generation.py`
- Result: 30 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py tests/test_calibration_config_contract.py`
- Result: 16 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 320 passed.

Next allowed step:

- Select one candidate real dataset for schema-first ingestion review. Do not
  implement broad biology or substrate-specific mechanisms as the next step.

## Registry And Ranges: R1 ValueSpec And Registry Loader

Date: 2026-06-01

R1 status: `complete` for the ValueSpec and registry-loader foundation.

Completed in R1:

- Added `ValueSpec` in `src/fungal_model/core/value_spec.py` to represent
  exact values, ranges, distributions, unknowns, and not-applicable values with
  explicit units, source, confidence, notes, validation, sampling, and exact
  quantity conversion.
- Supported initial `uniform` and `loguniform` distribution sampling with fixed
  RNG reproducibility.
- Added `src/fungal_model/registry/` with registry records, YAML loading, and
  an in-memory `FungModRegistry` store.
- Implemented minimal records for fungi, enzyme classes, substrates,
  environments, process compatibility, and parameters.
- Added registry lookup methods for fungi, enzyme classes, substrates,
  environments, process compatibility records, and parameter records.
- Added toy/development-only registry fixtures under `data_registry/`.
- Added registry documentation explaining that the registry is not a complete
  biological database and that all current records are toy/development
  fixtures only.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real literature capability records, real fungal datasets,
  range-based ensemble simulation, or new biological process equations were
  added.

Verification:

- `.venv/bin/python -m pytest tests/test_value_spec.py`
- Result: 10 passed.
- `.venv/bin/python -m pytest tests/test_registry_loading.py`
- Result: 11 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_guardrails_no_hardcoding.py`
- Result: 23 passed.
- `.venv/bin/python -m pytest tests/test_guardrails_no_shortcuts.py`
- Result: 2 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 341 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- R2 should implement a modelability report over the toy registry. Do not start
  range-based ensemble simulation or real registry data insertion yet.

## Registry And Ranges: R2 Modelability Report

Date: 2026-06-01

R2 status: `complete` for toy-registry modelability reporting.

Completed in R2:

- Added `src/fungal_model/screening/modelability.py` with:
  - `ReportItem`;
  - `ModelabilityReport`;
  - `assess_modelability`.
- Added `src/fungal_model/screening/__init__.py` as the public screening
  package boundary.
- Implemented registry-only case assessment for:
  - fungus record loading;
  - substrate record loading;
  - environment record loading;
  - fungus enzyme-class capability matching;
  - enzyme/substrate class and bond compatibility;
  - process compatibility discovery;
  - required parameter lookup;
  - exact, uncertain, unknown, and mode-incompatible parameter classification.
- Implemented the four R2 statuses over toy records:
  - `modelable`;
  - `exploratory`;
  - `underparameterized`;
  - `unsupported`.
- Added JSON-safe `ModelabilityReport.to_dict()` and a concise
  `ModelabilityReport.summary()`.
- Added tests that verify default toy underparameterization, exact-only
  modelability, range-based exploratory status, scientific-mode rejection of
  uncertain parameters, missing-parameter reporting, unsupported compatibility,
  JSON-safe report serialization, and invalid mode errors.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real registry records, case-builder workflow, model
  assembly, range-based ensemble simulation, or new process equations were
  added.

Verification:

- `.venv/bin/python -m pytest tests/test_modelability_report.py`
- Result: 8 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_modelability_report.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 33 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 349 passed.

Next milestone:

- R3 should implement a toy-registry case builder that converts a modelable
  registry case into a generic `ModelConfig` for `run_configured_model`. Do not
  start range-based ensemble simulation or real registry data insertion yet.

## Registry And Ranges: R3 Plug-And-Play Case Builder

Date: 2026-06-01

R3 status: `complete` for deterministic toy-registry case building.

Completed in R3:

- Added `src/fungal_model/screening/case_builder.py` with:
  - `build_model_config_from_registry_case`;
  - `RegistryCaseBuildError`;
  - an explicit toy-only config mode boundary for R3.
- The case builder now gates assembly through `assess_modelability` and refuses
  underparameterized, exploratory, unsupported, or non-toy cases.
- Added process-compatibility `parameter_roles` metadata so registry parameter
  symbols can be mapped into the existing generic process factory roles without
  hardcoding substrate-specific workflow logic.
- Converted modelable toy surface-catalysis registry cases into regular
  `ModelConfig` objects that run through `run_configured_model`.
- Kept the generated config self-contained with inline toy geometry, generic
  substrate metadata, toy product maps, explicit parameters, validators, time
  grid, and output settings.
- Added toy/development-only exact adsorption and accessible-surface parameter
  records for case-builder tests while preserving the default underparameterized
  R2 registry case.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real registry records, range-based ensemble simulation, or
  new process equations were added.

Verification:

- `.venv/bin/python -m pytest tests/test_registry_case_builder.py`
- Result: 6 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_modelability_report.py tests/test_registry_case_builder.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 39 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 355 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- R4 should implement exploratory ensemble simulation over `ValueSpec` ranges
  and distributions. Do not add real biology or real literature capability
  records as part of R4.

## Registry And Ranges: R4 Exploratory Ensemble Simulation

Date: 2026-06-01

R4 status: `complete` for toy-registry exploratory ensemble execution.

Completed in R4:

- Added `src/fungal_model/screening/ensemble.py` with:
  - `simulate_screen`;
  - `RegistryScreenResult`;
  - `RegistryCaseEnsemble`;
  - `EnsembleSample`;
  - `RegistryScreenSimulationError`.
- Implemented sampling over registry `ValueSpec` exact, range, and distribution
  values for exploratory toy screen runs.
- Added seeded reproducibility for sampled registry screens.
- Materialized each sampled run as a standard generic `ModelConfig`, then ran it
  through `run_configured_model`; no separate solver path was introduced.
- Wrote per-sample configs, configured output bundles, and
  `screen_summary.json`.
- Kept R4 limited to toy/exploratory registry cases and explicit
  surface-catalysis configs using existing generic process factories.
- Added clear rejection paths for underparameterized cases, unknown parameters,
  unsupported process types, missing parameter-role mappings, invalid sample
  counts, empty input lists, and non-exploratory screen modes.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real literature capability records, real fungal datasets,
  JAX, or new biological process equations were added.

Verification:

- `.venv/bin/python -m pytest tests/test_registry_ensemble_simulation.py`
- Result: 6 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_modelability_report.py tests/test_registry_case_builder.py tests/test_registry_ensemble_simulation.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 45 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 361 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- The registry-and-ranges foundation is now ready for a schema-first review of
  the first candidate real capability/dataset records. Real data should enter
  one selected case at a time, with literature-schema validation and no broad
  biology implementation.

## Data Intake Gate: Dataset Candidate Review

Date: 2026-06-01

Status: `complete` for schema-first candidate-review scaffolding before real
data insertion.

Completed:

- Added `src/fungal_model/data/candidate_review.py` with:
  - `DatasetCandidateReview`;
  - `DatasetCandidateReviewLoadError`;
  - `load_dataset_candidate_review`;
  - `validate_dataset_candidate_review`.
- Added public exports from `fungal_model.data`.
- Added `data/experiments/candidate_reviews/README.md` and a
  fake/schema-test-only candidate review fixture.
- Candidate reviews now require:
  - candidate id, name, status, maturity, source, intended use, schema gates,
    review metadata, and notes;
  - literature candidates to include citation, authors, year, and DOI or URL;
  - explicit schema-gate flags for units, uncertainty, preprocessing, and no
    embedded real data.
- Candidate reviews reject observations, measurement series, CSV paths, data
  rows, and other data-insertion fields.
- Documentation now states that candidate reviews are not datasets and must not
  contain extracted values.

Architecture/data debt:

- No architecture or data debt was added.
- No real literature data, real capability records, biological mechanisms, JAX,
  or broad biology implementation were added.

Verification:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py`
- Result: 11 passed.
- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py tests/test_experiment_dataset_loading.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 39 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 372 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- Select one real dataset candidate as a review record only, then validate its
  source/provenance metadata before adding any observations or registry
  capability records.
