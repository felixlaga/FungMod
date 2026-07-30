# FungMod Roadmap: From Curated Virtual Experiments to General Fungus/Substrate Screening

## Purpose

This document defines the next major phases for FungMod after cleanup, API-001, ENV-001, DATA-002, BIO-001, and VALIDATION-001.

The goal is to make FungMod usable for researchers who want to define a fungus or enzyme source, a substrate, and one or more environments, then receive scientifically honest degradation curves and output tables.

The central goal remains:

```text
FungMod exists to let researchers run mechanistic virtual experiments of fungi or enzyme systems degrading substrates across environments, producing clean time-series and summary tables of substrate loss, product release, degradation rates, threshold times, uncertainty, provenance, and limitations.
```

This roadmap is designed to prevent uncontrolled biology expansion.

FungMod should not become a pile of half-ingested datasets or half-implemented mechanisms.

The next phases should build the missing infrastructure needed for reliable biology.

Status note: this roadmap contains phase gates that predate the current
registry-backed BIO-001 and BIO-002 work. Phase 1 reconciliation verified that
the active source of truth is `AGENTS.md`, `README.md`, `progress.md`,
`ARCHITECTURE_DEBT.md`, the Phase 1 validation reports, code, and tests. This
roadmap remains directional and must not override the current biology rule in
`AGENTS.md` or reclassify exploratory BIO work as scientifically validated.
The current PR queue and reconciled scoped phase status are tracked in
`foundation_progress/ROADMAP_ORCHESTRATION_STATUS.md`.

---

# Current project status

As of this roadmap, FungMod has:

```text
- central virtual-experiment project directive;
- registry-backed VirtualExperiment API;
- EnvironmentGrid API;
- standard output tables;
- versioned output schema/data dictionary;
- SABIO-RK Reaction 618 enzyme-only homogeneous Michaelis-Menten pilot;
- DATA-002 multi-entry SABIO-RK Reaction 618 parameter-range curation;
- BIO-001 exploratory cellulose-like surface-degradation pilot;
- provenance/limitations/missing-parameter/suggested-experiment tables;
- tests for Reaction 618, homogeneous MM, environment grids, DATA-002, BIO-001, notebooks, and virtual-experiment outputs.
```

Additional scoped completions verified after the original phase text was
written:

```text
- SOURCE-002 notebook-driven SABIO-RK discovery and registry-proposal workflow
  is complete for offline fixtures, deterministic proposal writing, and
  no-network tests;
- RESOLVE-001 is complete for strict registry-backed exact and
  case-insensitive alias resolution;
- ASSEMBLY-001 is complete for arbitrary reactions using implemented
  homogeneous Michaelis-Menten semantics and for template-backed surface plus
  linear, branching, and cyclic pathway scopes;
- API-003 is complete for existing registry records, aliases, environment
  grids, scientific/exploratory modes, and table access;
- BIO-READINESS-LITE is complete for the template, validator, and tests;
- BIO-002 is complete for linear, branching, and cyclic enzyme-pathway
  assembly and software verification, but partial relative to broad
  provenance-backed pathway biology;
- Phase 2 static balance checks are complete for scoped static metadata,
  validators, assembly-time checks, process-reaction binding, and explicit
  dynamic-constraint binding.
```

