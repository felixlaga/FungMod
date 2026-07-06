"""Registry-backed extracellular enzyme-chain assembly and tables."""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fungal_model.api.metrics import threshold_crossing_time
from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import CaseTemplateRecord, ParameterRecord
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.results import SimulationResult
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_TYPES,
    build_template_environment_entity,
    build_template_environment_modifier,
)
from fungal_model.workflows import run_configured_model


EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE = "extracellular_enzyme_chain"
BIO002_ENZYME_CHAIN_TEMPLATE_ID = "bio002_extracellular_enzyme_chain_template"

_CHAIN_CORE_ROLES = ("substrate", "intermediate", "product")
_LEGACY_PRODUCT_MAP_FIELDS = frozenset(
    {
        "substrate_state",
        "product_state",
        "substrate_state_role",
        "product_state_role",
        "stoichiometric_yield",
    }
)


class EnzymeChainAssemblyError(ValueError):
    """Raised when an extracellular enzyme-chain template cannot assemble."""


@dataclass(frozen=True)
class ChainConservationSpec:
    """Template-declared conserved-equivalent definition."""

    validator_id: str
    role_weights: Mapping[str, float]
    state_weights: Mapping[str, float]
    closed_system: bool


@dataclass(frozen=True)
class ChainTemplateSpec:
    """Validated template data needed by the generic chain assembler."""

    template: CaseTemplateRecord
    metadata: Mapping[str, Any]
    state_roles: Mapping[str, str]
    state_units: Mapping[str, str]
    parameter_records: Mapping[str, ParameterRecord]
    product_maps: tuple[Mapping[str, Any], ...]
    processes: tuple[Mapping[str, Any], ...]
    conservation: ChainConservationSpec
    outputs: Mapping[str, Any]
    environment_id: str | None


@dataclass(frozen=True)
class EnzymeChainRunResult:
    """Enzyme-chain run output bundle."""

    config: ModelConfig
    config_path: str
    bundle_directory: str
    result: SimulationResult
    tables: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_path": self.config_path,
            "bundle_directory": self.bundle_directory,
            "tables": dict(self.tables),
            "result": self.result.to_dict(),
        }


def build_extracellular_enzyme_chain_config(
    *,
    registry: FungModRegistry,
    template_id: str = BIO002_ENZYME_CHAIN_TEMPLATE_ID,
    environment_id: str | None = None,
    output_directory: str | Path | None = None,
) -> ModelConfig:
    """Build an extracellular enzyme-chain ``ModelConfig`` from registry metadata."""

    chain = _chain_spec(registry=registry, template_id=template_id, environment_id=environment_id)
    processes = [
        _process_config(process, chain=chain, registry=registry)
        for process in chain.processes
    ]
    entities = {
        **_configured_entities(chain.metadata),
        "product_maps": [
            _product_map_entity(product_map, chain=chain)
            for product_map in chain.product_maps
        ],
    }
    environment_entity = _chain_environment_entity(
        registry=registry,
        chain=chain,
        processes=processes,
    )
    if environment_entity is not None:
        entities["environment"] = environment_entity
    data = {
        "kind": "model_config",
        "name": _metadata_text(chain.metadata, "config_name", chain.template.name),
        "mode": _metadata_text(chain.metadata, "config_mode", "exploratory"),
        "maturity": _metadata_text(chain.metadata, "config_maturity", "exploratory"),
        "provenance": _chain_provenance(registry=registry, chain=chain),
        "case_template": _case_template_config(chain),
        "chain_outputs": deepcopy(dict(chain.outputs)),
        "suggested_experiments": _suggested_experiments(chain.metadata),
        "entities": entities,
        "parameters": [
            {
                "id": "enzyme_chain_parameters",
                "parameters": [
                    _parameter_config(record, role=role)
                    for role, record in chain.parameter_records.items()
                ],
            }
        ],
        "processes": processes,
        "initial_state": _initial_state(chain),
        "time": _time_config(chain.template),
        "validators": _validators(chain),
        "outputs": {
            "directory": None if output_directory is None else str(output_directory),
            "save": ["record", "validation_report", "standard_tables"],
            "plots": ["state_trajectories", "process_rates", "mass_balance"],
        },
    }
    return ModelConfig.from_mapping(data)


def run_extracellular_enzyme_chain_demo(
    *,
    registry: FungModRegistry,
    output_dir: str | Path,
    template_id: str = BIO002_ENZYME_CHAIN_TEMPLATE_ID,
    environment_id: str | None = None,
) -> EnzymeChainRunResult:
    """Build, run, and table an extracellular enzyme-chain demo template."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    bundle_dir = root / "bundle"
    config = build_extracellular_enzyme_chain_config(
        registry=registry,
        template_id=template_id,
        environment_id=environment_id,
        output_directory=bundle_dir,
    )
    config_path = root / "model_config.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=bundle_dir)
    tables = write_enzyme_chain_standard_tables(config=config, result=result, output_dir=root)
    return EnzymeChainRunResult(
        config=config,
        config_path=str(config_path),
        bundle_directory=str(bundle_dir),
        result=result,
        tables=tables,
    )


def write_enzyme_chain_standard_tables(
    *,
    config: ModelConfig,
    result: SimulationResult,
    output_dir: str | Path,
) -> Mapping[str, str]:
    """Write standard chain tables derived from configured output metadata."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    outputs = _config_chain_outputs(config)
    conservation = _config_conservation(config)
    derived = _derived_series(config=config, result=result, outputs=outputs, conservation=conservation)
    paths = {
        "time_series_long": destination / "time_series_long.csv",
        "final_metrics": destination / "final_metrics.csv",
        "threshold_times": destination / "threshold_times.csv",
        "summary_metrics": destination / "summary_metrics.csv",
        "limitations_table": destination / "limitations_table.csv",
        "suggested_experiments": destination / "suggested_experiments.csv",
    }
    _write_csv(paths["time_series_long"], _time_series_rows(config, result, outputs, derived))
    final_rows = _final_metric_rows(config=config, result=result, outputs=outputs, derived=derived)
    _write_csv(paths["final_metrics"], final_rows)
    _write_csv(paths["threshold_times"], _threshold_rows(config=config, result=result, outputs=outputs, derived=derived))
    _write_csv(paths["summary_metrics"], _summary_rows(final_rows))
    _write_csv(paths["limitations_table"], _limitation_rows(config))
    _write_csv(paths["suggested_experiments"], _suggested_experiment_rows(config))
    return {name: str(path) for name, path in paths.items()}


