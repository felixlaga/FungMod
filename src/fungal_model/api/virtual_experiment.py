"""Researcher-facing virtual-experiment API."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Literal

from fungal_model.api.environment_grid import EnvironmentCase, EnvironmentGrid
from fungal_model.api.quicklook import write_quicklook_plots as write_quicklook_plot_files
from fungal_model.api.result_tables import WrittenTables, write_standard_tables
from fungal_model.registry.records import ParameterRecord
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.screening import (
    ModelabilityMode,
    ModelabilityReport,
    RegistryScreenResult,
    assess_modelability,
    simulate_screen,
)

VirtualExperimentMode = Literal["exploratory"]


class VirtualExperimentError(ValueError):
    """Raised when a virtual experiment cannot be defined or simulated."""


@dataclass(frozen=True)
class VirtualExperiment:
    """Registry-backed virtual experiment over fungus/substrate/environment IDs."""

    fungus_ids: tuple[str, ...]
    substrate_ids: tuple[str, ...]
    environment_ids: tuple[str, ...]
    registry: FungModRegistry
    registry_source: str = ""
    environment_cases: tuple[EnvironmentCase, ...] = ()

    @classmethod
    def from_registry(
        cls,
        *,
        fungi: Sequence[str] | str,
        substrates: Sequence[str] | str,
        environments: Sequence[str] | str | EnvironmentGrid,
        registry: str | Path | FungModRegistry = "data_registry/registry_index.yml",
    ) -> "VirtualExperiment":
        """Create a virtual experiment from curated registry IDs."""

        loaded_registry, registry_source = _load_registry_source(registry)
        fungus_ids = _string_tuple(fungi, field_name="fungi")
        substrate_ids = _string_tuple(substrates, field_name="substrates")
        environment_ids, environment_cases = _environment_inputs(environments)
        if environment_cases:
            loaded_registry = _registry_with_runtime_environment_overlay(
                loaded_registry,
                environment_cases=environment_cases,
            )
        for fungus_id in fungus_ids:
            loaded_registry.get_fungus(fungus_id)
        for substrate_id in substrate_ids:
            loaded_registry.get_substrate(substrate_id)
        for environment_id in environment_ids:
            loaded_registry.get_environment(environment_id)
        return cls(
            fungus_ids=fungus_ids,
            substrate_ids=substrate_ids,
            environment_ids=environment_ids,
            registry=loaded_registry,
            registry_source=registry_source,
            environment_cases=environment_cases,
        )

    def preflight(self, *, mode: ModelabilityMode = "exploratory") -> tuple[ModelabilityReport, ...]:
        """Run modelability as an internal guardrail without simulating."""

        _validate_preflight_mode(mode)
        return tuple(
            assess_modelability(
                fungus_id=fungus_id,
                substrate_id=substrate_id,
                environment_id=environment_id,
                registry=self.registry,
                mode=mode,
            )
            for fungus_id, substrate_id, environment_id in product(
                self.fungus_ids,
                self.substrate_ids,
                self.environment_ids,
            )
        )

    def simulate(
        self,
        *,
        mode: VirtualExperimentMode = "exploratory",
        n_samples: int = 128,
        seed: int | None = None,
        output_dir: str | Path = "outputs/virtual_experiment",
        quicklook: bool = True,
    ) -> "DegradationScreenResult":
        """Run modelable/exploratory registry cases and write API-001 tables."""

        _validate_simulation_mode(mode)
        reports = self.preflight(mode=mode)
        blocked = tuple(report for report in reports if report.status not in {"modelable", "exploratory"})
        if blocked:
            statuses = ", ".join(report.summary() for report in blocked)
            raise VirtualExperimentError(
                "VirtualExperiment can simulate only modelable or exploratory cases. "
                f"Blocked preflight reports: {statuses}"
            )
        root = Path(output_dir)
        screen = simulate_screen(
            fungus_ids=self.fungus_ids,
            substrate_ids=self.substrate_ids,
            environment_ids=self.environment_ids,
            registry=self.registry,
            n_samples=n_samples,
            seed=seed,
            output_dir=root,
            mode=mode,
        )
        result = DegradationScreenResult(
            experiment=self,
            mode=mode,
            n_samples=n_samples,
            seed=seed,
            output_directory=str(root),
            preflight_reports=reports,
            screen_result=screen,
        )
        result.write_tables()
        if quicklook:
            result.write_quicklook_plots()
        result.write_summary()
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus_ids": list(self.fungus_ids),
            "substrate_ids": list(self.substrate_ids),
            "environment_ids": list(self.environment_ids),
            "environment_cases": [case.to_dict() for case in self.environment_cases],
            "case_count": self.case_count,
            "registry_id": self.registry.registry_id,
            "registry_source": self.registry_source,
        }

    @property
    def case_count(self) -> int:
        """Return the fungus x substrate x environment case count."""

        return len(self.fungus_ids) * len(self.substrate_ids) * len(self.environment_ids)


@dataclass
class DegradationScreenResult:
    """Virtual-experiment result with standard biological table writers."""

    experiment: VirtualExperiment
    mode: VirtualExperimentMode
    n_samples: int
    seed: int | None
    output_directory: str
    preflight_reports: tuple[ModelabilityReport, ...]
    screen_result: RegistryScreenResult
    tables: WrittenTables | None = None
    quicklook_paths: tuple[str, ...] = field(default_factory=tuple)

    def write_tables(self, output_dir: str | Path | None = None) -> WrittenTables:
        """Write standard API-001 CSV tables."""

        destination = Path(output_dir) if output_dir is not None else Path(self.output_directory)
        self.tables = write_standard_tables(
            screen_result=self.screen_result,
            registry=self.experiment.registry,
            preflight_reports=self.preflight_reports,
            output_dir=destination,
        )
        return self.tables

    def write_quicklook_plots(self, output_dir: str | Path | None = None) -> tuple[str, ...]:
        """Write optional quick-look plots from the standard tables."""

        if self.tables is None:
            self.write_tables()
        destination = Path(output_dir) if output_dir is not None else Path(self.output_directory) / "figures"
        paths = write_quicklook_plot_files(table_dir=self.output_directory, output_dir=destination)
        self.quicklook_paths = tuple(str(path) for path in paths)
        return self.quicklook_paths

    def write_summary(self, path: str | Path | None = None) -> Path:
        """Write a JSON summary of the virtual experiment and table outputs."""

        destination = Path(path) if path is not None else Path(self.output_directory) / "virtual_experiment_summary.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return destination

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment.to_dict(),
            "mode": self.mode,
            "n_samples": self.n_samples,
            "seed": self.seed,
            "output_directory": self.output_directory,
            "preflight": [report.to_dict() for report in self.preflight_reports],
            "screen_summary": self.screen_result.to_dict(),
            "tables": None if self.tables is None else self.tables.to_dict(),
            "quicklook_paths": list(self.quicklook_paths),
        }


def _load_registry_source(registry: str | Path | FungModRegistry) -> tuple[FungModRegistry, str]:
    if isinstance(registry, FungModRegistry):
        return registry, registry.registry_id
    path = Path(registry)
    return load_registry(path), str(path)


def _string_tuple(values: Sequence[str] | str, *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        output = (values,) if values else ()
    else:
        output = tuple(str(value) for value in values)
    if not output:
        raise VirtualExperimentError(f"{field_name} must contain at least one registry ID.")
    return output


def _environment_inputs(environments: Sequence[str] | str | EnvironmentGrid) -> tuple[tuple[str, ...], tuple[EnvironmentCase, ...]]:
    if isinstance(environments, EnvironmentGrid):
        environment_cases = environments.environment_cases()
        environment_ids = environments.registry_ids()
    else:
        environment_cases = ()
        environment_ids = _string_tuple(environments, field_name="environments")
    if not environment_ids:
        raise VirtualExperimentError("environments must contain at least one registry ID.")
    return environment_ids, environment_cases


def _registry_with_runtime_environment_overlay(
    registry: FungModRegistry,
    *,
    environment_cases: tuple[EnvironmentCase, ...],
) -> FungModRegistry:
    runtime_parameters = tuple(
        _runtime_environment_parameter_record(record, environment_case=environment_case)
        for record in registry.parameters.values()
        for environment_case in environment_cases
        if record.environment_id is not None
    )
    provenance = {
        **dict(registry.provenance),
        "runtime_environment_grid_overlay": True,
        "runtime_environment_ids": [case.environment_id for case in environment_cases],
        "environment_effect_status": "metadata_only",
        "notes": (
            "Runtime EnvironmentGrid overlay. Generated environments and copied "
            "parameter records are in-memory only and are not written to data_registry."
        ),
    }
    return FungModRegistry.build(
        registry_id=registry.registry_id,
        version=registry.version,
        maturity=registry.maturity,
        provenance=provenance,
        fungi=registry.fungi.values(),
        enzyme_classes=registry.enzyme_classes.values(),
        substrates=registry.substrates.values(),
        environments=(*registry.environments.values(), *(case.to_record() for case in environment_cases)),
        process_compatibility=registry.process_compatibility.values(),
        parameters=(*registry.parameters.values(), *runtime_parameters),
    )


def _runtime_environment_parameter_record(
    record: ParameterRecord,
    *,
    environment_case: EnvironmentCase,
) -> ParameterRecord:
    assert record.environment_id is not None
    return ParameterRecord(
        record_id=f"{record.record_id}__envgrid__{environment_case.environment_id}",
        name=f"{record.name} runtime EnvironmentGrid reuse for {environment_case.environment_id}",
        maturity=record.maturity,
        provenance={
            **dict(record.provenance),
            "runtime_environment_grid_overlay": True,
            "source_environment_id": record.environment_id,
            "target_environment_id": environment_case.environment_id,
            "environment_effect_status": "metadata_only",
            "environment_response_model": "none",
            "notes": (
                "Parameter record reused for a runtime EnvironmentGrid case as "
                "metadata-only context. Temperature and pH do not modify kinetics."
            ),
        },
        notes=(
            f"{record.notes} Runtime EnvironmentGrid reuse for "
            f"{environment_case.environment_id}; no pH/temperature response law applied."
        ),
        parameter_symbol=record.parameter_symbol,
        process_type=record.process_type,
        enzyme_class=record.enzyme_class,
        substrate_class=record.substrate_class,
        fungus_id=record.fungus_id,
        substrate_id=record.substrate_id,
        environment_id=environment_case.environment_id,
        value=record.value,
        range_scope=record.range_scope,
        range_interpretation=record.range_interpretation,
        allowed_use=record.allowed_use,
    )


def _validate_preflight_mode(mode: str) -> None:
    if mode not in {"scientific", "exploratory", "toy"}:
        raise VirtualExperimentError("preflight mode must be one of: scientific, exploratory, toy.")


def _validate_simulation_mode(mode: str) -> None:
    if mode != "exploratory":
        raise VirtualExperimentError(
            "API-001 VirtualExperiment supports mode='exploratory' only. "
            "Scientific deterministic virtual experiments require a later public API "
            "that preserves exact-only modelability distinctions."
        )


__all__ = [
    "DegradationScreenResult",
    "VirtualExperiment",
    "VirtualExperimentError",
    "VirtualExperimentMode",
]
