"""Centralized run-mode and data-maturity policy checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import has_text
from fungal_model.core.validators import ValidationResult

VALID_RUN_MODES = frozenset({"toy", "exploratory", "scientific", "strict"})
NON_SCIENTIFIC_MATURITIES = frozenset({"toy", "framework_benchmark"})
TOY_ONLY_PRODUCT_MAP_MATURITIES = frozenset({"toy", "framework_benchmark"})
TOY_ONLY_TOKENS = ("toy", "framework", "benchmark", "artificial", "dummy", "testing")
UNKNOWN_UNIT_MARKERS = frozenset({"unknown", "not_applicable", "not applicable", "n/a", "na"})


@dataclass(frozen=True)
class MaturityIssue:
    """One structured maturity-policy violation."""

    object_type: str
    object_id: str
    field: str
    mode: str
    reason: str
    fix: str
    value: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "field": self.field,
            "mode": self.mode,
            "reason": self.reason,
            "fix": self.fix,
            "value": self.value,
        }

    def describe(self) -> str:
        value_text = "" if self.value is None else f" value={self.value!r};"
        return (
            f"{self.object_type} {self.object_id!r} field {self.field!r} failed "
            f"for mode {self.mode!r};{value_text} {self.reason} Fix: {self.fix}"
        )


class InvalidDataMaturityError(ValueError):
    """Raised when run mode and configured data maturity are incompatible."""

    stage = "maturity_policy"

    def __init__(
        self,
        *,
        mode: str,
        maturity: str,
        issues: Sequence[MaturityIssue],
        validation_results: Sequence[ValidationResult],
    ) -> None:
        self.mode = mode
        self.maturity = maturity
        self.issues = tuple(issues)
        self.validation_results = tuple(validation_results)
        issue_summary = "\n".join(f"- {issue.describe()}" for issue in self.issues)
        super().__init__(
            f"Run maturity validation failed for mode {mode!r} and maturity {maturity!r} "
            f"with {len(self.issues)} issue(s).\n{issue_summary}"
        )


def validate_run_maturity(
    *,
    mode: str,
    maturity: str,
    parameters: ParameterSet,
    entities: Sequence[Any],
    product_maps: Mapping[str, Any],
    process_configs: Sequence[Any],
) -> tuple[ValidationResult, ...]:
    """Validate that configured data are allowed for the requested run mode."""

    issues = _maturity_issues(
        mode=mode,
        maturity=maturity,
        parameters=parameters,
        entities=entities,
        product_maps=product_maps,
        process_configs=process_configs,
    )
    passed = not issues
    return (
        ValidationResult(
            name="run_maturity",
            passed=passed,
            message=(
                "Run maturity policy passed."
                if passed
                else "Run maturity policy rejected the requested mode/configuration combination."
            ),
            details={
                "mode": mode,
                "maturity": maturity,
                "issues": [issue.to_dict() for issue in issues],
            },
        ),
    )


def enforce_run_maturity(
    *,
    mode: str,
    maturity: str,
    parameters: ParameterSet,
    entities: Sequence[Any],
    product_maps: Mapping[str, Any],
    process_configs: Sequence[Any],
) -> tuple[ValidationResult, ...]:
    """Validate run maturity and raise a structured error on failure."""

    results = validate_run_maturity(
        mode=mode,
        maturity=maturity,
        parameters=parameters,
        entities=entities,
        product_maps=product_maps,
        process_configs=process_configs,
    )
    issues = tuple(
        MaturityIssue(
            object_type=str(issue["object_type"]),
            object_id=str(issue["object_id"]),
            field=str(issue["field"]),
            mode=str(issue["mode"]),
            reason=str(issue["reason"]),
            fix=str(issue["fix"]),
            value=issue.get("value"),
        )
        for issue in results[0].details["issues"]
    )
    if issues:
        raise InvalidDataMaturityError(
            mode=mode,
            maturity=maturity,
            issues=issues,
            validation_results=results,
        )
    return results


def _maturity_issues(
    *,
    mode: str,
    maturity: str,
    parameters: ParameterSet,
    entities: Sequence[Any],
    product_maps: Mapping[str, Any],
    process_configs: Sequence[Any],
) -> tuple[MaturityIssue, ...]:
    normalized_mode = mode.strip().lower()
    issues: list[MaturityIssue] = []
    if normalized_mode not in VALID_RUN_MODES:
        return (
            MaturityIssue(
                object_type="model_config",
                object_id="run",
                field="mode",
                mode=mode,
                value=mode,
                reason="The requested run mode is not recognized by the maturity policy.",
                fix=f"Use one of {sorted(VALID_RUN_MODES)}.",
            ),
        )
    if normalized_mode == "toy":
        return ()

    issues.extend(_scientific_maturity_issues(mode=mode, maturity=maturity))
    required_symbols = _required_parameter_symbols(process_configs)
    issues.extend(
        _required_parameter_issues(
            mode=mode,
            parameters=parameters,
            required_symbols=required_symbols,
            strict=normalized_mode == "strict",
        )
    )
    issues.extend(_product_map_issues(mode=mode, product_maps=product_maps))
    issues.extend(_entity_issues(mode=mode, entities=entities))
    issues.extend(_process_config_issues(mode=mode, process_configs=process_configs))
    return tuple(issues)


def _scientific_maturity_issues(*, mode: str, maturity: str) -> tuple[MaturityIssue, ...]:
    normalized_maturity = maturity.strip().lower()
    if normalized_maturity not in NON_SCIENTIFIC_MATURITIES:
        return ()
    return (
        MaturityIssue(
            object_type="model_config",
            object_id="run",
            field="maturity",
            mode=mode,
            value=maturity,
            reason="Scientific and strict modes cannot run toy or framework-benchmark model maturity.",
            fix="Use toy mode for framework benchmarks, or replace the config with sourced scientific inputs.",
        ),
    )


def _required_parameter_issues(
    *,
    mode: str,
    parameters: ParameterSet,
    required_symbols: Sequence[str],
    strict: bool,
) -> tuple[MaturityIssue, ...]:
    issues: list[MaturityIssue] = []
    for symbol in required_symbols:
        if symbol not in parameters:
            issues.append(
                MaturityIssue(
                    object_type="parameter",
                    object_id=symbol,
                    field="symbol",
                    mode=mode,
                    value=symbol,
                    reason="A process requires this parameter but no merged Parameter exists.",
                    fix="Define the parameter in a configured or entity parameter set before running.",
                )
            )
            continue
        parameter = parameters.get(symbol)
        issues.extend(_parameter_common_issues(mode=mode, parameter=parameter))
        if strict and parameter.uncertainty is None:
            issues.append(
                MaturityIssue(
                    object_type="parameter",
                    object_id=parameter.symbol,
                    field="uncertainty",
                    mode=mode,
                    value=None,
                    reason="Strict mode requires explicit uncertainty metadata for required parameters.",
                    fix="Provide an uncertainty value or stay in scientific mode until uncertainty is available.",
                )
            )
    return tuple(issues)


def _parameter_common_issues(*, mode: str, parameter: Parameter) -> tuple[MaturityIssue, ...]:
    issues: list[MaturityIssue] = []
    if parameter.value is None:
        issues.append(
            MaturityIssue(
                object_type="parameter",
                object_id=parameter.symbol,
                field="value",
                mode=mode,
                value=None,
                reason="Scientific and strict modes cannot solve with an unknown required parameter value.",
                fix="Provide a sourced value or run the benchmark in toy mode.",
            )
        )
    if _is_unknown_unit(parameter.units):
        issues.append(
            MaturityIssue(
                object_type="parameter",
                object_id=parameter.symbol,
                field="units",
                mode=mode,
                value=parameter.units,
                reason="Scientific and strict modes require known units for required parameters.",
                fix="Replace the unit marker with explicit physical or dimensionless units.",
            )
        )
    if parameter.confidence_level == "testing":
        issues.append(
            MaturityIssue(
                object_type="parameter",
                object_id=parameter.symbol,
                field="confidence_level",
                mode=mode,
                value=parameter.confidence_level,
                reason="Testing confidence is reserved for toy/framework/test data.",
                fix="Use toy mode, or replace the parameter with a sourced non-testing confidence level.",
            )
        )
    if not has_text(parameter.source):
        issues.append(
            MaturityIssue(
                object_type="parameter",
                object_id=parameter.symbol,
                field="source",
                mode=mode,
                value=parameter.source,
                reason="Scientific and strict modes require a source for each required parameter.",
                fix="Add a source describing where this parameter came from.",
            )
        )
    if not has_text(parameter.measurement_method):
        issues.append(
            MaturityIssue(
                object_type="parameter",
                object_id=parameter.symbol,
                field="measurement_method",
                mode=mode,
                value=parameter.measurement_method,
                reason="Scientific and strict modes require a measurement or derivation method.",
                fix="Add measurement_method metadata for the required parameter.",
            )
        )
    if not has_text(parameter.validity_range):
        issues.append(
            MaturityIssue(
                object_type="parameter",
                object_id=parameter.symbol,
                field="validity_range",
                mode=mode,
                value=parameter.validity_range,
                reason="Scientific and strict modes require an explicit validity range.",
                fix="Add validity_range metadata describing where the parameter may be used.",
            )
        )
    for field_name, value in (
        ("source", parameter.source),
        ("notes", parameter.notes),
        ("measurement_method", parameter.measurement_method),
        ("validity_range", parameter.validity_range),
    ):
        token = _toy_only_token(value)
        if token is not None:
            issues.append(
                MaturityIssue(
                    object_type="parameter",
                    object_id=parameter.symbol,
                    field=field_name,
                    mode=mode,
                    value=value,
                    reason=f"The value is marked with toy/framework/test-only provenance token {token!r}.",
                    fix="Use toy mode, or replace the provenance with non-benchmark scientific metadata.",
                )
            )
    return tuple(issues)


def _product_map_issues(*, mode: str, product_maps: Mapping[str, Any]) -> tuple[MaturityIssue, ...]:
    issues: list[MaturityIssue] = []
    for map_id, product_map in product_maps.items():
        maturity = getattr(product_map, "maturity", None)
        if _normalized(maturity) in TOY_ONLY_PRODUCT_MAP_MATURITIES:
            issues.append(
                MaturityIssue(
                    object_type="product_map",
                    object_id=str(map_id),
                    field="maturity",
                    mode=mode,
                    value=maturity,
                    reason="Product maps marked toy/framework-only cannot be used in scientific or strict mode.",
                    fix="Use toy mode, or provide a product map with non-toy maturity metadata.",
                )
            )
        source = getattr(product_map, "source", None)
        if not has_text(source):
            issues.append(
                MaturityIssue(
                    object_type="product_map",
                    object_id=str(map_id),
                    field="source",
                    mode=mode,
                    value=source,
                    reason="Scientific and strict modes require a source for product maps.",
                    fix="Add product-map provenance or keep the run in toy mode.",
                )
            )
        for field_name in ("name", "source", "notes"):
            value = getattr(product_map, field_name, None)
            token = _toy_only_token(value)
            if token is not None:
                issues.append(
                    MaturityIssue(
                        object_type="product_map",
                        object_id=str(map_id),
                        field=field_name,
                        mode=mode,
                        value=value,
                        reason=f"The product map is marked with toy/framework/test-only token {token!r}.",
                        fix="Use toy mode, or provide non-benchmark product-map metadata.",
                    )
                )
    return tuple(issues)


def _entity_issues(*, mode: str, entities: Sequence[Any]) -> tuple[MaturityIssue, ...]:
    issues: list[MaturityIssue] = []
    for index, entity in enumerate(entities):
        entity_data = _entity_data(entity)
        object_id = str(entity_data.get("name") or f"entity_{index}")
        completeness = entity_data.get("completeness")
        if completeness == "placeholder":
            issues.append(
                MaturityIssue(
                    object_type="entity",
                    object_id=object_id,
                    field="completeness",
                    mode=mode,
                    value=completeness,
                    reason="Placeholder entity completeness is not scientific data maturity.",
                    fix="Use toy mode, or provide an entity with non-placeholder completeness metadata.",
                )
            )
        for field_name in ("name", "chemical_class", "source", "notes"):
            value = entity_data.get(field_name)
            token = _toy_only_token(value)
            if token is not None:
                issues.append(
                    MaturityIssue(
                        object_type="entity",
                        object_id=object_id,
                        field=field_name,
                        mode=mode,
                        value=value,
                        reason=f"The entity metadata contains toy/framework/test-only token {token!r}.",
                        fix="Use toy mode, or replace benchmark entity metadata before scientific execution.",
                    )
                )
        for label in entity_data.get("validity_labels", ()) or ():
            token = _toy_only_token(label)
            if token is not None:
                issues.append(
                    MaturityIssue(
                        object_type="entity",
                        object_id=object_id,
                        field="validity_labels",
                        mode=mode,
                        value=label,
                        reason=f"The entity validity label contains toy/framework/test-only token {token!r}.",
                        fix="Use toy mode, or replace benchmark validity labels before scientific execution.",
                    )
                )
    return tuple(issues)


def _process_config_issues(*, mode: str, process_configs: Sequence[Any]) -> tuple[MaturityIssue, ...]:
    issues: list[MaturityIssue] = []
    for process_config in process_configs:
        process_id = str(getattr(process_config, "id", "process"))
        for assumption in getattr(process_config, "assumptions", ()) or ():
            token = _toy_only_token(assumption)
            if token is not None:
                issues.append(
                    MaturityIssue(
                        object_type="process_config",
                        object_id=process_id,
                        field="assumptions",
                        mode=mode,
                        value=str(assumption),
                        reason=f"The process assumption contains toy/framework/test-only token {token!r}.",
                        fix="Use toy mode, or replace benchmark assumptions before scientific execution.",
                    )
                )
    return tuple(issues)


def _required_parameter_symbols(process_configs: Sequence[Any]) -> tuple[str, ...]:
    symbols: list[str] = []
    for process_config in process_configs:
        parameters = getattr(process_config, "parameters", {})
        if not isinstance(parameters, Mapping):
            continue
        for key, value in parameters.items():
            symbols.extend(_parameter_symbols_from_value(key=str(key), value=value))
    return tuple(dict.fromkeys(symbols))


def _parameter_symbols_from_value(*, key: str, value: Any) -> tuple[str, ...]:
    if _is_unit_key(key):
        return ()
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    if isinstance(value, Mapping):
        symbols: list[str] = []
        for nested_key, nested_value in value.items():
            symbols.extend(_parameter_symbols_from_value(key=str(nested_key), value=nested_value))
        return tuple(symbols)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        symbols = []
        for item in value:
            symbols.extend(_parameter_symbols_from_value(key=key, value=item))
        return tuple(symbols)
    return ()


def _is_unit_key(key: str) -> bool:
    normalized_key = key.strip().lower()
    return normalized_key == "units" or normalized_key.endswith("_units")


def _is_unknown_unit(units: str) -> bool:
    return _normalized(units) in UNKNOWN_UNIT_MARKERS


def _toy_only_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    for token in TOY_ONLY_TOKENS:
        if token in lowered:
            return token
    return None


def _entity_data(entity: Any) -> Mapping[str, Any]:
    to_dict = getattr(entity, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    return {
        "name": getattr(entity, "name", type(entity).__name__),
        "source": getattr(entity, "source", None),
        "notes": getattr(entity, "notes", ""),
        "completeness": getattr(entity, "completeness", None),
        "validity_labels": getattr(entity, "validity_labels", ()),
    }


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


__all__ = [
    "InvalidDataMaturityError",
    "MaturityIssue",
    "enforce_run_maturity",
    "validate_run_maturity",
]