def _chain_spec(
    *,
    registry: FungModRegistry,
    template_id: str,
    environment_id: str | None,
) -> ChainTemplateSpec:
    template = _chain_template(registry, template_id)
    metadata = _chain_metadata(template)
    state_roles = dict(template.state_roles)
    parameter_records = _parameter_records(registry, metadata)
    state_units = _state_units(template, parameter_records=parameter_records)
    product_maps = _mapping_sequence(metadata.get("product_maps"), field_name="process_state_metadata.product_maps")
    processes = _mapping_sequence(metadata.get("process_templates"), field_name="process_state_metadata.process_templates")
    resolved_environment_id = _chain_environment_id(
        metadata=metadata,
        requested_environment_id=environment_id,
        requires_environment=_process_templates_require_environment(processes),
        template_id=template.case_template_id,
    )
    if len(processes) != 2:
        raise EnzymeChainAssemblyError(
            f"Template {template.case_template_id!r} must declare exactly two process_templates for a two-step chain."
        )
    _validate_product_map_ids(template, product_maps)
    _validate_process_templates(template, processes, state_roles=state_roles, parameter_records=parameter_records)
    conservation = _conservation_spec(
        template=template,
        metadata=metadata,
        state_roles=state_roles,
        state_units=state_units,
        product_maps=product_maps,
    )
    outputs = _chain_outputs(
        template=template,
        metadata=metadata,
        state_roles=state_roles,
        state_units=state_units,
        conservation=conservation,
    )
    return ChainTemplateSpec(
        template=template,
        metadata=metadata,
        state_roles=state_roles,
        state_units=state_units,
        parameter_records=parameter_records,
        product_maps=product_maps,
        processes=processes,
        conservation=conservation,
        outputs=outputs,
        environment_id=resolved_environment_id,
    )


def _chain_template(registry: FungModRegistry, template_id: str) -> CaseTemplateRecord:
    try:
        template = registry.get_case_template(template_id)
    except RegistryLookupError as exc:
        raise EnzymeChainAssemblyError(f"Unknown extracellular enzyme-chain template: {template_id}") from exc
    if template.process_type != EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE:
        raise EnzymeChainAssemblyError(
            f"Template {template_id!r} must use process_type={EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE!r}."
        )
    for role in _CHAIN_CORE_ROLES:
        if role not in template.state_roles:
            raise EnzymeChainAssemblyError(f"Template {template_id!r} is missing state role {role!r}.")
    return template


def _chain_metadata(template: CaseTemplateRecord) -> Mapping[str, Any]:
    metadata = template.process_state_metadata
    if not isinstance(metadata, Mapping):
        raise EnzymeChainAssemblyError(f"Template {template.case_template_id!r} lacks process_state_metadata.")
    return metadata


def _parameter_records(
    registry: FungModRegistry,
    metadata: Mapping[str, Any],
) -> dict[str, ParameterRecord]:
    record_ids = _mapping(metadata.get("parameter_record_ids"), field_name="process_state_metadata.parameter_record_ids")
    records: dict[str, ParameterRecord] = {}
    for role, record_id in record_ids.items():
        role_text = str(role)
        try:
            record = registry.parameters[str(record_id)]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(f"Unknown parameter record for role {role_text!r}: {record_id}") from exc
        if not record.value.is_exact:
            raise EnzymeChainAssemblyError(
                f"Template parameter role {role_text!r} requires an exact parameter record for deterministic assembly; "
                f"{record.record_id!r} has ValueSpec kind {record.value.kind!r}."
            )
        if record.value.value is None or record.value.units is None:
            raise EnzymeChainAssemblyError(f"Parameter record {record.record_id!r} must define value and units.")
        records[role_text] = record
    return records


def _state_units(
    template: CaseTemplateRecord,
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, str]:
    units: dict[str, str] = {}
    for role, state_name in template.state_roles.items():
        if role not in template.initial_state_mapping:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} state role {role!r} lacks initial_state_mapping and units."
            )
        spec = template.initial_state_mapping[role]
        units[state_name] = _initial_state_units(
            template=template,
            role=role,
            spec=spec,
            parameter_records=parameter_records,
        )
    return units


def _initial_state_units(
    *,
    template: CaseTemplateRecord,
    role: str,
    spec: Mapping[str, Any],
    parameter_records: Mapping[str, ParameterRecord],
) -> str:
    if "units" in spec and str(spec["units"]).strip():
        return str(spec["units"])
    units_from_role = str(spec.get("units_from_role", "")).strip()
    if units_from_role:
        try:
            record = parameter_records[units_from_role]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} initial state role {role!r} references unknown "
                f"units_from_role {units_from_role!r}."
            ) from exc
        if record.value.units is None:
            raise EnzymeChainAssemblyError(
                f"Parameter record {record.record_id!r} used for units_from_role {units_from_role!r} lacks units."
            )
        return str(record.value.units)
    parameter_role = str(spec.get("parameter_role", "")).strip()
    if parameter_role:
        try:
            record = parameter_records[parameter_role]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} initial state role {role!r} references unknown "
                f"parameter_role {parameter_role!r}."
            ) from exc
        if record.value.units is None:
            raise EnzymeChainAssemblyError(f"Parameter record {record.record_id!r} lacks units.")
        return str(record.value.units)
    raise EnzymeChainAssemblyError(
        f"Template {template.case_template_id!r} initial state role {role!r} must declare units or units_from_role."
    )


def _configured_entities(metadata: Mapping[str, Any]) -> dict[str, Any]:
    entities = _mapping(metadata.get("entities"), field_name="process_state_metadata.entities")
    geometry = _entity_reference(
        _mapping(entities.get("geometry"), field_name="process_state_metadata.entities.geometry"),
        field_name="process_state_metadata.entities.geometry",
        require_loader=True,
    )
    substrates = [
        _entity_reference(item, field_name="process_state_metadata.entities.substrates", require_loader=True)
        for item in _mapping_sequence(entities.get("substrates"), field_name="process_state_metadata.entities.substrates")
    ]
    enzymes = [
        _entity_reference(item, field_name="process_state_metadata.entities.enzymes", require_loader=False)
        for item in _mapping_sequence(entities.get("enzymes"), field_name="process_state_metadata.entities.enzymes")
    ]
    return {
        "geometry": geometry,
        "substrates": substrates,
        "enzymes": enzymes,
    }


