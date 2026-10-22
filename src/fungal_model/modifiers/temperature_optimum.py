"""Enzyme temperature modifiers with an optimum, driven by ``Environment.temperature``.

``SharpeSchoolfieldModifier`` (``temperature_sharpe_schoolfield``) and
``EquilibriumModelModifier`` (``temperature_equilibrium_model``) wrap the laws
in ``kinetics/temperature_optimum.py``. Each includes its own Arrhenius
activation term and is normalised to one at the reference temperature, so a
process carries exactly one temperature law; they are not meant to be stacked
on ``temperature_arrhenius_reference``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.kinetics.temperature_optimum import (
    EQUILIBRIUM_MODEL_LAW_SOURCE,
    SHARPE_SCHOOLFIELD_LAW_SOURCE,
    TEMPERATURE_OPTIMUM_LAW_MATURITY,
    equilibrium_model_activity,
    equilibrium_model_assumption,
    sharpe_schoolfield_activity,
    sharpe_schoolfield_assumption,
)
from fungal_model.modifiers.base import constant_activity_kernel

SHARPE_SCHOOLFIELD_MODIFIER_TYPE = "temperature_sharpe_schoolfield"
EQUILIBRIUM_MODEL_MODIFIER_TYPE = "temperature_equilibrium_model"
SHARPE_SCHOOLFIELD_EQUATION = (
    "a(T) = exp[-(E_a/R)(1/T - 1/T_ref)] D(T_ref) / D(T), "
    "D(T) = 1 + exp((dH_H/R)(1/T_H - 1/T)) [+ exp((dH_L/R)(1/T - 1/T_L))]"
)
EQUILIBRIUM_MODEL_EQUATION = (
    "a(T) = exp[-(E_a/R)(1/T - 1/T_ref)] f(T) / f(T_ref), "
    "f(T) = 1 / (1 + exp((dH_eq/R)(1/T_eq - 1/T)))"
)
_ENERGY_UNITS = "joule / mole"
_TEMPERATURE_UNITS = "kelvin"


@dataclass(frozen=True)
class SharpeSchoolfieldModifier:
    """Sharpe-Schoolfield activity modifier with an optional low-temperature term."""

    activation_energy_symbol: str
    reference_temperature_symbol: str
    high_inactivation_enthalpy_symbol: str
    high_half_inactivation_temperature_symbol: str
    source: str
    low_inactivation_enthalpy_symbol: str | None = None
    low_half_inactivation_temperature_symbol: str | None = None
    minimum_temperature_symbol: str | None = None
    maximum_temperature_symbol: str | None = None
    name: str = "sharpe_schoolfield_modifier"

    condition: str = "temperature"
    read_states: tuple[str, ...] = ()
    law_source: str = SHARPE_SCHOOLFIELD_LAW_SOURCE
    maturity: str = TEMPERATURE_OPTIMUM_LAW_MATURITY

    def __post_init__(self) -> None:
        if not str(self.source).strip():
            raise ValueError("SharpeSchoolfieldModifier requires a source.")
        if (self.low_inactivation_enthalpy_symbol is None) != (
            self.low_half_inactivation_temperature_symbol is None
        ):
            raise ValueError(
                "SharpeSchoolfieldModifier low-temperature term requires both "
                "low_inactivation_enthalpy_symbol and low_half_inactivation_temperature_symbol, or neither."
            )
        _require_distinct_symbols(
            "SharpeSchoolfieldModifier",
            self.activation_energy_symbol,
            self.reference_temperature_symbol,
            self.high_inactivation_enthalpy_symbol,
            self.high_half_inactivation_temperature_symbol,
            self.low_inactivation_enthalpy_symbol,
            self.low_half_inactivation_temperature_symbol,
        )

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (sharpe_schoolfield_assumption(),)

    @property
    def has_low_temperature_term(self) -> bool:
        return self.low_inactivation_enthalpy_symbol is not None

    @property
    def parameter_requirements(self) -> tuple[dict[str, str], ...]:
        """Parameter requirements for the wrapping process (symbol, units, name, description)."""

        entries: list[tuple[str | None, str, str]] = [
            (self.activation_energy_symbol, _ENERGY_UNITS, "Sharpe-Schoolfield activation energy"),
            (self.reference_temperature_symbol, _TEMPERATURE_UNITS, "Sharpe-Schoolfield reference temperature"),
            (
                self.high_inactivation_enthalpy_symbol,
                _ENERGY_UNITS,
                "Sharpe-Schoolfield high-temperature inactivation enthalpy",
            ),
            (
                self.high_half_inactivation_temperature_symbol,
                _TEMPERATURE_UNITS,
                "Sharpe-Schoolfield high half-inactivation temperature",
            ),
            (
                self.low_inactivation_enthalpy_symbol,
                _ENERGY_UNITS,
                "Sharpe-Schoolfield low-temperature inactivation enthalpy",
            ),
            (
                self.low_half_inactivation_temperature_symbol,
                _TEMPERATURE_UNITS,
                "Sharpe-Schoolfield low half-inactivation temperature",
            ),
            (self.minimum_temperature_symbol, _TEMPERATURE_UNITS, "Sharpe-Schoolfield measured lower temperature bound"),
            (self.maximum_temperature_symbol, _TEMPERATURE_UNITS, "Sharpe-Schoolfield measured upper temperature bound"),
        ]
        return tuple(
            {
                "symbol": symbol,
                "units": units,
                "name": label,
                "description": "Parameter of the explicit configured Sharpe-Schoolfield temperature modifier.",
            }
            for symbol, units, label in entries
            if symbol is not None
        )

    @property
    def limitation(self) -> str:
        return (
            "Temperature scaling uses the Sharpe-Schoolfield law: Arrhenius activation with reversible "
            "inactivation terms, normalised at the reference temperature, describing time-zero activity "
            "with no irreversible denaturation."
        )

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        return sharpe_schoolfield_activity(
            temperature=environment.require_temperature(),
            activation_energy=parameters.require_quantity(self.activation_energy_symbol, _ENERGY_UNITS),
            reference_temperature=parameters.require_quantity(self.reference_temperature_symbol, _TEMPERATURE_UNITS),
            high_inactivation_enthalpy=parameters.require_quantity(
                self.high_inactivation_enthalpy_symbol, _ENERGY_UNITS
            ),
            high_half_inactivation_temperature=parameters.require_quantity(
                self.high_half_inactivation_temperature_symbol, _TEMPERATURE_UNITS
            ),
            low_inactivation_enthalpy=_optional_quantity(
                parameters, self.low_inactivation_enthalpy_symbol, _ENERGY_UNITS
            ),
            low_half_inactivation_temperature=_optional_quantity(
                parameters, self.low_half_inactivation_temperature_symbol, _TEMPERATURE_UNITS
            ),
            minimum_temperature=_optional_quantity(parameters, self.minimum_temperature_symbol, _TEMPERATURE_UNITS),
            maximum_temperature=_optional_quantity(parameters, self.maximum_temperature_symbol, _TEMPERATURE_UNITS),
            source=self.source,
        )

    def scale(
        self,
        *,
        rate: Quantity,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        return assert_compatible(
            rate * self.activity(parameters=parameters, environment=environment, state=state),
            str(rate.units),
            name="Sharpe-Schoolfield-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Environment-only activity: evaluated once at build time."""

        return constant_activity_kernel(self, context)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": SHARPE_SCHOOLFIELD_MODIFIER_TYPE,
            "condition": self.condition,
            "activation_energy_symbol": self.activation_energy_symbol,
            "reference_temperature_symbol": self.reference_temperature_symbol,
            "high_inactivation_enthalpy_symbol": self.high_inactivation_enthalpy_symbol,
            "high_half_inactivation_temperature_symbol": self.high_half_inactivation_temperature_symbol,
            "low_inactivation_enthalpy_symbol": self.low_inactivation_enthalpy_symbol,
            "low_half_inactivation_temperature_symbol": self.low_half_inactivation_temperature_symbol,
            "minimum_temperature_symbol": self.minimum_temperature_symbol,
            "maximum_temperature_symbol": self.maximum_temperature_symbol,
            "source": self.source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": SHARPE_SCHOOLFIELD_EQUATION,
        }


