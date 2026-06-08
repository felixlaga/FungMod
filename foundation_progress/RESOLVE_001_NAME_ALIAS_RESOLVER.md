# RESOLVE-001 Name And Alias Resolver

## Status

Implemented.

RESOLVE-001 adds a strict, registry-backed resolver so researcher-facing
virtual-experiment code can use curated names and aliases without memorizing
internal registry IDs.

## Added Functionality

The new `RegistryResolver` resolves:

- fungus/source records;
- substrate records;
- environment records;
- enzyme-class records;
- unambiguous records across all supported types through `resolve_any`.

Resolution checks:

- exact registry ID;
- canonical `name`;
- optional `display_name`;
- optional `scientific_name`;
- optional `aliases`;
- optional `ec_number` for enzyme-class records;
- optional `database_ids` and string `external_refs`.

Matching is exact first, then case-insensitive exact matching. Fuzzy matching is
not enabled.

## Record Types With Aliases

Aliases are data fields on registry records, not hardcoded Python lookup tables.
The current registry includes conservative aliases for existing records only:

- `sabiork_beta_glucosidase_source`;
- `generic_cellulase_source`;
- `cellobiose`;
- `cellulose_film_generic`;
- `sabiork_reaction_618_selected_conditions`;
- `bio001_cellulose_surface_pilot_environment`;
- `cellulase_generic`;
- `beta_glucosidase`.

No new biological records, mechanisms, or datasets were added.

## Researcher-Facing Usage

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_names(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose substrate"],
    environments=["30C_pH5_assay"],
)
```

Equivalent opt-in form:

```python
study = VirtualExperiment.from_registry(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose substrate"],
    environments=["30C_pH5_assay"],
    resolve_names=True,
)
```

Existing ID-based code still works unchanged:

```python
study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
)
```

## Ambiguity Handling

Resolution is strict:

- exactly one match returns a `ResolvedRecord`;
- no match raises `ResolutionError`;
- multiple matches raise `AmbiguousResolutionError` with candidate records.

The resolver never silently chooses between multiple biological records.

## Deliberately Not Supported Yet

- default fuzzy matching;
- automatic SABIO-RK or external API fetches when a name is unknown;
- automatic promotion of SOURCE-001 proposed records into the simulation
  registry;
- new biology to make examples work;
- interpretation of oxygen labels where the environment record does not encode
  oxygen.

For that reason, the SABIO-RK selected-condition alias is `30C_pH5_assay`, not
`30C_pH5_aerobic`.

## Remaining Limitations

- Aliases are currently sparse and cover only existing common records.
- Alias uniqueness is enforced at resolution time, not as a registry load-time
  invariant.
- Cross-registry alias management and curated synonym provenance remain future
  work.

## Next Phase

The next recommended phase is ASSEMBLY-001: move case-specific model assembly
details out of Python branches and into registry/config schemas.