No next PR is selected. The user-scoped queue is complete through PR-59 after
the final PRODUCT-001 integration, PR-58 completed the bounded
provenance-backed competitive and Haldane substrate-inhibition laws, PR-57
completed dynamic thermodynamic feasibility and native solver-time
enforcement, and PR-56 completed
branching and cyclic enzyme-pathway assembly after
PR #71 merged as `caa0a17`, PR-55 completed arbitrary
supported-reaction onboarding after PR #70 merged as `6b3d275`, PR-54 completed
caller-trusted Ed25519 curator
authentication after PR #69 merged as `35a3ecb`, PR-53 completed product-map registry destination and
ownership after PR #68 merged as `19baedd`, PR-52 completed its five-family index-backed non-parameter
authoring bridge after PR #67 merged as `5da611b`, PR-51 completed its versioned
nonidentity ParameterRecord conversion registry after PR #66 merged as
`bef938f`, PR-50 completed checksum-loaded
written-source authoring after PR #65 merged as `933d2c8`, PR-49 public
curation-bundle loading merged as PR #64
(`bbe2ee6`), PR-48 identity-only
curator-authored ParameterRecord authoring merged as PR #63 (`764d1e4`),
PR-47 transactional apply merged as PR #62 (`b1ebb860`), PR-46
registry-promotion planning merged as PR #61 (`2b6c639`), PR-45
source-proposal curation review merged as PR #60 (`5ac7864`), and PR-44
researcher source-provider onboarding merged as PR #59,
PR-43 process-bound entropy-production-rate timeseries merged as PR #58 and
PR-42 arbitrary-length linear enzyme-chain assembly merged as PR #57,
the PR-41 Pyright optional-member-access ratchet merged as PR #56, the
PR-40 virtual-experiment conservation diagnostics bridge merged as PR #55,
the PR-39 virtual-experiment solver diagnostics bridge,
the PR-38 solver diagnostics example notebook,
the PR-37 solver diagnostics visibility follow-up,
the PR-36 configured-output solver diagnostics slice,
PR-35 repository hygiene guardrail extension,
the PR-34 configured-output conservation/drift diagnostics slice,
the PR-33 chain-template explicit environment modifier assembly slice,
the PR-32 repository hygiene cleanup slice, the PR-31
registry-backed explicit environment modifier assembly slice, and the
registry-backed
product-inhibition assembly and researcher-facing example, validation
ingestion gate, build-first reframe,
PRODUCT-001 public API/output slices including the PR-08 Markdown report
writer, PR-09 HTML report wrapper, PR-10 report-folder index/navigation,
PR-11 screen-comparison summary ergonomics, PR-12 comparison/report-output
example notebook, and PR-13 THERMO-003 entropy-production-rate notebook
coverage, plus the PR-14 THERMO-003 configured entropy-budget summary and
PR-15 entropy-budget output notebook inspection, and the PR-16
uncertainty-band output ergonomics slice, the PR-17 trajectory-quantile
output ergonomics slice, and the PR-18 trajectory-quantile example and
quicklook ergonomics slice, the PR-19 degradation-rate quicklook/report
ergonomics slice, the PR-20 threshold-time inspection/report ergonomics
slice, and the PR-21 THERMO-003 explicit thermodynamic-summary report
ergonomics slice, the PR-22 PRODUCT-001 provenance/limitations report
ergonomics slice, and the PR-23 PRODUCT-001 provenance/limitations report
example notebook slice, and the PR-24 BIO-003 non-PET product-inhibition
genericity-hardening slice, and the PR-25 THERMO-003 virtual-experiment
thermodynamic diagnostics bridge, the PR-26 THERMO-003
virtual-experiment thermodynamic diagnostics example notebook, the PR-27
explicit configured environmental rate-modifier wiring slice, and the PR-28
configured environment modifier example notebook slice, and the PR-29
explicit oxygen/water-activity configured modifier wiring slice, and the PR-30
configured oxygen/water-activity modifier example notebook slice. The completed
PR-32 cleanup removed tracked generated metadata and added a focused repository
hygiene guardrail after PR #47 without changing scientific, numerical, solver,
notebook output, validation-data, calibration, or biology behavior. The
completed PR-33 slice bridged explicit BIO-002-style chain process-template
modifier records to the existing configured `temperature_arrhenius_reference`,
`ph_gaussian`, `oxygen_monod`, and `water_activity_threshold` response-law
support after PR #48, emitting package-generated environment entities only from
exact registry environment values when an explicit environment id is supplied.
It did not infer parameters, fit curves, add validation data, oxygen
consumption, gas transfer, redox, anaerobic metabolism, substrate water-binding
behavior, EnvironmentGrid behavior changes, hidden notebook science, new
response laws, solver/model response-law changes, or silent fallback constants.
The completed PR-34 slice added configured-output conservation/drift diagnostics
copied from existing `SimulationResult` trajectories and explicit configured
`mass_balance` `conserved_weights` only. It does not add a validation rule,
solver equation, threshold change, thermodynamic enforcement, calibration,
validation data, empirical comparison, or biology claim. The completed PR-35
slice extended repository hygiene guardrails so tracked generated artifacts
already covered by `.gitignore` cannot enter git after PR #50, and generated
`foundation_progress/FUNGMOD_PROGRESS_REPORT_*.html` snapshots are ignored
without hiding the tracked final-goal HTML plan. It does not change code
behavior, solver behavior, notebook output, validation data, calibration,
biology, thermodynamics, or scientific claims. The completed PR-36 slice added
configured-output solver diagnostics derived from existing configured run
metadata, solver settings, solver metadata, time-grid/evaluation counts, state
counts, and process counts only after PR #51. It did not change solver
behavior, infer scientific values, add numerical thresholds, validation data,
calibration, empirical comparison, thermodynamic enforcement, or biology
claims. The completed PR-37 slice exposes those existing configured-output
solver diagnostics artifacts in report/index visibility paths only after
PR #52. It does not change solver behavior, define numerical thresholds, add
validation data, calibration, empirical comparison, thermodynamic enforcement,
hidden notebook science, or biology claims. The completed PR-38 slice added a
public configured-workflow solver diagnostics example notebook that inspects
package-generated `solver_diagnostics.json`/`.csv` artifacts, report/index
links, and the header-only/no-metadata guardrail only after PR #53. It did not
change solver behavior, define numerical thresholds, add validation data,
calibration, empirical comparison, thermodynamic enforcement, hidden notebook
science, configured-output schema changes, or biology claims. The completed
PR-39 slice added `solver_diagnostics.csv` and
`DegradationScreenResult.solver_diagnostics()` as a standard
virtual-experiment bridge over existing per-sample configured-output
`solver_diagnostics.json`/`.csv` artifacts only after PR #54. It did not change
solver behavior, define numerical thresholds, add validation data, calibration,
empirical comparison, thermodynamic enforcement, hidden notebook science,
configured-output schema changes, or biology claims. The completed PR-40 slice
added `conservation_diagnostics.csv` and
`DegradationScreenResult.conservation_diagnostics()` as a standard
virtual-experiment bridge over existing per-sample configured-output
`conservation_diagnostics.json`/`.csv` artifacts only after PR #55. It did not
infer conserved quantities, tolerances, pass/fail thresholds, validation evidence,
chemistry, thermodynamics, calibration, empirical comparison, or biology, and
it did not change configured-output conservation artifact behavior.
The completed PR-41 slice enabled Pyright `reportOptionalMemberAccess`
globally and narrowed the 35 baseline nullable-member errors across 11
scientific modules using explicit contracts or precise annotations only after
PR #56. It did not add guessed values, silent fallbacks, `Any` casts, blanket
suppressions, or scientific, numerical, solver, calibration-result,
validation-data, biology, public-API, or output-schema behavior changes. The
completed PR-42 slice generalized the registry/template-driven extracellular
enzyme-chain assembler from exactly two steps to ordered linear chains with at
least two existing process-law steps. It preserves explicit conservation,
parameter roles, modifiers, provenance, maturity, assumptions, limitations,
standard outputs, fail-fast modelability, the BIO-002 two-step template, and
the researcher API. An artificial three-step framework benchmark proves the
generic path; branching, cycles, disconnected chains, and malformed topology
were explicitly unsupported at the PR #57 linear-only checkpoint. No new rate law, production constant,
empirical record, validation data, calibration, inferred parameter, or hidden
notebook science was added. The completed PR-43 slice adds post-simulation,
process-bound entropy-production-rate JSON/CSV trajectories from native
process-rate trajectories only when explicit sourced condition-specific delta
Gibbs, positive temperature, reaction-extent interpretation, and dimensionally
compatible extent-rate units or conversion metadata are supplied. It fails on
missing processes or dishonest metadata and adds no inferred thermodynamics,
dynamic delta G, or solver-time enforcement after PR #58. The completed PR-44
slice added a top-level SABIO-RK provider UX over existing fetch/freeze,
parsing, and review-only proposal behavior. Friendly scientific selectors
replace raw query syntax for common use with official quoting/escaping and
strict numeric SABIO IDs. Live refresh stays explicit on the shared
fetch/freeze path and writes immutable query-specific bundles with checksummed
raw pages plus a separate derived combined export; SABIO-RK does not require a
credential, and no proposal enters simulation or the production registry
automatically after PR #59. The completed PR-45 slice validates in-memory or
written source proposals, classifies exact schema blockers, and writes explicit
curator decision bundles while leaving absent decisions deferred. It does not
mutate the production registry or claim scientific validation after PR #60.
The completed PR-46 `plan_registry_promotion(...)` slice checksum-verifies written
curation bundles, revalidates that explicit accepts have no curation blockers
and carry complete source provenance, and resolves index-declared destinations.
It validates candidates and combined prospective content through existing
registry loaders, requires scalar-type-exact loader round-trip fidelity for
would-be adds so dropped, synthesized/defaulted, or type-converted fields are
blocked, and preserves raw stored-content semantics for exact duplicates. It
emits deterministic classifications, exact YAML, hashes, and digests; owned
review output cannot overlap a registry root in either direction and is refused
if the plan payload no longer matches its construction digest. It
has no mutation, overwrite, apply operation, version policy, simulation
promotion, or validation claim. It completed after PR #61 merged as `2b6c639`.
The completed PR-47 `apply_registry_promotion(...)` slice intentionally advances
plan schema to `2.0.0`, places durable curator/source audit metadata in exact
prospective YAML, rejects preview-only `1.0.0` bundles at apply, and requires an
exact confirmation digest plus exact next numeric patch version. It re-resolves
current index destinations, rechecks full-root drift, stages and validates a
complete same-filesystem registry copy, locks cooperating writers, and commits
with interruption-safe digest-reconciled rollback and truthful cleanup state.
Plan applicability is candidate-derived, and overlapping target/curator source
identities must agree exactly. It does not alter scientific fields or package
version, authorize simulation, or claim scientific validation. The bounded
apply contract completed after PR #62 merged as `b1ebb860`.
The completed PR-48 `author_parameter_record(...)` slice is limited to accepted
in-memory PARAMETER curation results and complete curator-authored production
mappings with exact identity conversion, source digest/provenance,
loader-round-trip, ordered frozen-URL, full-registry-context, exact role/
compatibility, closed summary/result/full-report envelope, structural non-downgrade,
and mutation checks. Immutable frozen metadata page/request/URL/raw-page
cardinality and unique exact page-path identity are reconciled offline. Its
specialized checksummed curation output is promotion-plan-compatible but does
not mutate or apply; its public checksums establish internal consistency rather
than cryptographic authorship. One shared admission predicate blocks its exact
storage-only policy and intrinsic bridge evidence in every mode, and applies
closed exact per-mode `allowed_use` permissions before ranking. One shared exact
template-role resolver aligns preflight, public/runtime simulation,
deterministic/direct assembly, and result reconstruction; kinetic role owners
derive from component process templates. Exact ordered outer-compatibility
bindings plus intrinsic component-only scope, structural state/entity IDs, and
registry capabilities independently resolve each component slot through one
load/query-validated registry authority graph; role/record selectors are
assertions only. The configured outer substrate entity ID must be the exact
registry-backed `state_species` identity consumed by the outer process, and
each process must bind its roles and parameter-backed states to that slot
through exact semantic compatibility keys. Implemented direct process types
also impose canonical required fields and reject truncation, semantic renaming,
or role reuse before modelability. Curator-authored outer provenance is limited
to the closed identity-only bridge schema; unsupported validation, calibration,
readiness, or authorization claim metadata is rejected.
Initial-state roles declare record scope without claiming kinetic ownership.
The completed PR-49 slice adds public `load_curation_bundle(...)` and
`LoadedCurationBundle`, centralizes owned manifest/schema, exact inventory,
SHA-256, path/symlink containment, structured parsing, shared artifact,
summary, and deterministic report validation, and routes written promotion
planning through that path. Checksums remain internal-consistency evidence,
not curator authentication, and the loader performs no registry mutation,
scientific transformation, validation claim, or simulation authorization.
The completed PR-50 slice lets `author_parameter_record(...)` consume a
`LoadedCurationBundle`, reloading its owned manifest at call time before
applying every existing identity-only, frozen-source, storage-only,
registry-context, loader-fidelity, and no-mutation guardrail. Raw paths remain
unsupported. The completed PR-51 slice adds a public immutable versioned
conversion registry and one named Pint method with explicit parseable distinct
units, dimensional compatibility, deterministic recomputation, and
12-decimal-place half-even rounding. The completed PR-52 slice adds
`author_registry_records(...)` for complete `fungi`, `substrates`,
`enzyme_classes`, `process_compatibility`, and `case_templates` targets with
accepted-source identity, reserved audit/digest evidence, exact
production-loader fidelity, deterministic in-memory/written validation, and no
authoring/planning mutation. PR-53 adds the index-owned product-map
destination, strict production record/loader contract, exact runtime-map
conversion, and curator-authored promotion/apply without translating
participants or inferring stoichiometry. PR-54 adds exact-manifest Ed25519
signing, caller-supplied trusted key/curator bindings, decision-curator
matching, closed sibling sidecars, and boundary revalidation for authenticated
authoring/planning inputs. SHA-256 remains consistency evidence only, and
authentication does not claim scientific validation or simulation
authorization. CURATION-001 is complete for this defined curation workflow.
PR-55 removes Reaction 618/SABIO-RK/cellobiose/beta-glucosidase tokens and
fallback identities from generic homogeneous assembly, makes per-reaction
identity/mode/provenance/template data explicit, and proves a materially
different artificial reaction through the same implemented law. The
PR-56 slice adds explicit registry-owned `linear`, `branching`, and `cyclic`
graph types, directed process/product-map state-role edges, connectivity and
substrate-reachability checks, exact declared branch/cycle semantics, and
conserved artificial branch/cycle execution through the standard solver. The
completed PR-57 slice adds optional dynamic thermodynamic constraints over
explicitly bound molar states: sourced standard Gibbs or redox-derived energy,
temperature, gas/Faraday constants, standard concentration, activity floor,
tolerance, and provenance references; a passing bound electron/redox check;
trajectory-derived ideal-dilute activities/Q and dynamic Gibbs energy; and
native solver-time blocking of unfavorable nonnegative forward rates. It does
not infer chemistry, supply silent constants, implement reverse fluxes or
nonideal activities, or claim empirical validation. The completed PR-58 slice
adds competitive and Haldane substrate-inhibition modifiers for exactly
matched homogeneous Michaelis-Menten processes. Both require explicit
primary-source and maturity metadata, exact substrate and `K_m` binding,
positive unit-compatible `K_i`, visible assumptions and limitations, and
artificial framework benchmarks. The citations support the selected laws in
their study systems; they do not supply production FungMod parameters, case
applicability, or validation. The completed PR-59 slice raises the standard
output schema to `1.8.0`, preserves explicit per-process rate identity, copies
persisted derived trajectories with thermodynamic roles, and exposes existing
dynamic thermodynamic binding/count/extrema evidence in standard diagnostics
and reports. It does not change simulation or scientific behavior. No next PR
is selected; the user-scoped queue is complete through PR-59.

