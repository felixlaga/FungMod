"""Registry-driven whole-culture physiology case assembly.

A ``culture_physiology`` case template composes generic process laws (substrate
conversion coupled to biomass formation through an explicit yield, biomass
loss, producer-proportional enzyme synthesis, enzyme inactivation) into one
well-mixed organism case. Every state, parameter role, stoichiometric
coefficient and closure weight is declared by the template and resolved from
registry parameter records; nothing is inferred from the organism's name.

The assembler is organism-, substrate- and enzyme-agnostic. Organism identity
lives in the registry records bound through the process-compatibility record;
the template only names roles. The number of enzyme pools, their names and
their units are whatever the template declares: a process template may state
its ``rate_units`` as a fixed parameter or derive them from a state role
(``rate_units_from_state_role``: the units of that state's initial record per
unit of the template's time grid), so that one template serves cases whose
records state their pools in different units. ``geometry`` is required and is
either a well-mixed geometry mapping or an explicit ``null`` for a
concentration-only model that claims no vessel (as the enzyme-kinetics
assemblers do).

The composition itself (``build_composed_process_config_data``) is shared with
other template-declared compositions of generic process laws, such as the
``enzyme_network`` of several enzyme classes acting together
(``fungal_model.screening.enzyme_network``): the outer process type, its
non-negativity validator id and the fallback config name are its only
parameters. A process template may bind the existing ``product_inhibition``,
``competitive_inhibition`` and ``substrate_reactivity`` modifiers and the
environment-response modifiers; state roles of a modifier are named by keys
ending in ``_state_role`` and parameter roles by other keys ending in ``_role``.
A process template may name the ``enzyme_class`` it stands for; that name is
output metadata only (``process_enzyme_classes`` of the assembled case-template
config, written only when a template names one) and no process law reads it.

A product-map coefficient bound to a parameter record (``parameter_role``)
whose units are not dimensionless carries those units: it converts an amount of
the reactant into an amount of the product stated on another basis (for
example ``mmol/g``), and the coefficient times the reactant's units must have
the product state's dimension. A closure weight may then carry units as a
``{value, units}`` mapping, so that every weighted state is summed in one
ledger dimension through the stated conversion; the conservation check of each
product map runs in pint whenever a weight or coefficient carries units. An
initial state may take its units from ``units_from_roles``: the product of the
units of those roles' records, simplified by pint (for example a dry mass per
volume times an amount per dry mass gives an amount per volume). Nothing is
converted by a molar mass or any constant the template does not state.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from typing import Any

from fungal_model.core.units import Q_
from fungal_model.modifiers.reactivity import SUBSTRATE_REACTIVITY_MODIFIER_TYPE
from fungal_model.processes import ProcessLibrary
from fungal_model.registry.records import (
    CaseTemplateRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
)
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    _canonical_template_text,
    _case_template_config,
    _initial_state_from_template,
    _record_exact_value,
    _record_units,
    _scientific_parameter_config,
    _template_config_name,
    _template_parameter_record,
    _template_state,
    _template_time_config,
    _template_units_from_roles,
)
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_TYPES,
    build_template_environment_entity,
    build_template_environment_modifier,
)

CULTURE_PHYSIOLOGY_PROCESS_TYPE = "culture_physiology"
# The modifier type of the existing provenance-bound competitive-inhibition law (``modifiers.enzyme_inhibition``).
COMPETITIVE_INHIBITION_MODIFIER_TYPE = "competitive_inhibition"
CULTURE_PHYSIOLOGY_REQUIRED_STATE_ROLES = ("substrate", "biomass")
CULTURE_PHYSIOLOGY_REQUIRED_PROCESS_STATE_METADATA = (
    "config_name",
    "config_mode",
    "config_maturity",
    "parameter_set_id",
)
_STATE_SPECIES_ENTITY_TYPES = frozenset({"organism", "substrate", "product", "enzyme", "ledger"})
_COEFFICIENT_REFERENCE_FIELDS = frozenset({"parameter_role", "complement_of_parameter_role"})
_PROCESS_TEMPLATE_FIELDS = frozenset(
    {
        "id",
        "process_type",
        "state_roles",
        "fixed_states",
        "parameter_roles",
        "fixed_parameters",
        "product_map",
        "modifiers",
        "assumptions",
        "rate_units_from_state_role",
        "enzyme_class",
        "stoichiometry",
        "extent_state",
    }
)


def build_culture_physiology_config_data(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    substrate: SubstrateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    """Build raw model-config data for one culture-physiology registry case."""

    return build_composed_process_config_data(
        process_type=CULTURE_PHYSIOLOGY_PROCESS_TYPE,
        non_negative_validator_id="non_negative_culture_states",
        fallback_label="culture physiology case",
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        substrate=substrate,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        output_directory=output_directory,
    )


def build_composed_process_config_data(
    *,
    process_type: str,
    non_negative_validator_id: str,
    fallback_label: str,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    substrate: SubstrateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    """Build raw model-config data for a template-declared composition of generic process laws.

    ``process_type`` is the outer process type the template must declare (for
    example ``culture_physiology``); every inner process, product map, state
    species, closure weight and modifier comes from the template and its
    resolved parameter records. ``non_negative_validator_id`` names the
    non-negativity validator of every template state, and ``fallback_label``
    starts the config name when the template gives none.
    """

    del substrate  # The template's own entities describe every substrate the composition uses.
    metadata = case_template.process_state_metadata
    template_id = case_template.case_template_id
    if case_template.process_type != process_type:
        raise RegistryCaseBuildError(f"Case template {template_id!r} must use process_type={process_type!r}.")
    mode = str(metadata.get("config_mode", ""))
    if mode not in {"toy", "exploratory", "scientific"}:
        raise RegistryCaseBuildError(
            f"Case template {template_id!r} config_mode {mode!r} must be toy, exploratory, or scientific."
        )
    state_roles = dict(case_template.state_roles)
    state_units = _state_units(case_template, parameter_records=parameter_records)
    product_maps = _product_map_specs(case_template, parameter_records=parameter_records)
    process_specs = _process_template_specs(case_template, product_map_ids=frozenset(product_maps))
    # Resolve record-backed closure weights before the existing unit-aware check.
    raw_conservation = deepcopy(dict(case_template.process_state_metadata.get("conservation", {})))
    raw_weights = raw_conservation.get("state_weights", {})
    resolved_weights = {role: _record_coefficient(value, parameter_records=parameter_records) for role, value in raw_weights.items()}
    if resolved_weights != raw_weights:
        case_template = replace(case_template, process_state_metadata={**case_template.process_state_metadata,
            "conservation": {**raw_conservation, "state_weights": resolved_weights}})
    conservation = _conservation_spec(case_template, state_units=state_units, product_maps=product_maps)
    extra_conservation = []
    for extra in metadata.get("additional_conservation", ()):
        extra_template = replace(case_template, process_state_metadata={**metadata, "conservation": extra})
        extra_conservation.append(_conservation_spec(extra_template, state_units=state_units, product_maps={}))
    _require_every_role_used(
        case_template,
        parameter_records=parameter_records,
        process_specs=process_specs,
        product_maps=product_maps,
    )
    state_species = _state_species(case_template)
    fungus = registry.get_fungus(fungus_id)
    environment = registry.get_environment(environment_id)
    provenance = _provenance(
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        environment_conditions={name: value.to_dict() for name, value in environment.conditions.items()},
        organism={
            "fungus_id": fungus.record_id,
            "name": fungus.name,
            "scientific_name": fungus.scientific_name,
            "display_name": fungus.display_name,
        },
    )
    processes = [
        _process_config(
            spec,
            case_template=case_template,
            parameter_records=parameter_records,
            registry=registry,
            environment_id=environment_id,
            state_units=state_units,
        )
        for spec in process_specs
    ]
    entities = _entities(
        case_template,
        product_maps=product_maps,
        processes=processes,
        registry=registry,
        environment_id=environment_id,
    )
    case_template_config = _case_template_config(case_template)
    case_template_config.update(
        {
            "organism": provenance["organism"],
            "state_species": state_species,
            "conservation": {
                "id": conservation["id"],
                "closed_system": conservation["closed_system"],
                "state_weights": conservation["state_weights"],
            },
            "process_ids": [process["id"] for process in processes],
        }
    )
    if metadata.get("mechanism_sources"):
        case_template_config["mechanism_sources"] = list(metadata["mechanism_sources"])
        provenance["mechanism_sources"] = list(metadata["mechanism_sources"])
        provenance["mechanism_maturity"] = "software_tested"
    enzyme_classes = {
        str(spec["id"]): str(spec["enzyme_class"]) for spec in process_specs if spec.get("enzyme_class") is not None
    }
    if enzyme_classes:
        # Output metadata only: which enzyme class each process stands for (the process laws never read it).
        case_template_config["process_enzyme_classes"] = enzyme_classes
    return {
        "kind": "model_config",
        "name": _template_config_name(
            case_template=case_template,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            fallback=f"{fallback_label} {fungus_id} on {substrate_id}",
        ),
        "mode": mode,
        "maturity": str(metadata["config_maturity"]),
        "provenance": provenance,
        "case_template": case_template_config,
        "entities": entities,
        "parameters": [
            {
                "id": str(metadata["parameter_set_id"]),
                "parameters": [
                    _scientific_parameter_config(record, role=role)
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": processes,
        **({"metric_definitions": deepcopy(metadata["metric_definitions"])} if metadata.get("metric_definitions") else {}),
        **({"state_domains": {_template_state(case_template, str(role)): domain for role, domain in metadata["state_domains"].items()}} if metadata.get("state_domains") else {}),
        "initial_state": _initial_state_from_template(
            case_template=case_template,
            parameter_records=parameter_records,
        ),
        "time": _template_time_config(case_template),
        "validators": [
            {
                "id": non_negative_validator_id,
                "validator_type": "non_negative",
                "species": [name for role, name in state_roles.items() if metadata.get("state_domains", {}).get(role) != "signed"],
            },
            {
                "id": conservation["id"],
                "validator_type": "mass_balance",
                "closed_system": conservation["closed_system"],
                "conserved_weights": conservation["state_weights"],
            },
            *[{"id": extra["id"], "validator_type": "mass_balance", "closed_system": extra["closed_system"], "conserved_weights": extra["state_weights"]} for extra in extra_conservation],
        ],
        "outputs": {
            "directory": output_directory
            or f"outputs/registry_cases/{fungus_id}__{substrate_id}__{environment_id}",
            "save": ["record", "validation_report"],
            "plots": ["state_trajectories"],
        },
    }


def _state_units(
    template: CaseTemplateRecord,
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, str]:
    units: dict[str, str] = {}
    for role, state_name in template.state_roles.items():
        spec = template.initial_state_mapping.get(role)
        if not isinstance(spec, Mapping):
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} state role {role!r} lacks an initial_state_mapping entry."
            )
        units_from_role = spec.get("units_from_role")
        if units_from_role is not None:
            units[state_name] = _record_units(
                _template_parameter_record(parameter_records, str(units_from_role)),
                role=str(units_from_role),
            )
        elif spec.get("units_from_roles") is not None:
            units[state_name] = _template_units_from_roles(spec["units_from_roles"], parameter_records=parameter_records)
        else:
            units[state_name] = str(spec["units"])
    return units


def _product_map_specs(
    template: CaseTemplateRecord,
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, dict[str, Any]]:
    raw_maps = template.process_state_metadata.get("product_maps", [])
    if not isinstance(raw_maps, Sequence) or isinstance(raw_maps, (str, bytes)):
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} product_maps must be a sequence."
        )
    specs: dict[str, dict[str, Any]] = {}
    for raw in raw_maps:
        if not isinstance(raw, Mapping):
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} product_maps entries must be mappings."
            )
        map_id = _required_text(raw, "id", label=f"Case template {template.case_template_id!r} product map")
        if map_id in specs:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} repeats product map id {map_id!r}."
            )
        if str(raw.get("product_map_type", "")) != "stoichiometric":
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} product map {map_id!r} must be stoichiometric."
            )
        reactants = _coefficients(
            raw.get("reactants"),
            template=template,
            map_id=map_id,
            side="reactants",
            parameter_records=parameter_records,
        )
        products = _coefficients(
            raw.get("products"),
            template=template,
            map_id=map_id,
            side="products",
            parameter_records=parameter_records,
        )
        if not reactants["coefficients"] or not products["coefficients"]:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} product map {map_id!r} needs reactants and products."
            )
        if reactants["units"]:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} product map {map_id!r} binds a reactant coefficient to "
                f"a record with units ({', '.join(sorted(reactants['units']))}); reactant coefficients are pure "
                "numbers, and a conversion between bases belongs to a product coefficient."
            )
        specs[map_id] = {
            "id": map_id,
            "name": str(raw.get("name", map_id)),
            "notes": str(raw.get("notes", "")),
            "reactants": reactants["coefficients"],
            "products": products["coefficients"],
            "parameter_roles": tuple((*reactants["roles"], *products["roles"])),
            "coefficient_provenance": {**reactants["provenance"], **products["provenance"]},
            "coefficient_bindings": dict(products["bindings"]),
            "coefficient_units": dict(products["units"]),
        }
    return specs


def _coefficients(
    value: Any,
    *,
    template: CaseTemplateRecord,
    map_id: str,
    side: str,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} product map {map_id!r} {side} must be a non-empty mapping."
        )
    coefficients: dict[str, float] = {}
    roles: list[str] = []
    provenance: dict[str, str] = {}
    bindings: dict[str, dict[str, Any]] = {}
    units: dict[str, str] = {}
    for role, raw_coefficient in value.items():
        state_name = _template_state(template, str(role))
        if isinstance(raw_coefficient, Mapping):
            fields = set(raw_coefficient)
            if len(fields) != 1 or not fields <= _COEFFICIENT_REFERENCE_FIELDS:
                raise RegistryCaseBuildError(
                    f"Case template {template.case_template_id!r} product map {map_id!r} {side}.{role} must use "
                    "exactly one of parameter_role or complement_of_parameter_role."
                )
            field = next(iter(fields))
            parameter_role = str(raw_coefficient[field])
            record = _template_parameter_record(parameter_records, parameter_role)
            numeric = _record_exact_value(record, role=parameter_role)
            record_units = _dimensional_record_units(record, role=parameter_role)
            if record_units is None:
                numeric = _plain_fraction(numeric, record, role=parameter_role)
            if record_units is not None:
                if field == "complement_of_parameter_role":
                    raise RegistryCaseBuildError(
                        f"Case template {template.case_template_id!r} product map {map_id!r} {side}.{role} takes the "
                        f"complement of role {parameter_role!r}, whose record has units {record_units!r}; a complement "
                        "needs a dimensionless fraction."
                    )
                # A dimensional record keeps its units: the coefficient converts between two bases.
                units[state_name] = record_units
            if field == "complement_of_parameter_role":
                if not 0.0 <= numeric <= 1.0:
                    raise RegistryCaseBuildError(
                        f"Case template {template.case_template_id!r} product map {map_id!r} {side}.{role} complement "
                        f"requires a fraction in [0, 1]; role {parameter_role!r} resolved to {numeric!r}."
                    )
                numeric = 1.0 - numeric
            roles.append(parameter_role)
            provenance[state_name] = (
                f"{'1 - ' if field == 'complement_of_parameter_role' else ''}{record.parameter_symbol} "
                f"from registry parameter record {record.record_id} (role {parameter_role})"
            )
            bindings[state_name] = {
                "parameter_symbol": record.parameter_symbol,
                "complement": field == "complement_of_parameter_role",
            }
        else:
            try:
                numeric = float(raw_coefficient)
            except (TypeError, ValueError) as exc:
                raise RegistryCaseBuildError(
                    f"Case template {template.case_template_id!r} product map {map_id!r} {side}.{role} must be numeric "
                    "or a parameter-role reference."
                ) from exc
            provenance[state_name] = "fixed template coefficient"
        if not math.isfinite(numeric) or numeric < 0.0:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} product map {map_id!r} {side}.{role} must be a finite "
                f"non-negative coefficient; got {numeric!r}."
            )
        coefficients[state_name] = numeric
    return {"coefficients": coefficients, "roles": roles, "provenance": provenance, "bindings": bindings, "units": units}


def _dimensional_record_units(record: ParameterRecord, *, role: str) -> str | None:
    """The record's units when they are not dimensionless; None for a pure-number record (as before)."""

    if record.value.units is None:
        return None
    text = str(record.value.units)
    try:
        dimensionless = bool(Q_(1.0, text).dimensionless)
    except Exception as exc:  # pint raises several unrelated exception types for bad strings
        raise RegistryCaseBuildError(f"Role {role!r} record units {text!r} cannot be parsed: {exc}") from exc
    return None if dimensionless else text


