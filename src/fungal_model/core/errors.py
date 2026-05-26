"""Structured errors for model assembly and mechanism selection."""

from __future__ import annotations

from typing import Any


class ModelAssemblyError(ValueError):
    """Base class for failures that occur before a model can be run."""

    def __init__(self, message: str, *, report: Any | None = None) -> None:
        super().__init__(message)
        self.report = report

    def to_dict(self) -> dict[str, Any]:
        """Return a machine-readable error representation."""

        data: dict[str, Any] = {
            "error_type": self.__class__.__name__,
            "message": str(super().__str__()),
        }
        if self.report is not None and hasattr(self.report, "to_dict"):
            data["report"] = self.report.to_dict()
        return data

    def __str__(self) -> str:
        message = str(super().__str__())
        if self.report is not None and hasattr(self.report, "human_readable"):
            return f"{message}\n\n{self.report.human_readable()}"
        return message


class MissingProcessError(ModelAssemblyError):
    """Raised when no registered process satisfies a requested mechanism."""


class MissingParameterError(ModelAssemblyError):
    """Raised when a required parameter is absent, unknown, or unsourced."""


class IncompatibleUnitsError(ModelAssemblyError):
    """Raised when a supplied parameter has incompatible units."""


class InvalidMechanismError(ModelAssemblyError):
    """Raised when a process or mechanism declaration is internally invalid."""


__all__ = [
    "IncompatibleUnitsError",
    "InvalidMechanismError",
    "MissingParameterError",
    "MissingProcessError",
    "ModelAssemblyError",
]
