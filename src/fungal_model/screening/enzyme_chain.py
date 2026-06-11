"""Registry-backed extracellular enzyme-chain assembly and tables."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
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
from fungal_model.workflows import run_configured_model


EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE = "extracellular_enzyme_chain"
BIO002_ENZYME_CHAIN_TEMPLATE_ID = "bio002_extracellular_enzyme_chain_template"


class EnzymeChainAssemblyError(ValueError):
    """Raised when an extracellular enzyme-chain template cannot assemble."""


@dataclass(frozen=True)
class EnzymeChainRunResult:
    """BIO-002 enzyme-chain demo output bundle."""

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
    output_directory: str | Path | None = None,
) -> ModelConfig:
    """Build a reusable extracellular enzyme-chain ``ModelConfig`` from registry metadata."""

    template = _chain_template(registry, template_id)
    metadata = _chain_metadata(template)
    state_roles = dict(template.state_roles)
    parameter_records = _parameter_records(registry, metadata)
    product_map_specs = _mapping_sequence(metadata.get("product_maps"), field_name="process_state_metadata.product_maps")
    process_specs = _mapping_sequence(metadata.get("process_templates"), field_name="process_state_metadata.process_templates")
    source = str(template.provenance.get("source", "FungMod extracellular enzyme-chain registry template."))
    data = {
        "kind": "model_config",
        "name": _metadata_text(metadata, "config_name", template.name),
        "mode": _metadata_text(metadata, "config_mode", "exploratory"),
        "maturity": _metadata_text(metadata, "config_maturity", "exploratory"),
        "provenance": _chain_provenance(
            registry=registry,
            template=template,
            parameter_records=parameter_records,
        ),
        "case_template": _case_template_config(template),
        "chain_outputs": _chain_outputs(metadata),
        "suggested_experiments": _suggested_experiments(metadata),
        "entities": {
            "geometry": {
                "id": "geometry",
                "loader": "well_mixed",
                "data": _geometry_data(metadata, source=source),
            },
            "substrates": [
                {
                    "id": "cellulose_film_generic",
                    "loader": "generic_solid",
                    "data": _solid_cellulose_substrate_data(source=source),
                }
            ],
            "enzymes": _enzyme_entities(source=source),
            "product_maps": [
                _product_map_entity(spec, state_roles=state_roles, template=template)
                for spec in product_map_specs
            ],
        },
        "parameters": [
            {
                "id": "bio002_enzyme_chain_parameters",
                "parameters": [
                    _parameter_config(record, role=role)
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": [
            _process_config(spec, state_roles=state_roles, parameter_records=parameter_records)
            for spec in process_specs
        ],
        "initial_state": _initial_state(template, parameter_records=parameter_records),
        "time": _time_config(template),
        "validators": _validators(template),
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
) -> EnzymeChainRunResult:
    """Build, run, and table the BIO-002 extracellular enzyme-chain demo."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    bundle_dir = root / "bundle"
    config = build_extracellular_enzyme_chain_config(
        registry=registry,
        template_id=template_id,
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
    """Write BIO-002 standard chain tables derived from a configured result."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    state_roles = _config_state_roles(config)
    substrate_state = state_roles["substrate"]
    product_state = state_roles["product"]
    substrate = _values(result.states[substrate_state])
    product = _values(result.states[product_state])
    time = _values(result.time)
    initial_substrate = float(substrate[0])
    product_yield = _product_yield(config)
    degraded_fraction = _fraction(initial_substrate - substrate, initial_substrate)
    glucose_yield = _fraction(product / product_yield, initial_substrate)
    paths = {
        "time_series_long": destination / "time_series_long.csv",
        "final_metrics": destination / "final_metrics.csv",
        "threshold_times": destination / "threshold_times.csv",
        "summary_metrics": destination / "summary_metrics.csv",
        "limitations_table": destination / "limitations_table.csv",
        "suggested_experiments": destination / "suggested_experiments.csv",
    }
    _write_csv(paths["time_series_long"], _time_series_rows(config, result, degraded_fraction, glucose_yield))
    final_rows = _final_metric_rows(
        result=result,
        state_roles=state_roles,
        degraded_fraction=degraded_fraction,
        glucose_yield=glucose_yield,
    )
    _write_csv(paths["final_metrics"], final_rows)
    _write_csv(paths["threshold_times"], _threshold_rows(time, degraded_fraction, str(result.time.units)))
    _write_csv(paths["summary_metrics"], _summary_rows(final_rows))
    _write_csv(paths["limitations_table"], _limitation_rows(config))
    _write_csv(paths["suggested_experiments"], _suggested_experiment_rows(config))
    return {name: str(path) for name, path in paths.items()}


def _chain_template(registry: FungModRegistry, template_id: str) -> CaseTemplateRecord:
    try:
        template = registry.get_case_template(template_id)
    except RegistryLookupError as exc:
        raise EnzymeChainAssemblyError(f"Unknown extracellular enzyme-chain template: {template_id}") from exc
    if template.process_type != EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE:
        raise EnzymeChainAssemblyError(
            f"Template {template_id!r} must use process_type={EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE!r}."
        )
    for role in ("substrate", "intermediate", "product", "surface_catalyst", "homogeneous_catalyst"):
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
        try:
            record = registry.parameters[str(record_id)]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(f"Unknown parameter record for role {role!r}: {record_id}") from exc
        if not record.value.is_exact:
            raise EnzymeChainAssemblyError(
                f"BIO-002 deterministic demo requires exact parameter records; role {role!r} "
                f"uses {record.record_id!r} with ValueSpec kind {record.value.kind!r}."
            )
        if record.value.value is None or record.value.units is None:
            raise EnzymeChainAssemblyError(f"Parameter record {record.record_id!r} must define value and units.")
        records[str(role)] = record
    return records


def _product_map_entity(
    spec: Mapping[str, Any],
    *,
    state_roles: Mapping[str, str],
    template: CaseTemplateRecord,
) -> dict[str, Any]:
    product_map_type = str(spec["product_map_type"])
    reactants = _state_coefficients(spec.get("reactants"), state_roles=state_roles)
    products = _state_coefficients(spec.get("products"), state_roles=state_roles)
    data = {
        "kind": "product_map",
        "name": str(spec.get("name", spec["id"])),
        "product_map_type": product_map_type,
        "maturity": template.maturity,
        "provenance": {
            "source": template.provenance.get("source", "FungMod BIO-002 template."),
            "confidence_level": template.provenance.get("confidence_level", "exploratory_assumption"),
            "bio_milestone": "BIO-002",
            "notes": str(spec.get("notes", "")),
        },
        "notes": str(spec.get("notes", "")),
        "reactants": reactants,
        "products": products,
    }
    return {
        "id": str(spec["id"]),
        "loader": product_map_type,
        "data": data,
    }


def _state_coefficients(value: Any, *, state_roles: Mapping[str, str]) -> dict[str, float]:
    mapping = _mapping(value, field_name="product_map.coefficients")
    coefficients: dict[str, float] = {}
    for role, coefficient in mapping.items():
        try:
            state_name = state_roles[str(role)]
        except KeyError as exc:
            raise EnzymeChainAssemblyError(f"Unknown state role in product-map coefficients: {role}") from exc
        coefficients[state_name] = float(coefficient)
    return coefficients


def _process_config(
    spec: Mapping[str, Any],
    *,
    state_roles: Mapping[str, str],
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    state_role_refs = _mapping(spec.get("state_roles"), field_name="process_template.state_roles")
    fixed_states = _mapping(spec.get("fixed_states"), field_name="process_template.fixed_states", allow_empty=True)
    parameter_role_refs = _mapping(spec.get("parameter_roles"), field_name="process_template.parameter_roles")
    states = {
        process_field: state_roles[str(role)]
        for process_field, role in state_role_refs.items()
    }
    states.update({str(key): value for key, value in fixed_states.items()})
    parameters = {
        process_field: parameter_records[str(role)].parameter_symbol
        for process_field, role in parameter_role_refs.items()
    }
    parameters.update(_mapping(spec.get("fixed_parameters"), field_name="process_template.fixed_parameters", allow_empty=True))
    return {
        "id": str(spec["id"]),
        "process_type": str(spec["process_type"]),
        "states": states,
        "parameters": parameters,
        "product_map": str(spec["product_map"]),
        "output_state_roles": dict(state_roles),
        "assumptions": [str(item) for item in spec.get("assumptions", ()) or ()],
    }


def _initial_state(
    template: CaseTemplateRecord,
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    states: dict[str, dict[str, Any]] = {}
    for role, spec in template.initial_state_mapping.items():
        state_name = template.state_roles[role]
        if "parameter_role" in spec:
            record = parameter_records[str(spec["parameter_role"])]
            value, units = _exact_value_and_units(record)
            states[state_name] = {"value": value, "units": units}
        else:
            states[state_name] = {"value": float(spec["value"]), "units": str(spec["units"])}
    return {"states": states}


def _time_config(template: CaseTemplateRecord) -> dict[str, Any]:
    return {
        "start": {"value": float(template.time_grid["start"]), "units": str(template.time_grid["units"])},
        "stop": {"value": float(template.time_grid["stop"]), "units": str(template.time_grid["units"])},
        "points": int(template.time_grid["points"]),
    }


def _validators(template: CaseTemplateRecord) -> list[dict[str, Any]]:
    state_roles = template.state_roles
    return [
        {
            "id": "non_negative_chain_states",
            "validator_type": "non_negative",
            "species": list(state_roles.values()),
        },
        {
            "id": "cellobiose_equivalent_balance",
            "validator_type": "mass_balance",
            "conserved_weights": {
                state_roles["substrate"]: 1.0,
                state_roles["intermediate"]: 1.0,
                state_roles["product"]: 0.5,
            },
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
        "validity_range": record.provenance.get("validity_range", record.allowed_use or "BIO-002 demo only"),
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
    template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    return {
        "source": template.provenance.get("source", "FungMod BIO-002 registry template."),
        "confidence_level": template.provenance.get("confidence_level", "exploratory_assumption"),
        "bio_milestone": "BIO-002",
        "registry_id": registry.registry_id,
        "case_template_id": template.case_template_id,
        "parameter_record_ids": {
            role: record.record_id
            for role, record in parameter_records.items()
        },
        "notes": (
            "Reusable extracellular enzyme-chain demo assembled from registry template metadata. "
            "This is not a whole-fungus growth, secretion, uptake, or biomass model."
        ),
    }


def _case_template_config(template: CaseTemplateRecord) -> dict[str, Any]:
    return {
        "case_template_id": template.case_template_id,
        "schema_version": template.schema_version,
        "process_type": template.process_type,
        "state_roles": dict(template.state_roles),
        "observable_roles": list(template.observable_roles),
        "output_state_roles": dict(template.output_state_roles),
        "limitations": list(template.limitations),
        "validity_notes": list(template.validity_notes),
    }


def _solid_cellulose_substrate_data(*, source: str) -> dict[str, Any]:
    return {
        "kind": "substrate",
        "name": "Generic insoluble cellulose-equivalent substrate",
        "substrate_type": "generic_solid",
        "chemical_class": "cellulose_film_generic",
        "physical_state": "solid_polymer",
        "bond_types": ["beta_1_4_glycosidic"],
        "accessible_bonds": ["beta_1_4_glycosidic"],
        "required_enzyme_classes": ["cellulase_generic"],
        "degradation_products": [
            {
                "name": "cellobiose",
                "source": source,
                "notes": "BIO-002 soluble intermediate in a cellulose-equivalent enzyme-chain scaffold.",
            }
        ],
        "completeness": "partial",
        "default_degradation_model": "heterogeneous_surface",
        "water_activity_dependence": "unknown",
        "provenance": {
            "source": source,
            "confidence_level": "exploratory_assumption",
            "notes": "Solid substrate represented as an explicit cellobiose-equivalent concentration state.",
        },
        "parameters": [],
    }


def _enzyme_entities(*, source: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "cellulase_generic",
            "data": {
                "kind": "enzyme",
                "name": "Generic extracellular cellulase catalyst",
                "enzyme_class": "cellulase_generic",
                "target_bond_types": ["beta_1_4_glycosidic"],
                "target_substrate_classes": ["cellulose_film_generic"],
                "target_substrate_names": ["Generic insoluble cellulose-equivalent substrate"],
                "validity_labels": ["BIO-002", "surface_cellobiose_release", "exploratory_metadata"],
                "provenance": {
                    "source": source,
                    "confidence_level": "exploratory_assumption",
                    "notes": "Explicit catalyst metadata; no secretion, uptake, biomass, or growth is represented.",
                },
                "catalytic_parameters": [],
                "adsorption_parameters": [],
                "parameters": [],
            },
        },
        {
            "id": "beta_glucosidase",
            "data": {
                "kind": "enzyme",
                "name": "beta-glucosidase",
                "enzyme_class": "beta_glucosidase",
                "target_bond_types": ["beta_1_4_glycosidic"],
                "target_substrate_classes": ["cellobiose"],
                "target_substrate_names": ["Cellobiose"],
                "validity_labels": ["BIO-002", "homogeneous_cellobiose_hydrolysis"],
                "provenance": {
                    "source": "SABIO-RK Reaction 618 selected kinetic law and BIO-002 scaffold metadata.",
                    "confidence_level": "literature_curated",
                    "notes": "Enzyme metadata for cellobiose hydrolysis; no uptake or biomass is represented.",
                },
                "catalytic_parameters": [],
                "adsorption_parameters": [],
                "parameters": [],
            },
        },
    ]


def _geometry_data(metadata: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    geometry = metadata.get("geometry")
    if isinstance(geometry, Mapping):
        return dict(geometry)
    return {
        "kind": "geometry",
        "name": "BIO-002 well-mixed extracellular enzyme assay context",
        "geometry_type": "well_mixed",
        "provenance": {
            "source": source,
            "confidence_level": "exploratory_assumption",
            "notes": "Well-mixed assay context; no spatial gradients or morphology evolution are represented.",
        },
        "volume": {"value": 100.0, "units": "milliliter"},
        "surface_area": {"value": 0.5, "units": "meter ** 2"},
        "parameters": [],
    }


def _chain_outputs(metadata: Mapping[str, Any]) -> dict[str, Any]:
    outputs = metadata.get("chain_outputs")
    return dict(outputs) if isinstance(outputs, Mapping) else {}


def _suggested_experiments(metadata: Mapping[str, Any]) -> list[Any]:
    suggestions = metadata.get("suggested_experiments", ())
    return list(suggestions) if isinstance(suggestions, Sequence) and not isinstance(suggestions, str) else []


def _metadata_text(metadata: Mapping[str, Any], key: str, fallback: str) -> str:
    value = metadata.get(key)
    return fallback if value is None else str(value)


def _mapping(value: Any, *, field_name: str, allow_empty: bool = False) -> Mapping[str, Any]:
    if isinstance(value, Mapping) and (value or allow_empty):
        return value
    if allow_empty and value is None:
        return {}
    raise EnzymeChainAssemblyError(f"{field_name} must be a mapping.")


def _mapping_sequence(value: Any, *, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise EnzymeChainAssemblyError(f"{field_name} must be a non-empty sequence.")
    if not all(isinstance(item, Mapping) for item in value):
        raise EnzymeChainAssemblyError(f"{field_name} entries must be mappings.")
    return tuple(value)


def _config_state_roles(config: ModelConfig) -> Mapping[str, str]:
    case_template = config.raw.get("case_template", {})
    if isinstance(case_template, Mapping) and isinstance(case_template.get("state_roles"), Mapping):
        return case_template["state_roles"]
    raise EnzymeChainAssemblyError("Config is missing case_template.state_roles for enzyme-chain tables.")


def _product_yield(config: ModelConfig) -> float:
    case_template = config.raw.get("case_template", {})
    if not isinstance(case_template, Mapping):
        return 2.0
    product_maps = config.raw.get("entities", {}).get("product_maps", []) if isinstance(config.raw.get("entities"), Mapping) else []
    for entry in product_maps:
        if not isinstance(entry, Mapping):
            continue
        data = entry.get("data")
        if isinstance(data, Mapping) and "beta_D_glucose_concentration" in data.get("products", {}):
            return float(data["products"]["beta_D_glucose_concentration"])
    return 2.0


def _values(quantity: Any) -> np.ndarray:
    return np.asarray(quantity.magnitude, dtype=float).reshape(-1)


def _fraction(numerator: np.ndarray | float, denominator: float) -> np.ndarray:
    if denominator <= 0.0:
        return np.zeros_like(np.asarray(numerator, dtype=float))
    return np.asarray(numerator, dtype=float) / denominator


def _time_series_rows(
    config: ModelConfig,
    result: SimulationResult,
    degraded_fraction: np.ndarray,
    glucose_yield: np.ndarray,
) -> list[dict[str, Any]]:
    state_roles = _config_state_roles(config)
    rows: list[dict[str, Any]] = []
    time_values = _values(result.time)
    time_units = str(result.time.units)
    for role in ("substrate", "intermediate", "product", "surface_catalyst", "homogeneous_catalyst"):
        state_name = state_roles[role]
        quantity = result.states[state_name]
        rows.extend(
            {
                "time": time,
                "time_units": time_units,
                "role": role,
                "state": state_name,
                "value": value,
                "units": str(quantity.units),
                "status": "model_state",
            }
            for time, value in zip(time_values, _values(quantity), strict=True)
        )
    rows.extend(_derived_series_rows(time_values, time_units, "solid_substrate_degraded_fraction", degraded_fraction))
    rows.extend(_derived_series_rows(time_values, time_units, "glucose_yield", glucose_yield))
    for rate_name, quantity in result.process_rates.items():
        rows.extend(
            {
                "time": time,
                "time_units": time_units,
                "role": "process_rate",
                "state": rate_name,
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
    state_name: str,
    values: np.ndarray,
) -> list[dict[str, Any]]:
    return [
        {
            "time": time,
            "time_units": time_units,
            "role": "derived_metric",
            "state": state_name,
            "value": value,
            "units": "dimensionless",
            "status": "derived_from_chain_stoichiometry",
        }
        for time, value in zip(time_values, values, strict=True)
    ]


def _final_metric_rows(
    *,
    result: SimulationResult,
    state_roles: Mapping[str, str],
    degraded_fraction: np.ndarray,
    glucose_yield: np.ndarray,
) -> list[dict[str, Any]]:
    rows = [
        _final_state_metric("solid_substrate_remaining", result.states[state_roles["substrate"]]),
        _final_state_metric("cellobiose", result.states[state_roles["intermediate"]]),
        _final_state_metric("glucose", result.states[state_roles["product"]]),
        {
            "metric": "solid_substrate_degraded_fraction",
            "value": float(degraded_fraction[-1]),
            "units": "dimensionless",
            "status": "derived_from_chain_stoichiometry",
            "notes": "Computed from initial and final solid cellulose-equivalent state.",
        },
        {
            "metric": "final_glucose_yield",
            "value": float(glucose_yield[-1]),
            "units": "dimensionless",
            "status": "derived_from_chain_stoichiometry",
            "notes": "Glucose divided by the 2:1 glucose-per-cellobiose stoichiometric maximum.",
        },
    ]
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


def _final_state_metric(metric: str, quantity: Any) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": float(_values(quantity)[-1]),
        "units": str(quantity.units),
        "status": "model_state",
        "notes": "Final model state on the configured time grid.",
    }


def _threshold_rows(time: np.ndarray, degraded_fraction: np.ndarray, time_units: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in (0.1, 0.5, 0.9):
        crossing = threshold_crossing_time(
            time_values=time.tolist(),
            degraded_fraction=degraded_fraction.tolist(),
            threshold=threshold,
        )
        rows.append(
            {
                "threshold_fraction": threshold,
                "value": "" if crossing is None else crossing,
                "units": time_units,
                "status": "not_reached" if crossing is None else "computed",
                "metric": "solid_substrate_degraded_fraction",
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
    "EnzymeChainAssemblyError",
    "EnzymeChainRunResult",
    "build_extracellular_enzyme_chain_config",
    "run_extracellular_enzyme_chain_demo",
    "write_enzyme_chain_standard_tables",
]
