# Active Next Steps

Use `ROADMAP_ORCHESTRATION_STATUS.md` for the current PR queue and phase
status.

Scoped status after PR-49 merged as PR #64 (`bbe2ee6`), PR-50 written-source
authoring merged as PR #65 (`933d2c8`), and bounded
PR-51 registered nonidentity conversion merged as PR #66 (`bef938f`), bounded
PR-52 index-backed non-parameter authoring merged as PR #67 (`5da611b`), and
bounded PR-53 product-map ownership merged as PR #68 (`19baedd`), with
PR-54 authenticated curator signatures merged as PR #69 (`35a3ecb`) and
PR-55 arbitrary supported-reaction assembly merged as PR #70 (`6b3d275`),
PR-56 branching/cyclic pathway assembly complete after PR #71 merged as
`caa0a17`, PR-57 dynamic thermodynamic solver enforcement complete after PR
#72 merged as `ae8a5a3`, PR-58 biological-law expansion complete after PR #73
merged as `68c715b`, and PR-59 final PRODUCT-001 integration complete in the
current checkout:

```text
SOURCE-002: complete for the offline notebook discovery/proposal workflow.
PRE-BIO-001 / ASSEMBLY-001: complete for arbitrary reactions using implemented
homogeneous Michaelis-Menten semantics and template-backed surface plus
linear/branching/cyclic pathway scopes.
BIO-READINESS-LITE: complete for the proposal template, validator, and tests.
BIO-002: complete for linear, branching, and cyclic enzyme-pathway assembly
and software verification; broad pathway biology remains partial.
CASE-001: complete once PR-02 is merged for the researcher-facing named API path.
CURATION-001: complete for its defined workflow after PR-47 transactional apply, completed PR-48
PARAMETER-only identity authoring, and completed PR-49 reusable public
curation-bundle loading, and completed PR-50 checksum-loaded written-source
authoring, completed PR-51 versioned nonidentity conversion, and completed
PR-52 authoring for the original five index-backed non-parameter families and
PR-53 product-map storage/authoring, plus PR-54 caller-trusted Ed25519 curator
authentication. Completion does not claim scientific validation or automatic
simulation authorization.
VALIDATION-DATA-001: deferred; blocked/partial for ingestion until a
source-backed numeric time-course dataset satisfies the active gate.
PRODUCT-001: partial after top-level environment_grid helper,
assumption_summary.csv, modelability_items.csv, write_preflight_report, the
scoped `DegradationScreenResult.write_report(...)` Markdown report writer, the
PR-09 HTML report wrapper, and the PR-10 report-folder index/navigation slice.
The PR-09 `include_html=True` option and PR-10 `include_index=True` option
remain opt-in presentation layers over existing standard outputs.
The completed screen-comparison summary slice adds `comparison_summary.csv` as
a derived index over existing final-metric and threshold rows with explicit
comparison/ranking guardrail columns.
The completed comparison/report-output example-notebook slice demonstrates the
public workflow for writing reports and inspecting those guardrails without
ranking metadata-only environment grids.
Virtual-experiment outputs now include mechanism_summary.csv for active process
laws, maturity, assumptions, limitations, and provenance.
Example notebooks now include `10_virtual_experiment_product_tour.ipynb` for a
public-API virtual-experiment tour without validation claims.
Example notebooks also include
`13_screen_comparison_summary_example.ipynb` for public-API report-output and
guarded `comparison_summary.csv` inspection without validation claims.
Example notebooks now include
`14_trajectory_quantiles_example.ipynb` for public-API trajectory-quantile
inspection and presentation-only quicklook generation without validation
claims.
The completed degradation-rate quicklook/report ergonomics slice adds a
presentation-only `degradation_rate_vs_time.png` quicklook and a bounded degradation-rate inspection section
from existing `time_series_long.csv` `degradation_rate` rows without changing
solver/model behavior.
The completed threshold-time inspection/report ergonomics slice exposes
existing `threshold_times.csv` rows and `summary_metrics.csv` threshold
quantiles in the deterministic report and report/index links without
validation claims.
The completed provenance/limitations report ergonomics slice adds a Markdown
decision summary and richer assumption, limitation, missing-parameter,
suggested-experiment, and provenance row renderers derived only from existing
standard output tables. HTML and index paths add links to those existing
decision-support tables without changing the Markdown-primary contract.
The completed provenance/limitations report example-notebook slice adds
`15_provenance_limitations_report_example.ipynb` as a public-API example that
writes Markdown/HTML/index report artifacts and inspects the table-derived
decision summary plus existing decision-support links and rows without
validation claims.
THERMO-003: partial after explicit reaction-quotient Gibbs/entropy validation,
configured entropy-rate diagnostics and summaries, and PR-57 dynamic
ideal-dilute molar activity/Q/Gibbs evaluation with required bound
electron/redox evidence and native solver-time forward-rate blocking.
Nonideal activities, reverse rates, coupled-network optimization,
electrochemical gradients, and empirical validation remain unsupported.
The completed PR-43 slice adds opt-in process-bound
`entropy_production_rate_timeseries.json`/`.csv` diagnostics after simulation
from native process-rate trajectories only when explicit sourced delta G,
positive temperature, reaction-extent interpretation, and dimensionally
compatible extent-rate units/conversion metadata are supplied. It does not add
dynamic delta G or solver-time enforcement.
Thermodynamic summaries are available as JSON and CSV when such validators run.
The JSON summary includes `has_entropy_budget`,
`entropy_budget_evaluated_count`, `entropy_budget_negative_count`, and
`entropy_budget_status` fields while leaving missing or non-numeric
entropy-rate metadata unevaluated rather than treating it as zero.
Report utilities add Markdown, HTML, and report-folder index visibility for
existing configured-output `thermodynamic_summary.json` and
`thermodynamic_summary.csv` artifacts without inferring thermodynamic inputs
or enforcement that those artifacts do not contain.
Standard virtual-experiment outputs now include `thermodynamic_diagnostics.csv`
and `DegradationScreenResult.thermodynamic_diagnostics()` as a bridge over
existing per-sample configured-output `thermodynamic_summary.json`/`.csv`
artifacts only. The table is header-only when no configured thermodynamic
artifacts exist. When PR-57 dynamic rows are present, the table copies their
explicit activity/Q, electron/redox-binding, and solver-enforcement evidence;
it does not infer missing values or establish empirical validation.
Example notebooks now include
`11_thermodynamics_entropy_diagnostics.ipynb` for configured explicit-Q Gibbs,
entropy-production-rate, and entropy-budget output inspection without
validation claims or solver-time enforcement, including the
`has_entropy_production_rate`, `has_entropy_budget`, and
`entropy_budget_status` summary fields.
Example notebooks now also include
`16_thermodynamic_diagnostics_example.ipynb` for public-API inspection of the
standard `thermodynamic_diagnostics.csv` table, the header-only no-artifact
case, and a labelled package-generated artifact-copy demonstration without
validation claims or solver-time enforcement.
Configured generic processes can now opt into existing
`temperature_arrhenius_reference` and `ph_gaussian` environmental rate
modifiers when explicit Arrhenius or Gaussian pH parameters and the required
environment values are supplied. This is explicit configured framework
behavior, not inferred environment-response biology, calibration, validation,
or empirical comparison.
Example notebooks now include
`17_configured_environment_modifiers_example.ipynb` for public configured
workflow inspection of those explicit environment modifiers through
package-generated configured metadata, assumptions, merged parameters, entity
snapshots, and process rates without fitted response curves, validation,
empirical comparison, inferred environment responses, or EnvironmentGrid
behavior changes.
Configured generic processes can also opt into existing `oxygen_monod` and
`water_activity_threshold` environmental rate modifiers when explicit oxygen
half-saturation, oxygen units, water-activity threshold parameters, and the
required environment values are supplied. This is explicit configured framework
behavior, not inferred oxygen or moisture biology, calibration, validation,
empirical comparison, oxygen consumption, gas transfer, redox balance,
anaerobic metabolism, substrate water binding, or EnvironmentGrid behavior.
Example notebooks now include
`18_configured_oxygen_water_modifiers_example.ipynb` for public configured
workflow inspection of those explicit oxygen and water-activity modifiers
through package-generated configured metadata, assumptions, merged parameters,
entity snapshots, input config, and process rates without fitted response
curves, validation, empirical comparison, inferred environment responses,
oxygen consumption, gas transfer, redox balance, anaerobic metabolism,
substrate water-binding behavior, or EnvironmentGrid behavior changes.
One-process registry case templates can now bridge explicit environment
modifier records for `temperature_arrhenius_reference`, `ph_gaussian`,
`oxygen_monod`, and `water_activity_threshold` into those existing configured
modifier paths when all parameter roles resolve and exact registry environment
values are present. The builder emits a package-generated environment entity
from those explicit registry values when required and fails before execution
for missing fields, missing roles, missing environment conditions, non-exact
environment values, or unsupported modifier types.
BIO-002-style chain templates can now bridge those same explicit environment
modifier records from process-template modifier entries into existing
configured modifier paths when all parameter roles resolve and an explicit
environment id supplies exact registry environment values. Chain assembly emits
a package-generated environment entity from those exact values when required
and fails before execution for missing role fields, unresolved roles, missing
environment context, missing environment conditions, non-exact environment
values, missing oxygen units, or unsupported modifier types.
Configured output bundles now include `conservation_diagnostics.json` and
`conservation_diagnostics.csv` for explicit configured `mass_balance`
validators with `conserved_weights`. The diagnostics compute weighted initial
and final conserved totals, final drift, maximum absolute drift, relative
maximum drift when the initial total is finite and nonzero, units, and
allowed-use text from existing `SimulationResult` trajectories only. Header-only
CSV and `evaluated_count: 0` JSON behavior are used when no explicit configured
mass-balance weights exist. These artifacts are not validation, calibration,
threshold changes, thermodynamic enforcement, solver changes, or biology
claims.
Standard virtual-experiment outputs now also include
`conservation_diagnostics.csv` and
`DegradationScreenResult.conservation_diagnostics()` as a bridge over existing
per-sample configured-output `conservation_diagnostics.json`/`.csv` artifacts
only. The table is header-only when those artifacts are absent and must not be
read as inferred conserved quantities, tolerances, pass/fail thresholds,
validation evidence, chemistry, thermodynamics, calibration, empirical
comparison, or biology.
Configured output bundles now also include `solver_diagnostics.json` and
`solver_diagnostics.csv` for existing configured run metadata, solver
settings, solver metadata, time-grid/evaluation counts, state counts, and
process counts only. They expose recorded solver method/backend/status/message
and nfev/njev/nlu fields when present, and use header-only CSV plus JSON
`status: unavailable` behavior when solver metadata is absent. These artifacts
are not solver behavior changes, numerical thresholds, validation,
calibration, empirical comparison, thermodynamic enforcement, inferred
scientific values, or biology claims.
Standard virtual-experiment outputs now also include `solver_diagnostics.csv`
and `DegradationScreenResult.solver_diagnostics()` as a bridge over existing
per-sample configured-output `solver_diagnostics.json`/`.csv` artifacts only.
The table is header-only when no configured solver diagnostics artifacts exist
and must not be read as solver quality thresholds, validation evidence,
calibration evidence, empirical comparison, thermodynamic enforcement, inferred
scientific values, or biology claims.
Report utilities now expose existing configured-output `solver_diagnostics.json`
and `solver_diagnostics.csv` artifacts in Markdown, HTML, and report-folder
index paths without changing solver behavior, defining numerical quality
thresholds, adding validation/calibration evidence, comparing against empirical
data, enforcing thermodynamics, or adding biology claims.
Example notebooks now include `19_solver_diagnostics_example.ipynb` for public
configured-workflow inspection of package-generated solver diagnostics
artifacts, report/index links, and the explicit header-only/no-metadata
guardrail without solver behavior changes, numerical quality thresholds,
validation/calibration evidence, thermodynamic enforcement, inferred
scientific values, or biology claims.
BIO-003: partial/software-tested for generic reversible product inhibition plus
provenance-bound competitive and Haldane substrate inhibition. The PR-58 laws
are limited to exactly matched homogeneous Michaelis-Menten processes and
require explicit primary-source/maturity metadata and positive
unit-compatible parameters. Their fixtures are artificial software evidence,
not production applicability or validation.
The scoped reversible-product-inhibition target now has a public example
notebook, `12_reversible_product_inhibition_example.ipynb`, that compares
inhibited and uninhibited exploratory virtual experiments and inspects
mechanism summaries, configured metadata, limitations, and final metrics
without validation claims.
```

