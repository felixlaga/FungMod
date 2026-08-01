"""Generic process wrappers for explicit rate modifiers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity
from fungal_model.modifiers import (
    CompetitiveInhibitionModifier,
    CoupledSubstrateProductInhibitionModifier,
    OxygenModifier,
    PHModifier,
    ProductInhibitionModifier,
    SubstrateInhibitionModifier,
    TemperatureModifier,
    WaterActivityModifier,
)
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)


@dataclass(frozen=True, init=False)
class RateModifierProcess(Process):
    """Wrap a process and scale its rate with explicit generic modifiers."""

    base_process: Process
    rate_modifiers: tuple[Any, ...]

    def __init__(
        self,
        *,
        base_process: Process,
        rate_modifiers: tuple[Any, ...],
        notes: str = "",
    ) -> None:
        if not rate_modifiers:
            raise ValueError("RateModifierProcess requires at least one modifier.")
        Process.__init__(
            self,
            name=base_process.name,
            process_type=base_process.process_type,
            required_state_variables=_required_state_variables(base_process, rate_modifiers),
            changed_state_variables=base_process.changed_state_variables,
            required_parameters=_required_parameters(base_process, rate_modifiers),
            assumptions=_unique_assumptions(
                [*base_process.assumptions, *(assumption for modifier in rate_modifiers for assumption in modifier.assumptions)]
            ),
            validity=ValidityDomain(
                description=base_process.validity.description,
                labels=(*base_process.validity.labels, "rate_modified"),
                limitations=(*base_process.validity.limitations, *_modifier_limitations(rate_modifiers)),
            ),
            failure_modes=(*base_process.failure_modes, *_modifier_failure_modes(rate_modifiers)),
            source=base_process.source,
            notes=notes or base_process.notes,
        )
        object.__setattr__(self, "base_process", base_process)
        object.__setattr__(self, "rate_modifiers", tuple(rate_modifiers))

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        rate = self.base_process.rate(state, time, parameters, environment, geometry)
        if environment is None and _requires_environment(self.rate_modifiers):
            raise ValueError("Explicit environment rate modifiers require an environment entity.")
        for modifier in self.rate_modifiers:
            rate = modifier.scale(
                rate=rate,
                parameters=parameters,
                environment=environment,
                state=state,
            )
        return rate

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        return self.base_process.contributions(rate)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "base_process": self.base_process.to_dict(),
                "rate_modifiers": [
                    modifier.to_dict() if hasattr(modifier, "to_dict") else {"name": str(modifier)}
                    for modifier in self.rate_modifiers
                ],
            }
        )
        return data


def product_inhibition_modifier_from_config(
    modifier_config: Mapping[str, Any],
    *,
    state_units: Mapping[str, str],
) -> ProductInhibitionModifier:
    """Build a product-inhibition modifier from explicit config fields."""

    product_state = str(modifier_config.get("product_state") or "").strip()
    inhibition_constant = str(
        modifier_config.get("inhibition_constant")
        or modifier_config.get("inhibition_constant_symbol")
        or modifier_config.get("K_i")
        or ""
    ).strip()
    if not product_state:
        raise ValueError("product_inhibition modifier requires product_state.")
    if product_state not in state_units:
        raise ValueError(f"product_inhibition modifier references unknown state {product_state!r}.")
    if not inhibition_constant:
        raise ValueError("product_inhibition modifier requires inhibition_constant.")
    return ProductInhibitionModifier(
        product_state=product_state,
        inhibition_constant_symbol=inhibition_constant,
        product_units=state_units[product_state],
    )


def competitive_inhibition_modifier_from_config(
    modifier_config: Mapping[str, Any],
    *,
    state_units: Mapping[str, str],
) -> CompetitiveInhibitionModifier:
    """Build a provenance-bound competitive-inhibition modifier."""

    substrate_state = _required_text(
        modifier_config,
        "substrate_state",
        field_name="substrate_state",
        modifier_type="competitive_inhibition",
    )
    inhibitor_state = _required_text(
        modifier_config,
        "inhibitor_state",
        field_name="inhibitor_state",
        modifier_type="competitive_inhibition",
    )
    _require_state(
        substrate_state,
        state_units=state_units,
        modifier_type="competitive_inhibition",
    )
    _require_state(
        inhibitor_state,
        state_units=state_units,
        modifier_type="competitive_inhibition",
    )
    return CompetitiveInhibitionModifier(
        substrate_state=substrate_state,
        inhibitor_state=inhibitor_state,
        michaelis_constant_symbol=_required_symbol(
            modifier_config,
            "michaelis_constant",
            "michaelis_constant_symbol",
            field_name="michaelis_constant",
            modifier_type="competitive_inhibition",
        ),
        inhibition_constant_symbol=_required_symbol(
            modifier_config,
            "inhibition_constant",
            "inhibition_constant_symbol",
            "K_i",
            field_name="inhibition_constant",
            modifier_type="competitive_inhibition",
        ),
        substrate_units=state_units[substrate_state],
        inhibitor_units=state_units[inhibitor_state],
        primary_source=_required_text(
            modifier_config,
            "primary_source",
            field_name="primary_source",
            modifier_type="competitive_inhibition",
        ),
        maturity=_required_text(
            modifier_config,
            "maturity",
            field_name="maturity",
            modifier_type="competitive_inhibition",
        ),
    )


def substrate_inhibition_modifier_from_config(
    modifier_config: Mapping[str, Any],
    *,
    state_units: Mapping[str, str],
) -> SubstrateInhibitionModifier:
    """Build a provenance-bound Haldane substrate-inhibition modifier."""

    substrate_state = _required_text(
        modifier_config,
        "substrate_state",
        field_name="substrate_state",
        modifier_type="substrate_inhibition",
    )
    _require_state(
        substrate_state,
        state_units=state_units,
        modifier_type="substrate_inhibition",
    )
    return SubstrateInhibitionModifier(
        substrate_state=substrate_state,
        michaelis_constant_symbol=_required_symbol(
            modifier_config,
            "michaelis_constant",
            "michaelis_constant_symbol",
            field_name="michaelis_constant",
            modifier_type="substrate_inhibition",
        ),
        inhibition_constant_symbol=_required_symbol(
            modifier_config,
            "inhibition_constant",
            "inhibition_constant_symbol",
            "K_i",
            field_name="inhibition_constant",
            modifier_type="substrate_inhibition",
        ),
        substrate_units=state_units[substrate_state],
        primary_source=_required_text(
            modifier_config,
            "primary_source",
            field_name="primary_source",
            modifier_type="substrate_inhibition",
        ),
        maturity=_required_text(
            modifier_config,
            "maturity",
            field_name="maturity",
            modifier_type="substrate_inhibition",
        ),
    )


def coupled_substrate_product_inhibition_modifier_from_config(
    modifier_config: Mapping[str, Any],
    *,
    state_units: Mapping[str, str],
) -> CoupledSubstrateProductInhibitionModifier:
    """Build the explicit combined substrate/product-inhibition modifier."""

    modifier_type = "coupled_substrate_product_inhibition"
    substrate_state = _required_text(
        modifier_config,
        "substrate_state",
        field_name="substrate_state",
        modifier_type=modifier_type,
    )
    product_state = _required_text(
        modifier_config,
        "product_state",
        field_name="product_state",
        modifier_type=modifier_type,
    )
    _require_state(
        substrate_state,
        state_units=state_units,
        modifier_type=modifier_type,
    )
    _require_state(
        product_state,
        state_units=state_units,
        modifier_type=modifier_type,
    )
    return CoupledSubstrateProductInhibitionModifier(
        substrate_state=substrate_state,
        product_state=product_state,
        michaelis_constant_symbol=_required_symbol(
            modifier_config,
            "michaelis_constant",
            "michaelis_constant_symbol",
            field_name="michaelis_constant",
            modifier_type=modifier_type,
        ),
        substrate_inhibition_constant_symbol=_required_symbol(
            modifier_config,
            "substrate_inhibition_constant",
            "substrate_inhibition_constant_symbol",
            field_name="substrate_inhibition_constant",
            modifier_type=modifier_type,
        ),
        product_inhibition_constant_symbol=_required_symbol(
            modifier_config,
            "product_inhibition_constant",
            "product_inhibition_constant_symbol",
            field_name="product_inhibition_constant",
            modifier_type=modifier_type,
        ),
        substrate_units=state_units[substrate_state],
        product_units=state_units[product_state],
        primary_source=_required_text(
            modifier_config,
            "primary_source",
            field_name="primary_source",
            modifier_type=modifier_type,
        ),
        maturity=_required_text(
            modifier_config,
            "maturity",
            field_name="maturity",
            modifier_type=modifier_type,
        ),
    )


def temperature_modifier_from_config(modifier_config: Mapping[str, Any]) -> TemperatureModifier:
    """Build an Arrhenius temperature modifier from explicit config fields."""

    activation_energy = _required_symbol(
        modifier_config,
        "activation_energy_symbol",
        "activation_energy",
        field_name="activation_energy_symbol",
        modifier_type="temperature_arrhenius_reference",
    )
    reference_temperature = _required_symbol(
        modifier_config,
        "reference_temperature_symbol",
        "reference_temperature",
        field_name="reference_temperature_symbol",
        modifier_type="temperature_arrhenius_reference",
    )
    return TemperatureModifier(
        activation_energy_symbol=activation_energy,
        reference_temperature_symbol=reference_temperature,
        minimum_temperature_symbol=_optional_symbol(
            modifier_config,
            "minimum_temperature_symbol",
            "minimum_temperature",
        ),
        maximum_temperature_symbol=_optional_symbol(
            modifier_config,
            "maximum_temperature_symbol",
            "maximum_temperature",
        ),
        source=_modifier_source(modifier_config, "Explicit configured Arrhenius temperature modifier."),
    )


def ph_modifier_from_config(modifier_config: Mapping[str, Any]) -> PHModifier:
    """Build a Gaussian pH modifier from explicit config fields."""

    optimum = _required_symbol(
        modifier_config,
        "optimum_symbol",
        "optimum_ph_symbol",
        "optimum",
        "optimum_ph",
        field_name="optimum_symbol",
        modifier_type="ph_gaussian",
    )
    width = _required_symbol(
        modifier_config,
        "width_symbol",
        "width",
        field_name="width_symbol",
        modifier_type="ph_gaussian",
    )
    return PHModifier(
        optimum_symbol=optimum,
        width_symbol=width,
        minimum_ph_symbol=_optional_symbol(modifier_config, "minimum_ph_symbol", "minimum_ph"),
        maximum_ph_symbol=_optional_symbol(modifier_config, "maximum_ph_symbol", "maximum_ph"),
        source=_modifier_source(modifier_config, "Explicit configured Gaussian pH modifier."),
    )


def oxygen_modifier_from_config(modifier_config: Mapping[str, Any]) -> OxygenModifier:
    """Build a Monod oxygen modifier from explicit config fields."""

    half_saturation = _required_symbol(
        modifier_config,
        "half_saturation_symbol",
        "oxygen_half_saturation_symbol",
        "half_saturation",
        "K_O2",
        field_name="half_saturation_symbol",
        modifier_type="oxygen_monod",
    )
    oxygen_units = _required_text(
        modifier_config,
        "oxygen_units",
        field_name="oxygen_units",
        modifier_type="oxygen_monod",
    )
    return OxygenModifier(
        half_saturation_symbol=half_saturation,
        oxygen_units=oxygen_units,
    )


def water_activity_modifier_from_config(modifier_config: Mapping[str, Any]) -> WaterActivityModifier:
    """Build a binary water-activity threshold modifier from explicit config fields."""

    minimum_water_activity = _required_symbol(
        modifier_config,
        "minimum_water_activity_symbol",
        "minimum_water_activity",
        field_name="minimum_water_activity_symbol",
        modifier_type="water_activity_threshold",
    )
    return WaterActivityModifier(minimum_water_activity_symbol=minimum_water_activity)


def _required_state_variables(
    base_process: Process,
    modifiers: tuple[Any, ...],
) -> tuple[StateVariableSpec, ...]:
    specs = list(base_process.required_state_variables)
    existing = {(spec.name, spec.units) for spec in base_process.state_variables}
    for modifier in modifiers:
        if isinstance(modifier, ProductInhibitionModifier):
            key = (modifier.product_state, modifier.product_units)
            if key not in existing:
                specs.append(
                    StateVariableSpec(
                        modifier.product_state,
                        modifier.product_units,
                        role="inhibitor_product",
                        description="Explicit product state used by reversible product inhibition.",
                    )
                )
                existing.add(key)
        elif isinstance(modifier, CompetitiveInhibitionModifier):
            key = (modifier.inhibitor_state, modifier.inhibitor_units)
            if key not in existing:
                specs.append(
                    StateVariableSpec(
                        modifier.inhibitor_state,
                        modifier.inhibitor_units,
                        role="competitive_inhibitor",
                        description=(
                            "Explicit inhibitor state for provenance-bound "
                            "competitive Michaelis-Menten inhibition."
                        ),
                    )
                )
                existing.add(key)
        elif isinstance(modifier, CoupledSubstrateProductInhibitionModifier):
            key = (modifier.product_state, modifier.product_units)
            if key not in existing:
                specs.append(
                    StateVariableSpec(
                        modifier.product_state,
                        modifier.product_units,
                        role="inhibitor_product",
                        description=(
                            "Explicit product state for the provenance-bound "
                            "combined substrate/product-inhibition law."
                        ),
                    )
                )
                existing.add(key)
    return tuple(specs)


def _modifier_limitations(modifiers: tuple[Any, ...]) -> tuple[str, ...]:
    limitations = ["Rate is scaled only by explicitly configured generic modifiers."]
    if any(isinstance(modifier, ProductInhibitionModifier) for modifier in modifiers):
        limitations.append("Product inhibition support is single-product reversible inhibition only.")
    if any(isinstance(modifier, CompetitiveInhibitionModifier) for modifier in modifiers):
        limitations.append(
            "Competitive inhibition supports one inhibitor on an explicitly matched "
            "homogeneous Michaelis-Menten process only."
        )
    if any(isinstance(modifier, SubstrateInhibitionModifier) for modifier in modifiers):
        limitations.append(
            "Haldane substrate inhibition supports one explicitly matched homogeneous "
            "Michaelis-Menten substrate only and does not identify a molecular mechanism."
        )
    if any(
        isinstance(modifier, CoupledSubstrateProductInhibitionModifier)
        for modifier in modifiers
    ):
        limitations.append(
            "Combined substrate/product inhibition supports one explicitly matched "
            "homogeneous Michaelis-Menten substrate and one product state; its "
            "squared product term is preparation-specific empirical kinetics."
        )
    if any(isinstance(modifier, TemperatureModifier) for modifier in modifiers):
        limitations.append(
            "Temperature scaling uses the existing Arrhenius reference-rate modifier "
            "and requires explicit environment temperature plus configured parameters."
        )
    if any(isinstance(modifier, PHModifier) for modifier in modifiers):
        limitations.append(
            "pH scaling uses the existing Gaussian activity modifier and requires "
            "explicit environment pH plus configured parameters."
        )
    if any(isinstance(modifier, OxygenModifier) for modifier in modifiers):
        limitations.append(
            "Oxygen scaling uses the existing Monod oxygen modifier and requires "
            "explicit environment oxygen concentration plus configured parameters."
        )
    if any(isinstance(modifier, WaterActivityModifier) for modifier in modifiers):
        limitations.append(
            "Water-activity scaling uses the existing threshold modifier and requires "
            "explicit environment water activity plus a configured threshold parameter."
        )
    return tuple(limitations)


def _modifier_failure_modes(modifiers: tuple[Any, ...]) -> tuple[str, ...]:
    modes: list[str] = []
    if any(isinstance(modifier, ProductInhibitionModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing product inhibitor state",
                "negative product inhibitor state",
                "missing, non-positive, or unit-incompatible product inhibition constant",
            )
        )
    if any(isinstance(modifier, CompetitiveInhibitionModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing or negative competitive inhibitor state",
                "missing, non-positive, or unit-incompatible competitive inhibition constant",
                "competitive inhibition attached to a non-Michaelis-Menten process",
            )
        )
    if any(isinstance(modifier, SubstrateInhibitionModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing or negative substrate state",
                "missing, non-positive, or unit-incompatible substrate inhibition constant",
                "substrate inhibition attached to a non-Michaelis-Menten process",
            )
        )
    if any(
        isinstance(modifier, CoupledSubstrateProductInhibitionModifier)
        for modifier in modifiers
    ):
        modes.extend(
            (
                "missing or negative coupled-inhibition substrate/product state",
                "missing, non-positive, or unit-incompatible coupled-inhibition constants",
                "coupled inhibition attached to a non-Michaelis-Menten process",
            )
        )
    if any(isinstance(modifier, TemperatureModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing environment temperature",
                "missing, non-positive, or unit-incompatible Arrhenius temperature parameters",
            )
        )
    if any(isinstance(modifier, PHModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing environment pH",
                "missing, non-positive, or unit-incompatible Gaussian pH parameters",
            )
        )
    if any(isinstance(modifier, OxygenModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing environment oxygen concentration",
                "missing, non-positive, or unit-incompatible oxygen half-saturation parameter",
            )
        )
    if any(isinstance(modifier, WaterActivityModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing environment water activity",
                "missing or unit-incompatible minimum water-activity parameter",
            )
        )
    return tuple(modes)


def _requires_environment(modifiers: tuple[Any, ...]) -> bool:
    return any(
        isinstance(modifier, (TemperatureModifier, PHModifier, OxygenModifier, WaterActivityModifier))
        for modifier in modifiers
    )


def _required_parameters(
    base_process: Process,
    modifiers: tuple[Any, ...],
) -> tuple[ParameterRequirement, ...]:
    requirements = list(base_process.required_parameters)
    existing_units = {requirement.symbol: requirement.units for requirement in requirements}
    for modifier in modifiers:
        if isinstance(modifier, ProductInhibitionModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.inhibition_constant_symbol,
                units=modifier.product_units,
                name="product inhibition constant",
                description="Positive K_i for explicit reversible product inhibition.",
            )
        elif isinstance(modifier, CompetitiveInhibitionModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.inhibition_constant_symbol,
                units=modifier.inhibitor_units,
                name="competitive inhibition constant",
                description=(
                    "Positive K_i for the explicit competitive inhibitor state."
                ),
            )
        elif isinstance(modifier, SubstrateInhibitionModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.inhibition_constant_symbol,
                units=modifier.substrate_units,
                name="substrate inhibition constant",
                description=(
                    "Positive K_i for the explicit Haldane substrate-inhibition law."
                ),
            )
        elif isinstance(modifier, CoupledSubstrateProductInhibitionModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.substrate_inhibition_constant_symbol,
                units=modifier.substrate_units,
                name="substrate inhibition constant",
                description=(
                    "Positive K_i for the explicit combined substrate/product-"
                    "inhibition law."
                ),
            )
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.product_inhibition_constant_symbol,
                units=modifier.product_units,
                name="product inhibition constant",
                description=(
                    "Positive K_p for the squared product term in the explicit "
                    "combined inhibition law."
                ),
            )
        elif isinstance(modifier, TemperatureModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.activation_energy_symbol,
                units="joule / mole",
                name="Arrhenius activation energy",
                description="Activation energy for explicit configured Arrhenius temperature scaling.",
            )
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.reference_temperature_symbol,
                units="kelvin",
                name="Arrhenius reference temperature",
                description="Reference temperature for explicit configured Arrhenius temperature scaling.",
            )
            for symbol in (modifier.minimum_temperature_symbol, modifier.maximum_temperature_symbol):
                if symbol is not None:
                    _add_requirement(
                        requirements,
                        existing_units,
                        symbol=symbol,
                        units="kelvin",
                        name="Arrhenius validity temperature bound",
                        description="Optional explicit temperature bound for configured Arrhenius scaling.",
                    )
        elif isinstance(modifier, PHModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.optimum_symbol,
                units="dimensionless",
                name="Gaussian pH optimum",
                description="Optimum pH for explicit configured Gaussian pH scaling.",
            )
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.width_symbol,
                units="dimensionless",
                name="Gaussian pH width",
                description="Positive pH width for explicit configured Gaussian pH scaling.",
            )
            for symbol in (modifier.minimum_ph_symbol, modifier.maximum_ph_symbol):
                if symbol is not None:
                    _add_requirement(
                        requirements,
                        existing_units,
                        symbol=symbol,
                        units="dimensionless",
                        name="Gaussian pH validity bound",
                        description="Optional explicit pH bound for configured Gaussian pH scaling.",
                    )
        elif isinstance(modifier, OxygenModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.half_saturation_symbol,
                units=modifier.oxygen_units,
                name="oxygen half-saturation concentration",
                description="Positive K_O2 for explicit configured Monod oxygen scaling.",
            )
        elif isinstance(modifier, WaterActivityModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.minimum_water_activity_symbol,
                units="dimensionless",
                name="minimum water activity threshold",
                description="Minimum water activity for explicit configured threshold scaling.",
            )
    return tuple(requirements)


def _add_requirement(
    requirements: list[ParameterRequirement],
    existing_units: dict[str, str],
    *,
    symbol: str,
    units: str,
    name: str,
    description: str,
) -> None:
    if symbol in existing_units:
        if existing_units[symbol] != units:
            raise ValueError(
                f"Modifier parameter symbol {symbol!r} collides with an existing "
                f"parameter using different units: {existing_units[symbol]!r} and {units!r}."
            )
        return
    requirements.append(
        ParameterRequirement(
            symbol=symbol,
            units=units,
            name=name,
            description=description,
        )
    )
    existing_units[symbol] = units


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


def _required_text(
    modifier_config: Mapping[str, Any],
    *keys: str,
    field_name: str,
    modifier_type: str,
) -> str:
    value = _optional_symbol(modifier_config, *keys)
    if value is None:
        raise ValueError(f"{modifier_type} modifier requires {field_name}.")
    return value


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


def _require_state(
    state_name: str,
    *,
    state_units: Mapping[str, str],
    modifier_type: str,
) -> None:
    if state_name not in state_units:
        raise ValueError(
            f"{modifier_type} modifier references unknown state {state_name!r}."
        )


def _unique_assumptions(assumptions: list[Any]) -> tuple[Any, ...]:
    result: list[Any] = []
    seen: set[str] = set()
    for assumption in assumptions:
        name = str(getattr(assumption, "name", assumption))
        if name not in seen:
            result.append(assumption)
            seen.add(name)
    return tuple(result)


__all__ = [
    "RateModifierProcess",
    "competitive_inhibition_modifier_from_config",
    "coupled_substrate_product_inhibition_modifier_from_config",
    "oxygen_modifier_from_config",
    "ph_modifier_from_config",
    "product_inhibition_modifier_from_config",
    "substrate_inhibition_modifier_from_config",
    "temperature_modifier_from_config",
    "water_activity_modifier_from_config",
]
