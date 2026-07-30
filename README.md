# FungMod

Before changing the codebase, start with the root agent/developer contract and
the active directive:

- `AGENTS.md`
- `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`
- `foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md`

Historical foundation-first plans are archived under `old_progress/`. They are
useful context only and are non-binding. The active goal is now the
virtual-experiment engine: simulate degradation dynamics over time without
hiding assumptions, uncertainty, provenance, missing inputs, or unsupported
biology.

FungMod is a scientific Python codebase for building a physically grounded
fungal- and enzyme-mediated substrate-degradation virtual-experiment engine.
The long-term target is a modular API that can simulate a fungus or enzyme
source, substrate, environment, and parameter set without inventing biological
facts.

This repository currently implements the validated foundation plus the first
basic kinetics layer:

- unit-aware parameters and parameter sets,
- explicit assumptions and simulation records,
- a generic deterministic ODE reaction engine,
- non-negativity, mass-balance, and limiting-case validation helpers,
- homogeneous dissolved-substrate Michaelis-Menten rate laws,
- PET substrate metadata with explicit unknown physical parameters,
- a minimal heterogeneous PET surface-hydrolysis rate law,
- Arrhenius temperature scaling with validity-range warnings,
- Gaussian pH activity scaling with validity-range warnings,
- minimal fungal metadata, enzyme secretion, enzyme decay, maintenance, and product-coupled biomass growth,
- stoichiometric and thermodynamic metadata interfaces,
- carbon conservation, oxygen limitation, and biomass-yield validation checks,
- explicit reaction-quotient Gibbs feasibility and entropy-production
  diagnostics for caller-supplied dimensionless Q and entropy-rate metadata,
- optional configured dynamic thermodynamic constraints that derive
  ideal-dilute activities and reaction quotients from explicitly bound molar
  trajectory states, compute `delta_g = delta_g_standard + R*T*ln(Q)` from
  fully sourced inputs, require a passing bound electron/redox balance check,
  and block an unfavorable nonnegative forward process rate at every native
  solver RHS evaluation. Standard Gibbs and redox-derived
  `delta_g_standard = -n*F*E_standard` inputs are supported; activity floors,
  standard concentration, temperature, gas/Faraday constants, tolerances, and
  provenance references are mandatory rather than inferred,
- configured thermodynamic JSON/CSV summary outputs for explicit Gibbs/entropy
  validation diagnostics, including an aggregate explicit entropy-rate budget
  and report/index visibility for existing summary artifacts plus a standard
  virtual-experiment thermodynamic diagnostics table derived from existing
  per-sample configured summary artifacts,
- configured process-bound entropy-production-rate JSON/CSV timeseries derived
  after simulation from native process-rate trajectories only when explicit
  sourced delta-G, positive temperature, reaction-extent interpretation, and
  dimensionally compatible extent-rate conversion metadata are supplied,
- configured conservation JSON/CSV diagnostics copied from existing
  `SimulationResult` trajectories and explicit configured `mass_balance`
  `conserved_weights`, for drift inspection only, plus a standard
  virtual-experiment conservation diagnostics table/accessor derived from
  existing per-sample configured conservation diagnostics artifacts,
- configured solver JSON/CSV diagnostics copied from existing configured run
  metadata, solver settings, solver metadata, time-grid/evaluation counts,
  state counts, and process counts, with report/index visibility plus a
  standard virtual-experiment solver diagnostics table/accessor derived from
  existing per-sample configured solver diagnostics artifacts,
- 1D finite-volume reaction-diffusion with explicit boundary conditions,
- universal substrate metadata interfaces with PET, cellulose, lignin, starch, and chitin substrate classes,
- least-squares calibration utilities with train/validation residual reporting,
- Monte Carlo uncertainty propagation and local sensitivity analysis,
- process-centered assembly scaffolding with structured missing-process,
  missing-parameter, and incompatible-unit reports,
- a standardized result/export object that writes reports, CSV tables, logs,
  and figures,
- generic homogeneous process classes for first-order, mass-action, and
  Michaelis-Menten benchmark models,
- generic surface adsorption/catalysis process components that can run with PET
  or a dummy non-PET substrate,
- explicit `Environment`, `Geometry`, and `Enzyme` entities for process-centered
  assembly,
- environment-driven temperature, pH, water-activity, oxygen, and product
  inhibition modifiers,
- compatibility checks for enzyme/substrate/bond/fungus pairings during model
  assembly,
- a top-level notebook set that imports package code rather than redefining
  core model logic,
- a researcher-facing product-tour notebook for the public
  `virtual_experiment(...)` API and standard output tables,
- a researcher-facing screen-comparison notebook that writes report artifacts
  and inspects `comparison_summary.csv` guardrails without ranking
  metadata-only environment grids,
- a researcher-facing provenance/limitations report notebook that writes the
  Markdown/HTML/index report artifacts and inspects the table-derived decision
  summary and decision-support links,
- a public configured-workflow solver-diagnostics notebook that inspects
  package-generated `solver_diagnostics.json`/`.csv` artifacts, report/index
  links, and the header-only/no-metadata guardrail without interpreting solver
  metadata as validation or quality thresholds,
- human-editable YAML config folders for fungi, substrates, enzymes,
  environments, geometries, parameters, and experiments,
- schema-checked config loaders with explicit unknown-value handling,
- an optional PET plugin convenience helper that delegates to the generic
  configured workflow with an explicit plugin registry,
- software-test benchmark configs that are explicitly non-scientific;
- a registry-backed exploratory virtual-experiment API for Reaction 618 and
  the controlled BIO-001 surface-degradation pilot;
- schema-versioned virtual-experiment output tables with provenance,
  mechanism-summary, limitations, missing-parameter, suggested-experiment, and
  range-use fields;
- mechanism summaries that can expose active configured rate modifiers such as
  explicit reversible product inhibition when registry-backed case templates
  provide product-state and positive unit-compatible `K_i` records;
- a toy non-PET configured product-inhibition benchmark that exercises the
  same explicit product-state and positive unit-compatible `K_i` path as
  framework coverage only, not as biological evidence;
- configured generic process modifiers for explicit
  `temperature_arrhenius_reference` and `ph_gaussian` rate scaling, using the
  existing Arrhenius and Gaussian pH response-law implementations only when
  explicit parameters and environment values are supplied;
- configured generic process modifiers for explicit `oxygen_monod` and
  `water_activity_threshold` rate scaling, using the existing oxygen and
  water-activity response-law implementations only when explicit parameters,
  oxygen units, and environment values are supplied;