def _plain_fraction(numeric: float, record: ParameterRecord, *, role: str) -> float:
    """A dimensionless record's value as a plain number: 400 mg/g is 0.4 and 40 percent is 0.4.

    A product-map coefficient is a plain number, so a record stated in scaled
    dimensionless units is converted with pint, never read as its magnitude.
    """

    if record.value.units is None:
        return numeric
    try:
        return float(Q_(numeric, str(record.value.units)).to("dimensionless").magnitude)
    except Exception as exc:  # pint raises several unrelated exception types for bad strings
        raise RegistryCaseBuildError(
            f"Role {role!r} record units {record.value.units!r} cannot be read as a plain fraction: {exc}"
        ) from exc


def _process_template_specs(
    template: CaseTemplateRecord,
    *,
    product_map_ids: frozenset[str],
) -> tuple[Mapping[str, Any], ...]:
    raw_specs = template.process_state_metadata.get("process_templates")
    if not isinstance(raw_specs, Sequence) or isinstance(raw_specs, (str, bytes)) or not raw_specs:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires a non-empty process_templates sequence."
        )
    factory_types = frozenset(ProcessLibrary.default_foundation().factory_types())
    seen: set[str] = set()
    specs: list[Mapping[str, Any]] = []
    for raw in raw_specs:
        if not isinstance(raw, Mapping):
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} process_templates entries must be mappings."
            )
        unknown = sorted(str(key) for key in raw if str(key) not in _PROCESS_TEMPLATE_FIELDS)
        if unknown:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} process template has unsupported field(s): "
                f"{', '.join(unknown)}."
            )
        process_id = _required_text(raw, "id", label=f"Case template {template.case_template_id!r} process template")
        if "enzyme_class" in raw and not _canonical_template_text(raw["enzyme_class"]):
            raise RegistryCaseBuildError(
                f"Process template {process_id!r} enzyme_class must be canonical nonblank text when given."
            )
        if process_id in seen:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} repeats process template id {process_id!r}."
            )
        seen.add(process_id)
        process_type = _required_text(raw, "process_type", label=f"Process template {process_id!r}")
        if process_type not in factory_types:
            raise RegistryCaseBuildError(
                f"Process template {process_id!r} uses process_type {process_type!r}, which no registered "
                f"process factory implements; registered: {', '.join(sorted(factory_types))}."
            )
        state_roles = raw.get("state_roles")
        if not isinstance(state_roles, Mapping) or not state_roles:
            raise RegistryCaseBuildError(f"Process template {process_id!r} requires a non-empty state_roles mapping.")
        for field, role in state_roles.items():
            if str(role) not in template.state_roles:
                raise RegistryCaseBuildError(
                    f"Process template {process_id!r} field {field!r} references undeclared state role {role!r}."
                )
        parameter_roles = raw.get("parameter_roles")
        if not isinstance(parameter_roles, Mapping):
            raise RegistryCaseBuildError(f"Process template {process_id!r} requires a parameter_roles mapping.")
        units_role = raw.get("rate_units_from_state_role")
        if units_role is not None:
            if str(units_role) not in template.state_roles:
                raise RegistryCaseBuildError(
                    f"Process template {process_id!r} rate_units_from_state_role references undeclared state role "
                    f"{units_role!r}."
                )
            fixed = raw.get("fixed_parameters") or {}
            if isinstance(fixed, Mapping) and "rate_units" in fixed:
                raise RegistryCaseBuildError(
                    f"Process template {process_id!r} declares both fixed rate_units and rate_units_from_state_role; "
                    "give one."
                )
        product_map = raw.get("product_map")
        if product_map is not None and str(product_map) not in product_map_ids:
            raise RegistryCaseBuildError(
                f"Process template {process_id!r} references unknown product map {product_map!r}."
            )
        assumptions = raw.get("assumptions", ())
        if not isinstance(assumptions, Sequence) or isinstance(assumptions, (str, bytes)) or not assumptions:
            raise RegistryCaseBuildError(
                f"Process template {process_id!r} must declare at least one explicit assumption."
            )
        specs.append(raw)
    return tuple(specs)


