# ASSEMBLY-001: Config-Driven Registry Case Assembly

## Status

Complete for arbitrary onboarding of reactions supported by the implemented
homogeneous Michaelis-Menten process law after PR-55 and for template-backed
surface plus explicit linear, branching, and cyclic enzyme-pathway assembly
after PR-56.

ASSEMBLY-001 moves case-specific assembly metadata for the current registry-run
cases into explicit registry case templates. The change is architectural only:
it does not fetch data, add biology, or make missing parameters scientifically
valid.

## What Moved Out Of Python Branches

The following per-case wiring now lives in
`data_registry/case_templates/case_templates.yml`:

- state role to state-name mappings;
- initial-state mappings from parameter roles or literal starting values;
- product-map IDs and substrate/product state bindings;
- stoichiometric-yield metadata;
- time-grid defaults;
- observable and output-state roles;
- process-state metadata such as surface bond type and accessible-site-pool label;
- case-template limitations and validity notes.

`src/fungal_model/screening/case_builder.py` now selects a template through
`ProcessCompatibilityRecord.case_template_id` and uses template data when
building Reaction 618 and BIO-001 configs. PR-55 removes all Reaction 618,
cellobiose, beta-glucosidase, and SABIO-RK tokens from the generic case builder
and proves the same supported homogeneous law with a materially different
artificial reaction fixture.

## Template Schema Fields

Case templates are first-class registry records with schema version `1`.

Required fields:

- `case_template_id`
- `schema_version`
- `process_type`
- `state_roles`
- `initial_state_mapping`
- `product_map`
- `stoichiometric_yields`
- `time_grid`
- `observable_roles`
- `output_state_roles`
- `limitations`
- `validity_notes`

Supported optional extension field:

- `process_state_metadata`

Unsupported top-level fields fail during registry loading. Invalid state roles,
invalid time grids, invalid product maps, and process-type mismatches fail with
explicit validation or assembly errors.

## Reaction 618 Representation

`sabiork_reaction_618_homogeneous_mm_template` defines:

- process type: `homogeneous_michaelis_menten`;
- substrate state: `cellobiose_concentration`;
- product state: `beta_D_glucose_concentration`;
- enzyme state: `beta_glucosidase_concentration`;
- product-map metadata from cellobiose to beta-D-glucose with yield `2.0`;
- initial substrate/enzyme values from registry parameter roles;
- initial product value `0.0` using substrate units;
- the legacy runtime grid `0..1000 second`, `101` points.

The stoichiometric yield is recorded as template metadata and as a loaded
product-map entity used by the generic configured contribution path. PR-55
changes only where existing reaction-specific assembly metadata is owned, so
Reaction 618 numerical outputs remain unchanged.

## BIO-001 Representation

`bio001_cellulose_surface_catalysis_template` defines:

- process type: `surface_catalysis`;
- substrate state: `solid_substrate_remaining`;
- product state: `soluble_product_amount`;
- catalyst state: `free_enzyme_concentration`;
- accessibility proxy output: `accessible_site_fraction_remaining_proxy`;
- mass-equivalent one-to-one product-map metadata;
- initial substrate and enzyme values from exploratory parameter roles;
- initial product value `0.0` using substrate units;
- surface bond type and accessible-site-pool label;
- the legacy runtime grid `0..4000 second`, `81` points.

The BIO-001 template remains an exploratory assembly description. It is not a
whole-fungus model and does not add secretion, uptake, biomass growth, oxygen
limitation, or morphology dynamics.

## Process-Law Boundaries That Remain

Some process-law-specific scaffolding intentionally remains in Python:

- how homogeneous Michaelis-Menten and surface-catalysis configs are shaped;
- entity helper data for substrate, enzyme, and geometry config sections;
- provenance text for the current milestones;
- model mode and maturity selection for the existing deterministic builders;
- validator selection and mass-balance weights;
- derived output metric formulas in `result_tables.py`;
- the homogeneous process rate law and generic product-map contribution
  semantics.

PR-55 makes homogeneous request modes and all per-reaction config, process,
parameter-set, product-map, entity, state, time-grid, provenance, and output
identities explicit. Missing process identity or provenance fails rather than
using a Reaction 618 fallback. These remaining items are implemented
process/foundation responsibilities rather than per-reaction branches.

## Output Table Changes

Output tables now prefer `case_template.output_state_roles` when deriving
biological state roles from sample configs. They fall back to process-state
inspection for compatibility with older configs.

The provenance table now includes the `case_template` record. The limitations
table includes case-template limitations and validity notes.

## Tests Added

Added:

- `tests/test_registry_case_templates.py`
- `tests/test_config_driven_case_assembly.py`

Coverage includes template loading, invalid template failures, missing-template
selection, process-type/mode mismatch, Reaction 618 assembly/simulation,
BIO-001 assembly/simulation, a materially different artificial homogeneous
reaction, missing process identity, output role preservation, no runtime
registry mutation, reaction-token hardcoding guardrails, and a network-call
guard.

## Scientific Limitations

Templates describe assembly only. They do not:

- create parameter evidence;
- make exploratory priors literature-curated;
- resolve missing selected-entry enzyme concentration for Reaction 618;
- create environmental response models;
- create product uptake, biomass, secretion, or whole-fungus biology;
- implement dynamic surface accessibility or morphology changes.

## Adding More Supported Reactions

Adding another reaction that uses an already implemented homogeneous
Michaelis-Menten law requires:

- curated local reaction/product/parameter records;
- reviewed product-map semantics for the process law being used;
- explicit parameter-role mappings in process compatibility records;
- a case template with validated state roles, initial-state mapping, product
  map, time grid, output roles, and limitations;
- tests proving that registry assembly does not require new Python branches for
  state names, product states, or time grids;
- explicit config, process, parameter-set, and product-map identities in
  `process_state_metadata`;
- explicit provenance source and confidence metadata.

Pathway templates additionally require an explicit `topology_type`, distinct
process-owned product maps, directed state-role edges with one implemented
rate-law input and one or more explicit products, conservation weights, and
graph semantics that match the declared linear, branching, or cyclic shape.

An unsupported rate law remains an explicit blocker and requires a separately
provenance-backed, maturity-labelled, tested mechanism implementation. This
contract does not make artificial fixtures scientific or authorize arbitrary
biology.