Current next PR: **none selected; scoped queue complete through PR-59**.

PUBLIC-RELEASE-001 is complete in the current checkout as a user-directed
release/readiness slice outside the numbered roadmap queue. The Python
distribution, packaged assets, two full public notebooks, Read the Docs site,
and release gates expose existing implemented capabilities without adding
biology, empirical data, calibration, or validation claims.

The PR-03 gate document records that the existing Resa/Buckin and
Ariaeenejad/Frontiers candidate reviews are blocked and that this repo still
has no real observation table under `data/experiments/literature/`. That blocks
validation, calibration, and empirical comparison claims; it does not block
building the simulator.

Because the current validation evidence gate is still blocked, PR-27 completed
a build-first configured environment-modifier slice that wires existing
`TemperatureModifier` and `PHModifier` response laws into generic configured
processes with explicit parameters and environment values, PR-28 completed
a public configured-workflow example notebook for those modifiers after
PR #43 merged, PR-29 completed the explicit `oxygen_monod` and
`water_activity_threshold` configured modifier wiring after PR #44 merged,
PR-30 completed the configured oxygen/water-activity example notebook after
PR #45 merged, PR-31 completed the one-process registry-backed explicit
environment modifier assembly slice after PR #46 merged, PR-32 completed
the repository hygiene cleanup after PR #47 merged, and PR-33 completed the
chain-template explicit environment modifier assembly slice after PR #48
merged. PR-34 completed configured-output conservation/drift diagnostics after
PR #49 merged, deriving a small diagnostics artifact from existing
`SimulationResult` trajectories and explicit configured `mass_balance`
`conserved_weights` only. PR-35 completed a focused repository hygiene
guardrail extension after PR #50 merged, keeping generated artifacts already
covered by `.gitignore` out of git while preserving the tracked final-goal HTML
plan. PR-36 completed configured-output solver diagnostics after PR #51,
derived from existing configured run metadata, solver settings, solver
metadata, time-grid/evaluation counts, state counts, and process counts only.
PR-37 completed a small report/index visibility follow-up over those existing
solver diagnostics artifacts after PR #52. PR-38 completed the configured
solver diagnostics example notebook after PR #53. PR-39 completed the standard
virtual-experiment solver diagnostics table/accessor bridge after PR #54.
PR-40 completed the standard virtual-experiment conservation diagnostics
table/accessor bridge after PR #55. PR-41 completed the Pyright
optional-member-access ratchet after PR #56 without scientific or numerical
behavior changes. The completed PR-42 work generalized the existing
registry/template-driven chain assembler to ordered linear chains of two or
more existing process laws, preserves current two-step behavior and explicit
metadata, and rejects branching and cycles before execution.
PR-42 is complete after PR #57. PR-43 is complete after PR #58; it derives process-bound
entropy-production-rate trajectories after simulation only from native
process-rate trajectories plus explicit sourced, dimensionally compatible
metadata; missing or incompatible metadata fails instead of falling back.
The completed PR-44 work added the bounded top-level `provider="sabiork"`
researcher source-proposal UX over existing fetch/freeze/parser/proposal
behavior. It accepts officially quoted/escaped friendly scientific selectors
and strict numeric SABIO IDs, requires no SABIO-RK key, keeps refresh explicit
through the shared fetch/freeze path, preserves checksummed raw pages in unique
query-specific bundles, and emits review-only proposals without registry or
simulation promotion. No BRENDA, CAZy, or other provider is claimed. PR-44 is
complete after PR #59.
The completed PR-45 work added bounded CURATION-001 schema review and explicit
curator decision bundles for in-memory or written source proposals. It keeps
omitted decisions deferred, reports exact blockers, writes deterministic
review artifacts, and does not mutate `data_registry/`, promote records into
simulation, or claim scientific validation. PR-45 is complete after PR #60
merged as `5ac7864`.
The completed PR-46 work added the preview-only
`plan_registry_promotion(...)` API for explicit accept decisions. It
checksum-verifies written curation bundles, resolves only
registry-index destinations, rejects unsafe paths, validates candidates and the
combined prospective registry through existing loaders, requires would-be adds
to round-trip to the exact candidate mapping without silently dropped or
synthesized/defaulted fields, classifies addable,
exact-duplicate/no-op, conflict, and blocked/unsupported records, and emits
exact prospective YAML plus hashes/digests. PR-46 is complete after PR #61
merged as `2b6c639` and has no registry mutation path of its own.