def _conservation_spec(
    template: CaseTemplateRecord,
    *,
    state_units: Mapping[str, str],
    product_maps: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    raw = template.process_state_metadata.get("conservation")
    if not isinstance(raw, Mapping):
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires a conservation mapping."
        )
    validator_id = _required_text(raw, "id", label=f"Case template {template.case_template_id!r} conservation")
    if "closed_system" not in raw:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} conservation {validator_id!r} must declare closed_system."
        )
    raw_weights = raw.get("state_weights")
    if not isinstance(raw_weights, Mapping) or not raw_weights:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} conservation {validator_id!r} requires state_weights."
        )
    unit_bearing = any(isinstance(weight, Mapping) for weight in raw_weights.values()) or any(
        spec.get("coefficient_units") for spec in product_maps.values()
    )
    if unit_bearing:
        return _unit_bearing_conservation_spec(
            template,
            validator_id=validator_id,
            closed_system=bool(raw["closed_system"]),
            raw_weights=raw_weights,
            state_units=state_units,
            product_maps=product_maps,
        )
    state_weights: dict[str, float] = {}
    weight_units: set[str] = set()
    for role, weight in raw_weights.items():
        state_name = _template_state(template, str(role))
        try:
            numeric = float(weight)
        except (TypeError, ValueError) as exc:
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} weight for role {role!r} must be numeric."
            ) from exc
        if not math.isfinite(numeric) or numeric == 0.0 or (numeric < 0 and template.process_state_metadata.get("state_domains", {}).get(role) != "signed"):
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} weight for role {role!r} must be positive and finite unless explicitly signed."
            )
        state_weights[state_name] = numeric
        weight_units.add(state_units[state_name])
    if len(weight_units) != 1:
        raise RegistryCaseBuildError(
            f"Conservation {validator_id!r} weights span states with different units {sorted(weight_units)}; "
            "a closure ledger requires one common unit."
        )
    for map_id, spec in product_maps.items():
        touched = set(spec["reactants"]) | set(spec["products"])
        missing = sorted(touched.difference(state_weights))
        if missing:
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} lacks weights for product map {map_id!r} state(s): "
                f"{', '.join(missing)}."
            )
        reactant_total = sum(coefficient * state_weights[name] for name, coefficient in spec["reactants"].items())
        product_total = sum(coefficient * state_weights[name] for name, coefficient in spec["products"].items())
        if not math.isclose(reactant_total, product_total, rel_tol=1e-9, abs_tol=1e-12):
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} is inconsistent for product map {map_id!r}: "
                f"reactants={reactant_total}, products={product_total}."
            )
    return {"id": validator_id, "closed_system": bool(raw["closed_system"]), "state_weights": state_weights}


