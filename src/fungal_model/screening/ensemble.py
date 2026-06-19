"""Exploratory registry ensemble simulation over ValueSpec uncertainty."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml

from fungal_model.core.value_spec import ValueSpec
from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import ParameterRecord, ProcessCompatibilityRecord
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.results import SimulationResult
from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    build_registry_process_config_data,
    get_registry_process_assembler,
    select_registry_case_compatibility,
)
from fungal_model.screening.modelability import ModelabilityReport, assess_modelability
from fungal_model.workflows import run_configured_model

ScreenSimulationMode = Literal["exploratory", "scientific"]


class RegistryScreenSimulationError(ValueError):
    """Raised when a registry screen cannot be simulated."""


@dataclass(frozen=True)
class EnsembleSample:
    """One sampled config/run record in an exploratory registry screen."""

    sample_index: int
    config_path: str
    output_directory: str
    parameters: Mapping[str, Mapping[str, Any]]
    final_states: Mapping[str, Mapping[str, Any]]
    validation_passed: bool
    trajectory_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "config_path": self.config_path,
            "output_directory": self.output_directory,
            "parameters": {
                role: dict(value)
                for role, value in self.parameters.items()
            },
            "final_states": {
                name: dict(value)
                for name, value in self.final_states.items()
            },
            "validation_passed": self.validation_passed,
            "trajectory_path": self.trajectory_path,
        }


@dataclass(frozen=True)
class EnsembleSampleFailure:
    """One failed sample in an exploratory registry screen."""

    sample_index: int
    output_directory: str
    error_type: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "output_directory": self.output_directory,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass(frozen=True)
class RegistryCaseEnsemble:
    """All sampled runs for one fungus/substrate/environment registry case."""

    fungus_id: str
    substrate_id: str
    environment_id: str
    process_type: str
    modelability_report: ModelabilityReport
    samples: tuple[EnsembleSample, ...]
    sample_failures: tuple[EnsembleSampleFailure, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus_id": self.fungus_id,
            "substrate_id": self.substrate_id,
            "environment_id": self.environment_id,
            "process_type": self.process_type,
            "modelability_report": self.modelability_report.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples],
            "sample_failures": [failure.to_dict() for failure in self.sample_failures],
        }


@dataclass(frozen=True)
class RegistryScreenResult:
    """Structured result for one registry screen."""

    mode: ScreenSimulationMode
    n_samples: int
    seed: int | None
    output_directory: str
    case_results: tuple[RegistryCaseEnsemble, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "n_samples": self.n_samples,
            "seed": self.seed,
            "output_directory": self.output_directory,
            "case_results": [case.to_dict() for case in self.case_results],
        }

    def save(self, path: str | Path | None = None) -> Path:
        destination = Path(path) if path is not None else Path(self.output_directory)
        destination.mkdir(parents=True, exist_ok=True)
        summary_path = destination / "screen_summary.json"
        summary_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_screen_csv_outputs(destination=destination, case_results=self.case_results)
        return summary_path


def simulate_screen(
    *,
    fungus_ids: Sequence[str],
    substrate_ids: Sequence[str],
    environment_ids: Sequence[str],
    registry: FungModRegistry,
    n_samples: int,
    seed: int | None = None,
    output_dir: str | Path | None = None,
    mode: ScreenSimulationMode = "exploratory",
) -> RegistryScreenResult:
    """Run registry cases as sampled exploratory ensembles or exact scientific screens."""

    _validate_screen_inputs(
        fungus_ids=fungus_ids,
        substrate_ids=substrate_ids,
        environment_ids=environment_ids,
        n_samples=n_samples,
        mode=mode,
    )
    root = Path(output_dir) if output_dir is not None else Path("outputs/registry_screen")
    if mode == "scientific":
        n_samples = 1
    rng = np.random.default_rng(seed)
    case_results: list[RegistryCaseEnsemble] = []
    for fungus_id, substrate_id, environment_id in product(fungus_ids, substrate_ids, environment_ids):
        case_seed = int(rng.integers(0, np.iinfo(np.uint32).max))
        case_results.append(
            _simulate_case_ensemble(
                fungus_id=fungus_id,
                substrate_id=substrate_id,
                environment_id=environment_id,
                registry=registry,
                n_samples=n_samples,
                rng=np.random.default_rng(case_seed),
                output_root=root,
                mode=mode,
            )
        )
    result = RegistryScreenResult(
        mode=mode,
        n_samples=n_samples,
        seed=seed,
        output_directory=str(root),
        case_results=tuple(case_results),
    )
    result.save()
    return result


def _simulate_case_ensemble(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    n_samples: int,
    rng: np.random.Generator,
    output_root: Path,
    mode: ScreenSimulationMode,
) -> RegistryCaseEnsemble:
    report = assess_modelability(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        mode=mode,
    )
    allowed_statuses = {"modelable"} if mode == "scientific" else {"modelable", "exploratory"}
    if report.status not in allowed_statuses:
        raise RegistryScreenSimulationError(
            f"Registry case cannot be simulated in {mode!r} mode because "
            f"modelability status is {report.status!r}. Report: {report.to_dict()}"
        )
    compatibility = select_registry_case_compatibility(
        registry=registry,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        report=report,
    )
    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        raise RegistryScreenSimulationError(
            f"{mode.capitalize()} screen does not support process_type "
            f"{compatibility.process_type!r}."
        )
    role_records = (
        _resolve_scientific_role_records
        if mode == "scientific"
        else _resolve_role_records
    )(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        required_roles=assembler.required_parameter_roles,
        process_label=assembler.process_label,
    )
    if mode == "scientific":
        return _run_scientific_case_sample(
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            registry=registry,
            compatibility=compatibility,
            report=report,
            role_records=role_records,
            output_root=output_root,
        )
    return _run_case_samples(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        compatibility=compatibility,
        report=report,
        role_records=role_records,
        n_samples=n_samples,
        rng=rng,
        output_root=output_root,
    )


def _run_case_samples(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
    n_samples: int,
    rng: np.random.Generator,
    output_root: Path,
) -> RegistryCaseEnsemble:
    samples: list[EnsembleSample] = []
    failures: list[EnsembleSampleFailure] = []
    case_dir = output_root / f"{fungus_id}__{substrate_id}__{environment_id}"
    for sample_index in range(n_samples):
        sample_dir = case_dir / f"sample_{sample_index:04d}"
        try:
            sampled_records = _sample_role_records(
                role_records,
                rng=rng,
                sample_index=sample_index,
            )
            config = _build_sample_config(
                registry=registry,
                compatibility=compatibility,
                fungus_id=fungus_id,
                substrate_id=substrate_id,
                environment_id=environment_id,
                sampled_records=sampled_records,
                sample_dir=sample_dir,
            )
            samples.append(
                _run_sample(
                    config=config,
                    sample_dir=sample_dir,
                    sample_index=sample_index,
                    sampled_records=sampled_records,
                    trajectory_dir=case_dir / "trajectories",
                )
            )
        except Exception as exc:
            failures.append(
                EnsembleSampleFailure(
                    sample_index=sample_index,
                    output_directory=str(sample_dir),
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )
    if not samples:
        raise RegistryScreenSimulationError(
            "All exploratory samples failed for registry case "
            f"{fungus_id} + {substrate_id} + {environment_id}. "
            f"Failures: {[failure.to_dict() for failure in failures]}"
        )
    return RegistryCaseEnsemble(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        process_type=compatibility.process_type,
        modelability_report=report,
        samples=tuple(samples),
        sample_failures=tuple(failures),
    )


def _run_scientific_case_sample(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
    output_root: Path,
) -> RegistryCaseEnsemble:
    case_dir = output_root / f"{fungus_id}__{substrate_id}__{environment_id}"
    sample_dir = case_dir / "sample_0000"
    try:
        config = _build_scientific_config(
            registry=registry,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            role_records=role_records,
            sample_dir=sample_dir,
        )
        sample = _run_sample(
            config=config,
            sample_dir=sample_dir,
            sample_index=0,
            sampled_records=role_records,
            trajectory_dir=case_dir / "trajectories",
        )
        failures: tuple[EnsembleSampleFailure, ...] = ()
        samples = (sample,)
    except Exception as exc:
        failures = (
            EnsembleSampleFailure(
                sample_index=0,
                output_directory=str(sample_dir),
                error_type=type(exc).__name__,
                message=str(exc),
            ),
        )
        raise RegistryScreenSimulationError(
            "Scientific exact sample failed for registry case "
            f"{fungus_id} + {substrate_id} + {environment_id}. "
            f"Failures: {[failure.to_dict() for failure in failures]}"
        ) from exc
    return RegistryCaseEnsemble(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        process_type=compatibility.process_type,
        modelability_report=report,
        samples=samples,
        sample_failures=failures,
    )


def _resolve_role_records(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    required_roles: tuple[str, ...],
    process_label: str,
) -> Mapping[str, ParameterRecord]:
    chain_records = _chain_template_role_records(
        registry=registry,
        compatibility=compatibility,
        required_roles=required_roles,
        process_label=process_label,
        environment_id=environment_id,
        scientific=False,
    )
    if chain_records is not None:
        return chain_records
    missing_roles = tuple(
        role for role in required_roles if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryScreenSimulationError(
            f"{process_label} compatibility is missing parameter role mappings "
            f"for: {', '.join(missing_roles)}."
        )
    records: dict[str, ParameterRecord] = {}
    roles_to_resolve = tuple(
        dict.fromkeys((*required_roles, *compatibility.parameter_roles.keys()))
    )
    for role in roles_to_resolve:
        symbol = compatibility.parameter_roles[role]
        record = _best_exploratory_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
        )
        if record is None:
            raise RegistryScreenSimulationError(
                f"No registry parameter record found for role {role!r} and symbol {symbol!r}."
            )
        validation = record.value.validate(nonnegative=True)
        if not validation.passed:
            raise RegistryScreenSimulationError(
                f"Parameter {symbol!r} for role {role!r} failed ValueSpec validation: "
                f"{validation.to_dict()}"
            )
        if not record.value.is_exact and not record.value.is_uncertain:
            raise RegistryScreenSimulationError(
                f"Parameter role {role!r} uses ValueSpec kind {record.value.kind!r}, "
                "which cannot be sampled for R4 exploratory simulation."
            )
        records[role] = record
    return records


def _resolve_scientific_role_records(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    required_roles: tuple[str, ...],
    process_label: str,
) -> Mapping[str, ParameterRecord]:
    chain_records = _chain_template_role_records(
        registry=registry,
        compatibility=compatibility,
        required_roles=required_roles,
        process_label=process_label,
        environment_id=environment_id,
        scientific=True,
    )
    if chain_records is not None:
        return chain_records
    missing_roles = tuple(
        role for role in required_roles if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryScreenSimulationError(
            f"{process_label} compatibility is missing parameter role mappings "
            f"for: {', '.join(missing_roles)}."
        )
    records: dict[str, ParameterRecord] = {}
    roles_to_resolve = tuple(
        dict.fromkeys((*required_roles, *compatibility.parameter_roles.keys()))
    )
    for role in roles_to_resolve:
        symbol = compatibility.parameter_roles[role]
        record = _best_scientific_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
        )
        if record is None:
            raise RegistryScreenSimulationError(
                f"No non-exploratory registry parameter record found for scientific role {role!r} "
                f"and symbol {symbol!r}."
            )
        validation = record.value.validate(nonnegative=True)
        if not validation.passed:
            raise RegistryScreenSimulationError(
                f"Parameter {symbol!r} for scientific role {role!r} failed ValueSpec validation: "
                f"{validation.to_dict()}"
            )
        if not record.value.is_exact:
            raise RegistryScreenSimulationError(
                f"Scientific mode requires exact parameters; role {role!r} uses "
                f"symbol {symbol!r} with ValueSpec kind {record.value.kind!r}."
            )
        blocker = _scientific_parameter_record_blocker(record)
        if blocker is not None:
            raise RegistryScreenSimulationError(
                f"Scientific mode rejected parameter role {role!r} and symbol {symbol!r}: {blocker}"
            )
        records[role] = record
    return records


def _chain_template_role_records(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    required_roles: tuple[str, ...],
    process_label: str,
    environment_id: str,
    scientific: bool,
) -> Mapping[str, ParameterRecord] | None:
    if compatibility.process_type != "extracellular_enzyme_chain":
        return None
    if not compatibility.case_template_id:
        raise RegistryScreenSimulationError(
            f"{process_label} compatibility {compatibility.record_id!r} lacks case_template_id."
        )
    try:
        template = registry.get_case_template(compatibility.case_template_id)
    except RegistryLookupError as exc:
        raise RegistryScreenSimulationError(
            f"{process_label} compatibility {compatibility.record_id!r} references missing "
            f"case template {compatibility.case_template_id!r}."
        ) from exc
    parameter_ids = template.process_state_metadata.get("parameter_record_ids")
    if not isinstance(parameter_ids, dict):
        raise RegistryScreenSimulationError(
            f"{process_label} template {template.case_template_id!r} lacks parameter_record_ids."
        )
    missing_roles = tuple(
        role for role in required_roles if role not in compatibility.parameter_roles or role not in parameter_ids
    )
    if missing_roles:
        raise RegistryScreenSimulationError(
            f"{process_label} compatibility/template metadata is missing parameter role mappings "
            f"for: {', '.join(missing_roles)}."
        )
    roles_to_resolve = tuple(dict.fromkeys((*required_roles, *compatibility.parameter_roles.keys())))
    records: dict[str, ParameterRecord] = {}
    for role in roles_to_resolve:
        record_id = str(parameter_ids[role])
        record = registry.parameters.get(record_id)
        if record is None:
            raise RegistryScreenSimulationError(
                f"{process_label} template {template.case_template_id!r} references missing "
                f"parameter record {record_id!r} for role {role!r}."
            )
        if not _matches(record.environment_id, environment_id):
            raise RegistryScreenSimulationError(
                f"{process_label} template {template.case_template_id!r} parameter record "
                f"{record_id!r} is scoped to environment {record.environment_id!r}, not {environment_id!r}."
            )
        expected_symbol = compatibility.parameter_roles[role]
        if record.parameter_symbol != expected_symbol:
            raise RegistryScreenSimulationError(
                f"{process_label} role {role!r} expected symbol {expected_symbol!r}, "
                f"but template record {record_id!r} uses {record.parameter_symbol!r}."
            )
        validation = record.value.validate(nonnegative=True)
        if not validation.passed:
            raise RegistryScreenSimulationError(
                f"Parameter {record.parameter_symbol!r} for role {role!r} failed ValueSpec validation: "
                f"{validation.to_dict()}"
            )
        if scientific:
            if not record.value.is_exact:
                raise RegistryScreenSimulationError(
                    f"Scientific mode requires exact parameters; role {role!r} uses "
                    f"symbol {record.parameter_symbol!r} with ValueSpec kind {record.value.kind!r}."
                )
            blocker = _scientific_parameter_record_blocker(record)
            if blocker is not None:
                raise RegistryScreenSimulationError(
                    f"Scientific mode rejected parameter role {role!r} and symbol "
                    f"{record.parameter_symbol!r}: {blocker}"
                )
        elif not record.value.is_exact and not record.value.is_uncertain:
            raise RegistryScreenSimulationError(
                f"Parameter role {role!r} uses ValueSpec kind {record.value.kind!r}, "
                "which cannot be sampled for exploratory simulation."
            )
        records[role] = record
    return records


def _best_exploratory_parameter_record(
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
    return max(candidates, key=_exploratory_parameter_specificity)


def _best_scientific_parameter_record(
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
        and not _is_exploratory_parameter_record(record)
        and _matches(record.enzyme_class, compatibility.enzyme_class)
        and _matches(record.substrate_class, compatibility.substrate_class)
        and _matches(record.fungus_id, fungus_id)
        and _matches(record.substrate_id, substrate_id)
        and _matches(record.environment_id, environment_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=_scientific_parameter_specificity)


def _matches(record_value: str | None, requested: str) -> bool:
    return record_value is None or record_value == requested


def _exploratory_parameter_specificity(record: ParameterRecord) -> tuple[int, int, int]:
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
    value_score = 2 if record.value.is_uncertain else 1 if record.value.is_exact else 0
    exploratory_score = 1 if record.maturity == "exploratory_prior" or record.provenance.get("exploratory_prior") else 0
    return selector_score, value_score, exploratory_score


def _scientific_parameter_specificity(record: ParameterRecord) -> tuple[int, int, int]:
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


def _is_exploratory_parameter_record(record: ParameterRecord) -> bool:
    return record.maturity == "exploratory_prior" or bool(record.provenance.get("exploratory_prior"))


def _scientific_parameter_record_blocker(record: ParameterRecord) -> str | None:
    maturity = record.maturity.casefold()
    if maturity.startswith("toy") or maturity.startswith("synthetic"):
        return "toy or synthetic parameter records are not scientific inputs"
    allowed_use = record.allowed_use.casefold()
    if "scientific" not in allowed_use:
        return f"allowed_use={record.allowed_use!r} does not permit scientific use"
    return None


def _sample_role_records(
    role_records: Mapping[str, ParameterRecord],
    *,
    rng: np.random.Generator,
    sample_index: int,
) -> Mapping[str, ParameterRecord]:
    return {
        role: _sample_record(record, rng=rng, sample_index=sample_index)
        for role, record in role_records.items()
    }


def _sample_record(
    record: ParameterRecord,
    *,
    rng: np.random.Generator,
    sample_index: int,
) -> ParameterRecord:
    quantity = record.value.sample(rng)
    return ParameterRecord(
        record_id=f"{record.record_id}_sample_{sample_index}",
        name=record.name,
        maturity=record.maturity,
        provenance=dict(record.provenance),
        notes=f"{record.notes} Sampled for exploratory registry ensemble.",
        parameter_symbol=record.parameter_symbol,
        process_type=record.process_type,
        enzyme_class=record.enzyme_class,
        substrate_class=record.substrate_class,
        fungus_id=record.fungus_id,
        substrate_id=record.substrate_id,
        environment_id=record.environment_id,
        value=ValueSpec(
            kind="exact",
            value=float(quantity.magnitude),
            units=str(quantity.units),
            source=record.value.source or record.provenance.get("source"),
            confidence_level=record.value.confidence_level or record.provenance.get("confidence_level"),
            notes=f"Sample {sample_index} from original ValueSpec kind {record.value.kind}.",
        ),
        range_scope=record.range_scope,
        range_interpretation=record.range_interpretation,
        allowed_use=record.allowed_use,
    )


def _build_sample_config(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    sampled_records: Mapping[str, ParameterRecord],
    sample_dir: Path,
) -> ModelConfig:
    try:
        data = build_registry_process_config_data(
            registry=registry,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            parameter_records=sampled_records,
            output_directory=str(sample_dir / "bundle"),
        )
    except RegistryCaseBuildError as exc:
        raise RegistryScreenSimulationError(str(exc)) from exc
    data["name"] = f"{data['name']} sample {sample_dir.name}"
    data["provenance"]["screen_mode"] = "exploratory"
    data["provenance"]["sample_directory"] = str(sample_dir)
    return ModelConfig.from_mapping(data)


def _build_scientific_config(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    role_records: Mapping[str, ParameterRecord],
    sample_dir: Path,
) -> ModelConfig:
    try:
        data = build_registry_process_config_data(
            registry=registry,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            parameter_records=role_records,
            output_directory=str(sample_dir / "bundle"),
        )
    except RegistryCaseBuildError as exc:
        raise RegistryScreenSimulationError(str(exc)) from exc
    data["name"] = f"{data['name']} scientific exact sample"
    data["provenance"]["screen_mode"] = "scientific"
    data["provenance"]["run_label"] = "scientific_exact_unvalidated"
    data["provenance"]["sample_directory"] = str(sample_dir)
    data["provenance"]["scientific_mode_note"] = (
        "Scientific mode uses exact non-exploratory registry values and implemented "
        "process laws. It is not a claim of experimental validation."
    )
    return ModelConfig.from_mapping(data)


def _run_sample(
    *,
    config: ModelConfig,
    sample_dir: Path,
    sample_index: int,
    sampled_records: Mapping[str, ParameterRecord],
    trajectory_dir: Path,
) -> EnsembleSample:
    sample_dir.mkdir(parents=True, exist_ok=True)
    config_path = sample_dir / "model_config.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=sample_dir / "bundle")
    trajectory_path = _write_sample_trajectory(result, trajectory_dir=trajectory_dir, sample_index=sample_index)
    return EnsembleSample(
        sample_index=sample_index,
        config_path=str(config_path),
        output_directory=str(sample_dir / "bundle"),
        parameters=_sample_parameters(sampled_records),
        final_states=_final_states(result),
        validation_passed=_validation_passed(result),
        trajectory_path=str(trajectory_path),
    )


def _sample_parameters(sampled_records: Mapping[str, ParameterRecord]) -> Mapping[str, Mapping[str, Any]]:
    return {
        str(role): {
            "symbol": record.parameter_symbol,
            "value": record.value.value,
            "units": record.value.units,
        }
        for role, record in sampled_records.items()
    }


def _final_states(result: SimulationResult) -> Mapping[str, Mapping[str, Any]]:
    final: dict[str, Mapping[str, Any]] = {}
    for name, quantity in result.states.items():
        values = np.asarray(quantity.magnitude, dtype=float).reshape(-1)
        final[name] = {
            "value": float(values[-1]),
            "units": str(quantity.units),
        }
    return final


def _validation_passed(result: SimulationResult) -> bool:
    report = result.validation_report()
    return bool(report) and all(bool(item.get("passed")) for item in report)


def _write_sample_trajectory(
    result: SimulationResult,
    *,
    trajectory_dir: Path,
    sample_index: int,
) -> Path:
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    path = trajectory_dir / f"sample_{sample_index:03d}.csv"
    time_values = np.asarray(result.time.magnitude, dtype=float).reshape(-1)
    state_values = {
        name: np.asarray(quantity.magnitude, dtype=float).reshape(-1)
        for name, quantity in result.states.items()
    }
    fieldnames = ["time", "time_units"]
    for state_name in state_values:
        fieldnames.extend((state_name, f"{state_name}_units"))
    rows: list[dict[str, Any]] = []
    for index, time_value in enumerate(time_values):
        row: dict[str, Any] = {
            "time": float(time_value),
            "time_units": str(result.time.units),
        }
        for state_name, values in state_values.items():
            row[state_name] = float(values[index])
            row[f"{state_name}_units"] = str(result.states[state_name].units)
        rows.append(row)
    _write_csv(path, rows)
    return path


def _write_screen_csv_outputs(
    *,
    destination: Path,
    case_results: Sequence[RegistryCaseEnsemble],
) -> None:
    sampled_rows = _sampled_parameter_rows(case_results)
    final_rows = _final_state_rows(case_results)
    failure_rows = _failure_rows(case_results)
    _write_csv(destination / "sampled_parameters.csv", sampled_rows)
    _write_csv(destination / "final_states.csv", final_rows)
    _write_csv(
        destination / "sample_failures.csv",
        failure_rows,
        fieldnames=("case", "sample", "fungus_id", "substrate_id", "environment_id", "process_type", "error_type", "message"),
    )
    _write_summary_csv(destination / "sampled_parameter_summary.csv", sampled_rows)
    _write_summary_csv(destination / "final_state_summary.csv", final_rows)


def _sampled_parameter_rows(case_results: Sequence[RegistryCaseEnsemble]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_index, case in enumerate(case_results):
        for sample in case.samples:
            row = _base_sample_row(case=case, case_index=case_index, sample=sample)
            row["status"] = "success"
            for parameter in sample.parameters.values():
                symbol = str(parameter["symbol"])
                row[symbol] = parameter["value"]
                row[f"{symbol}_units"] = parameter["units"]
            rows.append(row)
    return rows


def _final_state_rows(case_results: Sequence[RegistryCaseEnsemble]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_index, case in enumerate(case_results):
        for sample in case.samples:
            row = _base_sample_row(case=case, case_index=case_index, sample=sample)
            row["status"] = "success"
            row["validation_passed"] = sample.validation_passed
            row["trajectory_path"] = sample.trajectory_path
            for state_name, final_state in sample.final_states.items():
                row[f"final_{state_name}"] = final_state["value"]
                row[f"final_{state_name}_units"] = final_state["units"]
            rows.append(row)
    return rows


def _failure_rows(case_results: Sequence[RegistryCaseEnsemble]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_index, case in enumerate(case_results):
        for failure in case.sample_failures:
            rows.append(
                {
                    "case": case_index,
                    "sample": failure.sample_index,
                    "fungus_id": case.fungus_id,
                    "substrate_id": case.substrate_id,
                    "environment_id": case.environment_id,
                    "process_type": case.process_type,
                    "error_type": failure.error_type,
                    "message": failure.message,
                }
            )
    return rows


def _base_sample_row(
    *,
    case: RegistryCaseEnsemble,
    case_index: int,
    sample: EnsembleSample,
) -> dict[str, Any]:
    return {
        "case": case_index,
        "sample": sample.sample_index,
        "fungus_id": case.fungus_id,
        "substrate_id": case.substrate_id,
        "environment_id": case.environment_id,
        "process_type": case.process_type,
    }


def _write_summary_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    numeric_columns: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            if key in {"case", "sample"} or key.endswith("_units"):
                continue
            if isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(number):
                numeric_columns.setdefault(key, []).append(number)
    summary_rows: list[dict[str, Any]] = []
    for metric, values in sorted(numeric_columns.items()):
        data = np.asarray(values, dtype=float)
        summary_rows.append(
            {
                "metric": metric,
                "count": int(data.size),
                "mean": float(np.mean(data)),
                "min": float(np.min(data)),
                "max": float(np.max(data)),
                "p05": float(np.quantile(data, 0.05)),
                "p50": float(np.quantile(data, 0.50)),
                "p95": float(np.quantile(data, 0.95)),
            }
        )
    _write_csv(
        path,
        summary_rows,
        fieldnames=("metric", "count", "mean", "min", "max", "p05", "p50", "p95"),
    )


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(fieldnames or _csv_fieldnames(rows))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in columns})


def _csv_fieldnames(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    ordered: dict[str, None] = {}
    for row in rows:
        for key in row:
            ordered.setdefault(str(key), None)
    return tuple(ordered)


def _csv_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _validate_screen_inputs(
    *,
    fungus_ids: Sequence[str],
    substrate_ids: Sequence[str],
    environment_ids: Sequence[str],
    n_samples: int,
    mode: str,
) -> None:
    if mode not in {"exploratory", "scientific"}:
        raise RegistryScreenSimulationError("simulate_screen supports only mode='exploratory' or mode='scientific'.")
    if n_samples < 1:
        raise RegistryScreenSimulationError("n_samples must be at least 1.")
    if not fungus_ids or not substrate_ids or not environment_ids:
        raise RegistryScreenSimulationError(
            "fungus_ids, substrate_ids, and environment_ids must each contain at least one id."
        )


__all__ = [
    "EnsembleSample",
    "EnsembleSampleFailure",
    "RegistryCaseEnsemble",
    "RegistryScreenResult",
    "RegistryScreenSimulationError",
    "ScreenSimulationMode",
    "simulate_screen",
]
