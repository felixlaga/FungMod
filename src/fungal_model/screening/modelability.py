"""Modelability reporting for registry-backed FungMod cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from fungal_model.registry.records import (
    ParameterRecord,
    ProcessCompatibilityRecord,
    parameter_is_simulation_authorized,
    parameter_simulation_authorization_blocker,
)
from fungal_model.registry.store import FungModRegistry, RegistryLookupError

ModelabilityMode = Literal["scientific", "exploratory", "toy"]
ModelabilityStatus = Literal["modelable", "exploratory", "underparameterized", "unsupported"]


@dataclass(frozen=True)
class ReportItem:
    """One known, uncertain, missing, or incompatible modelability fact."""

    item_type: str
    item_id: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_type": self.item_type,
            "item_id": self.item_id,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ModelabilityReport:
    """Structured report for whether a registry case can be modelled."""

    fungus_id: str
    substrate_id: str
    environment_id: str
    mode: ModelabilityMode
    status: ModelabilityStatus
    known: tuple[ReportItem, ...]
    uncertain: tuple[ReportItem, ...]
    missing: tuple[ReportItem, ...]
    incompatible: tuple[ReportItem, ...]
    required_processes: tuple[str, ...]
    candidate_processes: tuple[str, ...]
    required_parameters: tuple[str, ...]
    suggested_experiments: tuple[str, ...]
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus_id": self.fungus_id,
            "substrate_id": self.substrate_id,
            "environment_id": self.environment_id,
            "mode": self.mode,
            "status": self.status,
            "known": [item.to_dict() for item in self.known],
            "uncertain": [item.to_dict() for item in self.uncertain],
            "missing": [item.to_dict() for item in self.missing],
            "incompatible": [item.to_dict() for item in self.incompatible],
            "required_processes": list(self.required_processes),
            "candidate_processes": list(self.candidate_processes),
            "required_parameters": list(self.required_parameters),
            "suggested_experiments": list(self.suggested_experiments),
            "assumptions": list(self.assumptions),
        }

    def summary(self) -> str:
        return (
            f"{self.fungus_id} + {self.substrate_id} + {self.environment_id}: "
            f"{self.status}; known={len(self.known)}, uncertain={len(self.uncertain)}, "
            f"missing={len(self.missing)}, incompatible={len(self.incompatible)}"
        )


def assess_modelability(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: ModelabilityMode = "exploratory",
) -> ModelabilityReport:
    """Assess a registry case without assembling or running a model."""

    _validate_mode(mode)
    fungus = registry.get_fungus(fungus_id)
    substrate = registry.get_substrate(substrate_id)
    environment = registry.get_environment(environment_id)
    known: list[ReportItem] = [
        _item("fungus", fungus.record_id, "Fungus record loaded.", {"enzyme_classes": list(fungus.enzyme_classes)}),
        _item(
            "substrate",
            substrate.record_id,
            "Substrate record loaded.",
            {
                "substrate_class": substrate.substrate_class,
                "bond_classes": list(substrate.bond_classes),
                "products": list(substrate.products),
            },
        ),
        _item(
            "environment",
            environment.record_id,
            "Environment record loaded.",
            {"conditions": list(environment.conditions)},
        ),
    ]
    uncertain: list[ReportItem] = []
    missing: list[ReportItem] = []
    incompatible: list[ReportItem] = []
    candidate_processes: list[str] = []
    compatibility_records: list[ProcessCompatibilityRecord] = []

    for enzyme_class_id in fungus.enzyme_classes:
        try:
            enzyme_class = registry.get_enzyme_class(enzyme_class_id)
        except RegistryLookupError:
            missing.append(
                _item(
                    "enzyme_class",
                    enzyme_class_id,
                    "Fungus references an enzyme class that is absent from the registry.",
                    {},
                )
            )
            continue
        if substrate.substrate_class not in enzyme_class.compatible_substrate_classes:
            incompatible.append(
                _item(
                    "enzyme_substrate_match",
                    enzyme_class.record_id,
                    "Enzyme class is not compatible with the substrate class.",
                    {
                        "substrate_class": substrate.substrate_class,
                        "compatible_substrate_classes": list(enzyme_class.compatible_substrate_classes),
                    },
                )
            )
            continue
        shared_bonds = set(substrate.bond_classes).intersection(enzyme_class.target_bond_classes)
        if not shared_bonds:
            incompatible.append(
                _item(
                    "enzyme_bond_match",
                    enzyme_class.record_id,
                    "Enzyme class does not target any substrate bond class.",
                    {
                        "substrate_bond_classes": list(substrate.bond_classes),
                        "target_bond_classes": list(enzyme_class.target_bond_classes),
                    },
                )
            )
            continue
        known.append(
            _item(
                "enzyme_substrate_match",
                enzyme_class.record_id,
                "Fungus enzyme class can target the substrate class and bond class.",
                {"matched_bond_classes": sorted(shared_bonds)},
            )
        )
        for process_type in enzyme_class.compatible_processes:
            try:
                matches = registry.get_process_compatibility(
                    enzyme_class=enzyme_class.record_id,
                    substrate_class=substrate.substrate_class,
                    process_type=process_type,
                )
            except RegistryLookupError:
                incompatible.append(
                    _item(
                        "process_compatibility",
                        f"{enzyme_class.record_id}:{substrate.substrate_class}:{process_type}",
                        "No process compatibility record connects this enzyme class and substrate class.",
                        {},
                    )
                )
                continue
            for compatibility in matches:
                if set(compatibility.required_bond_classes).issubset(substrate.bond_classes):
                    compatibility_records.append(compatibility)
                    candidate_processes.append(compatibility.process_type)
                    known.append(
                        _item(
                            "process_compatibility",
                            compatibility.record_id,
                            "Compatible process record found.",
                            compatibility.to_dict(),
                        )
                    )
                else:
                    incompatible.append(
                        _item(
                            "process_compatibility",
                            compatibility.record_id,
                            "Process compatibility requires bond classes absent from the substrate.",
                            {
                                "required_bond_classes": list(compatibility.required_bond_classes),
                                "substrate_bond_classes": list(substrate.bond_classes),
                            },
                        )
                    )

    selected_required_parameters: tuple[str, ...] = ()
    selected_processes: tuple[str, ...] = tuple(record.process_type for record in compatibility_records)
    if compatibility_records:
        selected = max(
            (
                _evaluate_compatibility_parameters(
                    registry=registry,
                    compatibility=compatibility,
                    fungus_id=fungus_id,
                    substrate_id=substrate_id,
                    environment_id=environment_id,
                    mode=mode,
                )
                for compatibility in compatibility_records
            ),
            key=_compatibility_evaluation_priority,
        )
        known.extend(selected["known"])
        uncertain.extend(selected["uncertain"])
        missing.extend(selected["missing"])
        incompatible.extend(selected["incompatible"])
        selected_required_parameters = tuple(selected["required_parameters"])
        selected_processes = (selected["compatibility"].process_type,)

    status = _status(
        compatibility_records=tuple(compatibility_records),
        missing=tuple(missing),
        incompatible=tuple(incompatible),
        uncertain=tuple(uncertain),
    )
    return ModelabilityReport(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        mode=mode,
        status=status,
        known=tuple(known),
        uncertain=tuple(uncertain),
        missing=tuple(missing),
        incompatible=tuple(incompatible),
        required_processes=tuple(dict.fromkeys(selected_processes)),
        candidate_processes=tuple(dict.fromkeys(candidate_processes)),
        required_parameters=selected_required_parameters,
        suggested_experiments=_suggested_experiments(missing),
        assumptions=(
            "Modelability assessment only; no ODE model is assembled or run.",
            "Registry records may be toy, exploratory, or curated scientific records; mode-specific maturity rules decide how they are used.",
            f"Mode-specific classification used mode={mode!r}.",
        ),
    )


def _evaluate_compatibility_parameters(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    mode: ModelabilityMode,
) -> dict[str, Any]:
    known: list[ReportItem] = []
    uncertain: list[ReportItem] = []
    missing: list[ReportItem] = []
    incompatible: list[ReportItem] = []
    required_parameters = tuple(dict.fromkeys(compatibility.required_parameters))
    for symbol in required_parameters:
        record = _best_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            mode=mode,
        )
        if record is None:
            missing.append(
                _item(
                    "parameter",
                    symbol,
                    "Required parameter is absent from the registry.",
                    {"process_type": compatibility.process_type},
                )
            )
            continue
        _classify_parameter(
            record=record,
            mode=mode,
            known=known,
            uncertain=uncertain,
            missing=missing,
            incompatible=incompatible,
        )
    status = _status(
        compatibility_records=(compatibility,),
        missing=tuple(missing),
        incompatible=tuple(incompatible),
        uncertain=tuple(uncertain),
    )
    return {
        "compatibility": compatibility,
        "known": known,
        "uncertain": uncertain,
        "missing": missing,
        "incompatible": incompatible,
        "required_parameters": required_parameters,
        "status": status,
    }


def _compatibility_evaluation_priority(evaluation: Mapping[str, Any]) -> tuple[int, int, int]:
    status_score = {
        "modelable": 3,
        "exploratory": 2,
        "underparameterized": 1,
        "unsupported": 0,
    }[str(evaluation["status"])]
    compatibility = evaluation["compatibility"]
    template_score = 1 if getattr(compatibility, "case_template_id", "") else 0
    known_score = len(evaluation["known"])
    return status_score, template_score, known_score


def _classify_parameter(
    *,
    record: ParameterRecord,
    mode: ModelabilityMode,
    known: list[ReportItem],
    uncertain: list[ReportItem],
    missing: list[ReportItem],
    incompatible: list[ReportItem],
) -> None:
    validation = record.value.validate(nonnegative=True)
    if not validation.passed:
        incompatible.append(
            _item(
                "parameter",
                record.parameter_symbol,
                "Parameter ValueSpec failed validation.",
                {"record_id": record.record_id, "validation": validation.to_dict()},
            )
        )
        return
    authorization_blocker = parameter_simulation_authorization_blocker(record)
    if authorization_blocker is not None:
        incompatible.append(
            _item(
                "parameter",
                record.parameter_symbol,
                authorization_blocker,
                {
                    "record_id": record.record_id,
                    "maturity": record.maturity,
                    "allowed_use": record.allowed_use,
                    "value": record.value.to_dict(),
                },
            )
        )
        return
    if record.value.is_exact:
        if mode == "scientific":
            blocker = _scientific_parameter_blocker(record)
            if blocker is not None:
                incompatible.append(
                    _item(
                        "parameter",
                        record.parameter_symbol,
                        blocker,
                        {
                            "record_id": record.record_id,
                            "maturity": record.maturity,
                            "allowed_use": record.allowed_use,
                            "value": record.value.to_dict(),
                        },
                    )
                )
                return
        known.append(
            _item(
                "parameter",
                record.parameter_symbol,
                "Required parameter has an exact ValueSpec.",
                {"record_id": record.record_id, "value": record.value.to_dict()},
            )
        )
        return
    if record.value.is_uncertain:
        target = incompatible if mode == "scientific" else uncertain
        message = (
            "Scientific mode requires exact/calibrated parameters; this parameter is uncertain."
            if mode == "scientific"
            else "Required parameter has a sampleable uncertain ValueSpec."
        )
        target.append(
            _item(
                "parameter",
                record.parameter_symbol,
                message,
                {"record_id": record.record_id, "value": record.value.to_dict()},
            )
        )
        return
    if record.value.is_unknown:
        missing.append(
            _item(
                "parameter",
                record.parameter_symbol,
                "Required parameter is explicitly unknown.",
                {"record_id": record.record_id, "value": record.value.to_dict()},
            )
        )
        return
    incompatible.append(
        _item(
            "parameter",
            record.parameter_symbol,
            "Required parameter is not applicable to this case.",
            {"record_id": record.record_id, "value": record.value.to_dict()},
        )
    )


def _best_parameter_record(
    *,
    registry: FungModRegistry,
    parameter_symbol: str,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    mode: ModelabilityMode,
) -> ParameterRecord | None:
    chain_record = _chain_template_parameter_record(
        registry=registry,
        compatibility=compatibility,
        parameter_symbol=parameter_symbol,
        environment_id=environment_id,
    )
    if chain_record is not None:
        return chain_record
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
    if mode == "scientific":
        candidates = [
            record
            for record in candidates
            if not _is_exploratory_parameter_record(record)
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda record: _parameter_specificity(record, mode=mode))


def _chain_template_parameter_record(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    parameter_symbol: str,
    environment_id: str,
) -> ParameterRecord | None:
    if compatibility.process_type != "extracellular_enzyme_chain" or not compatibility.case_template_id:
        return None
    try:
        template = registry.get_case_template(compatibility.case_template_id)
    except RegistryLookupError:
        return None
    parameter_ids = template.process_state_metadata.get("parameter_record_ids")
    if not isinstance(parameter_ids, dict):
        return None
    for record_id in parameter_ids.values():
        record = registry.parameters.get(str(record_id))
        if (
            record is not None
            and record.parameter_symbol == parameter_symbol
            and _matches(record.environment_id, environment_id)
        ):
            return record
    return None


def _matches(record_value: str | None, requested: str) -> bool:
    return record_value is None or record_value == requested


def _parameter_specificity(record: ParameterRecord, *, mode: ModelabilityMode) -> tuple[int, ...]:
    authorization_score = int(parameter_is_simulation_authorized(record))
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
    if mode == "exploratory":
        value_score = 2 if record.value.is_uncertain else 1 if record.value.is_exact else 0
        exploratory_score = 1 if _is_exploratory_parameter_record(record) else 0
        return authorization_score, selector_score, value_score, exploratory_score, maturity_score
    value_score = 2 if record.value.is_exact else 1 if record.value.is_uncertain else 0
    return authorization_score, selector_score, value_score, maturity_score


def _is_exploratory_parameter_record(record: ParameterRecord) -> bool:
    return record.maturity == "exploratory_prior" or bool(record.provenance.get("exploratory_prior"))


def _scientific_parameter_blocker(record: ParameterRecord) -> str | None:
    maturity = record.maturity.casefold()
    if maturity.startswith("toy") or maturity.startswith("synthetic"):
        return "Scientific mode rejects toy or synthetic parameter records."
    allowed_use = record.allowed_use.casefold()
    if "scientific" not in allowed_use:
        return "Scientific mode requires parameter allowed_use to permit scientific use."
    return None


def _status(
    *,
    compatibility_records: tuple[ProcessCompatibilityRecord, ...],
    missing: tuple[ReportItem, ...],
    incompatible: tuple[ReportItem, ...],
    uncertain: tuple[ReportItem, ...],
) -> ModelabilityStatus:
    if not compatibility_records:
        return "unsupported"
    if missing:
        return "underparameterized"
    if incompatible:
        return "underparameterized"
    if uncertain:
        return "exploratory"
    return "modelable"


def _suggested_experiments(missing: list[ReportItem]) -> tuple[str, ...]:
    suggestions: list[str] = []
    for item in missing:
        if item.item_type == "parameter":
            suggestions.append(f"Measure or curate {item.item_id} for the selected registry case.")
    return tuple(dict.fromkeys(suggestions))


def _validate_mode(mode: str) -> None:
    if mode not in {"scientific", "exploratory", "toy"}:
        raise ValueError("mode must be one of: scientific, exploratory, toy.")


def _item(item_type: str, item_id: str, message: str, details: dict[str, Any]) -> ReportItem:
    return ReportItem(
        item_type=item_type,
        item_id=item_id,
        message=message,
        details=details,
    )


__all__ = [
    "ModelabilityMode",
    "ModelabilityReport",
    "ModelabilityStatus",
    "ReportItem",
    "assess_modelability",
]