- registry-backed one-process case-template assembly for explicit environment
  modifier records that bridge to the existing configured
  `temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
  `water_activity_threshold` modifier support only when explicit parameter
  roles and exact registry environment values are supplied;
- registry-backed BIO-002-style chain-template assembly for those same
  explicit environment modifier records, using process-template modifier roles
  and explicit environment ids only, with package-generated environment
  entities emitted from exact registry environment values when required;
- a top-level, offline-first SABIO-RK source-provider API that derives source
  queries from friendly scientific fields, loads frozen kinetic-law snapshots
  by default, and returns review-only proposed records without mutating the
  simulation registry;
- a digest-confirmed CURATION-001 apply API that transactionally promotes exact
  reviewed registry-plan bytes on copied or explicitly selected registries,
  with strict next-patch versioning, full-root drift detection, durable curator
  audit provenance, rollback, and no automatic simulation or validation claim;
- an identity-only, PARAMETER-specific CURATION-001 authoring bridge that binds
  an explicitly accepted in-memory source result to a complete curator-authored
  production `ParameterRecord`, verifies exact loader fidelity and source
  provenance through a closed identity-only outer metadata schema, and returns
  a promotion-plan-compatible result without applying it;
- a non-parameter CURATION-001 authoring bridge,
  `author_registry_records(...)`, for complete curator-supplied `fungi`,
  `substrates`, `enzyme_classes`, `process_compatibility`, and
  `case_templates`, and `product_maps` targets, with accepted-source identity, reserved
  audit/digest evidence, exact production-loader fidelity, deterministic
  in-memory and written integrity, promotion/apply revalidation, and no
  authoring/planning registry mutation;
- an index-owned `product_maps` registry destination and strict
  `ProductMapRecord` schema whose explicit positive-float reactant/product
  coefficients load without participant translation or inferred
  stoichiometry and can be converted explicitly to the existing runtime
  `ProductReleaseMap`;
- a public `load_curation_bundle(...)` reader that verifies the owned
  manifest/schema, exact artifact inventory, every declared SHA-256 checksum,
  path and symlink containment, and the shared deterministic YAML/CSV/report
  contracts before reconstructing a structured `LoadedCurationBundle` and
  `CurationResult`;
- an opt-in Ed25519 curator-authentication layer,
  `sign_curation_bundle(...)` and `load_authenticated_curation_bundle(...)`,
  that signs the exact manifest bytes in a sibling sidecar, binds the signer to
  every explicit curator decision, and verifies against caller-supplied
  `TrustedCuratorKey` bindings before authoring or promotion planning;
- mode-independent modelability and simulation rejection for parameters whose
  exact `allowed_use` is `registry_storage_only_no_simulation_authorization`;
- registry/template-driven onboarding for arbitrary reactions supported by the
  implemented homogeneous Michaelis-Menten law: config/process/parameter-set
  identities, state roles, initial values, product maps, yields, time grids,
  provenance, enzyme/substrate metadata, and output roles come from explicit
  records. A materially different artificial reaction assembles and runs
  without a new Python branch, while missing identities, provenance, mode
  mismatches, unsupported mechanisms, and incomplete parameters fail closed;
- a registry-backed extracellular enzyme-pathway assembler for explicit
  `linear`, `branching`, and `cyclic` graphs of two or more implemented process
  steps, whose topology type, directed state-role edges, stoichiometry,
  conserved quantities, entities, modifiers, and output labels come from
  template data rather than mechanism-code biological names. Each process owns
  one distinct map with one implemented rate-law input and one or more explicit
  products; graph connectivity, substrate reachability, declared topology
  shape, process/map role agreement, and conservation are checked before
  execution. Component process compatibilities use
  an intrinsic `component_only` scope and a registry-validated ownership graph,
  so removing or corrupting an outer binding cannot expose a component as a
  standalone compatibility. Exact templates also cross-bind configured
  substrate entity IDs to the exact registry-backed `state_species` identity
  consumed by the outer process, bind direct process parameters through
  process-type-owned semantic fields, and bind initial-state and modifier
  symbols through exact semantic compatibility keys;
- a scoped CASE-001 researcher-facing path that runs the existing BIO-002
  cellulose-equivalent enzyme-chain virtual experiment from names and aliases
  through the top-level `virtual_experiment(...)` API.

It does not yet implement coupled-network thermodynamic flux optimization,
nonideal activity coefficients, reverse-rate thermodynamics, resolved
intracellular metabolism, 2D/3D spatial models, publication-grade calibration
against curated biological datasets, or global uncertainty analysis. Those
stages are documented in `progress.md` and should be added only after the
current virtual-experiment layer has tests, provenance, and validation.

## Scientific Philosophy

The model is designed to fail honestly. Physical quantities carry units. Parameters require provenance before a scientific simulation can run, unless a test explicitly sets `allow_unsourced_for_testing=True`. Missing values are represented as missing values rather than guessed numbers. Validation failures are returned as results, not hidden.

Biology may be added only when the mechanism is explicitly implemented,
provenance-backed, maturity-labelled, covered by tests, and honest about
assumptions and limitations. Unsupported, invented, silently guessed, or falsely
validated biology is forbidden.

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## Test

```bash
pytest
```

## Quality Gates

CI is required before merging. The CI workflow installs `.[dev]` and runs the
package-quality gates below:

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml
```

The current Pyright gate resolves imports from the active Python interpreter
and enables the main argument, assignment, return, operator, call, attribute,
type-form, optional-operand, and optional-member-access diagnostics. Nullable
scientific values are narrowed explicitly before member access; the completed
FD-005 ratchet is documented in `ARCHITECTURE_DEBT.md`.
Coverage currently has an 80% minimum gate.

Branch protection expectations are documented in `.github/BRANCH_PROTECTION.md`.
The protected default branch should require pull requests, passing CI,
up-to-date branches, no force pushes, and no unaudited direct bypass.

## Propose Source Records

Researchers can create a review-only SABIO-RK registry proposal with one
scientific identifier. SABIO-RK does not require an API key, so no credential
is supplied or read from an environment variable:

```python
from fungal_model import source_proposal

proposal = source_proposal(provider="sabiork", reaction_id="618")
proposal.write("data/proposed_records/sabiork/reaction_618")
```

`source_proposal(...)` also accepts friendly `ec_number`, `enzyme`, `substrate`,
`organism`/`source`, and `entry_id` selectors. It does not expose raw Solr syntax.
Text selectors are quoted and escaped according to the SABIO-RK REST query
contract; SABIO reaction and entry identifiers must be positive decimal IDs.
Frozen snapshots are the default. `refresh=True` is the only public path that
performs a live fetch. Each refresh creates a unique query-specific snapshot
bundle under the cache: exact HTTP page bodies are preserved separately under
`raw/`, a checksummed parser input is written under
`derived/combined_export.json`, and `fetch_metadata.json` binds those artifacts.
The returned records remain `proposed_review_required` and are never promoted
into `data_registry/` or used by simulation automatically. Only
`provider="sabiork"` is currently implemented.

Review an in-memory proposal, or pass the directory written by
`proposal.write(...)`, without promoting any record:

