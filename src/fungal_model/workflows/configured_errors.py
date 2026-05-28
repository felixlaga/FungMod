"""Structured errors for configured-model workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from fungal_model.io.model_config import ModelConfig


@dataclass(frozen=True)
class ConfiguredModelRunReport:
    """Structured report for configured-model run attempts."""

    config_name: str
    config_path: str
    stage: str
    missing_capabilities: tuple[str, ...]
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "config_path": self.config_path,
            "stage": self.stage,
            "missing_capabilities": list(self.missing_capabilities),
            "message": self.message,
            "details": dict(self.details),
        }


class ConfiguredModelExecutionError(RuntimeError):
    """Raised when a configured model cannot be executed generically."""

    def __init__(self, message: str, *, report: ConfiguredModelRunReport) -> None:
        super().__init__(message)
        self.report = report


def raise_configured_model_execution_error(
    config: ModelConfig,
    *,
    stage: str,
    missing_capabilities: tuple[str, ...],
    message: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    report = configured_model_run_report(
        config,
        stage=stage,
        missing_capabilities=missing_capabilities,
        message=message,
        details={} if details is None else details,
    )
    raise ConfiguredModelExecutionError(message, report=report)


def configured_model_run_report(
    config: ModelConfig,
    *,
    stage: str,
    missing_capabilities: tuple[str, ...],
    message: str,
    details: Mapping[str, Any],
) -> ConfiguredModelRunReport:
    path = "" if config.path is None else str(config.path)
    return ConfiguredModelRunReport(
        config_name=config.name,
        config_path=path,
        stage=stage,
        missing_capabilities=missing_capabilities,
        message=message,
        details=details,
    )


__all__ = [
    "ConfiguredModelExecutionError",
    "ConfiguredModelRunReport",
    "configured_model_run_report",
    "raise_configured_model_execution_error",
]