def _unit_bearing_conservation_spec(
    template: CaseTemplateRecord,
    *,
    validator_id: str,
    closed_system: bool,
    raw_weights: Mapping[str, Any],
    state_units: Mapping[str, str],
    product_maps: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """The closure ledger when a weight or a product coefficient carries units, checked in pint.

    Each weighted term (state units times weight) must have the ledger's
    dimension, the first term's. Each product map consumes its reactants per
    unit extent in the reactants' common units; each product forms its
    coefficient (with its units, when it carries any) times that extent, which
    must have the product state's dimension; and the weighted reactant and
    product totals must agree. Pure-number weights stay floats and
    unit-bearing ones become ``{value, units}`` mappings in the config.
    """

    state_weights: dict[str, Any] = {}
    quantities: dict[str, Any] = {}
    ledger: Any = None
    for role, weight in raw_weights.items():
        state_name = _template_state(template, str(role))
        try:
            if isinstance(weight, Mapping):
                if set(weight) != {"value", "units"}:
                    raise ValueError("a unit-bearing weight gives exactly value and units")
                numeric = float(weight["value"])
                units = str(weight["units"])
                quantity = Q_(numeric, units)
            else:
                numeric = float(weight)
                units = ""
                quantity = Q_(numeric, "dimensionless")
        except Exception as exc:  # pint and float raise several unrelated exception types
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} weight for role {role!r} must be a number or a mapping of value and "
                f"units ({exc})."
            ) from exc
        if not math.isfinite(numeric) or numeric == 0.0 or (numeric < 0 and template.process_state_metadata.get("state_domains", {}).get(role) != "signed"):
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} weight for role {role!r} must be positive and finite unless explicitly signed."
            )
        term = Q_(1.0, state_units[state_name]) * quantity
        if ledger is None:
            ledger = term
        elif not term.is_compatible_with(ledger):
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} weight for role {role!r} gives a term in {term.units!s}, which is not "
                f"the ledger's dimension ({ledger.units!s}); a closure ledger sums one dimension."
            )
        state_weights[state_name] = {"value": numeric, "units": units} if units else numeric
        quantities[state_name] = quantity
    for map_id, spec in product_maps.items():
        touched = set(spec["reactants"]) | set(spec["products"])
        missing = sorted(touched.difference(quantities))
        if missing:
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} lacks weights for product map {map_id!r} state(s): "
                f"{', '.join(missing)}."
            )
        reactant_units = {state_units[name] for name in spec["reactants"]}
        if len(reactant_units) != 1:
            raise RegistryCaseBuildError(
                f"Product map {map_id!r} consumes reactants in different units {sorted(reactant_units)}; a "
                "unit-bearing conservation check measures the extent in one reactant unit."
            )
        extent = Q_(1.0, next(iter(reactant_units)))
        # The ledger change per unit extent: reactants consumed, then products formed, in the ledger's units.
        reactant_total: Any = None
        for name, coefficient in spec["reactants"].items():
            term = coefficient * quantities[name] * extent
            reactant_total = term if reactant_total is None else reactant_total + term.to(reactant_total.units)
        product_total: Any = Q_(0.0, reactant_total.units)
        for name, coefficient in spec["products"].items():
            units = spec.get("coefficient_units", {}).get(name)
            formed = (Q_(coefficient, units) if units else Q_(coefficient, "dimensionless")) * extent
            if not formed.is_compatible_with(Q_(1.0, state_units[name])):
                raise RegistryCaseBuildError(
                    f"Product map {map_id!r} forms {name!r} as {formed.units!s} per unit extent, which is not the "
                    f"product state's dimension ({state_units[name]}); the coefficient must convert the reactant's "
                    "amount into the product's."
                )
            term = formed.to(state_units[name]) * quantities[name]
            if not term.is_compatible_with(reactant_total):
                raise RegistryCaseBuildError(
                    f"Conservation {validator_id!r} weighs product {name!r} of map {map_id!r} in {term.units!s}, "
                    f"not in the ledger's dimension ({reactant_total.units!s})."
                )
            product_total = product_total + term.to(reactant_total.units)
        if not math.isclose(
            float(reactant_total.magnitude), float(product_total.magnitude), rel_tol=1e-9, abs_tol=1e-12
        ):
            raise RegistryCaseBuildError(
                f"Conservation {validator_id!r} is inconsistent for product map {map_id!r}: "
                f"reactants={reactant_total}, products={product_total}."
            )
    return {"id": validator_id, "closed_system": closed_system, "state_weights": state_weights}