```python
from fungal_model import CurationDecision, review_source_proposal

review = review_source_proposal(
    proposal,
    curator="Researcher Name",
    decisions={
        "proposed_sabiork_parameter_618_35622_kcat_cellobiose": CurationDecision(
            decision="defer",
            reason="Explicit original/converted conversion metadata is not yet supplied.",
            curation_date="2026-07-13",
            allowed_use="review_only_not_simulation_registry",
            limitations=("Not scientifically validated or promoted for simulation.",),
        )
    },
)
review.write("data/proposed_records/sabiork/reaction_618_curation")
```

Records without a complete explicit `accept`, `reject`, or `defer` decision
remain deferred. Schema blockers and exact missing fields are reported without
filling unknown biology or parameters. The resulting CURATION-001 files are
decision artifacts only: even `accepted_registry_records.yml` does not mutate
`data_registry/`, promote records into simulation, or claim scientific
validation. Accepted decisions require complete source provenance and explicit
original/converted parameter values, units, and conversion method when the
record is a parameter. Rejected and deferred decisions may preserve provenance
blockers with curator rationale. Decision allowed use is restricted to
`review_only_not_simulation_registry` or
`pending_registry_promotion_review`; scientific, validation, and simulation
use cannot be declared by this API.
Product-map participants also require parseable finite positive stoichiometry,
and each finite positive product yield must match exactly one product name or
id and its participant stoichiometry; no conversion is inferred.

Reload an owned decision bundle through the same integrity contract used by
promotion planning:

```python
from fungal_model import load_curation_bundle

loaded = load_curation_bundle(
    "data/proposed_records/sabiork/reaction_618_curation"
)
review = loaded.result
```

The loader accepts either the bundle directory or
`curation_manifest.json`. It requires exactly the six owned artifacts plus the
manifest, rejects undeclared files and symlinked/path-traversing inputs,
verifies every declared SHA-256 checksum before parsing, and reconstructs the
shared curation result only when the manifest, decision YAML, eligible/excluded
CSV, summary, and report agree. `LoadedCurationBundle` also exposes the
verified raw artifact payloads for workflow-specific validators. This proves
internal consistency relative to the manifest only; it is not a signature,
curator authentication, scientific validation, registry mutation, promotion,
or simulation authorization.

An owned bundle can additionally be authenticated with an Ed25519 signature:

```python
from fungal_model import (
    TrustedCuratorKey,
    load_authenticated_curation_bundle,
    sign_curation_bundle,
)

sign_curation_bundle(
    "data/proposed_records/sabiork/reaction_618_curation",
    curator_id="Researcher Name",
    key_id="researcher-ed25519-2026",
    private_key=private_key,
)
trusted_key = TrustedCuratorKey.from_public_key(
    curator_id="Researcher Name",
    key_id="researcher-ed25519-2026",
    public_key=private_key.public_key(),
)
authenticated = load_authenticated_curation_bundle(
    "data/proposed_records/sabiork/reaction_618_curation",
    trusted_curator_keys={trusted_key.key_id: trusted_key},
)
```

The deterministic signature sidecar is a sibling of the bundle, so the
bundle's closed internal inventory stays unchanged. The Ed25519 message binds
the exact manifest bytes; the manifest in turn binds the owned artifact
checksums. Trust is explicit and caller-owned: key ID, public key, curator
identity, and every explicit decision curator must agree.
`AuthenticatedCurationBundle.reload()` repeats checksum and signature
verification, and authoring/planning revalidates authenticated input at its
use boundary. The signature proves possession of a caller-trusted private key
and authorship of those exact manifest bytes. It does not prove scientific
validity, curation authority outside the caller's trust policy, registry
mutation, or simulation authorization. Unsigned `LoadedCurationBundle` input
remains supported and distinguishable. A subsequently detached promotion plan
is digest-confirmed review/apply evidence, not independent curator-signature
evidence.

Plan the registry effect of the curation decisions and inspect whether the
whole candidate set is applicable. The deferred SABIO-RK review above has no
addable accepted record, so its plan is intentionally not applied:

```python
from fungal_model import apply_registry_promotion, plan_registry_promotion

plan = plan_registry_promotion(
    review,
    registry_index="data_registry/registry_index.yml",
)
plan.write("data/proposed_records/sabiork/reaction_618_promotion_plan")

summary = plan.summary()
assert summary["apply_available"] is False

# Entered only for a separately curator-authored, loader-fidelitous plan.
if summary["apply_available"]:
    result = apply_registry_promotion(
        plan,
        confirmation_digest=plan.plan_digest,
        new_registry_version="0.1.1",
    )
```

`plan_registry_promotion(...)` accepts either the in-memory `CurationResult` or
its written owned curation bundle, including an explicitly authenticated
`AuthenticatedCurationBundle`. Written inputs reuse
`load_curation_bundle(...)` for the manifest, checksum, inventory, and path
contract before workflow-specific authoring validation. Only explicit
`accept` decisions are considered. Candidates are
validated through the actual destination registry loader and classified as
addable, exact duplicate/no-op, conflict, or blocked/unsupported. Exact target
paths, before hashes, deterministic prospective YAML, post hashes, and a full
prospective-registry digest are reviewable in memory or in the optional owned
plan bundle. A would-be addable must also round-trip through the loader to the
same record mapping, so unknown fields that a loader would silently drop and
omitted fields that it would synthesize/default are blocked. Plan schema
`2.0.0` intentionally adds apply binding, full registry-tree digests, and
deterministic non-scientific `provenance.fungmod_curation` audit metadata with
the curator, curation date, decision reason, limitations, source provenance,
and allowed-use decision. Apply writes those exact prospective bytes; it does
not transform scientific values, units, maturity, target `allowed_use`,
mechanisms, or IDs. Pre-PR-47 written schema `1.0.0` remains preview-only and
is explicitly rejected at apply because it lacks that durable audit contract.
Bundle checksums establish deterministic internal consistency and tamper
detection relative to the manifest; they are not signatures and do not prove
external curator identity or authorship.
When the target record's outer provenance also carries a source database,
entry ID or IDs, snapshot path, or source URL, that normalized source identity
must agree type- and value-exactly with the curator source provenance before
audit metadata is embedded or applied.

`apply_registry_promotion(...)` accepts an in-memory plan or its owned written
bundle. Written bundles require an explicit current `registry_index`; manifest
absolute paths are review metadata and are never write destinations. Apply
rechecks the confirmation digest, artifacts, index and full-root digests,
target hashes, loader fidelity, no-overwrite/path boundaries, and the complete
staged registry. Versions must be strict numeric `MAJOR.MINOR.PATCH`, with
exactly one patch increment. A sibling single-writer lock excludes concurrent
and reentrant cooperating applies; a same-filesystem full-root stage is swapped
at directory level with verified backup rollback. The structured result records
the plan/confirmation binding, old/new versions, before/planned/applied digests,
exact changed-file hashes, applied IDs, and transaction/rollback/cleanup status.
An interruption around either root rename or installed-runtime verification is
reconciled from the actual source, backup, and stage digests. The original
interrupt is preserved only after the old root is proven restored; unproven
rollback reports recovery paths and preserves the stage container.

