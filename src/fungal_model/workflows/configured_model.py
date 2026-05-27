"""Generic configured-model workflow entry points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fungal_model.io.model_config import ModelConfig, load_model_config


@dataclass(frozen=True)
class ConfiguredModelRunReport:
    """Structured report for configured-model run attempts."""

    config_name: str
    config_path: str
    stage: str
    missing_capabilities: tuple[str, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "config_path": self.config_path,
            "stage": self.stage,
            "missing_capabilities": list(self.missing_capabilities),
            "message": self.message,
        }


class ConfiguredModelExecutionError(RuntimeError):
    """Raised when a configured model cannot yet be executed generically."""

    def __init__(self, message: str, *, report: ConfiguredModelRunReport) -> None:
        super().__init__(message)
        self.report = report


def run_configured_model(
    config_path: str | Path,
    output_dir: str | Path | None = None,
) -> Any:
    """Load a generic model config and return a structured execution failure."""

    config = load_model_config(config_path)
    del output_dir
    report = _execution_not_ready_report(config)
    raise ConfiguredModelExecutionError(report.message, report=report)


def _execution_not_ready_report(config: ModelConfig) -> ConfiguredModelRunReport:
    path = "" if config.path is None else str(config.path)
    return ConfiguredModelRunReport(
        config_name=config.name,
        config_path=path,
        stage="configured_model_execution",
        missing_capabilities=(
            "entity_loader_registries",
            "process_factory_library",
            "native_assembled_model_run",
            "configured_output_bundle",
        ),
        message=(
            "The generic configured-model runner loaded the config, but cannot "
            "assemble and execute it until entity registries, process factories, "
            "native assembled-model execution, and configured output saving are available."
        ),
    )


__all__ = [
    "ConfiguredModelExecutionError",
    "ConfiguredModelRunReport",
    "run_configured_model",
]