def _chain_environment_id(
    *,
    metadata: Mapping[str, Any],
    requested_environment_id: str | None,
    requires_environment: bool,
    template_id: str,
) -> str | None:
    if requested_environment_id is not None and str(requested_environment_id).strip():
        return str(requested_environment_id)
    configured_environment_id = str(metadata.get("environment_id", "")).strip()
    if configured_environment_id:
        return configured_environment_id
    if requires_environment:
        raise EnzymeChainAssemblyError(
            f"Template {template_id!r} declares environment modifiers but no explicit environment_id was supplied "
            "to chain assembly or process_state_metadata.environment_id."
        )
    return None


def _process_templates_require_environment(processes: Sequence[Mapping[str, Any]]) -> bool:
    for spec in processes:
        process_id = str(spec.get("id", ""))
        for modifier in _mapping_sequence(
            spec.get("modifiers"),
            field_name=f"process_template {process_id}.modifiers",
            allow_empty=True,
        ):
            modifier_type = _required_text(
                modifier,
                "type",
                field_name=f"process_template {process_id}.modifiers",
            )
            if modifier_type in ENVIRONMENT_MODIFIER_TYPES:
                return True
    return False


def _entity_reference(
    value: Mapping[str, Any],
    *,
    field_name: str,
    require_loader: bool,
) -> dict[str, Any]:
    identifier = _required_text(value, "id", field_name=field_name)
    if "data" not in value and "path" not in value:
        raise EnzymeChainAssemblyError(f"{field_name} {identifier!r} must declare data or path.")
    loader = value.get("loader")
    if require_loader and not str(loader or "").strip():
        raise EnzymeChainAssemblyError(f"{field_name} {identifier!r} must declare a loader.")
    result: dict[str, Any] = {"id": identifier}
    if loader is not None:
        result["loader"] = str(loader)
    if "path" in value:
        result["path"] = str(value["path"])
    if "data" in value:
        result["data"] = deepcopy(value["data"])
    if "role" in value:
        result["role"] = str(value["role"])
    return result


def _product_map_entity(
    spec: Mapping[str, Any],
    *,
    chain: ChainTemplateSpec,
) -> dict[str, Any]:
    map_id = _required_text(spec, "id", field_name="process_state_metadata.product_maps")
    product_map_type = _required_text(spec, "product_map_type", field_name=f"product_map {map_id}")
    if product_map_type != "stoichiometric":
        raise EnzymeChainAssemblyError(
            f"Product map {map_id!r} in template {chain.template.case_template_id!r} must be stoichiometric."
        )
    reactants = _state_coefficients(
        spec.get("reactants"),
        state_roles=chain.state_roles,
        state_units=chain.state_units,
        template_id=chain.template.case_template_id,
        map_id=map_id,
        side="reactants",
    )
    products = _state_coefficients(
        spec.get("products"),
        state_roles=chain.state_roles,
        state_units=chain.state_units,
        template_id=chain.template.case_template_id,
        map_id=map_id,
        side="products",
    )
    return {
        "id": map_id,
        "loader": product_map_type,
        "data": {
            "kind": "product_map",
            "name": str(spec.get("name", map_id)),
            "product_map_type": product_map_type,
            "maturity": chain.template.maturity,
            "provenance": {
                "source": chain.template.provenance.get("source", "FungMod extracellular enzyme-chain template."),
                "confidence_level": chain.template.provenance.get("confidence_level", "exploratory_assumption"),
                "bio_milestone": "BIO-002",
                "notes": str(spec.get("notes", "")),
            },
            "notes": str(spec.get("notes", "")),
            "reactants": reactants,
            "products": products,
        },
    }


def _state_coefficients(
    value: Any,
    *,
    state_roles: Mapping[str, str],
    state_units: Mapping[str, str],
    template_id: str,
    map_id: str,
    side: str,
) -> dict[str, float]:
    mapping = _mapping(value, field_name=f"product_map {map_id}.{side}")
    coefficients: dict[str, float] = {}
    for role, coefficient in mapping.items():
        role_text = str(role)
        try:
            state_name = state_roles[role_text]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Template {template_id!r} product map {map_id!r} references unknown state role "
                f"{role_text!r} in {side}."
            ) from exc
        if state_name not in state_units:
            raise EnzymeChainAssemblyError(
                f"Template {template_id!r} product map {map_id!r} references state {state_name!r} "
                f"for role {role_text!r}, but no units are declared."
            )
        coefficients[state_name] = _positive_finite_float(
            coefficient,
            field_name=f"template {template_id} product_map {map_id}.{side}.{role_text}",
        )
    return coefficients


def _process_config(
    spec: Mapping[str, Any],
    *,
    chain: ChainTemplateSpec,
    registry: FungModRegistry,
) -> dict[str, Any]:
    process_id = _required_text(spec, "id", field_name="process_state_metadata.process_templates")
    process_type = _required_text(spec, "process_type", field_name=f"process_template {process_id}")
    state_role_refs = _mapping(spec.get("state_roles"), field_name=f"process_template {process_id}.state_roles")
    fixed_states = _mapping(spec.get("fixed_states"), field_name=f"process_template {process_id}.fixed_states", allow_empty=True)
    parameter_role_refs = _mapping(
        spec.get("parameter_roles"),
        field_name=f"process_template {process_id}.parameter_roles",
    )
    states: dict[str, Any] = {}
    for process_field, role in state_role_refs.items():
        role_text = str(role)
        try:
            states[str(process_field)] = chain.state_roles[role_text]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Process template {process_id!r} references unknown state role {role_text!r}."
            ) from exc
    states.update({str(key): value for key, value in fixed_states.items()})
    parameters: dict[str, Any] = {}
    for process_field, role in parameter_role_refs.items():
        role_text = str(role)
        try:
            parameters[str(process_field)] = chain.parameter_records[role_text].parameter_symbol
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Process template {process_id!r} references unknown parameter role {role_text!r}."
            ) from exc
    parameters.update(
        _mapping(
            spec.get("fixed_parameters"),
            field_name=f"process_template {process_id}.fixed_parameters",
            allow_empty=True,
        )
    )
    product_map = _required_text(spec, "product_map", field_name=f"process_template {process_id}")
    return {
        "id": process_id,
        "process_type": process_type,
        "states": states,
        "parameters": parameters,
        "product_map": product_map,
        "modifiers": _process_modifiers(
            spec,
            chain=chain,
            registry=registry,
            process_id=process_id,
        ),
        "output_state_roles": dict(chain.state_roles),
        "assumptions": [str(item) for item in spec.get("assumptions", ()) or ()],
    }


