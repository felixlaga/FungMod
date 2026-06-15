"""Standard simulation result, plotting, and export helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

import numpy as np

from fungal_model import __version__
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, Quantity, is_quantity
from fungal_model.core.validators import ValidationResult
from fungal_model.processes.assembly import AssemblyReport


def _quantity_to_dict(quantity: Quantity) -> dict[str, Any]:
    return {
        "value": np.asarray(quantity.magnitude, dtype=float).tolist(),
        "units": str(quantity.units),
    }


def _validation_to_dict(validation: ValidationResult | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(validation, Mapping):
        data = dict(validation)
        passed = bool(data.get("passed"))
        data.setdefault("status", "passed" if passed else "failed")
        data.setdefault("severity", "info" if passed else "error")
        data.setdefault("required", True)
        return data
    return validation.to_dict()


def _json_default(value: Any) -> Any:
    if is_quantity(value):
        return _quantity_to_dict(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


@dataclass
class SimulationResult:
    """First-class standardized output object for FungMod simulations."""

    time: Quantity
    states: dict[str, Quantity]
    parameters: ParameterSet
    assumptions: tuple[Assumption, ...]
    solver_settings: SolverSettings
    model_version: str = __version__
    process_rates: dict[str, Quantity] = field(default_factory=dict)
    derived_quantities: dict[str, Quantity] = field(default_factory=dict)
    validation_results: tuple[ValidationResult | Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    solver_metadata: dict[str, Any] = field(default_factory=dict)
    assembly_report: AssemblyReport | Mapping[str, Any] | None = None
    name: str = "simulation"
    label: str = "toy"
    source_result_summary: dict[str, Any] | None = None

    @classmethod
    def from_ode_result(
        cls,
        result: Any,
        *,
        validation_results: Sequence[ValidationResult | Mapping[str, Any]] = (),
        process_rates: Mapping[str, Quantity] | None = None,
        derived_quantities: Mapping[str, Quantity] | None = None,
        assembly_report: AssemblyReport | Mapping[str, Any] | None = None,
        warnings: Sequence[str] = (),
        name: str = "simulation",
        label: str = "toy",
    ) -> "SimulationResult":
        """Create a standard result from the existing well-mixed ODE result."""

        return cls(
            time=result.time,
            states=dict(result.species),
            parameters=result.parameters,
            assumptions=tuple(result.assumptions),
            solver_settings=result.solver_settings,
            model_version=result.model_version,
            process_rates=dict(process_rates or {}),
            derived_quantities=dict(derived_quantities or {}),
            validation_results=tuple(validation_results),
            warnings=tuple(warnings),
            solver_metadata=dict(result.solver_metadata),
            assembly_report=assembly_report,
            name=name,
            label=label,
            source_result_summary=result.results_summary(),
        )

    @classmethod
    def from_reaction_diffusion_result(
        cls,
        result: Any,
        *,
        validation_results: Sequence[ValidationResult | Mapping[str, Any]] = (),
        process_rates: Mapping[str, Quantity] | None = None,
        derived_quantities: Mapping[str, Quantity] | None = None,
        assembly_report: AssemblyReport | Mapping[str, Any] | None = None,
        warnings: Sequence[str] = (),
        name: str = "spatial_simulation",
        label: str = "toy",
    ) -> "SimulationResult":
        """Create a standard result from the existing 1D spatial result."""

        return cls(
            time=result.time,
            states=dict(result.fields),
            parameters=result.parameters,
            assumptions=tuple(result.assumptions),
            solver_settings=result.solver_settings,
            model_version=result.model_version,
            process_rates=dict(process_rates or {}),
            derived_quantities=dict(derived_quantities or {}),
            validation_results=tuple(validation_results),
            warnings=tuple(warnings),
            solver_metadata=dict(result.solver_metadata),
            assembly_report=assembly_report,
            name=name,
            label=label,
            source_result_summary=result.results_summary(),
        )

    def state(self, name: str) -> Quantity:
        return self.states[name]

    def rate(self, name: str) -> Quantity:
        return self.process_rates[name]

    def with_validation(
        self,
        validation_results: Sequence[ValidationResult | Mapping[str, Any]],
    ) -> "SimulationResult":
        """Attach validation results and return this object for fluent workflows."""

        self.validation_results = tuple(validation_results)
        return self

    def validate(
        self,
        validators: Sequence[Any],
    ) -> tuple[ValidationResult | Mapping[str, Any], ...]:
        """Run validators that accept a result-like object."""

        legacy_view = _LegacyResultView(self.time, self.states)
        self.validation_results = tuple(validator(legacy_view) for validator in validators)
        return self.validation_results

    def validation_report(self) -> list[dict[str, Any]]:
        return [_validation_to_dict(validation) for validation in self.validation_results]

    def to_dict(self) -> dict[str, Any]:
        assembly_report = self.assembly_report
        if assembly_report is None:
            assembly_data = None
        elif isinstance(assembly_report, Mapping):
            assembly_data = dict(assembly_report)
        else:
            assembly_data = assembly_report.to_dict()
        return {
            "name": self.name,
            "label": self.label,
            "model_version": self.model_version,
            "time": _quantity_to_dict(self.time),
            "states": {
                name: _quantity_to_dict(quantity)
                for name, quantity in self.states.items()
            },
            "process_rates": {
                name: _quantity_to_dict(quantity)
                for name, quantity in self.process_rates.items()
            },
            "derived_quantities": {
                name: _quantity_to_dict(quantity)
                for name, quantity in self.derived_quantities.items()
            },
            "parameters": self.parameters.to_dict(),
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "validation_report": self.validation_report(),
            "warnings": list(self.warnings),
            "solver_settings": self.solver_settings.to_dict(),
            "solver_metadata": dict(self.solver_metadata),
            "assembly_report": assembly_data,
            "source_result_summary": self.source_result_summary,
        }

    def plot_state(self, name: str, path: str | Path | None = None) -> Path | None:
        """Plot one state trajectory and optionally save it."""

        plt = _pyplot()
        quantity = self.states[name]
        time = self.time
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(np.asarray(time.magnitude, dtype=float), _plot_values(quantity), label=name)
        ax.set_xlabel(f"time ({time.units})")
        ax.set_ylabel(f"{name} ({quantity.units})")
        ax.legend()
        fig.tight_layout()
        return _finish_plot(fig, path)

    def plot_states(self, path: str | Path | None = None) -> Path | None:
        """Plot all state trajectories, grouping separate unit dimensions."""

        plt = _pyplot()
        time = self.time
        groups = _group_by_units(self.states)
        fig, axes = plt.subplots(len(groups) or 1, 1, figsize=(7, max(4, 2.5 * max(1, len(groups)))), squeeze=False)
        for ax, (units, quantities) in zip(axes.flat, groups.items(), strict=False):
            for name, quantity in quantities.items():
                ax.plot(np.asarray(time.magnitude, dtype=float), _plot_values(quantity), label=name)
            ax.set_ylabel(f"state ({units})")
            ax.legend()
        axes.flat[-1].set_xlabel(f"time ({time.units})")
        fig.tight_layout()
        return _finish_plot(fig, path)

    def plot_rates(self, path: str | Path | None = None) -> Path | None:
        """Plot process rates, or an empty diagnostics plot when none are recorded."""

        plt = _pyplot()
        time = self.time
        groups = _group_by_units(self.process_rates)
        fig, axes = plt.subplots(len(groups) or 1, 1, figsize=(7, max(4, 2.5 * max(1, len(groups)))), squeeze=False)
        if not groups:
            axes.flat[0].set_xlabel(f"time ({time.units})")
            axes.flat[0].set_ylabel("rate (not recorded)")
        for ax, (units, quantities) in zip(axes.flat, groups.items(), strict=False):
            for name, quantity in quantities.items():
                ax.plot(np.asarray(time.magnitude, dtype=float), _plot_values(quantity), label=name)
            ax.set_ylabel(f"rate ({units})")
            ax.legend()
        axes.flat[-1].set_xlabel(f"time ({time.units})")
        fig.tight_layout()
        return _finish_plot(fig, path)

    def plot_mass_balance(
        self,
        conserved_weights: Mapping[str, float | Quantity],
        path: str | Path | None = None,
    ) -> Path | None:
        """Plot weighted conserved-total residual over time."""

        total: Quantity | None = None
        for name, weight in conserved_weights.items():
            term = self.states[name] * weight if is_quantity(weight) else self.states[name] * float(weight)
            total = term if total is None else cast(Quantity, total + term.to(total.units))
        if total is None:
            raise ValueError("At least one conserved weight is required.")
        values = np.asarray(total.magnitude, dtype=float)
        residual = Q_(values - values.flat[0], total.units)

        plt = _pyplot()
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(np.asarray(self.time.magnitude, dtype=float), _plot_values(residual))
        ax.set_xlabel(f"time ({self.time.units})")
        ax.set_ylabel(f"mass-balance residual ({residual.units})")
        fig.tight_layout()
        return _finish_plot(fig, path)

    def save(
        self,
        output_dir: str | Path,
        *,
        mass_balance_weights: Mapping[str, float | Quantity] | None = None,
    ) -> None:
        """Save standardized reports, tables, logs, and core figures."""

        path = Path(output_dir)
        figures = path / "figures"
        logs = path / "logs"
        figures.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)

        _write_json(path / "record.json", self.to_dict())
        _write_json(path / "model_assembly_report.json", self.to_dict()["assembly_report"] or {})
        _write_json(path / "assumptions.json", [assumption.to_dict() for assumption in self.assumptions])
        _write_json(path / "validation_report.json", self.validation_report())
        _write_json(
            path / "solver_report.json",
            {
                "solver_settings": self.solver_settings.to_dict(),
                "solver_metadata": self.solver_metadata,
            },
        )
        _write_parameter_table(path / "parameters.csv", self.parameters)
        _write_quantity_table(path / "state_trajectories.csv", self.time, self.states, kind="state")
        _write_quantity_table(path / "process_rates.csv", self.time, self.process_rates, kind="rate")
        _write_quantity_table(path / "derived_quantities.csv", self.time, self.derived_quantities, kind="derived")
        self.plot_states(figures / "state_trajectories.png")
        self.plot_rates(figures / "process_rates.png")
        if mass_balance_weights is not None:
            self.plot_mass_balance(mass_balance_weights, figures / "mass_balance.png")
        (logs / "warnings.txt").write_text("\n".join(self.warnings) + ("\n" if self.warnings else ""), encoding="utf-8")
        (logs / "provenance_report.md").write_text(_provenance_report(self.parameters), encoding="utf-8")


@dataclass
class _LegacyResultView:
    time: Quantity
    species: dict[str, Quantity]


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _plot_values(quantity: Quantity) -> np.ndarray:
    values = np.asarray(quantity.magnitude, dtype=float)
    if values.ndim == 1:
        return values
    return values.reshape((values.shape[0], -1)).mean(axis=1)


def _group_by_units(quantities: Mapping[str, Quantity]) -> dict[str, dict[str, Quantity]]:
    groups: dict[str, dict[str, Quantity]] = {}
    for name, quantity in quantities.items():
        groups.setdefault(str(quantity.units), {})[name] = quantity
    return groups


def _finish_plot(fig: Any, path: str | Path | None) -> Path | None:
    if path is None:
        return None
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200)
    _pyplot().close(fig)
    return output


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _write_parameter_table(path: Path, parameters: ParameterSet) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "symbol",
                "name",
                "value",
                "units",
                "uncertainty",
                "source",
                "confidence_level",
                "measurement_method",
                "notes",
            ],
        )
        writer.writeheader()
        for parameter in parameters:
            writer.writerow(
                {
                    "symbol": parameter.symbol,
                    "name": parameter.name,
                    "value": "" if parameter.value is None else _scalar_or_json(parameter.value),
                    "units": parameter.units,
                    "uncertainty": "" if parameter.uncertainty is None else _scalar_or_json(parameter.uncertainty),
                    "source": parameter.source or "",
                    "confidence_level": parameter.confidence_level,
                    "measurement_method": parameter.measurement_method or "",
                    "notes": parameter.notes,
                }
            )


def _write_quantity_table(path: Path, time: Quantity, quantities: Mapping[str, Quantity], *, kind: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["kind", "name", "index", "time", "time_units", "value", "units"],
        )
        writer.writeheader()
        time_values = np.asarray(time.magnitude, dtype=float)
        for name, quantity in quantities.items():
            values = np.asarray(quantity.magnitude, dtype=float)
            if values.shape[0] != time_values.shape[0]:
                raise ValueError(f"{kind} quantity {name!r} does not align with time.")
            collapsed = _plot_values(quantity)
            for index, (time_value, value) in enumerate(zip(time_values, collapsed, strict=True)):
                writer.writerow(
                    {
                        "kind": kind,
                        "name": name,
                        "index": index,
                        "time": time_value,
                        "time_units": str(time.units),
                        "value": float(value),
                        "units": str(quantity.units),
                    }
                )


def _scalar_or_json(value: Any) -> str | float:
    if is_quantity(value):
        return json.dumps(_quantity_to_dict(value), sort_keys=True)
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, default=_json_default, sort_keys=True)


def _provenance_report(parameters: ParameterSet) -> str:
    lines = ["# Provenance Report", ""]
    for parameter in parameters:
        lines.extend(
            [
                f"## {parameter.symbol}",
                "",
                f"- name: {parameter.name}",
                f"- units: {parameter.units}",
                f"- source: {parameter.source or 'missing'}",
                f"- confidence: {parameter.confidence_level}",
                f"- measurement method: {parameter.measurement_method or 'unknown'}",
                f"- notes: {parameter.notes}",
                "",
            ]
        )
    return "\n".join(lines)


__all__ = ["SimulationResult"]