def _require_every_role_used(
    template: CaseTemplateRecord,
    *,
    parameter_records: Mapping[str, ParameterRecord],
    process_specs: Sequence[Mapping[str, Any]],
    product_maps: Mapping[str, Mapping[str, Any]],
) -> None:
    referenced: set[str] = set()
    for spec in process_specs:
        referenced.update(str(role) for role in spec["parameter_roles"].values())
        referenced.update(_modifier_roles(spec.get("modifiers")))
        referenced.update(_coefficient_roles(spec.get("stoichiometry", {})))
    for product_map in product_maps.values():
        referenced.update(product_map["parameter_roles"])
    for initial in template.initial_state_mapping.values():
        for field in ("parameter_role", "units_from_role"):
            value = initial.get(field)
            if isinstance(value, str) and value:
                referenced.add(value)
        roles = initial.get("units_from_roles")
        if isinstance(roles, Sequence) and not isinstance(roles, (str, bytes)):
            referenced.update(str(role) for role in roles if str(role))
    unresolved = sorted(referenced.difference(parameter_records))
    if unresolved:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} references parameter role(s) without resolved "
            f"registry records: {', '.join(unresolved)}."
        )
    unused = sorted(set(parameter_records).difference(referenced))
    if unused:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} resolved parameter role(s) that no process, product map, "
            f"or initial state uses: {', '.join(unused)}."
        )