PUBLIC-RELEASE-001 is complete in the current checkout as an explicitly
user-directed release/readiness slice outside that numbered queue. It adds an
installable `fungmod` distribution, immutable packaged registry/example
assets, two full public-API notebooks, strict Read the Docs content, and
release/package verification. Its advanced thermodynamic and inhibition
examples use existing implemented behavior and explicit artificial
framework-benchmark inputs only. It does not add biological records,
mechanisms, empirical observations, calibration, or validation claims.

The completed PR-24 BIO-003 slice added a
toy, framework-benchmark configured non-PET product-inhibition path with an
explicit artificial product-state `K_i`, proving the modifier runs outside the
researcher-facing BIO-002 example without adding validation data, calibration,
empirical comparison, solver-law changes, silent fallback constants, or new
biology claims. The completed PR-25 THERMO-003 slice added
`thermodynamic_diagnostics.csv` and
`DegradationScreenResult.thermodynamic_diagnostics()` as a standard
virtual-experiment bridge over existing per-sample configured-output
`thermodynamic_summary.json`/`.csv` artifacts only, with header-only output
when no artifacts exist and without inferred activities, reaction quotients,
concentrations, redox potentials, electron balances, validation evidence, or
solver-time thermodynamic enforcement. The completed PR-26 THERMO-003 slice
adds a public-API example notebook that inspects that standard table/accessor
path, including the header-only no-artifact case and a carefully labelled
package-generated artifact-copy demonstration, without inferred
thermodynamics, validation data, empirical comparison, hidden notebook science,
or solver-time thermodynamic enforcement. The completed PR-27 slice wires
existing `TemperatureModifier` and `PHModifier` response laws into configured
generic process modifier construction as explicit
`temperature_arrhenius_reference` and `ph_gaussian` modifiers with explicit
parameters and environment values, without validation data, calibration,
empirical comparison, fitted pH/temperature curves, organism-specific
physiology, inferred environment response, hidden notebook science,
solver-time thermodynamic enforcement, or silent fallback constants. The PR-28
slice added a public configured-workflow example notebook that
demonstrates those explicit modifiers through package APIs and configured
workflow outputs, without validation data, calibration, empirical comparison,
fitted pH/temperature curves, organism-specific physiology, inferred
environment response, EnvironmentGrid behavior changes, hidden notebook
science, oxygen/redox behavior, thermodynamic enforcement, or silent fallback
constants. The completed PR-29 slice wired existing `OxygenModifier` and
`WaterActivityModifier` response laws into configured generic process modifier
construction as explicit `oxygen_monod` and `water_activity_threshold`
modifiers with explicit parameters, oxygen units, and environment values after
PR #44 merged, without validation data, calibration, empirical comparison,
fitted oxygen or water-activity response curves, organism-specific physiology,
inferred environment response, oxygen consumption state, gas transfer, redox
balance, anaerobic metabolism, substrate water-binding model, EnvironmentGrid
behavior change, hidden notebook science, thermodynamic enforcement, or silent
fallback constants. The completed PR-30 slice added public configured-workflow
example notebook coverage for those explicit oxygen and water-activity
modifiers through package APIs and configured outputs, using artificial
framework-benchmark config values only, without validation data, calibration,
empirical comparison, fitted oxygen or water-activity response curves,
organism-specific physiology, inferred environment response, oxygen
consumption state, gas transfer, redox balance, anaerobic metabolism,
substrate water-binding model, EnvironmentGrid behavior change, hidden
notebook science, thermodynamic enforcement, solver/model behavior changes, or
silent fallback constants. The completed PR-31 slice bridged explicit
one-process registry case-template modifier records to the existing configured
`temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
`water_activity_threshold` response-law support, emitting package-generated
environment entities only from exact registry environment values when required
and failing before execution for missing fields, unresolved roles, missing or
non-exact environment conditions, or unsupported modifier types. It did not
infer parameters, fit curves, add validation data, oxygen consumption, gas
transfer, redox, anaerobic metabolism, substrate water-binding behavior,
EnvironmentGrid behavior changes, hidden notebook science, or silent fallback
constants.
The completed PR-33 slice extends the explicit registry-template environment
modifier bridge to BIO-002-style chain process-template modifier entries, using
the same existing configured response laws and exact registry environment
values only. It failed before execution for missing role fields, unresolved
roles, missing environment context, missing environment conditions, non-exact
environment values, missing oxygen units, or unsupported modifier types, and it
does not add validation data, fitted curves, inferred environment responses,
new response laws, oxygen consumption, gas transfer, redox, anaerobic
metabolism, substrate water-binding behavior, EnvironmentGrid behavior changes,
hidden notebook science, solver/model response-law changes, or silent fallback
constants.
The completed PR-34 slice is limited to configured-output conservation/drift
diagnostics over existing state trajectories and explicit configured
`mass_balance` `conserved_weights`. The completed PR-35 slice is limited to
repository hygiene guardrails for generated artifacts. The completed PR-36
slice is limited to configured-output solver diagnostics copied from existing
configured workflow metadata and solver metadata only. The completed PR-37
slice is limited to Markdown, HTML, and report-folder index visibility for
those existing configured-output solver diagnostics artifacts only. The
completed PR-38 slice is limited to a package-output-driven solver diagnostics
example notebook over those artifacts, report/index visibility, and the
explicit header-only/no-metadata guardrail. The completed PR-39 slice is limited
to a standard virtual-experiment `solver_diagnostics.csv` table/accessor bridge
over those existing per-sample configured artifacts after PR #54. The completed
PR-40 slice is limited to a standard virtual-experiment
`conservation_diagnostics.csv` table/accessor bridge over existing per-sample
configured conservation artifacts, with report/index visibility and header-only
output when artifacts are absent after PR #55. The completed PR-41 slice is
limited to the global Pyright optional-member-access ratchet and explicit
nullable-state narrowing that resolved FD-005 after PR #56 without runtime
behavior changes. The completed PR-42 slice is limited to arbitrary-length
ordered linear chain topology over existing process laws; branching and cycles
remain unsupported after PR #57. The completed PR-43 slice is limited to
configured-output process-bound entropy-production-rate trajectories derived
after simulation from existing native process-rate trajectories plus explicit
sourced and dimensionally compatible metadata; it does not alter solver or
process behavior after PR #58. The completed PR-44 slice is limited to public
source-provider onboarding for existing SABIO-RK behavior after PR #59. The
completed PR-45 slice is limited to review-only curation decisions over those
proposals after PR #60; it adds no automatic trust, registry promotion,
simulation-time fetch, scientific record, biology, solver behavior,
thermodynamic behavior, or validation evidence. The completed PR-46 slice is
limited to an immutable registry-promotion preview over explicit accepts after
PR #61. The completed PR-47 slice adds only digest-confirmed,
strict-next-patch, no-overwrite transactional application of exact schema
`2.0.0` prospective bytes after PR #62. The completed PR-48 slice adds only an
identity-only PARAMETER source-to-production authoring result for explicit
accepted source evidence and explicit complete production fields. The
completed PR-49 slice centralizes public written curation-bundle integrity and
reconstruction without accepting direct specialized written authoring input.
None adds
automatic simulation eligibility, scientific-field inference, biology, solver,
calibration, thermodynamic behavior, validation data, or validation evidence.
THERMO-003 remains partial after
explicit reaction-quotient Gibbs checks, configured entropy-production-rate
metadata diagnostics, configured JSON/CSV summaries, and configured-output
diagnostics notebook coverage for explicit-Q and entropy-rate rows, plus the
bounded PR-43 process-bound entropy-production-rate timeseries. The
completed PR-14 slice added only a JSON summary budget over existing explicit
entropy-rate metadata rows; it did not infer thermodynamics or change solver
behavior. The completed PR-15 slice should make that budget inspectable in the
diagnostics notebook path without adding equations, validation data, inferred
thermodynamics, or solver-time enforcement. The completed PR-16 slice should
surface existing explicit uncertainty/range information in standard outputs and
reports without adding validation data, calibration, empirical comparison,
posterior uncertainty claims, inferred environment responses, or silent
fallback constants. The completed PR-17 slice adds
`trajectory_quantiles.csv`, `DegradationScreenResult.trajectory_quantiles()`,
schema/data-dictionary coverage, and report/index visibility over existing
`time_series_long.csv` rows only. The completed PR-18 slice adds a public-API
trajectory-quantile notebook and a presentation-only
`trajectory_quantile_bands.png` quicklook generated from
`trajectory_quantiles.csv`; it does not add validation, calibration, empirical
comparison, posterior uncertainty, inferred environment response, or
solver/model behavior. The completed PR-19 slice adds a presentation-only
`degradation_rate_vs_time.png` quicklook and report visibility over existing
`time_series_long.csv` `degradation_rate` rows only; it does not add
validation, calibration, empirical comparison, inferred environment response, a
new rate law, posterior uncertainty, solver/model behavior, CSV row-contract
changes, or silent fallback constants. The completed PR-20 PRODUCT-001 slice
improves threshold-time inspection/report ergonomics from existing
`threshold_times.csv` and `summary_metrics.csv` rows without hidden notebook
science, validation data, calibration, empirical comparison, inferred
environment responses, posterior uncertainty claims, solver/model changes,
schema changes, or silent fallback constants. The completed PR-21 THERMO-003
slice adds Markdown, HTML, and index visibility for existing configured-output
`thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts without
inferring activities, reaction quotients, concentrations, redox potentials,
electron balances, validation evidence, or solver-time thermodynamic
enforcement. The completed PR-25 THERMO-003 slice bridges those existing
per-sample configured artifacts into standard virtual-experiment outputs only;
it must not compute or infer new thermodynamic quantities. The completed PR-26
notebook slice makes that bridge inspectable through public APIs without
changing scientific or numerical behavior. The completed PR-22
PRODUCT-001 slice improves provenance,
limitation, missing-parameter, and suggested-experiment report ergonomics from
existing standard output tables only, including a Markdown decision summary and
additive HTML/index links over existing decision-support tables. The completed
PR-23 PRODUCT-001 slice makes that report decision summary inspectable in a
public-API example notebook without adding validation data, calibration,
empirical comparison, inferred environment responses, hidden notebook science,
schema changes, or solver/model behavior. Do not rebuild the completed scoped
slices above unless code or tests contradict this status.