def _process_modifiers(
    spec: Mapping[str, Any],
    *,
    chain: ChainTemplateSpec,
    registry: FungModRegistry,
    process_id: str,
) -> list[dict[str, Any]]:
    modifiers: list[dict[str, Any]] = []
    for index, modifier in enumerate(
        _mapping_sequence(spec.get("modifiers"), field_name=f"process_template {process_id}.modifiers", allow_empty=True)
    ):
        modifier_type = _required_text(
            modifier,
            "type",
            field_name=f"process_template {process_id}.modifiers[{index}]",
        )
        if modifier_type in ENVIRONMENT_MODIFIER_TYPES:
            if chain.environment_id is None:
                raise EnzymeChainAssemblyError(
                    f"Process template {process_id!r} modifier {modifier_type!r} requires an explicit environment_id."
                )
            modifiers.append(
                build_template_environment_modifier(
                    template_id=chain.template.case_template_id,
                    parameter_symbols={
                        role: record.parameter_symbol
                        for role, record in chain.parameter_records.items()
                    },
                    registry=registry,
                    environment_id=chain.environment_id,
                    modifier=modifier,
                    modifier_type=modifier_type,
                    index=index,
                    modifier_label=(
                        f"Template {chain.template.case_template_id!r} process {process_id!r} "
                        f"modifiers[{index}]"
                    ),
                    unresolved_label=(
                        f"Template {chain.template.case_template_id!r} process {process_id!r} modifier"
                    ),
                    error_type=EnzymeChainAssemblyError,
                )
            )
            continue
        if modifier_type != "product_inhibition":
            raise EnzymeChainAssemblyError(
                f"Process template {process_id!r} declares unsupported modifier type {modifier_type!r}."
            )
        product_role = _required_text(
            modifier,
            "product_state_role",
            field_name=f"process_template {process_id}.modifiers[{index}]",
        )
        try:
            product_state = chain.state_roles[product_role]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Process template {process_id!r} product_inhibition modifier references unknown "
                f"product_state_role {product_role!r}."
            ) from exc
        inhibition_role = _required_text(
            modifier,
            "inhibition_constant_role",
            field_name=f"process_template {process_id}.modifiers[{index}]",
        )
        try:
            inhibition_constant = chain.parameter_records[inhibition_role].parameter_symbol
        except KeyError as exc:
            raise EnzymeChainAssemblyError(
                f"Process template {process_id!r} product_inhibition modifier references unknown "
                f"inhibition_constant_role {inhibition_role!r}."
            ) from exc
        modifiers.append(
            {
                "type": "product_inhibition",
                "product_state": product_state,
                "inhibition_constant": inhibition_constant,
            }
        )
    return modifiers


def _chain_environment_entity(
    *,
    registry: FungModRegistry,
    chain: ChainTemplateSpec,
    processes: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    modifiers: list[dict[str, Any]] = []
    for process in processes:
        for modifier in process.get("modifiers", ()) or ():
            modifiers.append(dict(modifier))
    if chain.environment_id is None:
        return None
    return build_template_environment_entity(
        registry=registry,
        environment_id=chain.environment_id,
        modifiers=modifiers,
        error_type=EnzymeChainAssemblyError,
    )


def _validate_product_map_ids(template: CaseTemplateRecord, specs: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for spec in specs:
        map_id = _required_text(spec, "id", field_name="process_state_metadata.product_maps")
        legacy = sorted(str(field) for field in _LEGACY_PRODUCT_MAP_FIELDS.intersection(spec))
        if legacy:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} product map {map_id!r} mixes chain product-map "
                f"coefficients with legacy field(s): {', '.join(legacy)}."
            )
        if map_id in seen:
            raise EnzymeChainAssemblyError(f"Template {template.case_template_id!r} repeats product map id {map_id!r}.")
        seen.add(map_id)
    legacy_map = template.product_map
    if legacy_map:
        legacy_id = str(legacy_map.get("id", ""))
        matching = next((spec for spec in specs if str(spec.get("id", "")) == legacy_id), None)
        if matching is None:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} legacy product_map id {legacy_id!r} does not match a "
                "declared chain product map."
            )
        product_role = str(legacy_map.get("product_state_role", ""))
        if product_role:
            products = _mapping(matching.get("products"), field_name=f"product_map {legacy_id}.products")
            if product_role not in products:
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} legacy product_state_role {product_role!r} conflicts "
                    f"with chain product map {legacy_id!r}."
                )
            legacy_yield = legacy_map.get("stoichiometric_yield")
            if legacy_yield is not None:
                declared = _positive_finite_float(
                    products[product_role],
                    field_name=f"product_map {legacy_id}.products.{product_role}",
                )
                legacy_numeric = _positive_finite_float(
                    legacy_yield,
                    field_name=f"template {template.case_template_id}.product_map.stoichiometric_yield",
                )
                if not math.isclose(declared, legacy_numeric, rel_tol=1.0e-12, abs_tol=1.0e-12):
                    raise EnzymeChainAssemblyError(
                        f"Template {template.case_template_id!r} legacy stoichiometric_yield conflicts with "
                        f"chain product map {legacy_id!r}."
                    )


