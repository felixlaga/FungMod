"""Generic process wrappers for explicit rate modifiers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity
from fungal_model.modifiers import ProductInhibitionModifier
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
                limitations=(
                    *base_process.validity.limitations,
                    "Rate is scaled only by explicitly configured generic modifiers.",
                    "Product inhibition support is single-product reversible inhibition only.",
                ),
            ),
            failure_modes=(
                *base_process.failure_modes,
                "missing product inhibitor state",
                "negative product inhibitor state",
                "missing, non-positive, or unit-incompatible product inhibition constant",
            ),
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
    return tuple(specs)


def _required_parameters(
    base_process: Process,
    modifiers: tuple[Any, ...],
) -> tuple[ParameterRequirement, ...]:
    requirements = list(base_process.required_parameters)
    existing_units = {requirement.symbol: requirement.units for requirement in requirements}
    for modifier in modifiers:
        if not isinstance(modifier, ProductInhibitionModifier):
            continue
        if modifier.inhibition_constant_symbol in existing_units:
            if existing_units[modifier.inhibition_constant_symbol] != modifier.product_units:
                raise ValueError(
                    "Product inhibition constant symbol collides with an existing "
                    f"parameter using different units: {modifier.inhibition_constant_symbol!r}."
                )
            continue
        if modifier.inhibition_constant_symbol not in existing_units:
            requirements.append(
                ParameterRequirement(
                    symbol=modifier.inhibition_constant_symbol,
                    units=modifier.product_units,
                    name="product inhibition constant",
                    description="Positive K_i for explicit reversible product inhibition.",
                )
            )
            existing_units[modifier.inhibition_constant_symbol] = modifier.product_units
    return tuple(requirements)


def _unique_assumptions(assumptions: list[Any]) -> tuple[Any, ...]:
    result: list[Any] = []
    seen: set[str] = set()
    for assumption in assumptions:
        name = str(getattr(assumption, "name", assumption))
        if name not in seen:
            result.append(assumption)
            seen.add(name)
    return tuple(result)


__all__ = ["RateModifierProcess", "product_inhibition_modifier_from_config"]