VALIDATION-DATA-001 remains deferred and evidence-gated. A validation
ingestion PR may start only if a source-backed numeric time-course dataset
satisfies the active evidence requirements in
`foundation_progress/VALIDATION_DATA_001_FIRST_TIMECOURSE.md`; because the
current candidate reviews do not satisfy that gate, PR-28 is complete as
build-first configured environment-modifier example-notebook work, PR-29 is
complete as build-first configured oxygen/water-activity modifier wiring after
PR #44, PR-30 is complete as build-first configured oxygen/water-activity
example-notebook coverage after PR #45, PR-31 completed after PR #46 as
build-first registry-backed explicit environment modifier assembly, PR-32
completed after PR #47 as repository hygiene cleanup, PR-33 completed after
PR #48 as chain-template explicit environment modifier assembly, and PR-34
completed after PR #49 as configured-output conservation/drift diagnostics.
PR-35 completed after PR #50 as a focused repository hygiene guardrail
extension, and PR-36 completed after PR #51 as configured-output solver
diagnostics. PR-37 completed after PR #52 as a diagnostics visibility follow-up.
PR-38 completed after PR #53 as a solver diagnostics example notebook. PR-39
completed after PR #54 as a virtual-experiment solver diagnostics bridge. PR-40
completed after PR #55 as a virtual-experiment conservation diagnostics bridge.
PR-41 completed after PR #56 as a Pyright optional-member-access ratchet. The
PR-42 arbitrary-length linear enzyme-chain assembly slice completed after PR
#57; branching and cycles were unsupported at that checkpoint. PR-43 process-bound
entropy-production-rate configured diagnostics completed after PR #58. PR-44
review-gated SABIO-RK researcher source onboarding completed after PR #59.
PR-45 source-proposal review/decision bundles completed after PR #60, PR-46
registry-promotion planning completed after PR #61 merged as `2b6c639`, and
PR-47 transactional apply completed after PR #62 merged as `b1ebb860`, PR-48
identity-only PARAMETER authoring completed after PR #63 merged as `764d1e4`,
PR-49 reusable public curation-bundle loading completed after PR #64 merged as
`bbe2ee6`, PR-50 checksum-loaded written-source authoring completed after PR
#65 merged as `933d2c8`, PR-51 registered nonidentity conversion completed
after PR #66 merged as `bef938f`, PR-52 index-backed non-parameter authoring
completed after PR #67 merged as `5da611b`, and PR-53 product-map registry ownership
completed after PR #68 merged as `19baedd`. PR-54 authenticated curator signatures are
complete after PR #69 merged as `35a3ecb`. PR-55 arbitrary supported-reaction
onboarding and assembly is complete after PR #70 merged as `6b3d275`. PR-56 branching
and cyclic enzyme-pathway assembly is complete in the current checkout. The
selected PR-57 slice adds dynamic thermodynamic feasibility and solver
enforcement rather than validation ingestion, digitization, fabricated
validation data, calibration, empirical comparison, inferred biology, or
automatic simulation authorization.

