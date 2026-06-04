"""Build runnable deterministic model configs from modelable registry cases."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import (
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
)
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.modelability import ModelabilityReport, assess_modelability

RegistryCaseConfigMode = Literal["toy", "scientific"]

SURFACE_CATALYSIS_PARAMETER_ROLES = (
    "surface_rate_constant",
    "adsorption_constant",
    "accessible_surface_area",
)
HOMOGENEOUS_MM_PARAMETER_ROLES = (
    "km",
    "kcat",
    "substrate_initial_concentration",
    "enzyme_initial_concentration",
)


class RegistryCaseBuildError(ValueError):
    """Raised when a registry case cannot be converted into a model config."""


@dataclass(frozen=True)
class RegistryProcessAssembler:
    """Config assembly metadata for one registry process type."""

    process_type: str
    process_label: str
    required_parameter_roles: tuple[str, ...]
    deterministic_mode: RegistryCaseConfigMode
    unsupported_mode_message: str
    config_data_builder: Callable[..., dict[str, Any]]


def build_model_config_from_registry_case(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: RegistryCaseConfigMode = "toy",
    output_directory: str | None = None,
) -> ModelConfig:
    """Convert a modelable registry case into a generic deterministic ``ModelConfig``."""

    _validate_mode(mode)
    report = assess_modelability(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        mode=mode,
    )
    if report.status != "modelable":
        raise RegistryCaseBuildError(
            "Registry case cannot be built because modelability status is "
            f"{report.status!r}; deterministic assembly requires exact modelable cases. "
            f"Report: {report.to_dict()}"
        )

    compatibility = select_registry_case_compatibility(
        registry=registry,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        report=report,
    )
    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        raise RegistryCaseBuildError(
            "Registry case builder does not support process_type "
            f"{compatibility.process_type!r}."
        )
    if mode != assembler.deterministic_mode:
        raise RegistryCaseBuildError(assembler.unsupported_mode_message)
    parameter_records = _exact_role_parameters(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        required_roles=assembler.required_parameter_roles,
        process_label=assembler.process_label,
    )
    config_data = build_registry_process_config_data(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        output_directory=output_directory,
    )
    return ModelConfig.from_mapping(config_data)


def get_registry_process_assembler(process_type: str) -> RegistryProcessAssembler | None:
    """Return assembly metadata for a supported registry process type."""

    return _REGISTRY_PROCESS_ASSEMBLERS.get(process_type)


def build_registry_process_config_data(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    """Build raw model-config data for a supported registry process."""

    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        raise RegistryCaseBuildError(
            "Registry case builder does not support process_type "
            f"{compatibility.process_type!r}."
        )
    substrate = registry.get_substrate(substrate_id)
    return assembler.config_data_builder(
        registry=registry,
        compatibility=compatibility,
        substrate=substrate,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        output_directory=output_directory,
    )


def select_registry_case_compatibility(
    *,
    registry: FungModRegistry,
    fungus_id: str,
    substrate_id: str,
    report: ModelabilityReport,
) -> ProcessCompatibilityRecord:
    fungus = registry.get_fungus(fungus_id)
    substrate = registry.get_substrate(substrate_id)
    for enzyme_class_id in fungus.enzyme_classes:
        for process_type in report.required_processes:
            for compatibility in registry.get_process_compatibility(
                enzyme_class=enzyme_class_id,
                substrate_class=substrate.substrate_class,
                process_type=process_type,
            ):
                if set(compatibility.required_bond_classes).issubset(substrate.bond_classes):
                    return compatibility
    raise RegistryCaseBuildError(
        "Modelability reported a modelable case, but no compatible process "
        "record could be selected for config assembly."
    )


def _exact_role_parameters(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    required_roles: tuple[str, ...],
    process_label: str,
) -> Mapping[str, ParameterRecord]:
    missing_roles = tuple(
        role for role in required_roles if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryCaseBuildError(
            f"{process_label} registry compatibility is missing parameter role "
            f"mappings for: {', '.join(missing_roles)}."
        )

    resolved: dict[str, ParameterRecord] = {}
    for role in required_roles:
        symbol = compatibility.parameter_roles[role]
        record = _best_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
        )
        if record is None:
            raise RegistryCaseBuildError(
                f"No registry parameter record found for role {role!r} and symbol {symbol!r}."
            )
        if not record.value.is_exact:
            raise RegistryCaseBuildError(
                f"Deterministic registry case builder requires exact parameters; role {role!r} uses "
                f"symbol {symbol!r} with ValueSpec kind {record.value.kind!r}."
            )
        validation = record.value.validate(nonnegative=True)
        if not validation.passed:
            raise RegistryCaseBuildError(
                f"Parameter {symbol!r} for role {role!r} failed ValueSpec validation: "
                f"{validation.to_dict()}"
            )
        resolved[role] = record
    return resolved


def _surface_catalysis_config_data(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    substrate_state = "solid_substrate_amount"
    product_state = "released_product_amount"
    catalyst_state = "free_catalyst_concentration"
    product_map_id = "registry_case_release_map"
    primary_bond = substrate.bond_classes[0]
    return {
        "kind": "model_config",
        "name": f"toy registry case {fungus_id} on {substrate_id}",
        "mode": "toy",
        "maturity": "framework_benchmark",
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "measurement_method": "software registry-to-config assembly test",
            "confidence_level": "testing",
            "notes": (
                "Toy/development plug-and-play assembly fixture only; not "
                "empirical evidence and not a biological model."
            ),
            "validity_range": "R3 framework tests only",
            "units": "not_applicable",
            "registry_id": registry.registry_id,
            "fungus_id": fungus_id,
            "substrate_id": substrate_id,
            "environment_id": environment_id,
            "process_compatibility_id": compatibility.record_id,
        },
        "entities": {
            "geometry": {
                "id": "geometry",
                "loader": "well_mixed",
                "data": _toy_geometry_data(),
            },
            "substrates": [
                {
                    "id": substrate_id,
                    "loader": "generic_solid",
                    "data": _generic_substrate_data(
                        substrate=substrate,
                        enzyme_class=compatibility.enzyme_class,
                    ),
                }
            ],
            "enzymes": [
                {
                    "id": compatibility.enzyme_class,
                    "data": _toy_enzyme_data(
                        compatibility=compatibility,
                        substrate=substrate,
                    ),
                }
            ],
            "product_maps": [
                {
                    "id": product_map_id,
                    "loader": "one_to_one",
                    "data": {
                        "kind": "product_map",
                        "name": "toy registry one-to-one product release map",
                        "product_map_type": "one_to_one",
                        "maturity": "framework_benchmark",
                        "provenance": {
                            "source": "FungMod R3 toy registry case builder.",
                            "confidence_level": "testing",
                            "notes": "Toy product map for config workflow tests only.",
                        },
                        "substrate_state": substrate_state,
                        "product_state": product_state,
                        "notes": "Mass-equivalent toy map; not a chemical stoichiometry claim.",
                    },
                }
            ],
        },
        "parameters": [
            {
                "id": "registry_case_parameters",
                "parameters": [
                    _parameter_config(record, role=role)
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": [
            {
                "id": "registry_surface_catalysis",
                "process_type": "surface_catalysis",
                "states": {
                    "substrate": substrate_state,
                    "catalyst": catalyst_state,
                    "product": product_state,
                    "bond_type": primary_bond,
                },
                "parameters": {
                    role: record.parameter_symbol
                    for role, record in parameter_records.items()
                },
                "product_map": product_map_id,
                "assumptions": [
                    "Toy registry case builder only.",
                    "Uses the existing generic surface-catalysis factory without adding biology.",
                ],
            }
        ],
        "initial_state": {
            "states": {
                substrate_state: {"value": 0.0001, "units": "kilogram"},
                product_state: {"value": 0.0, "units": "kilogram"},
                catalyst_state: {"value": 1.0, "units": "mole / liter"},
            }
        },
        "time": {
            "start": {"value": 0.0, "units": "second"},
            "stop": {"value": 20.0, "units": "second"},
            "points": 41,
        },
        "validators": [
            {
                "id": "non_negative_states",
                "validator_type": "non_negative",
                "species": [substrate_state, product_state, catalyst_state],
            },
            {
                "id": "closed_mass_balance",
                "validator_type": "mass_balance",
                "conserved_weights": {
                    substrate_state: 1.0,
                    product_state: 1.0,
                },
            },
        ],
        "outputs": {
            "directory": output_directory
            or f"outputs/registry_cases/{fungus_id}__{substrate_id}__{environment_id}",
            "save": ["record", "validation_report"],
            "plots": ["state_trajectories"],
        },
    }


def _homogeneous_mm_config_data(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    substrate_state = "cellobiose_concentration"
    product_state = "beta_D_glucose_concentration"
    enzyme_state = "beta_glucosidase_concentration"
    substrate_initial = parameter_records["substrate_initial_concentration"]
    enzyme_initial = parameter_records["enzyme_initial_concentration"]
    substrate_units = _record_units(substrate_initial, role="substrate_initial_concentration")
    enzyme_units = _record_units(enzyme_initial, role="enzyme_initial_concentration")
    rate_units = f"{substrate_units} / second"
    provenance = _homogeneous_mm_provenance(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
    )
    return {
        "kind": "model_config",
        "name": "SABIO-RK Reaction 618 beta-glucosidase cellobiose homogeneous Michaelis-Menten",
        "mode": "scientific",
        "maturity": "scientific",
        "provenance": provenance,
        "entities": {
            "substrates": [
                {
                    "id": substrate_id,
                    "loader": "generic_dissolved",
                    "data": _homogeneous_substrate_data(
                        substrate=substrate,
                        enzyme_class=compatibility.enzyme_class,
                        provenance=provenance,
                    ),
                }
            ],
            "enzymes": [
                {
                    "id": compatibility.enzyme_class,
                    "data": _homogeneous_enzyme_data(
                        compatibility=compatibility,
                        substrate=substrate,
                        provenance=provenance,
                    ),
                }
            ],
        },
        "parameters": [
            {
                "id": "sabiork_reaction_618_parameters",
                "parameters": [
                    _scientific_parameter_config(record, role=role)
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": [
            {
                "id": "sabiork_reaction_618_homogeneous_mm",
                "process_type": "homogeneous_michaelis_menten",
                "states": {
                    "substrate": substrate_state,
                    "product": product_state,
                    "enzyme": enzyme_state,
                },
                "parameters": {
                    "km": parameter_records["km"].parameter_symbol,
                    "kcat": parameter_records["kcat"].parameter_symbol,
                    "rate_units": rate_units,
                },
                "assumptions": [
                    "Dissolved homogeneous Michaelis-Menten kinetics for the selected SABIO-RK entry.",
                    "This is an enzyme-kinetics case, not a whole-fungus growth or uptake model.",
                ],
            }
        ],
        "initial_state": {
            "states": {
                substrate_state: {
                    "value": _record_exact_value(substrate_initial, role="substrate_initial_concentration"),
                    "units": substrate_units,
                },
                product_state: {
                    "value": 0.0,
                    "units": substrate_units,
                },
                enzyme_state: {
                    "value": _record_exact_value(enzyme_initial, role="enzyme_initial_concentration"),
                    "units": enzyme_units,
                },
            }
        },
        "time": {
            "start": {"value": 0.0, "units": "second"},
            "stop": {"value": 1000.0, "units": "second"},
            "points": 101,
        },
        "validators": [
            {
                "id": "non_negative_concentrations",
                "validator_type": "non_negative",
                "species": [substrate_state, product_state, enzyme_state],
            },
            {
                "id": "substrate_product_balance",
                "validator_type": "mass_balance",
                "conserved_weights": {
                    substrate_state: 1.0,
                    product_state: 1.0,
                },
            },
        ],
        "outputs": {
            "directory": output_directory
            or f"outputs/registry_cases/{fungus_id}__{substrate_id}__{environment_id}",
            "save": ["record", "validation_report"],
            "plots": ["state_trajectories"],
        },
    }


def _homogeneous_substrate_data(
    *,
    substrate: SubstrateRecord,
    enzyme_class: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": "generic_dissolved",
        "chemical_class": substrate.substrate_class,
        "physical_state": "dissolved",
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "source": provenance["source"],
                "notes": "Product listed by SABIO-RK Reaction 618 stoichiometry.",
            }
            for product in substrate.products
        ],
        "completeness": "partial",
        "default_degradation_model": "homogeneous_dissolved",
        "water_activity_dependence": "unknown",
        "provenance": {
            "source": provenance["source"],
            "confidence_level": "literature_curated",
            "notes": "Cellobiose substrate metadata from the curated Reaction 618 registry case.",
        },
        "parameters": [],
    }


def _homogeneous_enzyme_data(
    *,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "enzyme",
        "name": "beta-glucosidase",
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [substrate.name],
        "validity_labels": ["literature_metadata", "homogeneous_enzyme_kinetics"],
        "provenance": {
            "source": provenance["source"],
            "measurement_method": "SABIO-RK kinetic-law curation",
            "confidence_level": "literature_curated",
            "notes": (
                "Enzyme metadata for the selected Reaction 618 kinetic-law entry; "
                "does not model secretion, uptake, biomass growth, or organism-level degradation."
            ),
            "validity_range": "Selected SABIO-RK EntryID assay conditions.",
            "units": "not_applicable",
        },
        "catalytic_parameters": [],
        "adsorption_parameters": [],
        "parameters": [],
    }


def _toy_geometry_data() -> dict[str, Any]:
    return {
        "kind": "geometry",
        "name": "toy registry well-mixed 100 mL",
        "geometry_type": "well_mixed",
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "measurement_method": "defined benchmark metadata",
            "confidence_level": "testing",
            "notes": "Inline toy geometry for registry-to-config workflow tests.",
            "validity_range": "R3 framework tests only",
            "units": "not_applicable",
        },
        "volume": {"value": 100.0, "units": "milliliter"},
        "surface_area": {"value": 0.1, "units": "meter ** 2"},
        "parameters": [],
    }


def _generic_substrate_data(*, substrate: SubstrateRecord, enzyme_class: str) -> dict[str, Any]:
    return {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": "generic_solid",
        "chemical_class": substrate.substrate_class,
        "physical_state": _configured_physical_state(substrate.physical_state),
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "notes": "Toy registry product placeholder; not empirical.",
            }
            for product in substrate.products
        ],
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "confidence_level": "testing",
            "notes": "Inline generic substrate generated from toy registry metadata.",
        },
        "parameters": [],
    }


def _toy_enzyme_data(
    *,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
) -> dict[str, Any]:
    return {
        "kind": "enzyme",
        "name": f"Toy registry catalyst for {compatibility.enzyme_class}",
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [],
        "validity_labels": ["toy", "registry_case_builder"],
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "measurement_method": "defined benchmark metadata",
            "confidence_level": "testing",
            "notes": "Inline toy enzyme metadata for process compatibility only.",
            "validity_range": "R3 framework tests only",
            "units": "not_applicable",
        },
        "catalytic_parameters": [],
        "adsorption_parameters": [],
        "parameters": [],
    }


def _configured_physical_state(registry_physical_state: str) -> str:
    if registry_physical_state in {"mixed_solid", "solid_polymer", "solid_biomass", "dissolved", "unknown"}:
        return registry_physical_state
    if registry_physical_state in {"toy_solid", "solid"}:
        return "mixed_solid"
    raise RegistryCaseBuildError(
        "Registry substrate physical_state "
        f"{registry_physical_state!r} cannot be represented by the generic config loader."
    )


def _parameter_config(record: ParameterRecord, *, role: str) -> dict[str, Any]:
    assert record.value.value is not None
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": record.value.value,
        "units": record.value.units or "dimensionless",
        "uncertainty": 0.0,
        "source": record.value.source or record.provenance.get("source"),
        "confidence_level": record.value.confidence_level
        or record.provenance.get("confidence_level", "testing"),
        "notes": f"{record.notes} Registry case role: {role}. Toy/development only.",
        "measurement_method": "registry exact ValueSpec",
        "validity_range": "R3 toy registry case only",
    }


def _scientific_parameter_config(record: ParameterRecord, *, role: str) -> dict[str, Any]:
    value = _record_exact_value(record, role=role)
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": value,
        "units": _record_units(record, role=role),
        "uncertainty": 0.0,
        "source": record.value.source or _record_source(record),
        "confidence_level": record.value.confidence_level
        or record.provenance.get("confidence_level", "literature_curated"),
        "notes": f"{record.notes} Registry case role: {role}.",
        "measurement_method": "SABIO-RK selected kinetic-law curation",
        "validity_range": "Selected SABIO-RK EntryID assay conditions only.",
    }


def _record_exact_value(record: ParameterRecord, *, role: str) -> float:
    if record.value.value is None:
        raise RegistryCaseBuildError(
            f"Role {role!r} resolved to parameter {record.parameter_symbol!r} without an exact value."
        )
    return float(record.value.value)


def _record_units(record: ParameterRecord, *, role: str) -> str:
    if record.value.units is None:
        raise RegistryCaseBuildError(
            f"Role {role!r} resolved to parameter {record.parameter_symbol!r} without units."
        )
    return record.value.units


def _record_source(record: ParameterRecord) -> str:
    source = record.provenance.get("source")
    if source is not None:
        return str(source)
    if record.provenance.get("source_database") == "SABIO-RK":
        return "SABIO-RK Reaction 618 selected kinetic law"
    return "FungMod registry record"


def _homogeneous_mm_provenance(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    environment = registry.get_environment(environment_id)
    source = "SABIO-RK Reaction 618 selected kinetic law"
    return {
        "source": source,
        "source_database": compatibility.provenance.get("source_database", "SABIO-RK"),
        "source_reaction_id": compatibility.provenance.get("source_reaction_id"),
        "selected_kinlaw_entry_id": compatibility.provenance.get("selected_kinlaw_entry_id"),
        "kinetic_record": _first_present(
            record.provenance.get("kinetic_record")
            for record in parameter_records.values()
        ),
        "registry_id": registry.registry_id,
        "fungus_id": fungus_id,
        "substrate_id": substrate_id,
        "environment_id": environment_id,
        "process_compatibility_id": compatibility.record_id,
        "parameter_record_ids": {
            role: record.record_id
            for role, record in parameter_records.items()
        },
        "parameter_value_sources": {
            role: record.value.source
            for role, record in parameter_records.items()
        },
        "environment_conditions": {
            name: value.to_dict()
            for name, value in environment.conditions.items()
        },
        "notes": (
            "Homogeneous Michaelis-Menten config assembled from local FungMod registry "
            "records derived from the selected SABIO-RK Reaction 618 entry."
        ),
    }


def _first_present(values) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return None


def _best_parameter_record(
    *,
    registry: FungModRegistry,
    parameter_symbol: str,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
) -> ParameterRecord | None:
    candidates = [
        record
        for record in registry.parameters.values()
        if record.parameter_symbol == parameter_symbol
        and record.process_type == compatibility.process_type
        and _matches(record.enzyme_class, compatibility.enzyme_class)
        and _matches(record.substrate_class, compatibility.substrate_class)
        and _matches(record.fungus_id, fungus_id)
        and _matches(record.substrate_id, substrate_id)
        and _matches(record.environment_id, environment_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=_parameter_specificity)


def _matches(record_value: str | None, requested: str) -> bool:
    return record_value is None or record_value == requested


def _parameter_specificity(record: ParameterRecord) -> tuple[int, int, int]:
    selector_score = sum(
        value is not None
        for value in (
            record.enzyme_class,
            record.substrate_class,
            record.fungus_id,
            record.substrate_id,
            record.environment_id,
        )
    )
    value_score = 2 if record.value.is_exact else 1 if record.value.is_uncertain else 0
    maturity_score = 1 if record.maturity == "calibrated" else 0
    return selector_score, value_score, maturity_score


def _validate_mode(mode: str) -> None:
    if mode not in {"toy", "scientific"}:
        raise RegistryCaseBuildError(
            "Deterministic registry case builder supports only mode='toy' "
            "or mode='scientific'."
        )


_REGISTRY_PROCESS_ASSEMBLERS = {
    "surface_catalysis": RegistryProcessAssembler(
        process_type="surface_catalysis",
        process_label="Surface-catalysis",
        required_parameter_roles=SURFACE_CATALYSIS_PARAMETER_ROLES,
        deterministic_mode="toy",
        unsupported_mode_message=(
            "Surface-catalysis registry assembly currently only emits toy model configs."
        ),
        config_data_builder=_surface_catalysis_config_data,
    ),
    "homogeneous_michaelis_menten": RegistryProcessAssembler(
        process_type="homogeneous_michaelis_menten",
        process_label="Homogeneous Michaelis-Menten",
        required_parameter_roles=HOMOGENEOUS_MM_PARAMETER_ROLES,
        deterministic_mode="scientific",
        unsupported_mode_message=(
            "Homogeneous Michaelis-Menten registry assembly requires mode='scientific'."
        ),
        config_data_builder=_homogeneous_mm_config_data,
    ),
}


__all__ = [
    "RegistryCaseBuildError",
    "RegistryCaseConfigMode",
    "RegistryProcessAssembler",
    "build_registry_process_config_data",
    "build_model_config_from_registry_case",
    "get_registry_process_assembler",
    "select_registry_case_compatibility",
]