def _validate_process_templates(
    template: CaseTemplateRecord,
    specs: Sequence[Mapping[str, Any]],
    *,
    state_roles: Mapping[str, str],
    parameter_records: Mapping[str, ParameterRecord],
) -> None:
    product_map_ids = {str(item.get("id", "")) for item in _mapping_sequence(template.process_state_metadata.get("product_maps"), field_name="process_state_metadata.product_maps")}
    for spec in specs:
        process_id = _required_text(spec, "id", field_name="process_state_metadata.process_templates")
        legacy = sorted(str(field) for field in _LEGACY_PRODUCT_MAP_FIELDS.intersection(spec))
        if legacy:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} process template {process_id!r} contains legacy "
                f"product-map field(s): {', '.join(legacy)}."
            )
        for field_name, role_map in (
            ("state_roles", _mapping(spec.get("state_roles"), field_name=f"process_template {process_id}.state_roles")),
            (
                "parameter_roles",
                _mapping(spec.get("parameter_roles"), field_name=f"process_template {process_id}.parameter_roles"),
            ),
        ):
            valid_roles = state_roles if field_name == "state_roles" else parameter_records
            for role in role_map.values():
                role_text = str(role)
                if role_text not in valid_roles:
                    raise EnzymeChainAssemblyError(
                        f"Template {template.case_template_id!r} process {process_id!r} references unknown "
                        f"{field_name[:-1]} {role_text!r}."
                    )
        product_map = _required_text(spec, "product_map", field_name=f"process_template {process_id}")
        if product_map not in product_map_ids:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} process {process_id!r} references unknown product map "
                f"{product_map!r}."
            )
        for index, modifier in enumerate(
            _mapping_sequence(
                spec.get("modifiers"),
                field_name=f"process_template {process_id}.modifiers",
                allow_empty=True,
            )
        ):
            modifier_type = _required_text(
                modifier,
                "type",
                field_name=f"process_template {process_id}.modifiers[{index}]",
            )
            if modifier_type in ENVIRONMENT_MODIFIER_TYPES:
                continue
            if modifier_type != "product_inhibition":
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} process {process_id!r} declares unsupported "
                    f"modifier type {modifier_type!r}."
                )
            product_role = _required_text(
                modifier,
                "product_state_role",
                field_name=f"process_template {process_id}.modifiers[{index}]",
            )
            if product_role not in state_roles:
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} process {process_id!r} modifier references unknown "
                    f"product_state_role {product_role!r}."
                )
            inhibition_role = _required_text(
                modifier,
                "inhibition_constant_role",
                field_name=f"process_template {process_id}.modifiers[{index}]",
            )
            if inhibition_role not in parameter_records:
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} process {process_id!r} modifier references unknown "
                    f"inhibition_constant_role {inhibition_role!r}."
                )


def _conservation_spec(
    *,
    template: CaseTemplateRecord,
    metadata: Mapping[str, Any],
    state_roles: Mapping[str, str],
    state_units: Mapping[str, str],
    product_maps: Sequence[Mapping[str, Any]],
) -> ChainConservationSpec:
    conservation = _mapping(metadata.get("conservation"), field_name="process_state_metadata.conservation")
    validator_id = _required_text(conservation, "id", field_name="process_state_metadata.conservation")
    if "closed_system" not in conservation:
        raise EnzymeChainAssemblyError(
            f"Template {template.case_template_id!r} conservation {validator_id!r} must declare closed_system."
        )
    role_weights: dict[str, float] = {}
    for role, weight in _mapping(
        conservation.get("state_weights"),
        field_name="process_state_metadata.conservation.state_weights",
    ).items():
        role_text = str(role)
        if role_text not in state_roles:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} conservation {validator_id!r} references unknown "
                f"state role {role_text!r}."
            )
        state_name = state_roles[role_text]
        if state_name not in state_units:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} conservation {validator_id!r} references state "
                f"{state_name!r} without units."
            )
        role_weights[role_text] = _positive_finite_float(
            weight,
            field_name=f"template {template.case_template_id} conservation.state_weights.{role_text}",
        )
    state_weights = {state_roles[role]: weight for role, weight in role_weights.items()}
    for spec in product_maps:
        map_id = _required_text(spec, "id", field_name="process_state_metadata.product_maps")
        reactants = _state_coefficients(
            spec.get("reactants"),
            state_roles=state_roles,
            state_units=state_units,
            template_id=template.case_template_id,
            map_id=map_id,
            side="reactants",
        )
        products = _state_coefficients(
            spec.get("products"),
            state_roles=state_roles,
            state_units=state_units,
            template_id=template.case_template_id,
            map_id=map_id,
            side="products",
        )
        missing_weights = sorted((set(reactants) | set(products)).difference(state_weights))
        if missing_weights:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} conservation {validator_id!r} lacks weights for "
                f"product map {map_id!r} state(s): {', '.join(missing_weights)}."
            )
        reactant_total = sum(coef * state_weights[state] for state, coef in reactants.items())
        product_total = sum(coef * state_weights[state] for state, coef in products.items())
        if not math.isclose(reactant_total, product_total, rel_tol=1.0e-9, abs_tol=1.0e-12):
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} conservation {validator_id!r} is inconsistent for "
                f"product map {map_id!r}: reactants={reactant_total}, products={product_total}."
            )
    return ChainConservationSpec(
        validator_id=validator_id,
        role_weights=role_weights,
        state_weights=state_weights,
        closed_system=bool(conservation["closed_system"]),
    )


def _chain_outputs(
    *,
    template: CaseTemplateRecord,
    metadata: Mapping[str, Any],
    state_roles: Mapping[str, str],
    state_units: Mapping[str, str],
    conservation: ChainConservationSpec,
) -> Mapping[str, Any]:
    outputs = _mapping(metadata.get("chain_outputs"), field_name="process_state_metadata.chain_outputs")
    derived_ids: set[str] = set()
    for item in _mapping_sequence(outputs.get("state_series"), field_name="chain_outputs.state_series"):
        _validate_output_role(template, item, state_roles=state_roles, state_units=state_units, field_name="state_series")
        _required_text(item, "label", field_name="chain_outputs.state_series")
    for item in _mapping_sequence(outputs.get("derived_series"), field_name="chain_outputs.derived_series"):
        derived_id = _required_text(item, "id", field_name="chain_outputs.derived_series")
        if derived_id in derived_ids:
            raise EnzymeChainAssemblyError(f"Template {template.case_template_id!r} repeats derived output {derived_id!r}.")
        derived_ids.add(derived_id)
        kind = _required_text(item, "kind", field_name=f"chain_outputs.derived_series.{derived_id}")
        _required_text(item, "label", field_name=f"chain_outputs.derived_series.{derived_id}")
        if kind == "fractional_depletion":
            _validate_output_role(template, item, state_roles=state_roles, state_units=state_units, field_name=derived_id)
        elif kind == "conserved_equivalent_fraction":
            role = _validate_output_role(template, item, state_roles=state_roles, state_units=state_units, field_name=derived_id)
            denominator_role = _required_text(item, "denominator_role", field_name=f"chain_outputs.derived_series.{derived_id}")
            if denominator_role not in state_roles:
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} derived output {derived_id!r} references unknown "
                    f"denominator_role {denominator_role!r}."
                )
            for weighted_role in (role, denominator_role):
                if weighted_role not in conservation.role_weights:
                    raise EnzymeChainAssemblyError(
                        f"Template {template.case_template_id!r} derived output {derived_id!r} needs a conservation "
                        f"weight for role {weighted_role!r}."
                    )
        else:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} derived output {derived_id!r} has unsupported kind {kind!r}."
            )
        for threshold in item.get("threshold_fractions", ()) or ():
            numeric = _positive_finite_float(
                threshold,
                field_name=f"template {template.case_template_id} derived output {derived_id}.threshold_fractions",
            )
            if numeric > 1.0:
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} derived output {derived_id!r} threshold {numeric} "
                    "must be <= 1.0."
                )
    for item in _mapping_sequence(outputs.get("final_metrics"), field_name="chain_outputs.final_metrics"):
        metric_id = _required_text(item, "id", field_name="chain_outputs.final_metrics")
        kind = _required_text(item, "kind", field_name=f"chain_outputs.final_metrics.{metric_id}")
        _required_text(item, "label", field_name=f"chain_outputs.final_metrics.{metric_id}")
        if kind == "final_state":
            _validate_output_role(template, item, state_roles=state_roles, state_units=state_units, field_name=metric_id)
        elif kind == "final_derived":
            derived_ref = _required_text(item, "derived_series", field_name=f"chain_outputs.final_metrics.{metric_id}")
            if derived_ref not in derived_ids:
                raise EnzymeChainAssemblyError(
                    f"Template {template.case_template_id!r} final metric {metric_id!r} references unknown "
                    f"derived_series {derived_ref!r}."
                )
        else:
            raise EnzymeChainAssemblyError(
                f"Template {template.case_template_id!r} final metric {metric_id!r} has unsupported kind {kind!r}."
            )
    return deepcopy(dict(outputs))