Validation remains important, but it is now deliberately deferred behind core
simulator capability. Real time-course observations are needed before FungMod
makes validation, calibration, or empirical comparison claims. They are not
required before improving the virtual-experiment engine that generates
exploratory degradation curves from implemented mechanisms, explicit
assumptions, uncertainty ranges, provenance, and limitations.

The current API can run registered cases from internal registry IDs.

Example:

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
)

result = study.simulate(mode="exploratory", n_samples=128)
result.write_tables()
```

This is good, but it is still developer-facing.

The final researcher goal is closer to:

```python
study = FungMod.virtual_experiment(
    fungi=["Pleurotus ostreatus"],
    substrates=["cellulose film"],
    environments=FungMod.environment_grid(
        temperature_C=[20, 25, 30],
        ph=[4.5, 5.0, 5.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(mode="exploratory", n_samples=1000)
result.write_tables("outputs/")
```

The next phases bridge that gap.

---

# What rule governs biology work now?

## Short answer

Biology may be added only when the mechanism is explicitly implemented,
provenance-backed, maturity-labelled, covered by tests, and honest about
assumptions and limitations. Unsupported, invented, silently guessed, or falsely
validated biology is forbidden.

The roadmap phase gates below are directional. Current BIO-001 and BIO-002
work is implemented and technically verified for its scoped exploratory
registry-backed pilots, but it is not publication-grade validation and does not
unlock arbitrary unsupported fungus/substrate biology.

## Why not immediately?

The current codebase can simulate registered cases, but arbitrary researcher-defined fungus/substrate cases still need:

```text
- human-name and alias resolution;
- SABIO-RK-backed reaction/product discovery;
- local source snapshots;
- curated record generation;
- product-map generation;
- state-role mapping;
- config-driven case assembly;
- public scientific-mode simulation;
- environment-response distinction;
- no-new-biology readiness gates.
```

Adding unsupported biology before this risks creating hardcoded one-off cases.

## When biology can proceed

Biology can proceed only when the specific proposal satisfies the current
biology rule and the applicable readiness gate:

```text
A researcher can choose a known fungus/source ID or alias,
choose a known substrate ID or alias,
choose environments or an EnvironmentGrid,
and FungMod can:

1. resolve the names;
2. discover or use known reaction/product/kinetic records;
3. assemble the correct process model from registry/config schemas;
4. run scientific or exploratory simulation;
5. output degradation curves and tables;
6. state missing mechanisms or parameters honestly.
```

Only then should the proposed biology be added or extended.

---

# Phase 1: SOURCE-001 — SABIO-RK Reaction/Product Discovery Adapter

## Goal

Build a controlled SABIO-RK source adapter that can fetch, freeze, parse, and propose FungMod records from SABIO-RK kinetic-law entries.

This phase does not replace the local FungMod registry.

SABIO-RK is an external source.

FungMod still needs a local curated cache/registry for reproducibility, simulation semantics, provenance, and review.

Correct architecture:

```text
SABIO-RK API
-> raw frozen snapshot
-> parser/normalizer
-> curated kinetic/reaction records
-> proposed FungMod registry/product-map records
-> human/review gate
-> simulation registry
```

Incorrect architecture:

```text
VirtualExperiment.simulate()
-> live SABIO-RK API call
-> build model directly from raw API response
```

Live APIs must not be runtime dependencies for simulation.

## Why SOURCE-001 matters

The user wants SABIO-RK to fetch products, reactions, enzymes, and parameters so FungMod does not need a giant manually maintained database.

That is partly correct.

SABIO-RK can supply:

```text
- reaction equation;
- substrates;
- products;
- enzyme names;
- EC numbers;
- organism/source metadata;
- kinetic-law type;
- Km, kcat, Vmax, concentrations, pH, temperature, buffer;
- publication metadata;
- external reaction/compound identifiers when available.
```

But SABIO-RK does not supply everything FungMod needs:

```text
- whole-fungus growth model;
- enzyme secretion model;
- product uptake;
- biomass yield;
- substrate geometry/accessibility;
- state-role semantics;
- simulation time grids;
- allowed-use policy;
- environment-response model;
- output schema interpretation.
```

Therefore SABIO-RK should feed FungMod, not replace FungMod.

## Required SOURCE-001 API

Add a source adapter API, likely under:

```text
src/fungal_model/sources/sabiork/
```

or:

```text
src/fungal_model/data/sabiork_source.py
```

Suggested developer API:

```python
from fungal_model.sources.sabiork import SabioRKSource

source = SabioRKSource(cache_dir="data/source_snapshots/sabiork")

snapshot = source.fetch_kinlaw_entries(
    query='SabioReactionID:618',
    refresh=False,
)

reaction_records = source.parse_reaction_records(snapshot)
proposal = source.propose_fungmod_records(reaction_records)
proposal.write("data/proposed_records/sabiork/reaction_618/")
```

There should also be a CLI/script:

```bash
python scripts/fetch_sabiork_kinlaw_entries.py \
  --query "SabioReactionID:618" \
  --output-dir data/source_snapshots/sabiork/reaction_618
```

The existing fetch script is a good start. SOURCE-001 should integrate it into the source-adapter story, not bypass it.

## Required SOURCE-001 outputs

For a SABIO-RK reaction or query, write:

```text
raw/
    kinlaw_entries_<query>.json
    fetch_metadata.json

curated/
    reaction_records.json
    compound_roles.csv
    kinetic_law_entries.csv
    parameters.csv
    publications.csv
    proposed_product_maps.yml
    proposed_parameter_records.yml
    proposed_process_compatibility.yml
    source_adapter_report.md
```

These are proposed/curated source files, not automatically trusted scientific registry records.

## Required SOURCE-001 behavior

SOURCE-001 must:

```text
1. Use local snapshots by default.
2. Fetch live SABIO-RK data only when explicitly requested.
3. Never call the live API during simulation.
4. Never call the live API during tests.
5. Preserve raw API responses.
6. Preserve original units and values.
7. Preserve EntryID and source metadata.
8. Extract reaction participants and roles.
9. Extract products and stoichiometry when available.
10. Extract kinetic laws and parameters.
11. Extract pH, temperature, buffer, organism, enzyme, EC number, publication metadata.
12. Create proposed FungMod records, not silently committed records.
13. Produce inclusion/exclusion reports.
14. Fail clearly if API is unavailable.
```

## Required SOURCE-001 tests

Add tests such as:

```text
tests/test_sabiork_source_adapter.py
```

Required tests:

```text
- parses a local fixture without network access;
- extracts substrates and products from Reaction 618;
- extracts EC number and enzyme name;
- extracts Km and kcat where present;
- preserves pH and temperature;
- writes proposed product-map records;
- writes proposed parameter records;
- does not mutate the simulation registry;
- network refresh is not used in tests;
- invalid/missing fields are reported, not guessed.
```

## SOURCE-001 acceptance criteria

SOURCE-001 is complete when:

```text
- SABIO-RK entries can be fetched/frozen or loaded from cache;
- reaction products and substrates can be extracted into proposed product maps;
- kinetic parameters can be extracted into proposed parameter records;
- provenance is preserved;
- tests do not require live API;
- no simulation depends on live SABIO-RK;
- proposed records are reviewable before entering the registry.
```

---

# Phase 2: RESOLVE-001 — Human-Readable Name and Alias Resolver

## Goal

Allow researchers to define virtual experiments using human-readable names instead of internal registry IDs.

Current API requires:

```python
fungi=["sabiork_beta_glucosidase_source"]
substrates=["cellobiose"]
environments=["sabiork_reaction_618_selected_conditions"]
```

Future API should allow:

```python
fungi=["beta-glucosidase source"]
substrates=["cellobiose"]
environments=["30C_pH5_aerobic"]
```

and eventually:

```python
fungi=["Pleurotus ostreatus"]
substrates=["cellulose film"]
```

## Required resolver concepts

Add a resolver layer that can resolve:

```text
fungus/source names
substrate names
enzyme class names
environment names
reaction names/equations
EC numbers
external database IDs
aliases
```

Suggested module:

```text
src/fungal_model/api/resolver.py
```

or:

```text
src/fungal_model/registry/resolver.py
```

Suggested API:

```python
resolver = RegistryResolver(registry)

resolver.resolve_fungus("sabiork_beta_glucosidase_source")
resolver.resolve_fungus("beta-glucosidase source")
resolver.resolve_substrate("cellobiose")
resolver.resolve_environment("30C_pH5_aerobic")
resolver.resolve_enzyme_class("EC 3.2.1.21")
```

## Required registry additions

Registry records should support:

```text
canonical_id
display_name
scientific_name
aliases
external_refs
taxon_id, if applicable
ec_number, if applicable
database_ids
```

Do not implement fuzzy matching first.

Start with exact canonical IDs and aliases.

Then add case-insensitive exact matching.

Only later add fuzzy matching with ambiguity reports.

## Required resolver behavior

If one match exists:

```text
return resolved ID + record + confidence
```

If multiple matches exist:

```text
raise AmbiguousResolutionError with candidate list
```

If no match exists:

```text
raise ResolutionError with suggestions:
- available close aliases if safe;
- source adapter suggestions;
- "not in registry" message.
```

Never silently choose among multiple biological records.

## Required RESOLVE-001 tests

Add tests:

```text
tests/test_registry_resolver.py
```

Required:

```text
- resolve exact ID;
- resolve alias;
- resolve case-insensitive alias;
- fail on unknown name;
- fail on ambiguous alias;
- resolve substrate;
- resolve environment;
- resolve enzyme class or EC number if registry supports it;
- VirtualExperiment.from_registry can optionally use resolver.
```

## RESOLVE-001 acceptance criteria

RESOLVE-001 is complete when:

```text
- researcher-facing code no longer requires memorized internal IDs for common cases;
- ambiguous biological names fail explicitly;
- aliases are registry data, not hardcoded Python dictionaries;
- resolver is tested;
- VirtualExperiment can use resolver without weakening exact ID behavior.
```

---

# Phase 3: ASSEMBLY-001 — Config-Driven Case Assembly

## Goal

Move case-specific model assembly information out of Python branches and into registry/config schemas.

Historical risk before PR-55:

```text
case_builder.py hardcodes Reaction 618 and BIO-001 state names, product-map names, and time-grid defaults.
```

PR-55 removes the Reaction 618/SABIO-RK/cellobiose/beta-glucosidase tokens
from the generic builder. Existing BIO-001-specific surface metadata remains
within its declared exploratory template-backed scope; it is not used to
onboard arbitrary homogeneous reactions.

For arbitrary reactions and substrates, state roles, products, stoichiometry, and time grids must be data-driven.

## Required assembly schemas

Add or formalize a case-assembly schema.

Possible file:

```text
data_registry/case_templates/case_templates.yml
```

or add fields to process compatibility records.

Minimum required fields:

```yaml
case_template_id: homogeneous_mm_cellobiose_to_glucose
process_type: homogeneous_michaelis_menten

state_roles:
  substrate: cellobiose_concentration
  product: beta_D_glucose_concentration
  enzyme: beta_glucosidase_concentration

product_map:
  substrate_state: cellobiose_concentration
  product_state: beta_D_glucose_concentration
  stoichiometric_yield: 2.0

time_grid:
  start: 0
  stop: 48
  points: 200
  units: hour

observables:
  substrate_remaining:
    state: cellobiose_concentration
    units: mM
  product_release:
    state: beta_D_glucose_concentration
    units: mM
```

For surface cases:

```yaml
case_template_id: surface_cellulose_degradation
process_type: surface_catalysis

state_roles:
  substrate: solid_substrate_remaining
  product: soluble_product_amount
  accessibility_proxy: accessible_site_fraction_proxy

time_grid:
  start: 0
  stop: 168
  points: 300
  units: hour
```

## What ASSEMBLY-001 must remove

It should remove or reduce:

```text
hardcoded Reaction 618 state names
hardcoded BIO-001 state names
hardcoded product-state naming
hardcoded time-grid defaults
hardcoded product-map identity in generic builders
```

Some default fallback can exist, but production cases should be template-driven.

## Required ASSEMBLY-001 behavior

Given:

```text
fungus/source record
substrate record
environment record
process compatibility record
case template
parameter records
```

FungMod should assemble:

```text
ModelConfig
state variables
initial conditions
process parameters
product maps
time grid
output state roles
```

without adding a new Python branch for every reaction.

## Required ASSEMBLY-001 tests

Add tests:

```text
tests/test_registry_case_templates.py
tests/test_config_driven_case_assembly.py
```

Required:

```text
- Reaction 618 assembles from a template;
- BIO-001 assembles from a template;
- missing template fails clearly;
- invalid state role fails validation;
- invalid product map fails validation;
- time grid is read from template/config;
- no hardcoded Reaction 618 branch is needed for standard assembly;
- outputs are unchanged for existing cases except expected metadata improvements.
```

## ASSEMBLY-001 acceptance criteria

Complete when:

```text
- adding a new SABIO-RK reaction does not require editing case_builder.py for state names;
- product maps and state roles are registry/config records;
- Reaction 618 and BIO-001 still pass tests;
- output tables still use biological state roles correctly.
```

Scoped completion after PR-55: a materially different artificial homogeneous
reaction supplies config/process/parameter-set/product-map identities, states,
initial values, time grid, request mode, provenance, entity metadata,
parameters, and outputs through registry/template data, then assembles and
simulates without a new Python branch. Missing identity/provenance and
request/template mode mismatch fail closed. This completes arbitrary reaction
onboarding only for already implemented process-law semantics; unsupported
rate laws remain explicit blockers and require separate provenance-backed,
maturity-labelled implementations.

Scoped completion after PR-56: enzyme-pathway templates explicitly declare
`linear`, `branching`, or `cyclic` topology. One distinct process-owned
stoichiometric map supplies directed state-role edges from one implemented
rate-law input to one or more explicit products. Assembly verifies graph
connectivity, substrate reachability, distinct runtime topology states,
process/map role agreement, the declared branch/cycle shape, conservation,
parameters, and supported process laws before execution. Artificial conserved
branching and cyclic fixtures assemble and run through the standard configured
solver; they add no production biology, parameter evidence, rate law, or
validation claim.

---

# Phase 4: API-003 — Researcher-Facing Virtual Experiment From Names

## Goal

Create the first real researcher-facing API that combines resolver, environment grids, registry-backed simulation, and output tables.

Target:

```python
from fungal_model import virtual_experiment, EnvironmentGrid

study = virtual_experiment(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose"],
    environments=EnvironmentGrid(
        temperature_C=[20, 25, 30],
        ph=[4.5, 5.0, 5.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(mode="exploratory", n_samples=1000)
result.write_tables("outputs/study")
```

Or:

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_names(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose"],
    environments=["30C_pH5_aerobic"],
)
```

## Required API-003 features

```text
1. top-level convenience function or classmethod;
2. resolver integration;
3. exact error messages for unknown names;
4. ambiguity errors with candidate IDs;
5. support for EnvironmentGrid;
6. table-first outputs;
7. no live API calls during simulation;
8. optional source-discovery suggestions when records are missing;
9. public scientific and exploratory simulation modes;
10. output folder manifest.
```

## Required API-003 methods

`VirtualExperiment` or result object should expose:

```python
study.preflight(mode="scientific")
study.preflight(mode="exploratory")
study.simulate(mode="scientific")
study.simulate(mode="exploratory", n_samples=1000)

result.time_series()
result.final_metrics()
result.threshold_times()
result.sampled_parameters()
result.provenance()
result.limitations()
result.write_tables()
result.write_quicklook_plots()
```

These may read from CSVs internally.

The point is that researchers should not have to manually inspect the output folder for common queries.

## API-003 scientific mode

Public scientific mode is required.

Behavior:

```text
mode="scientific":
    exact/literature-supported values only;
    reject exploratory priors;
    reject broad ranges unless allowed for scientific use;
    run deterministic or exact-record ensemble if appropriate;
    output same table schema.

mode="exploratory":
    allow explicitly marked exploratory priors and allowed literature ranges;
    output uncertainty summaries and provenance.
```

Scientific mode must not imply validation.

Use wording like:

```text
scientific_exact_but_unvalidated
```

where appropriate.

## API-003 acceptance criteria

Complete when:

```text
- user can define a virtual experiment from aliases/names for existing records;
- user can run scientific mode when exact case is modelable;
- user can run exploratory mode with uncertainty;
- result object exposes biological tables;
- unknown/ambiguous names fail clearly;
- no live source API calls occur during simulation;
- output tables remain schema-versioned.
```

---

# Phase 5: ENV-002 — Condition-Specific Parameter Matching and Environment Response Guardrails

## Goal

Make environment screens scientifically meaningful.

ENV-001 created environment grids but treated them as metadata-only unless response laws exist.

ENV-002 should add condition-specific parameter matching.

This is safer than immediately fitting pH/temperature response curves.

## Required ENV-002 behavior

For each environment case:

```text
temperature_C
ph
oxygen
```

FungMod should attempt to select parameter records that match the environment.

Example:

```text
If a parameter record has pH=5.0 and temperature=30C,
use it for environment temp_30C_ph_5p0_aerobic.

If no matching record exists,
either:
    - use environment-independent parameter only if allowed;
    - mark environment_effect_status=metadata_only;
    - or block simulation as missing condition-specific parameters.
```

## Environment matching policies

Add explicit policies:

```text
exact_condition_match
nearest_condition_match
range_condition_match
environment_independent
metadata_only
active_response_model
```

Do not silently use nearest-condition matching in scientific mode.

Exploratory mode may allow nearest/range matching if explicitly marked.

## Required output additions

Include in tables:

```text
environment_parameter_match_policy
matched_parameter_environment_id
condition_distance
condition_match_status
```

## ENV-002 tests

Required:

```text
- exact condition matching works;
- unmatched environment is blocked or metadata-only depending on policy;
- scientific mode rejects nearest-condition matching unless exact;
- exploratory mode records nearest/range matching as exploratory;
- environment ranking remains blocked if metadata-only;
- environment ranking allowed only when active condition effects exist.
```

## ENV-002 acceptance criteria

Complete when:

```text
- environment grids can become scientifically meaningful without fake response curves;
- output tables tell whether environment changed parameters;
- pH/temperature rankings are impossible unless supported by active condition-specific data or response models.
```

---

# Phase 6: CURATION-001 — Registry Review and Promotion Gate

## Goal

Create a formal promotion path from proposed source records to curated registry records.

SOURCE-001 will produce proposed records.

Those records must not automatically become trusted simulation records.

CURATION-001 defines how records are promoted.

## Record maturity ladder

Use or formalize:

```text
raw_source
proposed
curated_exact
curated_literature_range
exploratory_prior
synthetic_fixture
validated
deprecated
```

## Required curation process

Every promoted record must have:

```text
source_database
source_entry_id
source_url or source_snapshot
curator
curation_date
original_value
original_units
converted_value
converted_units
conversion_method
inclusion_reason
exclusion_reason if rejected
allowed_use
limitations
```

## Required curation reports

For every source import:

```text
curation_report.md
eligible_records.csv
excluded_records.csv
proposed_registry_records.yml
accepted_registry_records.yml
rejected_registry_records.yml
```

Scoped status after PR #64 and bounded PR-50 completion: PR-45 supplies owned curator decision bundles,
PR-46 supplies checksum-verified, index-resolved, loader-validated promotion
plans, and PR-47 supplies explicit digest-confirmed production apply with
durable curation audit provenance, full-root drift detection/staging, strict
next-patch versioning, candidate-derived applicability, source-identity
consistency, locking, no overwrite, and interruption-safe verified rollback.
PR-48 adds a real frozen SABIO PARAMETER identity path into a
complete loader-fidelitous curator-authored target and promotion plan against a
copied registry only. PR-49 adds public checksum-validated loading and shared
artifact reconstruction without mutation or curator authentication. PR-50
accepts a revalidated loaded written source in the identity-only authoring
bridge. PR-51 admits only one versioned registered, dimensionally compatible,
deterministically recomputed nonidentity conversion policy. PR-52 admits
complete curator-authored targets for the original five index-backed
non-parameter families through exact source identity, reserved integrity
evidence, production loader fidelity, and promotion/apply revalidation. PR-53
adds the sixth family, product maps, through an explicit production schema,
owner, loader, index destination, and unchanged-state/unchanged-coefficient
runtime conversion. At that PR-53 checkpoint CURATION-001 remained partial
for curator authentication/signatures. PR-54 completes that defined workflow with
Ed25519 signatures over exact manifest bytes, explicit caller trust,
decision-curator identity binding, and authoring/planning boundary
revalidation. CURATION-001 is therefore complete for the defined review,
authoring, authentication, planning, and transactional-apply scope. This
status does not claim scientific validation, external curation authority, or
automatic simulation authorization.

## CURATION-001 acceptance criteria

Complete when:

```text
- no proposed API/source record is silently used for simulation;
- all simulation records have maturity and allowed-use policy;
- curation reports are testable and versioned;
- registry promotion is explicit.
- at least one real frozen source record can be mapped into the exact production
  loader schema through explicit curator-authored fields and conversion metadata
  without guessed values, conversions, or defaults.
```

---

# Phase 7: BIO-READINESS Gate

## Goal

Before adding or extending biology, enforce a readiness gate.

No new biological process should be added unless it has:

```text
required inputs
state variables
process law
parameters
units
validity domain
output states
summary metrics
limitations
tests
provenance plan
```

## Biology readiness checklist

A new biology module must define:

```text
1. What biological process is being modeled?
2. What is the process law?
3. What are the state variables?
4. What are the required parameters?
5. What units are expected?
6. What substrate classes are valid?
7. What enzyme/fungus classes are valid?
8. What environmental variables affect it?
9. What output curves does it produce?
10. What scalar metrics does it produce?
11. What assumptions are made?
12. What data sources support it?
13. What is unknown?
14. What experiments would reduce uncertainty?
15. What failure modes should block simulation?
16. What tests prove correct behavior?
```

## BIO-READINESS acceptance criteria

Complete when:

```text
- a new biology proposal cannot be merged without this checklist;
- tests or CI check for required process metadata;
- foundation_progress has a biology proposal template;
- Codex is instructed to reject unsupported, invented, silently guessed, or
  falsely validated biology.
```

---

# Phase 8: BIO-002 — Biology Work Under The Gate

Status note: this section predates the current BIO-002 records documented in
`progress.md`. Phase 1 Task 2 must reconcile whether the prerequisites below are
still roadmap gates, already satisfied, or superseded by current implementation
evidence.

## When to start BIO-002

Start or extend BIO-002-class work only after:

```text
SOURCE-001 complete
RESOLVE-001 complete
ASSEMBLY-001 complete
API-003 complete
ENV-002 at least partially complete
CURATION-001 complete
BIO-READINESS gate active
```

## Recommended BIO-002 target

Do not jump to whole-fungus growth yet.

Recommended:

```text
BIO-002: cellulase/cellulose product-chain extension
```

Possible scope:

```text
cellulose-like substrate
endoglucanase/cellobiohydrolase/beta-glucosidase chain
solid cellulose -> cellobiose -> glucose
```

Why this is a good next biology target:

```text
- continues from Reaction 618 and BIO-001;
- connects soluble and surface degradation;
- still enzyme-mediated, not full fungus growth;
- product chain is interpretable;
- SABIO-RK/BRENDA/CAZy can support parts of it;
- outputs remain degradation/product curves.
```

Avoid:

```text
whole fungus growth
PET
lignin
full lignocellulose
oxygen regulation
secretion dynamics
intracellular metabolism
```

until the enzyme-chain layer is stable.

## BIO-002 required outputs

```text
solid_cellulose_remaining(t)
cellobiose_release(t)
glucose_release(t)
substrate_degraded_fraction(t)
time_to_10/50/90_percent_degradation
final_glucose_yield
rate-limiting step indicator
uncertainty intervals
```

---

# Phase 9: PRODUCT-001 — Build-First Exploratory Virtual-Experiment Expansion

## Goal

Make the researcher-facing virtual-experiment engine more useful before
requiring validation data.

Given a fungus or enzyme source, a substrate, and an environment or environment
range, FungMod should produce honest exploratory degradation dynamics when the
needed mechanisms and assumptions are available. It should fail explicitly when
mechanisms, parameters, or compatibility records are missing.

## Scope

Prioritize:

```text
fungus_or_source + substrate + pH/temperature/oxygen/water-activity ranges
implemented mechanism selection
explicit exploratory prior/range use
substrate remaining over time
substrate mass loss over time
product release over time
degradation rate over time
threshold times
uncertainty intervals
provenance
limitations
missing mechanisms and suggested follow-up experiments
researcher-facing reports generated from standard output tables
```

Do not require a real observation table for this phase. Observations are useful
later for validation and calibration, but PRODUCT-001 is about making the
simulator itself more complete and honest.

## Acceptance criteria

Complete when:

```text
- a small build-first simulator capability is implemented in code;
- the capability is generic or has a materially different non-specific test;
- assumptions and exploratory priors are visible in output tables;
- unsupported mechanisms remain explicit instead of guessed;
- outputs include useful time-series or summary degradation metrics;
- report/output ergonomics remain a presentation layer over standard tables;
- tests prove no validation or scientific certainty is claimed without data.
```

---

# Phase 10: THERMO-003 — Dynamic Thermodynamic and Entropy Constraints

## Goal

Add more first-principles constraints so FungMod can avoid case-specific
fungus models where general thermodynamic or entropy-based rules are the right
abstraction.

Examples of acceptable directions:

```text
dynamic reaction feasibility checks
free-energy or affinity gates where equations and inputs exist
irreversibility / entropy-production accounting where implemented explicitly
redox or oxygen-coupling constraints where state variables are represented
energy-dissipation limits on process rates where provenance is available
```

Do not emit thermodynamic state, entropy production, redox behavior, or
organism-specific physiology unless the equations, parameters, provenance,
maturity labels, and tests exist.

Current scoped support includes explicit-metadata reaction-quotient Gibbs
diagnostics; scalar and configured process-bound entropy-production-rate
diagnostics; and PR-57 optional dynamic constraints over explicitly bound molar
states. The dynamic path derives ideal-dilute activities, Q, and
`delta_g = delta_g_standard + R*T*ln(Q)` from complete sourced inputs, requires
a passing bound electron/redox check, and blocks unfavorable nonnegative
forward rates at native solver RHS evaluations. PR-59 copies the persisted
dynamic trajectories and configured binding/count/extrema evidence into
standard PRODUCT outputs. The PRODUCT bridge does not infer or recompute these
quantities, revalidate their inputs, or apply solver enforcement.

---

# Phase 11: BIO-003 — Generic Mechanism Expansion Through Process Laws

## Goal

Add more biology through reusable mechanism families, not ad hoc fungus-specific
branches.

Examples of acceptable directions:

```text
additional extracellular enzyme-chain motifs
generic hydrolysis process families
generic oxidative process components
generic inhibition or environmental modifier laws
mechanism proposals promoted only after implementation and tests
```

Every mechanism must remain provenance-backed, maturity-labelled, tested, and
honest about assumptions and limitations.

Current scoped BIO-003 status: generic reversible product inhibition is
software-tested for configured process modifiers and registry-backed
case-template assembly when explicit product-state and positive unit-compatible
`K_i` records exist. The scoped researcher-facing example notebook
`notebooks/examples/12_reversible_product_inhibition_example.ipynb` now
compares inhibited and uninhibited exploratory virtual experiments and shows
where to inspect mechanism summaries, configured metadata, limitations, and
final metrics. This does not add organism-specific inhibition behavior,
toxicity, uptake, secretion, biomass, physiology, calibration, validation,
multi-product inhibition, or fallback inhibition constants.

Competitive and Haldane substrate-inhibition modifiers are additionally
software-tested for explicit homogeneous Michaelis-Menten configuration.
Their primary law references, maturity labels, substrate/Km ownership, Ki
parameters, assumptions, and limitations are mandatory. They reject other
base-process families, mismatched states or parameters, unsupported combined
inhibition, and missing provenance. The included fixtures are artificial and
make no organism, substrate, production-parameter, empirical-validity, or
whole-fungus claim.

---

# Deferred Phase: VALIDATION-DATA-001 — First Real Time-Course Validation Dataset

## Goal

Add the first experimental time-course dataset to validate or compare against a virtual experiment.

This is not required before building the simulator. FungMod still needs real
validation cases later, but validation should happen after the relevant
simulated outputs are mature enough that comparison is meaningful.

## Recommended validation target

Choose a narrow enzyme-only or enzyme-chain dataset:

```text
beta-glucosidase + cellobiose -> glucose time course
```

or:

```text
cellulase cocktail + cellulose/Avicel -> soluble sugar release time course
```

Do not start with whole-fungus colony growth.

## Required dataset fields

```text
time
substrate concentration or mass remaining
product concentration or amount
enzyme loading
pH
temperature
buffer
replicates if available
source publication
units
measurement method
```

## Required outputs

```text
experiment_dataset.yml
raw_data.csv
curated_data.csv
model_comparison.csv
residuals.csv
validation_report.md
```

## Acceptance criteria

Complete when:

```text
- dataset is local, curated, and provenance-rich;
- model can simulate corresponding case;
- outputs compare simulation to observation;
- limitations state whether this is validation, calibration, or qualitative comparison.
```

---

# Later Phase: Whole-Fungus Minimal Growth Coupling

## When to start

Only after build-first simulator work, generic mechanism expansion,
thermodynamic/entropy constraints, and a specific scope decision.

Whole-fungus biology should not be added casually.

## Minimal scope

```text
extracellular substrate degradation
soluble product uptake
biomass proxy growth
maintenance cost
```

Do not add full metabolism.

Do not add gene regulation.

Do not add intracellular flux balance.

Do not add morphology unless required.

## Required outputs

```text
substrate_remaining(t)
soluble_product(t)
uptake_flux(t)
biomass_proxy(t)
growth_rate(t)
time_to_substrate_degradation_threshold
time_to_biomass_threshold
```

---

# Phase 11: Database Strategy

## Important principle

FungMod does not need a giant built-in database.

FungMod needs:

```text
source adapters
local source snapshots
curated registry records
review gates
provenance
allowed-use policies
```

SABIO-RK, BRENDA, CAZy, UniProt, KEGG, and literature can feed FungMod.

They do not replace FungMod’s registry.

## Why local records are still needed

Local records are needed for:

```text
reproducibility
offline tests
reviewed curation
source drift detection
provenance
allowed-use semantics
simulation templates
state roles
product maps
process compatibility
```

Live external APIs should never be required to reproduce a simulation.

---

# Phase 12: Recommended immediate next order

Use this exact order:

```text
1. SOURCE-001
2. RESOLVE-001
3. ASSEMBLY-001
4. API-003
5. ENV-002
6. CURATION-001
7. BIO-READINESS
8. BIO-002
9. VALIDATION-DATA-001
10. BIO-003
```

If time is limited, do the first four before expanding biology further.

---

# Final answer to "Can we start biology after this?"

After SOURCE-001, RESOLVE-001, ASSEMBLY-001, API-003, CURATION-001, and BIO-READINESS:

```text
yes, carefully, if the biology proposal passes the BIO-READINESS gate.
```

Before roadmap reconciliation:

```text
verify the specific task against progress.md, code, tests, and AGENTS.md.
```

The project should not add unsupported biological mechanisms. Any added or
extended mechanism must be explicitly implemented, provenance-backed,
maturity-labelled, covered by tests, and honest about assumptions and
limitations.

The next real biology should probably be:

```text
cellulose enzyme-chain degradation:
solid cellulose -> cellobiose -> glucose
```

not whole-fungus growth and not PET.

---

# One-sentence directive

Before adding or extending biology, make sure FungMod can discover/source
reaction data, resolve researcher names, assemble cases from registry/config
schemas, run scientific and exploratory virtual experiments, and output
degradation curves/tables without hardcoded case branches, or document why the
proposal is scoped narrowly enough to proceed under the current biology rule.