The completed PR-47 work adds `apply_registry_promotion(...)` over intentional
plan schema `2.0.0`. Addable prospective records now carry deterministic
`provenance.fungmod_curation` audit metadata, and written schema `1.0.0` plans
remain preview-only and must be regenerated before apply. Apply requires the
exact plan digest and exact next numeric patch version, resolves destinations
only from the current index, rechecks full-root and target drift, stages and
loader-validates a complete same-filesystem registry copy, excludes concurrent
or reentrant cooperating writers, and swaps with verified rollback. Results
record plan/confirmation binding, versions, digests, changed hashes, IDs, and
transaction/cleanup state. At that historical PR-47 checkpoint product maps
remained blocked; PR-53 now supplies their explicit destination. No scientific fields,
package version, solver/biology behavior, validation data, simulation
authorization, or scientific-validation claim is added. Applicability is true
only for at least one addable record with no conflict or blocked candidate;
source identities shared by target and curator provenance must agree exactly.
The bounded apply contract is complete after PR #62 merged as `b1ebb860`.
The completed PR-48 adds the source-to-production `author_parameter_record(...)`
bridge for one explicitly accepted in-memory PARAMETER curation result and one complete curator-authored
production mapping. It accepts identity conversion only, rechecks exact
source/original/converted/target value and units, frozen-source SHA256, complete
source and curator provenance, conservative maturity/allowed-use/range policy,
loader round-trip fidelity, selector compatibility, and post-result mutation.
The specialized result uses the existing checksummed curation writer and is
consumable by `plan_registry_promotion(...)` after revalidation. It does not
accept written source curation, infer or convert values, mutate/apply a
registry, authorize simulation, or claim validation. CURATION-001 stays
partial at that point for nonidentity conversion and non-parameter source
records.