Raw stored content still defines exact-duplicate/no-op classification, and an
exact duplicate is never rewritten merely to add audit metadata. Plans with a
conflict or blocked candidate, or without at least one addable record, cannot
apply, and their summaries and written manifests report
`apply_available: false`. `parameter_records` map to the registry index's
`parameters` destination and `product_maps` map to the index-owned
`product_maps/product_maps.yml` destination. Production promotion does not
infer product-map participants or coefficients, authorize simulation, alter
package version, or claim scientific validation.

After a curator explicitly completes and accepts an eligible PARAMETER source
record as an in-memory `CurationResult`, author the separate production target
without mutating or applying to a registry:

```python
from fungal_model import author_parameter_record, plan_registry_promotion

accepted = accepted_review.accepted_records[0]
source_identity = accepted.source_provenance
authored = author_parameter_record(
    accepted_review,
    source_record_id="proposed_sabiork_parameter_618_35622_kcat_cellobiose",
    parameter_record={
        "record_id": "sabiork_reaction_618_kcat_cellobiose",
        "name": "SABIO-RK Reaction 618 kcat for cellobiose",
        "maturity": "literature_processed",
        "provenance": {
            "source_database": source_identity["source_database"],
            "source_entry_ids": source_identity["source_entry_ids"],
            "source_reaction_ids": source_identity["source_reaction_ids"],
            "source_query": source_identity["source_query"],
            "source_field": source_identity["source_field"],
            "source_snapshot_path": source_identity["source_snapshot_path"],
            "source_url": source_identity["source_url"],
            "source_urls": source_identity["source_urls"],
            "source_snapshot_sha256": source_identity["source_snapshot_sha256"],
            "parameter_role": accepted.proposed_record["parameter_role"],
            "curator": "Researcher Name",
            "curation_date": "2026-07-14",
            "source_reaction_id": "618",
            "selected_kinlaw_entry_id": "35622",
        },
        "notes": "Identity transcription only; not validated science.",
        "parameter_symbol": "kcat_cellobiose",
        "process_type": "homogeneous_michaelis_menten",
        "enzyme_class": "beta_glucosidase",
        "substrate_class": "cellobiose",
        "fungus_id": "sabiork_beta_glucosidase_source",
        "substrate_id": "cellobiose",
        "environment_id": "sabiork_reaction_618_selected_conditions",
        "value": {
            "kind": "exact",
            "units": "s^(-1)",
            "value": 0.13,
            "lower": None,
            "upper": None,
            "distribution": None,
            "parameters": {},
            "source": "SABIO-RK Reaction 618 selected kinetic law",
            "confidence_level": "curator_accepted_identity_transcription_not_validation",
            "notes": "Not validation, calibration, or simulation authorization.",
        },
        "range_scope": "single_source_entry",
        "range_interpretation": "exact_identity_transcription_not_uncertainty",
        "allowed_use": "registry_storage_only_no_simulation_authorization",
    },
    registry_index="path/to/copied_registry/registry_index.yml",
)
authored.write("data/proposed_records/sabiork/authored_parameter")
plan = plan_registry_promotion(
    authored,
    registry_index="path/to/copied_registry/registry_index.yml",
)
```

`author_parameter_record(...)` accepts either a validated in-memory
`CurationResult` or a `LoadedCurationBundle` returned by
`load_curation_bundle(...)`. A loaded written source is reloaded from its owned
manifest at authoring time before the existing identity, frozen-source,
registry-context, loader-fidelity, storage-only, and no-mutation checks run.
Raw paths remain unsupported so callers cannot bypass the public loader. The
specialized result uses the existing deterministic, checksummed curation writer,
and either that written bundle or the in-memory result is consumable by
`plan_registry_promotion(...)` after authoring-digest, loader, registry-context,
selector, closed-summary, and exact reconstruction of the manifest, all three
decision YAML payloads, both decision CSV tables, and full report.
Removing the bridge marker or specialized summary labels cannot downgrade a
candidate with the intrinsic source/curator authoring provenance shape into a
generic promotion; apply independently rejects a legacy or reconstructed
generic plan unless the complete bridge audit, schema, digest, identity, and
closed safety policies revalidate. The shared classifier treats either reserved
`fungmod_parameter_bridge`/`fungmod_curation` namespace, including malformed
forms and distinctive nested source evidence, as non-simulation provenance;
ordinary outer `curator`, `curation_date`, or `parameter_role` fields alone do
not trigger the bridge contract. Public checksums establish internal consistency only; they
are not signatures or proof of curator authorship. Registry context binds the index plus the complete
registry file tree; selector audit binds resolved entity classes, exactly one
compatibility record, and the source/curator-authored runtime parameter-role
key. The source/acceptance evidence remains audit
metadata; only the complete curator-authored `ParameterRecord` is the
loader/promotion target. Identity transcription still requires type-exact value
and unit correspondence. Nonidentity transcription is admitted only when
`conversion_method` resolves in the versioned
`ParameterConversionRegistry`; the built-in
`pint_unit_conversion_decimal_places_half_even_12_v1` method parses explicit
source/target units with Pint, requires compatible dimensionality, recomputes
the converted float, and applies 12-decimal-place half-even rounding. Unknown
methods, unparseable or incompatible units, matching unit text, nonfinite
values, and curator-supplied results that disagree with recomputation fail
closed. The six index-backed non-parameter families, including product maps,
have a separate complete target authoring bridge. Product-map targets require
explicit state names and positive float coefficients; no source participant is
translated automatically. Automatic apply, scientific validation, and
automatic simulation authorization remain unsupported. CURATION-001 is
complete for its defined review, authoring, authentication,
promotion-planning, and transactional-apply scope; this completion does not
claim scientific validation. The curator-authored
outer provenance is a closed
parameter-authoring schema: complete
source identity and singular aliases, one explicit parameter role, curator and
date, plus the established optional kinetic-record path. Additional validation,
calibration, readiness, authorization, or nested claim metadata is rejected
rather than reconciled by name guessing.
The source adapter's `frozen_source_urls(...)` helper reads only adjacent local
fetch metadata and performs no network access. It reconciles `total_pages`,
`requests_made`, ordered `source_urls`, and, for immutable bundles, raw-page
count/order/page numbers, URLs, unique exact `raw/page_NNNN.json` paths, sizes,
and checksums. The
bridge revalidates that frozen URL identity during authoring and planning. One fetched URL requires the
same singular `source_url`; multiple ordered URLs require `source_url=None` and
the exact nonempty `source_urls` sequence. Its exact storage-only `allowed_use`
and its intrinsic bridge-derived provenance shape are enforced by one shared
admission predicate in modelability, parameter ranking, case
assembly, ensemble runtime, and chain-template resolution in every supported
mode, so an authored or later promoted record cannot authorize
`VirtualExperiment.simulate(...)`. Dynamic parameter searches in modelability,
ensemble runtime, deterministic case assembly, and result-table reconstruction
first apply one mode-aware eligibility predicate and then one complete ranking
key, including the calibrated-maturity tie-break. Admission uses exact closed
`allowed_use` values: scientific mode accepts only
`scientific_or_exploratory_when_all_other_inputs_are_valid`; exploratory and toy
modes additionally accept the named exploratory/screening and software-test
policies. Empty, unknown, negative, near-match, storage-only, and
bridge/curation-evidence policies fail closed before ranking.