def _validate_output_role(
    template: CaseTemplateRecord,
    item: Mapping[str, Any],
    *,
    state_roles: Mapping[str, str],
    state_units: Mapping[str, str],
    field_name: str,
) -> str:
    role = _required_text(item, "role", field_name=f"chain_outputs.{field_name}")
    if role not in state_roles:
        raise EnzymeChainAssemblyError(
            f"Template {template.case_template_id!r} output {field_name!r} references unknown state role {role!r}."
        )
    state_name = state_roles[role]
    if state_name not in state_units:
        raise EnzymeChainAssemblyError(
            f"Template {template.case_template_id!r} output {field_name!r} references state {state_name!r} without units."
        )
    return role


def _initial_state(chain: ChainTemplateSpec) -> dict[str, Any]:
    states: dict[str, dict[str, Any]] = {}
    for role, spec in chain.template.initial_state_mapping.items():
        state_name = chain.state_roles[role]
        if "parameter_role" in spec:
            record = chain.parameter_records[str(spec["parameter_role"])]
            value, units = _exact_value_and_units(record)
            states[state_name] = {"value": value, "units": units}
        else:
            units = chain.state_units[state_name]
            states[state_name] = {"value": float(spec["value"]), "units": units}
    return {"states": states}


def _time_config(template: CaseTemplateRecord) -> dict[str, Any]:
    return {
        "start": {"value": float(template.time_grid["start"]), "units": str(template.time_grid["units"])},
        "stop": {"value": float(template.time_grid["stop"]), "units": str(template.time_grid["units"])},
        "points": int(template.time_grid["points"]),
    }


def _validators(chain: ChainTemplateSpec) -> list[dict[str, Any]]:
    return [
        {
            "id": "non_negative_chain_states",
            "validator_type": "non_negative",
            "species": list(dict.fromkeys(chain.state_roles.values())),
        },
        {
            "id": chain.conservation.validator_id,
            "validator_type": "mass_balance",
            "closed_system": chain.conservation.closed_system,
            "conserved_weights": dict(chain.conservation.state_weights),
        },
    ]


def _parameter_config(record: ParameterRecord, *, role: str) -> dict[str, Any]:
    value, units = _exact_value_and_units(record)
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": value,
        "units": units,
        "uncertainty": 0.0,
        "source": record.value.source or record.provenance.get("source", "FungMod registry record"),
        "confidence_level": record.value.confidence_level
        or record.provenance.get("confidence_level", "exploratory_assumption"),
        "notes": f"{record.notes} Registry chain role: {role}.",
        "measurement_method": record.provenance.get("measurement_method", "registry exact ValueSpec"),
        "validity_range": record.provenance.get("validity_range", record.allowed_use or "enzyme-chain template only"),
    }


def _exact_value_and_units(record: ParameterRecord) -> tuple[float, str]:
    value = record.value.value
    units = record.value.units
    if value is None or units is None:
        raise EnzymeChainAssemblyError(f"Parameter record {record.record_id!r} must define value and units.")
    return float(value), str(units)


def _chain_provenance(
    *,
    registry: FungModRegistry,
    chain: ChainTemplateSpec,
) -> dict[str, Any]:
    return {
        "source": chain.template.provenance.get("source", "FungMod extracellular enzyme-chain registry template."),
        "confidence_level": chain.template.provenance.get("confidence_level", "exploratory_assumption"),
        "bio_milestone": "BIO-002",
        "registry_id": registry.registry_id,
        "case_template_id": chain.template.case_template_id,
        "parameter_record_ids": {
            role: record.record_id
            for role, record in chain.parameter_records.items()
        },
        "notes": (
            "Reusable extracellular enzyme-chain assembled from registry template metadata. "
            "The configured template supplies all entity, stoichiometry, conservation, and output semantics."
        ),
    }


def _case_template_config(chain: ChainTemplateSpec) -> dict[str, Any]:
    return {
        "case_template_id": chain.template.case_template_id,
        "schema_version": chain.template.schema_version,
        "process_type": chain.template.process_type,
        "state_roles": dict(chain.state_roles),
        "observable_roles": list(chain.template.observable_roles),
        "output_state_roles": dict(chain.template.output_state_roles),
        "limitations": list(chain.template.limitations),
        "validity_notes": list(chain.template.validity_notes),
        "conservation": {
            "id": chain.conservation.validator_id,
            "state_weights": dict(chain.conservation.state_weights),
            "closed_system": chain.conservation.closed_system,
        },
    }


def _suggested_experiments(metadata: Mapping[str, Any]) -> list[Any]:
    suggestions = metadata.get("suggested_experiments", ())
    return deepcopy(list(suggestions)) if isinstance(suggestions, Sequence) and not isinstance(suggestions, str) else []


def _metadata_text(metadata: Mapping[str, Any], key: str, fallback: str) -> str:
    value = metadata.get(key)
    return fallback if value is None else str(value)