def _modifier_roles(value: Any) -> set[str]:
    """Parameter roles a modifier names: values of keys ending in ``_role``, except state roles (``_state_role``)."""

    roles: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if (
                isinstance(key, str)
                and key.endswith("_role")
                and not key.endswith("_state_role")
                and key != "state_source_role"
                and isinstance(nested, str)
                and nested
            ):
                roles.add(nested)
            roles.update(_modifier_roles(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            roles.update(_modifier_roles(nested))
    return roles


def _state_species(template: CaseTemplateRecord) -> dict[str, dict[str, str]]:
    raw = template.process_state_metadata.get("state_species")
    if not isinstance(raw, Mapping) or not raw:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires state_species identities for every state role."
        )
    resolved: dict[str, dict[str, str]] = {}
    for role, binding in raw.items():
        if str(role) not in template.state_roles:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} state_species references undeclared role {role!r}."
            )
        if not isinstance(binding, Mapping) or set(binding) != {"entity_type", "species"}:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} state_species.{role} must contain exactly "
                "entity_type and species."
            )
        entity_type = str(binding["entity_type"])
        if entity_type not in _STATE_SPECIES_ENTITY_TYPES:
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} state_species.{role}.entity_type must be one of "
                f"{sorted(_STATE_SPECIES_ENTITY_TYPES)}."
            )
        species = binding["species"]
        if not _canonical_template_text(species):
            raise RegistryCaseBuildError(
                f"Case template {template.case_template_id!r} state_species.{role}.species must be canonical text."
            )
        resolved[str(role)] = {"entity_type": entity_type, "species": str(species)}
    missing = sorted(set(template.state_roles).difference(resolved))
    if missing:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} state_species lacks identities for: {', '.join(missing)}."
        )
    return resolved


def _process_config(
    spec: Mapping[str, Any],
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    registry: FungModRegistry,
    environment_id: str,
    state_units: Mapping[str, str],
) -> dict[str, Any]:
    process_id = str(spec["id"])
    states: dict[str, Any] = {
        str(field): _template_state(case_template, str(role))
        for field, role in spec["state_roles"].items()
    }
    fixed_states = spec.get("fixed_states", {}) or {}
    if not isinstance(fixed_states, Mapping):
        raise RegistryCaseBuildError(f"Process template {process_id!r} fixed_states must be a mapping.")
    states.update({str(key): value for key, value in fixed_states.items()})
    parameters: dict[str, Any] = {
        str(field): _template_parameter_record(parameter_records, str(role)).parameter_symbol
        for field, role in spec["parameter_roles"].items()
    }
    fixed_parameters = spec.get("fixed_parameters", {}) or {}
    if not isinstance(fixed_parameters, Mapping):
        raise RegistryCaseBuildError(f"Process template {process_id!r} fixed_parameters must be a mapping.")
    parameters.update({str(key): value for key, value in fixed_parameters.items()})
    units_role = spec.get("rate_units_from_state_role")
    if units_role is not None:
        # The rate is in the units of the state it changes, per unit of the case's time grid.
        state_name = _template_state(case_template, str(units_role))
        parameters["rate_units"] = f"({state_units[state_name]}) / {case_template.time_grid['units']}"
    config: dict[str, Any] = {
        "id": process_id,
        "process_type": str(spec["process_type"]),
        "states": states,
        "parameters": parameters,
        "modifiers": _process_modifiers(
            spec,
            case_template=case_template,
            parameter_records=parameter_records,
            registry=registry,
            environment_id=environment_id,
        ),
        "output_state_roles": dict(case_template.output_state_roles),
        "assumptions": [str(item) for item in spec["assumptions"]],
    }
    if spec.get("product_map") is not None:
        config["product_map"] = str(spec["product_map"])
    if spec.get("stoichiometry") is not None:
        raw = spec["stoichiometry"]
        if not isinstance(raw, Mapping) or not raw:
            raise RegistryCaseBuildError(f"Process {process_id!r} stoichiometry must be a non-empty mapping.")
        config["stoichiometry"] = {_template_state(case_template, str(role)): _record_coefficient(value, parameter_records=parameter_records)
                                   for role, value in raw.items()}
        # Explicitly zero demand is an absent contribution, never a guessed coefficient.
        config["stoichiometry"] = {name: coefficient for name, coefficient in config["stoichiometry"].items()
                                   if float(coefficient["value"] if isinstance(coefficient, Mapping) else coefficient) != 0.0}
    if spec.get("extent_state") is not None:
        states["extent"] = _template_state(case_template, str(spec["extent_state"]))
    return config


def _coefficient_roles(value: Any) -> set[str]:
    roles: set[str] = set()
    if isinstance(value, Mapping):
        if "parameter_role" in value:
            roles.add(str(value["parameter_role"]))
        if "inverse_parameter_roles" in value:
            roles.update(str(role) for role in value["inverse_parameter_roles"])
        for nested in value.values():
            if isinstance(nested, Mapping):
                roles.update(_coefficient_roles(nested))
    return roles