Explicit CASE-001 chain mappings use their exact role-to-record IDs and one
shared resolver across preflight, ensemble/public simulation, deterministic
assembly, direct chain assembly, and result reconstruction. Each mapped role has
an exact symbol and selector contract. The outer process compatibility record
binds each ordered process-template ID to one exact component compatibility
record. Component `state_roles` then resolve through canonical `state_species`
enzyme-entity or substrate IDs; classes derive from those declared entities and
the registry, and must agree with enzyme capabilities and the bound component
compatibility. Process parameters and parameter-backed catalyst/substrate
initial states must match that independently resolved owning slot. Role/record
selectors are assertions only, and `component_selectors` shadow metadata is
rejected. Inventory membership or a mutually consistent rewrite of role
contracts, records, and selector assertions is insufficient. Null record entity
selectors may remain only where the record contract permits them; class
assertions must still match the bound component identity.
Component-process parameter ownership is derived from `process_templates`;
implemented direct process types also impose their canonical parameter fields,
so required roles cannot be truncated, renamed, or reused across fields before
role ownership is resolved. The configured outer substrate entity must be the
exact registry identity consumed by the outer substrate state; parking that ID
on an unused state does not satisfy the contract.
initial-state roles declare a
`record_process_type` scope without claiming a kinetic owner. Missing,
unauthorized, mode-ineligible, selector-incompatible, component-incompatible,
or process-incompatible records are rejected without dynamic fallback.

## Run A Virtual Experiment

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
)

result = study.simulate(mode="exploratory", n_samples=128)
```

Blocked or scientific-mode cases can be inspected without running a model:

```python
study.write_preflight_report(mode="scientific")
```

The standard output folder includes long-format time series, final states,
final metrics, threshold times, sampled parameters, summary metrics,
guarded screen-comparison summaries, uncertainty/range summaries,
trajectory quantile summaries,
configured thermodynamic diagnostics copied from existing per-sample
`thermodynamic_summary.json`/`.csv` artifacts when those artifacts are present,
configured conservation diagnostics copied from existing per-sample
`conservation_diagnostics.json`/`.csv` artifacts when those artifacts are present,
modelability item reports, assumption
summaries, mechanism summaries, provenance, limitations, missing-parameter and
suggested-experiment tables, and a versioned data dictionary/schema.
Preflight tables include machine-readable simulation policy columns such as
`simulation_allowed_for_mode`, `blocking_reason`, and
`recommended_next_action`.
Exploratory priors remain allowed, but the tables mark them as assumptions
rather than literature-curated values.
`comparison_summary.csv` indexes existing final-metric and threshold rows for
researcher-facing side-by-side inspection while preserving standard
environment comparison/ranking guardrails; metadata-only runtime environment
grids remain explicitly blocked from ranking or response-plot interpretation.
`uncertainty_summary.csv` summarizes existing sampled parameters and simulated
sample-output quantiles with explicit interpretation guardrails; it is not
validation, calibration, empirical confidence intervals, or an inferred
environment-response model.
`trajectory_quantiles.csv` summarizes existing `time_series_long.csv` sample
rows into p05/p50/p95 trajectory bands with explicit allowed-use and
interpretation guardrails; it is not validation data, calibration evidence,
empirical confidence intervals, posterior uncertainty, or new simulation
behavior.
`conservation_diagnostics.csv` copies existing per-sample configured-output
`conservation_diagnostics.json`/`.csv` fields into a standard
virtual-experiment table with explicit artifact-presence, allowed-use, and
interpretation guardrails. If no per-sample configured conservation artifacts
exist, the table remains header-only; it does not infer conserved quantities,
tolerances, pass/fail thresholds, validation evidence, chemistry,
thermodynamics, calibration, empirical comparison, or biology.
`thermodynamic_diagnostics.csv` copies existing per-sample configured-output
`thermodynamic_summary.json`/`.csv` fields into a standard virtual-experiment
table with explicit artifact-presence, entropy-budget, allowed-use, and
interpretation guardrails. If no configured thermodynamic artifacts exist, the
table remains header-only; it does not infer activities, reaction quotients,
concentrations, redox potentials, electron balances, validation evidence, or
solver-time thermodynamic enforcement.
`solver_diagnostics.csv` copies existing per-sample configured-output
`solver_diagnostics.json`/`.csv` fields into a standard virtual-experiment
table with explicit artifact-presence, metadata-availability, allowed-use, and
interpretation guardrails. If no per-sample configured solver diagnostics
artifacts exist, the table remains header-only; it does not change solver
behavior, infer scientific values, define numerical quality thresholds, add
validation/calibration evidence, compare against empirical data, enforce
thermodynamics, or add biology claims.
Configured output bundles also include `conservation_diagnostics.json` and
`conservation_diagnostics.csv` for explicit configured `mass_balance`
validators with `conserved_weights`; these rows copy weighted conserved totals
from existing state trajectories and are diagnostics only, not validation,
calibration, thresholding, solver enforcement, thermodynamics, or biological
evidence. If no such validator is configured, the JSON reports
`evaluated_count: 0` and the CSV remains header-only.
Configured output bundles also include `solver_diagnostics.json` and
`solver_diagnostics.csv` derived from existing configured run metadata, solver
settings, solver metadata, time-grid/evaluation counts, state counts, and
process counts only. If solver metadata is absent, the JSON reports
`status: unavailable` and the CSV remains header-only. These artifacts do not
change solver behavior, infer scientific values, define numerical quality
thresholds, add validation/calibration evidence, compare against empirical
data, or enforce thermodynamics.
When explicitly configured, bundles also include
`entropy_production_rate_timeseries.json` and
`entropy_production_rate_timeseries.csv`. These artifacts evaluate
`-DeltaG * extent_rate(t) / T` after simulation for a named configured process,
using its native `SimulationResult.process_rates` trajectory and only explicit
sourced metadata. Mass-, concentration-, or other non-molar native rates
require an explicit unit-bearing conversion to amount-of-substance per time.
Missing processes, undefined or incompatible units, nonpositive temperature,
and unsupported metadata fail explicitly. The artifacts do not infer dynamic
Delta G, activities, reaction quotients, concentrations, redox/electron
balances, validation evidence, or solver-time enforcement.
Quicklook plots include a presentation-only trajectory-band figure generated
from `trajectory_quantiles.csv`; it is for inspection, not validation or
calibration.
Quicklook plots also include a presentation-only degradation-rate figure
generated from existing `time_series_long.csv` `degradation_rate` rows; it is
for inspection, not validation, calibration, empirical comparison, or a new
rate law.
Results can also render a deterministic Markdown report from those standard
tables, including bounded degradation-rate and threshold-time inspection
sections plus a provenance/limitation decision summary over existing standard
rows, without adding validation or calibration claims. The decision summary
uses existing assumption, limitation, missing-parameter, suggested-experiment,
and provenance rows only; it is for inspection and planning next experiments,
not empirical comparison or inferred biology. Optional HTML artifacts can be
written beside the Markdown report for browser viewing: an HTML sidecar over
the same report and an index page that links existing report, table, manifest,
decision-support, and quicklook files without reinterpreting scientific values.
When it is pointed at a configured-output folder with existing
`conservation_diagnostics.json` and `conservation_diagnostics.csv`, it adds an
explicit conservation-diagnostics inspection section and links those artifacts
without inferring conserved quantities, tolerances, pass/fail thresholds,
validation evidence, chemistry, thermodynamics, calibration, empirical
comparison, or biology.
When the report utility is pointed at a configured-output folder that already
contains `thermodynamic_summary.json` and `thermodynamic_summary.csv`, it adds
an explicit thermodynamic-diagnostics inspection section and links those
artifacts without inferring activities, reaction quotients, concentrations,
redox chemistry, validation evidence, or solver-time thermodynamic enforcement.
The same section and report index expose configured
`entropy_production_rate_timeseries.json`/`.csv` artifacts when present, with
their process binding, provenance, units, status, and no-inference guardrails.
When it is pointed at a configured-output folder with existing
`solver_diagnostics.json` and `solver_diagnostics.csv`, it adds an explicit
solver-diagnostics inspection section and links those artifacts without
changing solver behavior, defining numerical quality thresholds, adding
validation/calibration evidence, comparing against empirical data, enforcing
thermodynamics, or adding biology claims:

```python
result.write_report("outputs/report/", include_html=True, include_index=True)
```

The scoped CASE-001 BIO-002 chain can also be run from researcher-facing names
and a runtime environment grid:

```python
from fungal_model import environment_grid, virtual_experiment