The completed PR-49 adds top-level `load_curation_bundle(...)` and
`LoadedCurationBundle`, verifies the owned manifest/schema, exact artifact
inventory, declared SHA-256 checksums, path/symlink containment, and shared
deterministic curation artifacts, and routes written promotion planning through
that path. Checksums establish internal consistency only, not curator identity.
It adds no registry mutation, scientific transformation, validation claim, or
broader record support.

The completed PR-50 extends `author_parameter_record(...)` to accept a
`LoadedCurationBundle`. It reloads the owned manifest at call time before
applying every existing identity-only, frozen-source, storage-only,
registry-context, loader-fidelity, and no-mutation guardrail. Raw paths remain
unsupported, and no scientific value, registry, validation status, or
simulation authorization is changed.

The completed PR-51 adds a public immutable versioned conversion-method
registry and the named
`pint_unit_conversion_decimal_places_half_even_12_v1` policy. Registered
nonidentity authoring requires finite floats, parseable explicit distinct
source/target units, compatible dimensionality, deterministic recomputation,
12-decimal-place half-even rounding, and exact audit/digest-bound
converted/target correspondence.

The completed PR-52 adds `author_registry_records(...)` for accepted source
records mapped to complete `fungi`, `substrates`, `enzyme_classes`,
`process_compatibility`, and `case_templates` targets. It binds source and
target identity, reserved audit/digest evidence, deterministic in-memory and
written integrity, exact production-loader fidelity, and promotion/apply
revalidation without mutating the production registry during authoring or
planning.