def _config_state_roles(config: ModelConfig) -> Mapping[str, str]:
    case_template = config.raw.get("case_template", {})
    if isinstance(case_template, Mapping) and isinstance(case_template.get("state_roles"), Mapping):
        return {str(role): str(state) for role, state in case_template["state_roles"].items()}
    raise EnzymeChainAssemblyError("Config is missing case_template.state_roles for enzyme-chain tables.")


def _config_chain_outputs(config: ModelConfig) -> Mapping[str, Any]:
    outputs = config.raw.get("chain_outputs")
    if isinstance(outputs, Mapping):
        return outputs
    raise EnzymeChainAssemblyError("Config is missing chain_outputs for enzyme-chain tables.")


def _config_conservation(config: ModelConfig) -> Mapping[str, float]:
    for validator in config.validators:
        if validator.validator_type == "mass_balance" and "conserved_weights" in validator.settings:
            return {
                str(name): _positive_finite_float(value, field_name=f"validator {validator.id}.conserved_weights.{name}")
                for name, value in validator.settings["conserved_weights"].items()
            }
    raise EnzymeChainAssemblyError("Config is missing a mass_balance validator with conserved_weights.")


def _derived_series(
    *,
    config: ModelConfig,
    result: SimulationResult,
    outputs: Mapping[str, Any],
    conservation: Mapping[str, float],
) -> dict[str, dict[str, Any]]:
    state_roles = _config_state_roles(config)
    derived: dict[str, dict[str, Any]] = {}
    for spec in _mapping_sequence(outputs.get("derived_series"), field_name="chain_outputs.derived_series"):
        series_id = _required_text(spec, "id", field_name="chain_outputs.derived_series")
        label = _required_text(spec, "label", field_name=f"chain_outputs.derived_series.{series_id}")
        kind = _required_text(spec, "kind", field_name=f"chain_outputs.derived_series.{series_id}")
        role = _required_text(spec, "role", field_name=f"chain_outputs.derived_series.{series_id}")
        state_name = _state_for_role(state_roles, role, field_name=f"chain_outputs.derived_series.{series_id}.role")
        values = _values(result.states[state_name])
        if kind == "fractional_depletion":
            denominator = _positive_denominator(float(values[0]), field_name=f"derived output {series_id}")
            series_values = (float(values[0]) - values) / denominator
        elif kind == "conserved_equivalent_fraction":
            denominator_role = _required_text(
                spec,
                "denominator_role",
                field_name=f"chain_outputs.derived_series.{series_id}",
            )
            denominator_state = _state_for_role(
                state_roles,
                denominator_role,
                field_name=f"chain_outputs.derived_series.{series_id}.denominator_role",
            )
            denominator_values = _values(result.states[denominator_state])
            numerator_weight = conservation[state_name]
            denominator_weight = conservation[denominator_state]
            denominator = _positive_denominator(
                float(denominator_values[0]) * denominator_weight,
                field_name=f"derived output {series_id}",
            )
            series_values = values * numerator_weight / denominator
        else:
            raise EnzymeChainAssemblyError(f"Unsupported derived output kind {kind!r} for {series_id!r}.")
        derived[series_id] = {
            "id": series_id,
            "label": label,
            "kind": kind,
            "values": np.asarray(series_values, dtype=float),
            "units": str(spec.get("units", "dimensionless")),
            "status": str(spec.get("status", "derived_from_chain_stoichiometry")),
            "notes": str(spec.get("notes", "")),
        }
    return derived


