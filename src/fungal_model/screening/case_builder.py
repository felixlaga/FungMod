"""Build runnable toy model configs from modelable registry cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import (
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
)
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.modelability import ModelabilityReport, assess_modelability

RegistryCaseConfigMode = Literal["toy"]

SURFACE_CATALYSIS_PARAMETER_ROLES = (
    "surface_rate_constant",
    "adsorption_constant",
    "accessible_surface_area",
)


class RegistryCaseBuildError(ValueError):
    """Raised when a registry case cannot be converted into a model config."""


def build_model_config_from_registry_case(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: RegistryCaseConfigMode = "toy",
    output_directory: str | None = None,
) -> ModelConfig:
    """Convert a modelable toy registry case into a generic ``ModelConfig``.

    R3 deliberately builds only deterministic toy configs from exact registry
    values. Uncertain ranges and distributions remain R4 work.
    """

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
            f"{report.status!r}; only exact modelable cases can be converted in R3. "
            f"Report: {report.to_dict()}"
        )

    compatibility = _select_compatibility(
        registry=registry,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        report=report,
    )
    if compatibility.process_type != "surface_catalysis":
        raise RegistryCaseBuildError(
            "R3 case builder currently supports only existing generic "
            f"surface_catalysis configs, not {compatibility.process_type!r}."
        )
    parameter_records = _surface_catalysis_parameters(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
    )
    substrate = registry.get_substrate(substrate_id)
    config_data = _surface_catalysis_config_data(
        registry=registry,
        compatibility=compatibility,
        substrate=substrate,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        output_directory=output_directory,
    )
    return ModelConfig.from_mapping(config_data)


def _select_compatibility(
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


def _surface_catalysis_parameters(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
) -> Mapping[str, ParameterRecord]:
    missing_roles = tuple(
        role for role in SURFACE_CATALYSIS_PARAMETER_ROLES if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryCaseBuildError(
            "Surface-catalysis registry compatibility is missing parameter role "
            f"mappings for: {', '.join(missing_roles)}."
        )

    resolved: dict[str, ParameterRecord] = {}
    for role in SURFACE_CATALYSIS_PARAMETER_ROLES:
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
                f"R3 case builder requires exact parameters; role {role!r} uses "
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


def _parameter_specificity(record: ParameterRecord) -> tuple[int, int]:
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
    maturity_score = 1 if record.maturity == "calibrated" else 0
    return selector_score, maturity_score


def _validate_mode(mode: str) -> None:
    if mode != "toy":
        raise RegistryCaseBuildError(
            "R3 case builder only emits toy model configs. Scientific and "
            "strict registry assembly require curated records in later milestones."
        )


__all__ = [
    "RegistryCaseBuildError",
    "RegistryCaseConfigMode",
    "build_model_config_from_registry_case",
]