PR-53 adds the index-owned `product_maps/product_maps.yml` destination, strict
`ProductMapRecord` schema/loader, explicit runtime conversion, and
curator-authored planning/apply support. State names and positive float
coefficients are supplied exactly; no participant translation or
stoichiometric inference is allowed.

PR-54 adds `sign_curation_bundle(...)`,
`load_authenticated_curation_bundle(...)`, `TrustedCuratorKey`, and
`AuthenticatedCurationBundle`. Ed25519 signs exact manifest bytes in a sibling
sidecar; the manifest binds all owned artifact checksums. The caller explicitly
owns the trusted key-ID/public-key/curator binding, every explicit decision
curator must match, and authenticated input is reloaded before authoring or
promotion planning. SHA-256 remains consistency evidence. Authentication proves
trusted-key possession and exact-manifest authorship only; it does not prove
scientific validity, general curation authority, registry mutation, or
simulation authorization. Detached promotion plans remain digest-confirmed
review/apply artifacts rather than independent signature evidence.

PR-55 removes Reaction 618, SABIO-RK, cellobiose, and beta-glucosidase tokens
from the generic homogeneous builder. Explicit templates own config, process,
parameter-set, product-map, state, time-grid, mode, provenance, entity, and
output identities. A materially different artificial reaction assembles and
simulates through the same implemented law. Missing identity/provenance,
request/template mode mismatch, incomplete parameters, and unsupported laws
fail closed; the fixture is not scientific data.

