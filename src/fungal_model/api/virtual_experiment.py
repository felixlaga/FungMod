"""Researcher-facing virtual-experiment API."""

from __future__ import annotations

import json
import csv
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Literal

from fungal_model.api.environment_grid import EnvironmentCase, EnvironmentGrid
from fungal_model.api.output_schema import OUTPUT_SCHEMA_VERSION
from fungal_model.api.quicklook import write_quicklook_plots as write_quicklook_plot_files
from fungal_model.api.result_tables import WrittenTables, write_preflight_tables, write_standard_tables
from fungal_model.registry.records import ParameterRecord
from fungal_model.registry import FungModRegistry, RegistryResolver, ResolvedRecord, load_registry
from fungal_model.screening import (
    ModelabilityMode,
    ModelabilityReport,
    RegistryScreenResult,
    assess_modelability,
    simulate_screen,
)

VirtualExperimentMode = Literal["exploratory", "scientific"]


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
    resolved_records: tuple[ResolvedRecord, ...] = ()

    @classmethod
    def from_registry(
        cls,
        *,
        fungi: Sequence[str] | str,
        substrates: Sequence[str] | str,
        environments: Sequence[str] | str | EnvironmentGrid,
        registry: str | Path | FungModRegistry = "data_registry/registry_index.yml",
        resolve_names: bool = False,
    ) -> "VirtualExperiment":
        """Create a virtual experiment from curated registry IDs or opted-in aliases."""

        loaded_registry, registry_source = _load_registry_source(registry)
        fungus_inputs = _string_tuple(fungi, field_name="fungi")
        substrate_inputs = _string_tuple(substrates, field_name="substrates")
        environment_ids, environment_cases = _environment_inputs(environments)
        resolved_records: tuple[ResolvedRecord, ...] = ()
        if resolve_names:
            resolver = RegistryResolver(loaded_registry)
            fungus_resolutions = tuple(resolver.resolve_fungus(value) for value in fungus_inputs)
            substrate_resolutions = tuple(resolver.resolve_substrate(value) for value in substrate_inputs)
            environment_resolutions = (
                ()
                if environment_cases
                else tuple(resolver.resolve_environment(value) for value in environment_ids)
            )
            fungus_ids = tuple(resolution.record_id for resolution in fungus_resolutions)
            substrate_ids = tuple(resolution.record_id for resolution in substrate_resolutions)
            environment_ids = tuple(resolution.record_id for resolution in environment_resolutions) or environment_ids
            resolved_records = (*fungus_resolutions, *substrate_resolutions, *environment_resolutions)
        else:
            fungus_ids = fungus_inputs
            substrate_ids = substrate_inputs
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
            resolved_records=resolved_records,
        )

    @classmethod
    def from_names(
        cls,
        *,
        fungi: Sequence[str] | str,
        substrates: Sequence[str] | str,
        environments: Sequence[str] | str | EnvironmentGrid,
        registry: str | Path | FungModRegistry = "data_registry/registry_index.yml",
    ) -> "VirtualExperiment":
        """Create a virtual experiment by resolving researcher-facing names and aliases."""

        return cls.from_registry(
            fungi=fungi,
            substrates=substrates,
            environments=environments,
            registry=registry,
            resolve_names=True,
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

    def write_preflight_report(
        self,
        *,
        mode: ModelabilityMode = "exploratory",
        output_dir: str | Path = "outputs/virtual_experiment_preflight",
    ) -> WrittenTables:
        """Write preflight-only diagnostic tables without assembling or running a model."""

        reports = self.preflight(mode=mode)
        return write_preflight_tables(
            registry=self.registry,
            preflight_reports=reports,
            output_dir=output_dir,
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
        """Run registry cases and write standard virtual-experiment tables."""

        _validate_simulation_mode(mode)
        reports = self.preflight(mode=mode)
        allowed_statuses = {"modelable"} if mode == "scientific" else {"modelable", "exploratory"}
        blocked = tuple(report for report in reports if report.status not in allowed_statuses)
        if blocked:
            statuses = ", ".join(report.summary() for report in blocked)
            details = json.dumps([report.to_dict() for report in blocked], sort_keys=True)
            if mode == "scientific":
                message = (
                    "Scientific simulation requires exact, non-exploratory, non-toy modelable cases. "
                    "Scientific means exact with current registry records and implemented mechanisms; "
                    "it does not mean experimentally validated."
                )
            else:
                message = "Exploratory simulation can simulate only modelable or exploratory cases."
            raise VirtualExperimentError(
                f"{message} Blocked preflight reports: {statuses}. Details: {details}"
            )
        root = Path(output_dir)
        effective_n_samples = 1 if mode == "scientific" else n_samples
        screen = simulate_screen(
            fungus_ids=self.fungus_ids,
            substrate_ids=self.substrate_ids,
            environment_ids=self.environment_ids,
            registry=self.registry,
            n_samples=effective_n_samples,
            seed=seed,
            output_dir=root,
            mode=mode,
        )
        result = DegradationScreenResult(
            experiment=self,
            mode=mode,
            n_samples=effective_n_samples,
            seed=seed,
            output_directory=str(root),
            preflight_reports=reports,
            screen_result=screen,
        )
        result.write_tables()
        if quicklook:
            result.write_quicklook_plots()
        result.write_summary()
        result.write_manifest()
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
            "resolved_records": [record.to_dict() for record in self.resolved_records],
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

    def time_series(self) -> list[dict[str, str]]:
        """Load the standard long-form time-series table without rerunning simulation."""

        return self._table_rows("time_series_long", "time_series_long.csv")

    def final_metrics(self) -> list[dict[str, str]]:
        """Load the standard final-metrics table without rerunning simulation."""

        return self._table_rows("final_metrics", "final_metrics.csv")

    def threshold_times(self) -> list[dict[str, str]]:
        """Load the standard threshold-times table without rerunning simulation."""

        return self._table_rows("threshold_times", "threshold_times.csv")

    def sampled_parameters(self) -> list[dict[str, str]]:
        """Load the standard sampled-parameters table without rerunning simulation."""

        return self._table_rows("sampled_parameters", "sampled_parameters.csv")

    def modelability_items(self) -> list[dict[str, str]]:
        """Load the standard modelability-items table without rerunning simulation."""

        return self._table_rows("modelability_items", "modelability_items.csv")

    def assumption_summary(self) -> list[dict[str, str]]:
        """Load the standard assumption-summary table without rerunning simulation."""

        return self._table_rows("assumption_summary", "assumption_summary.csv")

    def provenance(self) -> list[dict[str, str]]:
        """Load the standard provenance table without rerunning simulation."""

        return self._table_rows("provenance_table", "provenance_table.csv")

    def limitations(self) -> list[dict[str, str]]:
        """Load the standard limitations table without rerunning simulation."""

        return self._table_rows("limitations_table", "limitations_table.csv")

    def missing_parameters(self) -> list[dict[str, str]]:
        """Load the standard missing-parameters table without rerunning simulation."""

        return self._table_rows("missing_parameters", "missing_parameters.csv")

    def suggested_experiments(self) -> list[dict[str, str]]:
        """Load the standard suggested-experiments table without rerunning simulation."""

        return self._table_rows("suggested_experiments", "suggested_experiments.csv")

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

    def write_manifest(self, path: str | Path | None = None) -> Path:
        """Write a self-describing output manifest for the virtual-experiment folder."""

        destination = Path(path) if path is not None else Path(self.output_directory) / "output_manifest.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        root = destination.parent
        files = sorted(
            str(file_path.relative_to(root))
            for file_path in root.rglob("*")
            if file_path.is_file() and file_path != destination
        )
        manifest = {
            "kind": "virtual_experiment_output_manifest",
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "mode": self.mode,
            "run_label": _run_label(self.mode),
            "scientific_mode_note": (
                "Scientific mode uses exact non-exploratory registry values and implemented process laws. "
                "It is not a claim of experimental validation."
            )
            if self.mode == "scientific"
            else "",
            "output_directory": str(root),
            "tables": None if self.tables is None else self.tables.to_dict(),
            "quicklook_paths": list(self.quicklook_paths),
            "files": [*files, destination.name],
        }
        destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return destination

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment.to_dict(),
            "mode": self.mode,
            "run_label": _run_label(self.mode),
            "n_samples": self.n_samples,
            "seed": self.seed,
            "output_directory": self.output_directory,
            "preflight": [report.to_dict() for report in self.preflight_reports],
            "screen_summary": self.screen_result.to_dict(),
            "tables": None if self.tables is None else self.tables.to_dict(),
            "quicklook_paths": list(self.quicklook_paths),
        }

    def _table_rows(self, table_name: str, filename: str) -> list[dict[str, str]]:
        path = self._table_path(table_name, filename)
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _table_path(self, table_name: str, filename: str) -> Path:
        if self.tables is not None:
            table_path = self.tables.paths.get(table_name)
            if table_path is not None:
                return Path(table_path)
        return Path(self.output_directory) / filename


def virtual_experiment(
    *,
    fungi: Sequence[str] | str,
    substrates: Sequence[str] | str,
    environments: Sequence[str] | str | EnvironmentGrid,
    registry: str | Path | FungModRegistry = "data_registry/registry_index.yml",
) -> VirtualExperiment:
    """Create a researcher-facing virtual experiment from registry IDs, names, or aliases."""

    return VirtualExperiment.from_names(
        fungi=fungi,
        substrates=substrates,
        environments=environments,
        registry=registry,
    )


def _run_label(mode: VirtualExperimentMode) -> str:
    if mode == "scientific":
        return "scientific_exact_unvalidated"
    return "exploratory_uncertainty_screen"


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
        case_templates=registry.case_templates.values(),
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
    if mode not in {"exploratory", "scientific"}:
        raise VirtualExperimentError("simulation mode must be one of: exploratory, scientific.")


__all__ = [
    "DegradationScreenResult",
    "VirtualExperiment",
    "VirtualExperimentError",
    "VirtualExperimentMode",
    "virtual_experiment",
]