def _time_series_rows(
    config: ModelConfig,
    result: SimulationResult,
    outputs: Mapping[str, Any],
    derived: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    state_roles = _config_state_roles(config)
    rows: list[dict[str, Any]] = []
    time_values = _values(result.time)
    time_units = str(result.time.units)
    for spec in _mapping_sequence(outputs.get("state_series"), field_name="chain_outputs.state_series"):
        role = _required_text(spec, "role", field_name="chain_outputs.state_series")
        label = _required_text(spec, "label", field_name="chain_outputs.state_series")
        state_name = _state_for_role(state_roles, role, field_name=f"chain_outputs.state_series.{label}.role")
        quantity = result.states[state_name]
        rows.extend(
            {
                "time": time,
                "time_units": time_units,
                "role": role,
                "state": label,
                "state_id": state_name,
                "value": value,
                "units": str(quantity.units),
                "status": str(spec.get("status", "model_state")),
            }
            for time, value in zip(time_values, _values(quantity), strict=True)
        )
    for item in derived.values():
        rows.extend(
            _derived_series_rows(
                time_values,
                time_units,
                state_name=str(item["label"]),
                values=np.asarray(item["values"], dtype=float),
                units=str(item["units"]),
                status=str(item["status"]),
            )
        )
    for rate_name, quantity in result.process_rates.items():
        rows.extend(
            {
                "time": time,
                "time_units": time_units,
                "role": "process_rate",
                "state": rate_name,
                "state_id": rate_name,
                "value": value,
                "units": str(quantity.units),
                "status": "process_rate",
            }
            for time, value in zip(time_values, _values(quantity), strict=True)
        )
    return rows


def _derived_series_rows(
    time_values: np.ndarray,
    time_units: str,
    *,
    state_name: str,
    values: np.ndarray,
    units: str,
    status: str,
) -> list[dict[str, Any]]:
    return [
        {
            "time": time,
            "time_units": time_units,
            "role": "derived_metric",
            "state": state_name,
            "state_id": state_name,
            "value": value,
            "units": units,
            "status": status,
        }
        for time, value in zip(time_values, values, strict=True)
    ]


def _final_metric_rows(
    *,
    config: ModelConfig,
    result: SimulationResult,
    outputs: Mapping[str, Any],
    derived: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    state_roles = _config_state_roles(config)
    rows: list[dict[str, Any]] = []
    for spec in _mapping_sequence(outputs.get("final_metrics"), field_name="chain_outputs.final_metrics"):
        metric_id = _required_text(spec, "id", field_name="chain_outputs.final_metrics")
        label = _required_text(spec, "label", field_name=f"chain_outputs.final_metrics.{metric_id}")
        kind = _required_text(spec, "kind", field_name=f"chain_outputs.final_metrics.{metric_id}")
        if kind == "final_state":
            role = _required_text(spec, "role", field_name=f"chain_outputs.final_metrics.{metric_id}")
            state_name = _state_for_role(state_roles, role, field_name=f"chain_outputs.final_metrics.{metric_id}.role")
            rows.append(_final_state_metric(label, result.states[state_name], notes=str(spec.get("notes", ""))))
        elif kind == "final_derived":
            derived_id = _required_text(spec, "derived_series", field_name=f"chain_outputs.final_metrics.{metric_id}")
            item = derived[derived_id]
            rows.append(
                {
                    "metric": label,
                    "value": float(np.asarray(item["values"], dtype=float)[-1]),
                    "units": str(item["units"]),
                    "status": str(item["status"]),
                    "notes": str(spec.get("notes", item.get("notes", ""))),
                }
            )
        else:
            raise EnzymeChainAssemblyError(f"Unsupported final metric kind {kind!r} for {metric_id!r}.")
    rate_metrics = outputs.get("process_rate_metrics", {})
    if isinstance(rate_metrics, Mapping) and bool(rate_metrics.get("include_maximum", False)):
        for rate_name, quantity in result.process_rates.items():
            rows.append(
                {
                    "metric": f"maximum_{rate_name}",
                    "value": float(np.max(_values(quantity))),
                    "units": str(quantity.units),
                    "status": "computed",
                    "notes": "Maximum process rate over the configured time grid.",
                }
            )
    return rows


def _final_state_metric(metric: str, quantity: Any, *, notes: str = "") -> dict[str, Any]:
    return {
        "metric": metric,
        "value": float(_values(quantity)[-1]),
        "units": str(quantity.units),
        "status": "model_state",
        "notes": notes or "Final model state on the configured time grid.",
    }


def _threshold_rows(
    *,
    config: ModelConfig,
    result: SimulationResult,
    outputs: Mapping[str, Any],
    derived: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    del config
    rows: list[dict[str, Any]] = []
    time = _values(result.time)
    time_units = str(result.time.units)
    for spec in _mapping_sequence(outputs.get("derived_series"), field_name="chain_outputs.derived_series"):
        series_id = _required_text(spec, "id", field_name="chain_outputs.derived_series")
        thresholds = spec.get("threshold_fractions", ()) or ()
        if not thresholds:
            continue
        item = derived[series_id]
        for threshold in thresholds:
            numeric_threshold = float(threshold)
            crossing = threshold_crossing_time(
                time_values=time.tolist(),
                degraded_fraction=np.asarray(item["values"], dtype=float).tolist(),
                threshold=numeric_threshold,
            )
            rows.append(
                {
                    "threshold_fraction": numeric_threshold,
                    "value": "" if crossing is None else crossing,
                    "units": time_units,
                    "status": "not_reached" if crossing is None else "computed",
                    "metric": str(item["label"]),
                }
            )
    return rows


def _summary_rows(final_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "metric": row["metric"],
            "mean": row["value"],
            "min": row["value"],
            "max": row["value"],
            "units": row["units"],
            "n": 1,
            "status": row["status"],
        }
        for row in final_rows
    ]


def _limitation_rows(config: ModelConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    case_template = config.raw.get("case_template", {})
    if isinstance(case_template, Mapping):
        for index, limitation in enumerate(case_template.get("limitations", ()) or ()):
            rows.append(
                {
                    "category": "limitation",
                    "item_id": f"template_limitation_{index}",
                    "limitation": str(limitation),
                    "source": str(case_template.get("case_template_id", "")),
                }
            )
        for index, note in enumerate(case_template.get("validity_notes", ()) or ()):
            rows.append(
                {
                    "category": "validity_note",
                    "item_id": f"template_validity_note_{index}",
                    "limitation": str(note),
                    "source": str(case_template.get("case_template_id", "")),
                }
            )
    return rows


def _suggested_experiment_rows(config: ModelConfig) -> list[dict[str, Any]]:
    suggestions = config.raw.get("suggested_experiments", ()) or ()
    rows: list[dict[str, Any]] = []
    for index, suggestion in enumerate(suggestions):
        if isinstance(suggestion, Mapping):
            rows.append(
                {
                    "experiment_id": str(suggestion.get("id", f"suggested_experiment_{index}")),
                    "priority": str(suggestion.get("priority", "")),
                    "suggested_experiment": str(suggestion.get("description", "")),
                    "rationale": str(suggestion.get("rationale", "")),
                }
            )
        else:
            rows.append(
                {
                    "experiment_id": f"suggested_experiment_{index}",
                    "priority": "",
                    "suggested_experiment": str(suggestion),
                    "rationale": "",
                }
            )
    return rows


def _state_for_role(state_roles: Mapping[str, str], role: str, *, field_name: str) -> str:
    try:
        return state_roles[role]
    except KeyError as exc:
        raise EnzymeChainAssemblyError(f"{field_name} references unknown state role {role!r}.") from exc


def _values(quantity: Any) -> np.ndarray:
    return np.asarray(quantity.magnitude, dtype=float).reshape(-1)


def _positive_denominator(value: float, *, field_name: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise EnzymeChainAssemblyError(f"{field_name} requires a positive finite denominator; got {value}.")
    return value


def _positive_finite_float(value: Any, *, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise EnzymeChainAssemblyError(f"{field_name} must be numeric.") from exc
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise EnzymeChainAssemblyError(f"{field_name} must be positive and finite; got {numeric!r}.")
    return numeric


def _required_text(value: Mapping[str, Any], key: str, *, field_name: str) -> str:
    text = str(value.get(key, "")).strip()
    if not text:
        raise EnzymeChainAssemblyError(f"{field_name}.{key} is required.")
    return text


def _mapping(value: Any, *, field_name: str, allow_empty: bool = False) -> Mapping[str, Any]:
    if isinstance(value, Mapping) and (value or allow_empty):
        return value
    if allow_empty and value is None:
        return {}
    raise EnzymeChainAssemblyError(f"{field_name} must be a mapping.")


def _mapping_sequence(value: Any, *, field_name: str, allow_empty: bool = False) -> tuple[Mapping[str, Any], ...]:
    if allow_empty and value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        if allow_empty and value == []:
            return ()
        raise EnzymeChainAssemblyError(f"{field_name} must be a non-empty sequence.")
    if not all(isinstance(item, Mapping) for item in value):
        raise EnzymeChainAssemblyError(f"{field_name} entries must be mappings.")
    return tuple(value)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({str(key) for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)


__all__ = [
    "BIO002_ENZYME_CHAIN_TEMPLATE_ID",
    "EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE",
    "ChainConservationSpec",
    "ChainTemplateSpec",
    "EnzymeChainAssemblyError",
    "EnzymeChainRunResult",
    "build_extracellular_enzyme_chain_config",
    "run_extracellular_enzyme_chain_demo",
    "write_enzyme_chain_standard_tables",
]