PR-56 adds explicit `linear`, `branching`, and `cyclic` registry-owned pathway
topology, directed process/product-map state-role edges, graph connectivity
and substrate-reachability checks, declared branch/cycle enforcement, and
conserved artificial branch/cycle execution through the standard solver.

PR-57 adds optional explicit ideal-dilute molar activities, trajectory Q and
dynamic Gibbs energy, required passing process-bound electron/redox evidence,
direct standard-Gibbs or redox-derived standard energy, and native RHS
forward-rate blocking. All scientific/numerical inputs, constants, floors,
tolerances, units, state/reaction bindings, and provenance are explicit and
fail closed.

PR-58 adds provenance-bound competitive and Haldane substrate-inhibition laws
for exactly matched homogeneous Michaelis-Menten processes. It requires
explicit primary-source and maturity metadata, exact substrate and `K_m`
ownership, positive unit-compatible `K_i`, visible assumptions/limitations,
and two materially different artificial configured benchmarks. It does not add
production parameter records, case applicability, validation, growth,
secretion, uptake, toxicity, or whole-fungus physiology.

PR-59 integrates implemented simulator evidence into standard output schema
`1.8.0`: explicit `process_rate.<process_id>` rows, namespaced persisted
derived trajectories, dynamic thermodynamic binding/count/extrema fields, and
report visibility. It does not add a biological law, production constant,
solver behavior, validation claim, or inferred mechanism.

Recommended next task: none in the user-scoped queue. Review, verify, and merge
PR-59, then stop rather than selecting another roadmap item.

Build-first work should now improve FungMod as a virtual-experiment engine:
broader researcher-facing inputs, explicit exploratory priors, richer
degradation curves, uncertainty bands, provenance, limitations,
missing-mechanism reports, and generic thermodynamic/entropy constraints. Do
not advance validation again until the simulator outputs are mature enough that
comparison to observations is meaningful.