@dataclass(frozen=True)
class EquilibriumModelModifier:
    """Equilibrium Model activity modifier (Arrhenius activation times the active fraction)."""

    activation_energy_symbol: str
    reference_temperature_symbol: str
    equilibrium_enthalpy_symbol: str
    equilibrium_temperature_symbol: str
    source: str
    minimum_temperature_symbol: str | None = None
    maximum_temperature_symbol: str | None = None
    name: str = "equilibrium_model_modifier"

    condition: str = "temperature"
    read_states: tuple[str, ...] = ()
    law_source: str = EQUILIBRIUM_MODEL_LAW_SOURCE
    maturity: str = TEMPERATURE_OPTIMUM_LAW_MATURITY

    def __post_init__(self) -> None:
        if not str(self.source).strip():
            raise ValueError("EquilibriumModelModifier requires a source.")
        _require_distinct_symbols(
            "EquilibriumModelModifier",
            self.activation_energy_symbol,
            self.reference_temperature_symbol,
            self.equilibrium_enthalpy_symbol,
            self.equilibrium_temperature_symbol,
        )

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (equilibrium_model_assumption(),)

    @property
    def parameter_requirements(self) -> tuple[dict[str, str], ...]:
        """Parameter requirements for the wrapping process (symbol, units, name, description)."""

        entries: list[tuple[str | None, str, str]] = [
            (self.activation_energy_symbol, _ENERGY_UNITS, "Equilibrium Model activation energy"),
            (self.reference_temperature_symbol, _TEMPERATURE_UNITS, "Equilibrium Model reference temperature"),
            (self.equilibrium_enthalpy_symbol, _ENERGY_UNITS, "Equilibrium Model equilibrium enthalpy dH_eq"),
            (self.equilibrium_temperature_symbol, _TEMPERATURE_UNITS, "Equilibrium Model equilibrium temperature T_eq"),
            (self.minimum_temperature_symbol, _TEMPERATURE_UNITS, "Equilibrium Model measured lower temperature bound"),
            (self.maximum_temperature_symbol, _TEMPERATURE_UNITS, "Equilibrium Model measured upper temperature bound"),
        ]
        return tuple(
            {
                "symbol": symbol,
                "units": units,
                "name": label,
                "description": "Parameter of the explicit configured Equilibrium Model temperature modifier.",
            }
            for symbol, units, label in entries
            if symbol is not None
        )

    @property
    def limitation(self) -> str:
        return (
            "Temperature scaling uses the Equilibrium Model: Arrhenius activation times a reversible "
            "active fraction with midpoint T_eq, normalised at the reference temperature, describing "
            "time-zero activity with no irreversible denaturation."
        )

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        return equilibrium_model_activity(
            temperature=environment.require_temperature(),
            activation_energy=parameters.require_quantity(self.activation_energy_symbol, _ENERGY_UNITS),
            reference_temperature=parameters.require_quantity(self.reference_temperature_symbol, _TEMPERATURE_UNITS),
            equilibrium_enthalpy=parameters.require_quantity(self.equilibrium_enthalpy_symbol, _ENERGY_UNITS),
            equilibrium_temperature=parameters.require_quantity(
                self.equilibrium_temperature_symbol, _TEMPERATURE_UNITS
            ),
            minimum_temperature=_optional_quantity(parameters, self.minimum_temperature_symbol, _TEMPERATURE_UNITS),
            maximum_temperature=_optional_quantity(parameters, self.maximum_temperature_symbol, _TEMPERATURE_UNITS),
            source=self.source,
        )

    def scale(
        self,
        *,
        rate: Quantity,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        return assert_compatible(
            rate * self.activity(parameters=parameters, environment=environment, state=state),
            str(rate.units),
            name="Equilibrium-Model-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Environment-only activity: evaluated once at build time."""

        return constant_activity_kernel(self, context)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": EQUILIBRIUM_MODEL_MODIFIER_TYPE,
            "condition": self.condition,
            "activation_energy_symbol": self.activation_energy_symbol,
            "reference_temperature_symbol": self.reference_temperature_symbol,
            "equilibrium_enthalpy_symbol": self.equilibrium_enthalpy_symbol,
            "equilibrium_temperature_symbol": self.equilibrium_temperature_symbol,
            "minimum_temperature_symbol": self.minimum_temperature_symbol,
            "maximum_temperature_symbol": self.maximum_temperature_symbol,
            "source": self.source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": EQUILIBRIUM_MODEL_EQUATION,
        }


def sharpe_schoolfield_modifier_from_config(
    modifier_config: Mapping[str, Any],
) -> SharpeSchoolfieldModifier:
    """Build a Sharpe-Schoolfield temperature modifier from explicit config fields."""

    modifier_type = SHARPE_SCHOOLFIELD_MODIFIER_TYPE
    return SharpeSchoolfieldModifier(
        activation_energy_symbol=_required_symbol(
            modifier_config,
            "activation_energy_symbol",
            "activation_energy",
            field_name="activation_energy_symbol",
            modifier_type=modifier_type,
        ),
        reference_temperature_symbol=_required_symbol(
            modifier_config,
            "reference_temperature_symbol",
            "reference_temperature",
            field_name="reference_temperature_symbol",
            modifier_type=modifier_type,
        ),
        high_inactivation_enthalpy_symbol=_required_symbol(
            modifier_config,
            "high_inactivation_enthalpy_symbol",
            "high_inactivation_enthalpy",
            field_name="high_inactivation_enthalpy_symbol",
            modifier_type=modifier_type,
        ),
        high_half_inactivation_temperature_symbol=_required_symbol(
            modifier_config,
            "high_half_inactivation_temperature_symbol",
            "high_half_inactivation_temperature",
            field_name="high_half_inactivation_temperature_symbol",
            modifier_type=modifier_type,
        ),
        low_inactivation_enthalpy_symbol=_optional_symbol(
            modifier_config, "low_inactivation_enthalpy_symbol", "low_inactivation_enthalpy"
        ),
        low_half_inactivation_temperature_symbol=_optional_symbol(
            modifier_config,
            "low_half_inactivation_temperature_symbol",
            "low_half_inactivation_temperature",
        ),
        minimum_temperature_symbol=_optional_symbol(modifier_config, "minimum_temperature_symbol", "minimum_temperature"),
        maximum_temperature_symbol=_optional_symbol(modifier_config, "maximum_temperature_symbol", "maximum_temperature"),
        source=_modifier_source(modifier_config, "Explicit configured Sharpe-Schoolfield temperature modifier."),
    )


def equilibrium_model_modifier_from_config(
    modifier_config: Mapping[str, Any],
) -> EquilibriumModelModifier:
    """Build an Equilibrium Model temperature modifier from explicit config fields."""

    modifier_type = EQUILIBRIUM_MODEL_MODIFIER_TYPE
    return EquilibriumModelModifier(
        activation_energy_symbol=_required_symbol(
            modifier_config,
            "activation_energy_symbol",
            "activation_energy",
            field_name="activation_energy_symbol",
            modifier_type=modifier_type,
        ),
        reference_temperature_symbol=_required_symbol(
            modifier_config,
            "reference_temperature_symbol",
            "reference_temperature",
            field_name="reference_temperature_symbol",
            modifier_type=modifier_type,
        ),
        equilibrium_enthalpy_symbol=_required_symbol(
            modifier_config,
            "equilibrium_enthalpy_symbol",
            "equilibrium_enthalpy",
            field_name="equilibrium_enthalpy_symbol",
            modifier_type=modifier_type,
        ),
        equilibrium_temperature_symbol=_required_symbol(
            modifier_config,
            "equilibrium_temperature_symbol",
            "equilibrium_temperature",
            field_name="equilibrium_temperature_symbol",
            modifier_type=modifier_type,
        ),
        minimum_temperature_symbol=_optional_symbol(modifier_config, "minimum_temperature_symbol", "minimum_temperature"),
        maximum_temperature_symbol=_optional_symbol(modifier_config, "maximum_temperature_symbol", "maximum_temperature"),
        source=_modifier_source(modifier_config, "Explicit configured Equilibrium Model temperature modifier."),
    )


def _optional_quantity(parameters: ParameterSet, symbol: str | None, units: str) -> Quantity | None:
    if symbol is None:
        return None
    return parameters.require_quantity(symbol, units)


def _require_distinct_symbols(owner: str, *symbols: str | None) -> None:
    present = [str(symbol).strip() for symbol in symbols if symbol is not None]
    if any(not symbol for symbol in present):
        raise ValueError(f"{owner} parameter symbols must be non-empty.")
    if len(set(present)) != len(present):
        raise ValueError(f"{owner} parameter symbols must be distinct.")


def _required_symbol(
    modifier_config: Mapping[str, Any],
    *keys: str,
    field_name: str,
    modifier_type: str,
) -> str:
    symbol = _optional_symbol(modifier_config, *keys)
    if symbol is None:
        raise ValueError(f"{modifier_type} modifier requires {field_name}.")
    return symbol


def _optional_symbol(modifier_config: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = modifier_config.get(key)
        if value is None:
            continue
        symbol = str(value).strip()
        if symbol:
            return symbol
    return None


def _modifier_source(modifier_config: Mapping[str, Any], default: str) -> str:
    source = str(modifier_config.get("source") or "").strip()
    return source or default


__all__ = [
    "EQUILIBRIUM_MODEL_EQUATION",
    "EQUILIBRIUM_MODEL_MODIFIER_TYPE",
    "EquilibriumModelModifier",
    "SHARPE_SCHOOLFIELD_EQUATION",
    "SHARPE_SCHOOLFIELD_MODIFIER_TYPE",
    "SharpeSchoolfieldModifier",
    "equilibrium_model_modifier_from_config",
    "sharpe_schoolfield_modifier_from_config",
]