study = virtual_experiment(
    fungi="generic cellulase source",
    substrates="cellulose film",
    environments=environment_grid(
        temperature_C=[25, 30, 35],
        ph=[4.5, 5.0, 5.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(mode="exploratory", n_samples=1)
```

This CASE-001 path is exploratory and enzyme-chain/cellulose-equivalent only.
It is not whole-fungus growth, secretion, uptake, biomass, PET, lignin, full
lignocellulose, organism-specific physiology, or empirical validation. Runtime
environment-grid values are metadata unless an explicit response law or
condition-specific parameter record is active.

For a complete public-API walkthrough of guarded screen comparisons, report
artifacts, and metadata-only environment-grid limitations, see
`notebooks/examples/13_screen_comparison_summary_example.ipynb`.
For a public-API walkthrough of trajectory-quantile inspection and the
presentation-only trajectory-band quicklook, see
`notebooks/examples/14_trajectory_quantiles_example.ipynb`.
For a public-API walkthrough of the provenance/limitation decision summary and
decision-support report links, see
`notebooks/examples/15_provenance_limitations_report_example.ipynb`.
For a public-API walkthrough of the standard virtual-experiment thermodynamic
diagnostics table and header-only/artifact-copy guardrails, see
`notebooks/examples/16_thermodynamic_diagnostics_example.ipynb`.
For a public configured-workflow walkthrough of explicit
`temperature_arrhenius_reference` and `ph_gaussian` modifier outputs, see
`notebooks/examples/17_configured_environment_modifiers_example.ipynb`.
For a public configured-workflow walkthrough of explicit `oxygen_monod` and
`water_activity_threshold` modifier outputs, see
`notebooks/examples/18_configured_oxygen_water_modifiers_example.ipynb`.
For a public configured-workflow walkthrough of configured solver diagnostics
artifact inspection, report/index links, and the header-only/no-metadata
guardrail, see
`notebooks/examples/19_solver_diagnostics_example.ipynb`.

## Public API

The stable API is intentionally generic-first. These names are supported from
top-level `fungal_model` for researcher-facing virtual experiments, config
loading, model assembly, execution, and result inspection:

- `VirtualExperiment`
- `virtual_experiment`
- `EnvironmentGrid`
- `environment_grid`
- `EnvironmentCase`
- `DegradationScreenResult`
- `VirtualExperimentError`
- `source_proposal`
- `SourceProviderError`
- `review_source_proposal`
- `CurationDecision`
- `CurationResult`
- `CurationError`
- `load_curation_bundle`
- `LoadedCurationBundle`
- `ParameterConversionMethod`
- `ParameterConversionRegistry`
- `ParameterConversionError`
- `default_parameter_conversion_registry`
- `run_configured_model`
- `load_model_config`
- `load_substrate`
- `load_geometry`
- `load_product_map`
- `load_parameter_set`
- `ModelBuilder`
- `AssembledModel`
- `ProcessLibrary`
- `ProcessRegistry`
- `ProcessODESolver`
- `RunRequest`
- `SimulationResult`
- `Parameter`
- `ParameterSet`

The same virtual-experiment names are also available from `fungal_model.api`.
PET-specific convenience helpers are not part of the top-level public API.
They live under `fungal_model.plugins.pet`, where plugin users can explicitly
import `pet_substrate_loader_registry`, `PETSurfaceWorkflowConfig`, and
`run_pet_surface_integration`.

Former `process.as_reaction()` users should now choose one explicit path:
build process-centered models through `ModelBuilder`, `AssembledModel.run()`,
or `run_configured_model`; or construct a low-level
`fungal_model.chemistry.reactions.Reaction` directly when using
`SimulationEngine` or `ReactionDiffusionEngine1D`. Concrete `Process` classes
no longer provide a process-to-`Reaction` adapter bridge.

## Notebooks

The `notebooks/examples/` folder contains software-test notebooks for
configured workflow plumbing, configured thermodynamic-output inspection, and
researcher-facing exploratory examples for public virtual-experiment outputs.
These researcher-facing notebooks are not empirical validation:

- `00_quickstart.ipynb`
- `01_config_entity_inspection.ipynb`
- `02_failure_report.ipynb`
- `03_configured_outputs.ipynb`
- `10_virtual_experiment_product_tour.ipynb`
- `11_thermodynamics_entropy_diagnostics.ipynb`
- `12_reversible_product_inhibition_example.ipynb`
- `13_screen_comparison_summary_example.ipynb`
- `14_trajectory_quantiles_example.ipynb`
- `15_provenance_limitations_report_example.ipynb`
- `16_thermodynamic_diagnostics_example.ipynb`
- `17_configured_environment_modifiers_example.ipynb`
- `18_configured_oxygen_water_modifiers_example.ipynb`
- `19_solver_diagnostics_example.ipynb`

Notebook tests check that notebooks import `fungal_model`, avoid defining core
rate laws/classes or low-level solvers inline, and execute every foundation,
product-tour, and configured-output diagnostics smoke path. The thermodynamics notebook
uses configured explicit-Q Gibbs and entropy-production-rate metadata only and
inspects the configured entropy-budget JSON summary; it does not infer
activities, reaction quotients, concentrations, redox potentials, or
solver-time thermodynamic enforcement.
The virtual-experiment thermodynamic diagnostics notebook inspects
`thermodynamic_diagnostics.csv` and
`DegradationScreenResult.thermodynamic_diagnostics()` through public APIs,
including the header-only no-artifact case and a labelled copy of
package-generated configured summary artifacts. It does not infer activities,
reaction quotients, concentrations, redox potentials, electron balances,
validation evidence, or solver-time thermodynamic enforcement.
The product-inhibition notebook demonstrates the generic reversible
`1 / (1 + P / K_i)` modifier through the public virtual-experiment API and
standard output tables with an explicit exploratory example `K_i`; it is not
validation, calibration, toxicity, uptake, secretion, biomass, whole-fungus
physiology, or multi-product inhibition evidence.
Configured generic processes can also opt into existing
`temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
`water_activity_threshold` modifiers when the config supplies explicit
parameters and the environment defines the required temperature, pH, oxygen
concentration, or water-activity value. This is explicit configured framework
behavior, not inferred environment-response biology, calibration, validation,
or empirical comparison.
Registry case templates can bridge explicit modifier records into those same
configured paths for one-process templates and BIO-002-style chain process
templates when every parameter role resolves and an explicit environment id
provides exact registry values. Chain assembly does not infer missing
environment context or silently default values.
The configured environment-modifier notebook demonstrates this path with a
temporary artificial framework-benchmark config, then inspects package-generated
configured metadata, assumptions, merged parameters, entity snapshots, and
process rates for the pH/temperature slice. The configured oxygen and
water-activity modifier notebook demonstrates the explicit `oxygen_monod` and
`water_activity_threshold` path with temporary artificial framework-benchmark
config values, then inspects package-generated configured metadata,
assumptions, merged parameters, entity snapshots, input config, and process
rates. It does not fit response curves, validate biology, infer environment
responses, model oxygen consumption, gas transfer, redox balance, anaerobic
metabolism, substrate water binding, or change `EnvironmentGrid` behavior.
The configured solver-diagnostics notebook demonstrates package-generated
`solver_diagnostics.json` and `solver_diagnostics.csv` inspection for the
normal metadata path, report/index visibility, and the explicit header-only
JSON `status: unavailable` path when solver metadata is absent. It does not
change solver behavior, define numerical quality thresholds, add validation or
calibration evidence, compare against empirical data, enforce thermodynamics,
infer scientific values, or add biology claims.

## Data And Configs

Top-level YAML configs live under `data/model_configs/`, `data/fungi/`,
`data/substrates/`, `data/enzymes/`, `data/environments/`, `data/geometries/`,
`data/parameters/`, and `data/experiments/`. Loaders are exposed from
`fungal_model` as `load_fungus`, `load_substrate`, `load_enzyme`,
`load_environment`, `load_geometry`, and `load_parameter_set`.

Toy and synthetic assets in `data/` are software-test or example fixtures, not
scientific records. They remain available for tests and configured-workflow
examples, but researcher-facing work should start from the registry-backed
virtual-experiment API and inspect table provenance before interpreting any
output.

Internal software-test model-config shells include:

- `data/model_configs/toy_homogeneous_ab.yml`
- `data/model_configs/toy_surface_pet_plugin.yml`
- `data/model_configs/toy_surface_dummy_non_pet.yml`
- `data/model_configs/toy_surface_dummy_non_pet_product_inhibition.yml`

All four load through `load_model_config`. They are framework benchmarks, not
scientific biology or validation evidence.

Product maps live under `data/product_maps/` and are loaded through
`load_product_map`. They carry configured state names and benchmark maturity
metadata, so product release mappings do not have to be embedded in process
code or a substrate-specific workflow.

Source discovery is intentionally separate from simulation. The top-level
`source_proposal(...)` API composes the existing `SabioRKSource` parser and
proposal behavior. Frozen SABIO-RK kinetic-law snapshots remain the default;
live refresh is explicit and uses immutable query-specific bundles with raw
page checksums and a separate derived combined export. Proposed product maps,
parameter records, and process-compatibility records are written for human
review under a proposal bundle; they are not silently committed into the
simulation registry. SABIO parameter proposals now include an explicit
`parameter_role` aligned with runtime compatibility roles; the SABIO `Km`
symbol role is normalized to runtime key `km`. This changes proposal payloads
in addition to preserving exact frozen source URLs, but does not change source
values, units, process laws, or scientific maturity. Use
`scripts/fetch_sabiork_kinlaw_entries.py` to freeze raw SABIO-RK exports and
`scripts/propose_sabiork_source_records.py` to create review-only proposal
artifacts from a frozen snapshot.

The top-level `review_source_proposal(...)` API validates either the in-memory
`RegistryProposal` or its written manifest through the same curation path. It
writes deterministic review CSV/YAML/report/checksum artifacts, requires
complete curator metadata for every explicit decision, validates record types
and content without inferring conversion data, and defaults every omitted
decision to deferred. Repeated writes replace only an existing curation folder
with the expected owned manifest kind/version. The top-level
`plan_registry_promotion(...)` API now verifies explicit accepts, resolves only
index-declared destinations, classifies no-op/conflict/unsupported cases, and
validates exact prospective YAML through a temporary full-registry copy. Each
accepted record is rechecked for unresolved curation blockers and complete
source provenance. Each would-be add also has to round-trip faithfully and with
type-exact scalar values through its actual target loader; silently dropped,
synthesized/defaulted, or type-converted fields are blocked. Exact duplicates
are compared against raw stored content with the same scalar-type fidelity.
Owned review output cannot overlap a registry root in either direction, and a
write rechecks the immutable plan digest before touching its destination. The
top-level `apply_registry_promotion(...)` API now supplies the separately
reviewed digest-confirmed transaction, exact-next-patch version policy,
full-root staging, single-writer lock, rollback, and structured apply result.
This completed the bounded transactional-apply contract when PR-47 merged as
PR #62 (`b1ebb860`),
without making promoted records scientifically validated or automatically
simulation-authorized. The top-level `author_parameter_record(...)` API adds
the separate PARAMETER-specific source-to-production bridge over accepted
in-memory or checksum-loaded curation, including the one registered
nonidentity unit-conversion policy. Its checksummed output remains planning
input, not an apply instruction. Its exact storage-only policy is a simulation
blocker in every modelability mode. The top-level
`author_registry_records(...)` API separately authors the six index-backed
non-parameter families, including product maps, without inferred fields or
authoring/planning mutation. `AuthenticatedCurationBundle` adds opt-in
caller-trusted Ed25519 verification and revalidation at authoring/planning
boundaries. CURATION-001 is complete for that defined curation workflow, not
for scientific validation or automatic simulation authorization.

Foundation process configs can be built through `ProcessLibrary.default_foundation()`.
The current library provides factories for first-order, mass-action,
homogeneous Michaelis-Menten, and generic surface-catalysis benchmark
processes. These are framework mechanisms, not organism- or substrate-specific
biology.

Assembled process models now support native well-mixed execution through
`AssembledModel.run()`. The method delegates to `ProcessODESolver`, returns a
standard `SimulationResult`, records process-rate trajectories, runs supplied
validators, and rejects unsupported geometry instead of silently switching
execution paths.

Substrate, geometry, product-map, and validator loading now goes through
registries. The default substrate registry is generic-first and supports
foundation benchmark substrates such as `generic_solid` and
`generic_dissolved`. PET substrate loading is available only through the
explicit PET plugin registry:

```python
from fungal_model import load_substrate
from fungal_model.plugins.pet import pet_substrate_loader_registry

substrate = load_substrate(
    "data/substrates/pet_film.yml",
    registry=pet_substrate_loader_registry(),
)
```

Configs are intentionally provenance-heavy. Top-level records and parameter
entries must include source, measurement method, confidence, notes, validity
range, units, and value fields. Unknown scientific values should be written as
`value: null`; loaders preserve them as explicit unknown parameters.

## Integration Workflow

The generic configured-model API is the public workflow entry point:

```python
from fungal_model import load_model_config, run_configured_model

config = load_model_config("path/to/model_config.yml")
result = run_configured_model("path/to/model_config.yml")
```

`run_configured_model` now loads entities through registries, merges configured
and entity parameter sets, builds processes through `ProcessLibrary`, assembles
a `ModelBuilder`, executes through `AssembledModel.run()`, validates the
`SimulationResult`, and saves the standard output bundle when an output
directory is configured.

Configured output folders include the core `SimulationResult` files plus
configuration-facing artifacts:

- `input_model_config.json`
- `configured_model_run.json`
- `configured_metadata.json`
- `process_build_decisions.json`
- `initial_state.json`
- `time_grid.json`
- `validators.json`
- `conservation_diagnostics.json`
- `conservation_diagnostics.csv`
- `solver_diagnostics.json`
- `solver_diagnostics.csv`
- optional `entropy_production_rate_timeseries.json`
- optional `entropy_production_rate_timeseries.csv`
- `merged_parameters.json`
- `solver_settings.json`
- `entity_snapshots/`
- `output_manifest.json`

Plugin-backed configured runs use explicit registry injection. The bundled PET
plugin config is an internal software-test fixture, not a scientific PET
degradation record.

The older PET convenience entry point now lives under
`fungal_model.plugins.pet` and delegates to `run_configured_model`; the generic
`fungal_model.workflows` package stays substrate-neutral.

## Current Limitations

Current capability labels mean:

- `implemented`: code exists for the stated scope.
- `technically verified`: repository tests prove the software contract, not the
  empirical biology.
- `exploratory`: outputs are provenance-labelled assumptions, priors, ranges,
  or controlled pilots.
- `scientifically validated`: empirical validation data support the prediction
  claim. FungMod does not currently bundle publication-grade validation for
  arbitrary fungus/substrate/environment predictions.
- `unsupported`: the mechanism or workflow should fail explicitly or remain
  documented as future work.

- Well-mixed ODE systems and an initial 1D reaction-diffusion engine are supported.
- Michaelis-Menten kinetics currently means homogeneous dissolved-substrate kinetics only.
- PET surface hydrolysis currently uses a minimal equilibrium Langmuir coverage model with constant accessible surface area.
- PET product release is represented as a lumped mass-equivalent hydrolysate in the Stage 4 example, not resolved MHET/BHET/TPA/EG chemistry.
- Temperature scaling currently uses Arrhenius acceleration only; enzyme thermal deactivation is recorded as a limitation and is not implemented.
- pH activity currently uses an empirical Gaussian profile; mechanistic ionization chemistry is not implemented.
- Fungal growth currently uses a simple assimilable-product uptake law; oxygen, transporters, toxicity, regulation, and intracellular metabolism are not modelled.
- Enzyme production has an explicit active-biomass cost, but the cost parameter is lumped and must be sourced before scientific use.
- Stage 7 oxygen handling is currently a validation check against available oxygen, not a coupled oxygen state in the ODE model.
- Optional single-process dynamic Gibbs constraints can block unfavorable
  configured forward rates when all molar activity, reaction, electron/redox,
  constant, tolerance, and provenance inputs are explicit. Coupled-network,
  reverse-rate, nonideal-activity, and electrochemical thermodynamics remain
  unsupported.
- Spatial modelling is currently 1D finite-volume method-of-lines only.
- Stage 8 diffusion fields are unit-aware, but geometry is a simple uniform 1D grid; 2D, variable geometry, and true volume/area coupling are not implemented.
- PET is marked `partial`. Cellulose has narrow registry-backed exploratory
  BIO-001/BIO-002 surface and enzyme-chain paths, but the generic
  `CelluloseSubstrate` class remains Stage 9 placeholder metadata and is not a
  validated default cellulose-degradation model. Lignin, starch, and chitin
  remain Stage 9 placeholder metadata classes with unknown physical parameters
  and no default degradation model.
- Universal substrate modules record bond classes, required enzyme classes, and product classes, but they do not implement substrate-specific kinetics, accessibility models, thermodynamic constraints, or assimilation evidence.
- Calibration utilities are generic least-squares tools; no literature data are bundled and no parameters are calibrated by default.
- Monte Carlo and local sensitivity utilities require explicit uncertainty/perturbation specifications; Bayesian calibration and global sensitivity are not implemented.
- `AssembledModel.run()` currently supports well-mixed process ODE execution;
  unsupported geometry fails before simulation.
- The generic configured workflow currently supports foundation process
  factories and well-mixed execution; unsupported process types and geometry
  fail before simulation.
- The standardized `results.SimulationResult` is native output for
  `AssembledModel.run()` and is also produced by explicit low-level reaction
  and reaction-diffusion APIs when those APIs are invoked directly.
- Generic surface catalysis now exists, and PET composes it through a PET
  accessibility adapter, but resolved PET product chemistry and dynamic
  morphology remain future work.
- Geometry abstractions currently wrap well-mixed and 1D film cases; particle,
  slab, and porous-medium geometries are honest metadata placeholders.
- Enzyme/fungus compatibility matching checks declared capabilities, but it
  does not yet auto-build full living-fungus ODE systems from entities.
- The PET plugin convenience helper is a deprecated compatibility slice; the
  generic configured workflow is the main foundation path.
- PET must not be treated with the homogeneous Michaelis-Menten layer except as an explicitly labelled artificial benchmark.
- The reaction engine assumes each reaction rate can be converted into every affected species unit per simulation time unit.
- Mass-balance validation requires the caller to provide conserved weights when species do not share directly compatible units.
- Solver tolerances are numerical settings, not physical parameters, and are recorded in the simulation record.