The first PRODUCT-001 implementation slices add the top-level
`environment_grid(...)` helper plus `assumption_summary.csv` and
`modelability_items.csv` outputs, plus a `write_preflight_report(...)` path for
blocked cases. They improve the target researcher workflow and make exploratory
assumptions, uncertain inputs, and preflight facts easier to inspect, but
runtime pH, temperature, and oxygen grid values remain metadata-only unless an
explicit response law or condition-specific parameter record is active.
The completed screen-comparison summary slice adds `comparison_summary.csv` and
`DegradationScreenResult.comparison_summary()` as a derived view over existing
standard output rows. The completed example-notebook slice preserves
metadata-only environment guardrails and must not add biological mechanisms,
solver behavior, validation data, calibration, empirical-comparison claims,
unsupported ranking, inferred environment response, or hidden scientific logic.
The completed uncertainty-output ergonomics slice adds
`uncertainty_summary.csv` and
`DegradationScreenResult.uncertainty_summary()` as a derived view over existing
sampled-parameter and summary-metric rows. It preserves allowed-use,
uncertainty-band status, and interpretation guardrails and must not be read as
validation, calibration, empirical confidence intervals, posterior
uncertainty, inferred environment response, or solver/model behavior.
The completed trajectory-quantile output ergonomics slice adds
`trajectory_quantiles.csv` and
`DegradationScreenResult.trajectory_quantiles()` as a derived view over
existing `time_series_long.csv` sample rows. It preserves allowed-use,
trajectory-band status, and interpretation guardrails and must not be read as
validation data, calibration evidence, empirical confidence intervals,
posterior uncertainty, inferred environment response, or solver/model
behavior.
The completed thermodynamic-diagnostics bridge slice adds
`thermodynamic_diagnostics.csv` and
`DegradationScreenResult.thermodynamic_diagnostics()` as a standard table
derived only from existing per-sample configured-output
`thermodynamic_summary.json`/`.csv` artifacts. It preserves artifact-presence,
entropy-budget, allowed-use, and interpretation guardrails and must not be
read as inferred thermodynamics, validation evidence, empirical comparison, or
solver-time enforcement.
The completed trajectory-quantile example and quicklook ergonomics slice adds
`14_trajectory_quantiles_example.ipynb` and a presentation-only
`trajectory_quantile_bands.png` quicklook generated from
`trajectory_quantiles.csv`. The figure is an inspection artifact over existing
standard output tables, not validation, calibration, empirical comparison,
posterior uncertainty, inferred environment response, or solver/model
behavior.
The completed degradation-rate quicklook/report ergonomics slice adds
`degradation_rate_vs_time.png` as a presentation-only quicklook generated from
existing `time_series_long.csv` `degradation_rate` rows. The Markdown report
and optional HTML/index outputs expose those existing rate rows for inspection
with explicit guardrails; they do not add validation, calibration, empirical
comparison, a new rate law, inferred environment response, or solver/model
behavior.

THERMO-003 configured-output diagnostics should remain explicit metadata in and
`thermodynamic_summary.json`/`.csv` out. The completed notebook inspection path
must not infer activities, reaction quotients, concentrations, redox potentials,
electron balances, validation evidence, or solver-time thermodynamic
enforcement.

The completed threshold-time inspection/report ergonomics slice improves
inspection of existing `threshold_times.csv` rows and `summary_metrics.csv`
threshold quantiles in report paths only. It does not add validation data,
calibration, empirical-comparison claims, inferred environment responses,
posterior uncertainty claims, solver/model changes, hidden notebook science,
schema changes, or silent fallback constants.

The completed THERMO-003 thermodynamic-summary report ergonomics slice exposes
existing `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts
in Markdown, HTML, and index report paths only. It may display explicit PR-57
dynamic rows but does not infer activities, reaction quotients, concentrations,
redox potentials, electron balances, validation evidence, or solver
enforcement when those artifacts do not contain them.

The completed provenance/limitations report ergonomics slice improves
inspection of existing assumption, limitation, missing-parameter,
suggested-experiment, and provenance rows in Markdown, HTML, and index report
paths only. It does not add validation data, calibration, empirical comparison,
inferred environment responses, hidden notebook science, schema changes, or
solver/model behavior.

The completed PRODUCT-001 provenance/limitations example-notebook slice adds a
public-API example notebook that writes reports and inspects the
provenance/limitation decision summary and decision-support table links. It
does not add validation data, calibration, empirical comparison, inferred
environment responses, hidden notebook science, schema changes, or
solver/model behavior.

VALIDATION-DATA-001 remains deferred and evidence-gated. A validation
ingestion PR should start only if source-backed numeric time-course
observations satisfy the active gate; otherwise future makers should pick
build-first simulator/output ergonomics slices rather than treating incomplete
candidate reviews as data.

The first BIO-003 target is generic reversible product inhibition. The
mechanism is recorded in `BIO_003_GENERIC_PROCESS_LAWS.md` and the
machine-checkable `proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml`.
Configured model processes can now opt into it with explicit `product_state`
and positive unit-compatible `K_i`. Registry-backed case templates can now
carry explicit product-inhibition modifiers into configured runs and standard
mechanism summaries when product-state and `K_i` records exist. The scoped
researcher-facing example for this reversible-product-inhibition target is
covered by `notebooks/examples/12_reversible_product_inhibition_example.ipynb`;
the non-PET configured benchmark is
`data/model_configs/toy_surface_dummy_non_pet_product_inhibition.yml`. Broad
BIO-003 remains partial.

`old_progress/` is historical and non-binding.