def _record_coefficient(value: Any, *, parameter_records: Mapping[str, ParameterRecord]) -> Any:
    """A signed coefficient or reciprocal product of explicit, unit-bearing records."""
    if not isinstance(value, Mapping) or not ({"parameter_role", "inverse_parameter_roles"} & set(value)):
        return value
    allowed = {"factor", "parameter_role", "inverse_parameter_roles"}
    if set(value) - allowed or ("parameter_role" in value and "inverse_parameter_roles" in value):
        raise RegistryCaseBuildError("A record coefficient needs parameter_role or inverse_parameter_roles, with optional factor.")
    coefficient = Q_(float(value.get("factor", 1.0)), "dimensionless")
    roles = [str(value["parameter_role"])] if "parameter_role" in value else value["inverse_parameter_roles"]
    if not isinstance(roles, Sequence) or isinstance(roles, (str, bytes)) or not roles:
        raise RegistryCaseBuildError("inverse_parameter_roles must be a non-empty list.")
    for role in roles:
        record = _template_parameter_record(parameter_records, str(role))
        magnitude = _record_exact_value(record, role=str(role))
        if magnitude < 0 or (magnitude == 0 and "inverse_parameter_roles" in value):
            raise RegistryCaseBuildError(f"Coefficient record {role!r} must be nonnegative (positive when inverted).")
        quantity = Q_(magnitude, _record_units(record, role=str(role)))
        coefficient = coefficient * quantity if "parameter_role" in value else coefficient / quantity
    if not math.isfinite(float(coefficient.magnitude)):
        raise RegistryCaseBuildError("Record coefficient must be finite.")
    if coefficient.dimensionless:
        return float(coefficient.to("dimensionless").magnitude)
    return {"value": float(coefficient.magnitude), "units": str(coefficient.units)}


def _process_modifiers(
    spec: Mapping[str, Any],
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    registry: FungModRegistry,
    environment_id: str,
) -> list[dict[str, Any]]:
    raw_modifiers = spec.get("modifiers", ()) or ()
    if not isinstance(raw_modifiers, Sequence) or isinstance(raw_modifiers, (str, bytes)):
        raise RegistryCaseBuildError(f"Process template {spec['id']!r} modifiers must be a sequence.")
    modifiers: list[dict[str, Any]] = []
    for index, modifier in enumerate(raw_modifiers):
        if not isinstance(modifier, Mapping):
            raise RegistryCaseBuildError(f"Process template {spec['id']!r} modifiers[{index}] must be a mapping.")
        modifier_type = str(modifier.get("type", "")).strip()
        label = f"Case template {case_template.case_template_id!r} process {spec['id']!r} modifiers[{index}]"
        if modifier_type == "oxygen_monod" and modifier.get("state_source_role"):
            role = str(modifier["half_saturation_role"])
            record = _template_parameter_record(parameter_records, role)
            modifiers.append({"type": "oxygen_monod", "state_source": _template_state(case_template, str(modifier["state_source_role"])),
                "half_saturation_symbol": record.parameter_symbol, "oxygen_units": _record_units(record, role=role)})
            continue
        if modifier_type in ENVIRONMENT_MODIFIER_TYPES:
            modifiers.append(
                build_template_environment_modifier(
                    template_id=case_template.case_template_id,
                    parameter_symbols={role: record.parameter_symbol for role, record in parameter_records.items()},
                    registry=registry,
                    environment_id=environment_id,
                    modifier=modifier,
                    modifier_type=modifier_type,
                    index=index,
                    modifier_label=label,
                    unresolved_label=label,
                    error_type=RegistryCaseBuildError,
                )
            )
            continue
        if modifier_type == "product_inhibition":
            product_role = str(modifier.get("product_state_role", "")).strip()
            inhibition_role = str(modifier.get("inhibition_constant_role", "")).strip()
            if not product_role or not inhibition_role:
                raise RegistryCaseBuildError(f"{label} requires product_state_role and inhibition_constant_role.")
            modifiers.append(
                {
                    "type": "product_inhibition",
                    "product_state": _template_state(case_template, product_role),
                    "inhibition_constant": _template_parameter_record(
                        parameter_records, inhibition_role
                    ).parameter_symbol,
                }
            )
            continue
        if modifier_type == COMPETITIVE_INHIBITION_MODIFIER_TYPE:
            modifiers.append(
                _competitive_inhibition_modifier(
                    modifier, case_template=case_template, parameter_records=parameter_records, label=label
                )
            )
            continue
        if modifier_type == SUBSTRATE_REACTIVITY_MODIFIER_TYPE:
            fields = _modifier_fields(
                modifier,
                ("substrate_state_role", "reference_concentration_role", "exponent_role"),
                label=label,
            )
            modifiers.append(
                {
                    "type": SUBSTRATE_REACTIVITY_MODIFIER_TYPE,
                    "substrate_state": _template_state(case_template, fields["substrate_state_role"]),
                    "reference_concentration": _template_parameter_record(
                        parameter_records, fields["reference_concentration_role"]
                    ).parameter_symbol,
                    "exponent": _template_parameter_record(parameter_records, fields["exponent_role"]).parameter_symbol,
                }
            )
            continue
        raise RegistryCaseBuildError(f"{label} declares unsupported modifier type {modifier_type!r}.")
    return modifiers


def _competitive_inhibition_modifier(
    modifier: Mapping[str, Any],
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    label: str,
) -> dict[str, Any]:
    """Bind the existing provenance-bound competitive-inhibition modifier from template roles.

    The template names the substrate and inhibitor state roles, the roles of the
    process's own Michaelis constant and of the inhibition constant, and the
    law's primary source and maturity; the modifier itself checks that the
    substrate and Michaelis constant are those of its base process.
    """

    fields = _modifier_fields(
        modifier,
        (
            "substrate_state_role",
            "inhibitor_state_role",
            "michaelis_constant_role",
            "inhibition_constant_role",
            "primary_source",
            "maturity",
        ),
        label=label,
    )
    return {
        "type": COMPETITIVE_INHIBITION_MODIFIER_TYPE,
        "substrate_state": _template_state(case_template, fields["substrate_state_role"]),
        "inhibitor_state": _template_state(case_template, fields["inhibitor_state_role"]),
        "michaelis_constant": _template_parameter_record(
            parameter_records, fields["michaelis_constant_role"]
        ).parameter_symbol,
        "inhibition_constant": _template_parameter_record(
            parameter_records, fields["inhibition_constant_role"]
        ).parameter_symbol,
        "primary_source": fields["primary_source"],
        "maturity": fields["maturity"],
    }


def _modifier_fields(modifier: Mapping[str, Any], names: Sequence[str], *, label: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name in names:
        value = modifier.get(name)
        if not _canonical_template_text(value):
            raise RegistryCaseBuildError(f"{label} requires canonical nonblank {name!r} text.")
        fields[name] = str(value)
    return fields


def _entities(
    template: CaseTemplateRecord,
    *,
    product_maps: Mapping[str, Mapping[str, Any]],
    processes: Sequence[Mapping[str, Any]],
    registry: FungModRegistry,
    environment_id: str,
) -> dict[str, Any]:
    metadata = template.process_state_metadata
    if "geometry" not in metadata:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires explicit geometry metadata."
        )
    # An explicit null is a concentration-only model that claims no vessel; anything else must be a geometry.
    geometry = metadata["geometry"]
    if geometry is not None and (not isinstance(geometry, Mapping) or not geometry):
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires explicit geometry metadata."
        )
    raw_entities = metadata.get("entities")
    if not isinstance(raw_entities, Mapping):
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires an entities mapping with substrates and enzymes."
        )
    substrates = _entity_references(raw_entities.get("substrates"), label="entities.substrates", require_loader=True)
    enzymes = _entity_references(raw_entities.get("enzymes"), label="entities.enzymes", require_loader=False)
    if not substrates:
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} must declare at least one substrate entity."
        )
    entities: dict[str, Any] = {}
    if geometry is not None:
        entities["geometry"] = {"id": "geometry", "loader": "well_mixed", "data": deepcopy(dict(geometry))}
    entities |= {
        "substrates": substrates,
        "enzymes": enzymes,
        "product_maps": [
            {
                "id": spec["id"],
                "loader": "stoichiometric",
                "data": {
                    "kind": "product_map",
                    "name": spec["name"],
                    "product_map_type": "stoichiometric",
                    "maturity": template.maturity,
                    "provenance": {
                        "source": _template_source(template),
                        "confidence_level": str(template.provenance.get("confidence_level", "registry_metadata")),
                        "coefficient_provenance": dict(spec["coefficient_provenance"]),
                        "notes": spec["notes"],
                    },
                    "notes": spec["notes"],
                    "reactants": dict(spec["reactants"]),
                    "products": dict(spec["products"]),
                    "coefficient_bindings": {
                        state: dict(binding) for state, binding in spec["coefficient_bindings"].items()
                    },
                    # Written only when a coefficient carries units, so pure-number maps assemble as before.
                    **({"coefficient_units": dict(spec["coefficient_units"])} if spec["coefficient_units"] else {}),
                },
            }
            for spec in product_maps.values()
        ],
    }
    modifiers = [dict(modifier) for process in processes for modifier in process.get("modifiers", ())]
    environment_entity = build_template_environment_entity(
        registry=registry,
        environment_id=environment_id,
        modifiers=modifiers,
        error_type=RegistryCaseBuildError,
        process_types=tuple(str(process["process_type"]) for process in processes),
    )
    if environment_entity is not None:
        entities["environment"] = environment_entity
    return entities


def _entity_references(value: Any, *, label: str, require_loader: bool) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RegistryCaseBuildError(f"Case template {label} must be a sequence.")
    references: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise RegistryCaseBuildError(f"Case template {label} entries must be mappings.")
        identifier = _required_text(item, "id", label=f"Case template {label}")
        if "data" not in item:
            raise RegistryCaseBuildError(f"Case template {label} {identifier!r} must declare inline data.")
        loader = item.get("loader")
        if require_loader and not _canonical_template_text(loader):
            raise RegistryCaseBuildError(f"Case template {label} {identifier!r} must declare a loader.")
        reference: dict[str, Any] = {"id": identifier, "data": deepcopy(item["data"])}
        if loader is not None:
            reference["loader"] = str(loader)
        references.append(reference)
    return references


def _provenance(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    environment_conditions: Mapping[str, Any],
    organism: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "source": _template_source(case_template),
        "confidence_level": str(case_template.provenance.get("confidence_level", "registry_metadata")),
        "registry_id": registry.registry_id,
        "fungus_id": fungus_id,
        "substrate_id": substrate_id,
        "environment_id": environment_id,
        "process_compatibility_id": compatibility.record_id,
        "case_template_id": case_template.case_template_id,
        "organism": dict(organism),
        "parameter_record_ids": {role: record.record_id for role, record in parameter_records.items()},
        "parameter_value_sources": {role: record.value.source for role, record in parameter_records.items()},
        "parameter_record_maturities": {role: record.maturity for role, record in parameter_records.items()},
        "parameter_record_provenance": {
            role: deepcopy(dict(record.provenance)) for role, record in parameter_records.items()
        },
        "environment_conditions": dict(environment_conditions),
        "notes": case_template.notes,
    }


def _template_source(template: CaseTemplateRecord) -> str:
    source = template.provenance.get("source")
    if not _canonical_template_text(source):
        raise RegistryCaseBuildError(
            f"Case template {template.case_template_id!r} requires explicit provenance source text."
        )
    return str(source)


def _required_text(value: Mapping[str, Any], key: str, *, label: str) -> str:
    text = value.get(key)
    if not _canonical_template_text(text):
        raise RegistryCaseBuildError(f"{label} requires canonical nonblank {key!r} text.")
    return str(text)


__all__ = [
    "COMPETITIVE_INHIBITION_MODIFIER_TYPE",
    "CULTURE_PHYSIOLOGY_PROCESS_TYPE",
    "CULTURE_PHYSIOLOGY_REQUIRED_PROCESS_STATE_METADATA",
    "CULTURE_PHYSIOLOGY_REQUIRED_STATE_ROLES",
    "build_composed_process_config_data",
    "build_culture_physiology_config_data",
]
