"""Generic process wrappers for explicit rate modifiers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity
from fungal_model.modifiers import (
    CONDITION_PH,
    CONDITION_STATE,
    CONDITION_TEMPERATURE,
    CONDITION_WATER_ACTIVITY,
    MODIFIER_CONDITIONS,
    CardinalPHModifier,
    CardinalTemperatureModifier,
    CardinalWaterActivityModifier,
    CompetitiveInhibitionModifier,
    CoupledSubstrateProductInhibitionModifier,
    InhibitorTerm,
    MixedInhibitionModifier,
    OxygenModifier,
    PHModifier,
    ProductInhibitionModifier,
    SubstrateReactivityModifier,
    SubstrateInhibitionModifier,
    TemperatureModifier,
    WaterActivityModifier,
    zero_activity_gradient,
)
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)


GAMMA_CONCEPT_SOURCE = (
    "Zwietering M.H., Wijtzes T., de Wit J.C., van 't Riet K. (1992) A decision support system for "
    "prediction of the microbial spoilage in foods. J. Food Prot. 55:973-979; "
    "Rosso L., Lobry J.R., Bajard S., Flandrois J.P. (1995) Convenient model to describe the combined "
    "effects of temperature and pH on microbial growth. Appl. Environ. Microbiol. 61:610-616; "
    "Akkermans S., Noriega Fernandez E., Logist F., Van Impe J.F. (2017) Introducing a novel interaction "
    "model structure for the combined effect of temperature and pH on the microbial growth rate. "
    "Int. J. Food Microbiol. 240:85-96"
)

# Modifier classes that read only the environment and predate the ``condition``
# protocol member. The wrapper declares their condition here, explicitly, so a
# modifier that declares nothing and is not listed is refused rather than guessed.
# The pH and oxygen modifiers (which may read a declared ``state_source``,
# BIO-004) and the cardinal water-activity modifiers declare ``condition`` and
# ``read_states`` themselves.
_ENVIRONMENT_ONLY_MODIFIER_CONDITIONS: tuple[tuple[type, str], ...] = (
    (TemperatureModifier, CONDITION_TEMPERATURE),
    (CardinalTemperatureModifier, CONDITION_TEMPERATURE),
    (WaterActivityModifier, CONDITION_WATER_ACTIVITY),
)


def gamma_concept_assumption() -> Assumption:
    """The multiplicative composition of rate modifiers, named as the hypothesis it is."""

    return Assumption(
        name="multiplicative gamma-concept composition of rate modifiers",
        description=(
            "The base rate is multiplied by one dimensionless factor per configured modifier. Factors for "
            "different environment conditions (temperature, pH, oxygen, water activity) are treated as "
            "independent and multiplied, the gamma concept; state-dependent factors (inhibition, conversion "
            "dependence) multiply the same product."
        ),
        justification=(
            "The independent-factor product is the standard baseline for combined environmental responses "
            "(Zwietering et al. 1992; Rosso et al. 1995) and keeps every factor explicit and separately "
            "testable."
        ),
        known_limitations=(
            "No interaction term between conditions: near growth or activity boundaries combined stresses "
            "deviate from the product (Akkermans et al. 2017). Two laws for one condition double-count it, so "
            "the wrapper refuses them unless allow_stacked_condition_laws is set explicitly."
        ),
        source=GAMMA_CONCEPT_SOURCE,
    )


@dataclass(frozen=True, init=False)
class RateModifierProcess(Process):
    """Wrap a process and scale its rate with explicit generic modifiers."""

    base_process: Process
    rate_modifiers: tuple[Any, ...]
    allow_stacked_condition_laws: bool

    def __init__(
        self,
        *,
        base_process: Process,
        rate_modifiers: tuple[Any, ...],
        notes: str = "",
        allow_stacked_condition_laws: bool = False,
    ) -> None:
        if not rate_modifiers:
            raise ValueError("RateModifierProcess requires at least one modifier.")
        stacked = _stacked_conditions(rate_modifiers)
        if stacked and not allow_stacked_condition_laws:
            raise ValueError(
                "RateModifierProcess refuses more than one environment law per condition "
                f"(stacked: {stacked}); two laws for one condition double-count it under the gamma concept. "
                "Set allow_stacked_condition_laws=True to declare the stacking deliberately."
            )
        Process.__init__(
            self,
            name=base_process.name,
            process_type=base_process.process_type,
            required_state_variables=_required_state_variables(base_process, rate_modifiers),
            changed_state_variables=base_process.changed_state_variables,
            required_parameters=_required_parameters(base_process, rate_modifiers),
            assumptions=_unique_assumptions(
                [
                    *base_process.assumptions,
                    gamma_concept_assumption(),
                    *(assumption for modifier in rate_modifiers for assumption in modifier.assumptions),
                ]
            ),
            validity=ValidityDomain(
                description=base_process.validity.description,
                labels=(*base_process.validity.labels, "rate_modified"),
                limitations=(
                    *base_process.validity.limitations,
                    *_modifier_limitations(rate_modifiers),
                    *_stacking_limitations(stacked),
                ),
            ),
            failure_modes=(*base_process.failure_modes, *_modifier_failure_modes(rate_modifiers)),
            source=base_process.source,
            notes=notes or base_process.notes,
        )
        object.__setattr__(self, "base_process", base_process)
        object.__setattr__(self, "rate_modifiers", tuple(rate_modifiers))
        object.__setattr__(self, "allow_stacked_condition_laws", bool(allow_stacked_condition_laws))

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

    def derived_quantities(self, states: Mapping[str, Quantity], parameters: ParameterSet) -> dict[str, Quantity]:
        """Delegate diagnostics without changing the underlying partition or serialization."""
        method = getattr(self.base_process, "derived_quantities", None)
        return {} if method is None else method(states, parameters)

    @property
    def rate_units(self) -> str:
        """Rate units are those of the wrapped base process; modifiers are dimensionless."""

        units = getattr(self.base_process, "rate_units", None)
        if not isinstance(units, str):
            raise AttributeError(f"Base process {self.base_process.name!r} declares no rate_units.")
        return units

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        base = self.base_process.compile_rate(context)
        if base is None:
            return None
        if context.environment is None and _requires_environment(self.rate_modifiers):
            raise ValueError("Explicit environment rate modifiers require an environment entity.")
        activities: list[RateKernel] = []
        for modifier in self.rate_modifiers:
            compile_activity = getattr(modifier, "compile_activity", None)
            activity = None if compile_activity is None else compile_activity(context)
            if activity is None:
                return None
            activities.append(activity)
        activity_kernels = tuple(activities)

        def kernel(time: float, state: np.ndarray) -> float:
            rate = base(time, state)
            for activity in activity_kernels:
                rate = rate * activity(time, state)
            return rate

        return kernel

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel | None:
        """Product rule over the base gradient and every modifier's activity gradient.

        ``d(v prod_k a_k)/dy = (dv/dy) prod_k a_k + v sum_k (da_k/dy) prod_{j != k} a_j``.
        Returns ``None`` (the caller then records a finite-difference Jacobian)
        when the base process or any state-reading modifier offers no analytic
        gradient. Environment-only modifiers contribute a zero gradient.
        """

        compile_base_jacobian = getattr(self.base_process, "compile_jacobian", None)
        base_gradient = None if compile_base_jacobian is None else compile_base_jacobian(context)
        base_rate = self.base_process.compile_rate(context)
        if base_gradient is None or base_rate is None:
            return None
        activities: list[RateKernel] = []
        gradients: list[JacobianKernel | None] = []
        for modifier in self.rate_modifiers:
            compile_activity = getattr(modifier, "compile_activity", None)
            activity = None if compile_activity is None else compile_activity(context)
            if activity is None:
                return None
            gradient = _activity_gradient(modifier, context)
            if gradient is None:
                return None
            activities.append(activity)
            gradients.append(None if _reads_no_state(modifier) else gradient)
        activity_kernels = tuple(activities)
        gradient_kernels = tuple(gradients)
        count = len(activity_kernels)

        def jacobian(time: float, state: np.ndarray) -> np.ndarray:
            values = [activity(time, state) for activity in activity_kernels]
            product = 1.0
            for value in values:
                product *= value
            result = base_gradient(time, state) * product
            rate = base_rate(time, state)
            for k in range(count):
                gradient = gradient_kernels[k]
                if gradient is None:
                    continue
                others = 1.0
                for j in range(count):
                    if j != k:
                        others *= values[j]
                result = result + rate * others * gradient(time, state)
            return result

        return jacobian

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "base_process": self.base_process.to_dict(),
                "rate_modifiers": [
                    modifier.to_dict() if hasattr(modifier, "to_dict") else {"name": str(modifier)}
                    for modifier in self.rate_modifiers
                ],
                "modifier_conditions": [_modifier_condition(modifier) for modifier in self.rate_modifiers],
                "allow_stacked_condition_laws": self.allow_stacked_condition_laws,
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


def substrate_reactivity_modifier_from_config(
    modifier_config: Mapping[str, Any],
    *,
    state_units: Mapping[str, str],
) -> SubstrateReactivityModifier:
    """Build a conversion-dependent substrate reactivity modifier from explicit config fields."""

    substrate_state = _required_text(
        modifier_config,
        "substrate_state",
        field_name="substrate_state",
        modifier_type="substrate_reactivity",
    )
    _require_state(substrate_state, state_units=state_units, modifier_type="substrate_reactivity")
    return SubstrateReactivityModifier(
        substrate_state=substrate_state,
        reference_concentration_symbol=_required_symbol(
            modifier_config,
            "reference_concentration",
            "reference_concentration_symbol",
            field_name="reference_concentration",
            modifier_type="substrate_reactivity",
        ),
        exponent_symbol=_required_symbol(
            modifier_config,
            "exponent",
            "exponent_symbol",
            field_name="exponent",
            modifier_type="substrate_reactivity",
        ),
        substrate_units=state_units[substrate_state],
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


def mixed_inhibition_modifier_from_config(
    modifier_config: Mapping[str, Any],
    *,
    state_units: Mapping[str, str],
) -> MixedInhibitionModifier:
    """Build the general reversible-inhibition modifier from explicit config fields.

    ``inhibitors`` is a list of mappings with ``state``, ``mechanism`` and the
    constant symbols that mechanism needs: ``competitive_constant`` (K_ic),
    ``uncompetitive_constant`` (K_iu), or ``inhibition_constant`` for a
    noncompetitive inhibitor (one symbol for both). A constant the mechanism
    does not use must be absent; a constant it needs is never defaulted.
    """

    modifier_type = "mixed_inhibition"
    substrate_state = _required_text(
        modifier_config, "substrate_state", field_name="substrate_state", modifier_type=modifier_type
    )
    _require_state(substrate_state, state_units=state_units, modifier_type=modifier_type)
    raw_inhibitors = modifier_config.get("inhibitors")
    if not isinstance(raw_inhibitors, (list, tuple)) or not raw_inhibitors:
        raise ValueError(f"{modifier_type} modifier requires a nonempty inhibitors list.")
    inhibitors: list[InhibitorTerm] = []
    for entry in raw_inhibitors:
        if not isinstance(entry, Mapping):
            raise ValueError(f"{modifier_type} modifier inhibitors entries must be mappings.")
        state = _required_text(entry, "state", "inhibitor_state", field_name="inhibitors[].state",
                               modifier_type=modifier_type)
        _require_state(state, state_units=state_units, modifier_type=modifier_type)
        mechanism = _required_text(entry, "mechanism", field_name="inhibitors[].mechanism",
                                   modifier_type=modifier_type)
        competitive = _optional_symbol(entry, "competitive_constant", "competitive_constant_symbol")
        uncompetitive = _optional_symbol(entry, "uncompetitive_constant", "uncompetitive_constant_symbol")
        shared = _optional_symbol(entry, "inhibition_constant", "inhibition_constant_symbol")
        if shared is not None:
            if mechanism != "noncompetitive":
                raise ValueError(
                    f"{modifier_type} inhibitor {state!r}: inhibition_constant is the single noncompetitive "
                    f"constant; mechanism {mechanism!r} must name competitive_constant and/or "
                    "uncompetitive_constant instead."
                )
            if (competitive is not None and competitive != shared) or (
                uncompetitive is not None and uncompetitive != shared
            ):
                raise ValueError(
                    f"{modifier_type} inhibitor {state!r}: inhibition_constant conflicts with the declared "
                    "competitive_constant/uncompetitive_constant."
                )
            competitive = uncompetitive = shared
        inhibitors.append(
            InhibitorTerm(
                state=state,
                units=state_units[state],
                mechanism=mechanism,
                competitive_constant_symbol=competitive,
                uncompetitive_constant_symbol=uncompetitive,
            )
        )
    return MixedInhibitionModifier(
        substrate_state=substrate_state,
        michaelis_constant_symbol=_required_symbol(
            modifier_config, "michaelis_constant", "michaelis_constant_symbol",
            field_name="michaelis_constant", modifier_type=modifier_type,
        ),
        substrate_units=state_units[substrate_state],
        inhibitors=tuple(inhibitors),
        primary_source=_required_text(
            modifier_config, "primary_source", field_name="primary_source", modifier_type=modifier_type
        ),
        maturity=_required_text(modifier_config, "maturity", field_name="maturity", modifier_type=modifier_type),
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


def cardinal_temperature_modifier_from_config(
    modifier_config: Mapping[str, Any],
) -> CardinalTemperatureModifier:
    """Build a Rosso cardinal-temperature modifier from explicit config fields."""

    modifier_type = "temperature_cardinal_rosso"
    return CardinalTemperatureModifier(
        minimum_temperature_symbol=_required_symbol(
            modifier_config,
            "minimum_temperature_symbol",
            "minimum_temperature",
            field_name="minimum_temperature_symbol",
            modifier_type=modifier_type,
        ),
        optimum_temperature_symbol=_required_symbol(
            modifier_config,
            "optimum_temperature_symbol",
            "optimum_temperature",
            field_name="optimum_temperature_symbol",
            modifier_type=modifier_type,
        ),
        maximum_temperature_symbol=_required_symbol(
            modifier_config,
            "maximum_temperature_symbol",
            "maximum_temperature",
            field_name="maximum_temperature_symbol",
            modifier_type=modifier_type,
        ),
        source=_modifier_source(modifier_config, "Explicit configured Rosso cardinal temperature modifier."),
    )


def cardinal_ph_modifier_from_config(modifier_config: Mapping[str, Any]) -> CardinalPHModifier:
    """Build a Rosso cardinal-pH modifier from explicit config fields."""

    modifier_type = "ph_cardinal_rosso"
    return CardinalPHModifier(
        minimum_ph_symbol=_required_symbol(
            modifier_config,
            "minimum_ph_symbol",
            "minimum_ph",
            field_name="minimum_ph_symbol",
            modifier_type=modifier_type,
        ),
        optimum_ph_symbol=_required_symbol(
            modifier_config,
            "optimum_ph_symbol",
            "optimum_ph",
            field_name="optimum_ph_symbol",
            modifier_type=modifier_type,
        ),
        maximum_ph_symbol=_required_symbol(
            modifier_config,
            "maximum_ph_symbol",
            "maximum_ph",
            field_name="maximum_ph_symbol",
            modifier_type=modifier_type,
        ),
        source=_modifier_source(modifier_config, "Explicit configured Rosso cardinal pH modifier."),
        state_source=_optional_symbol(modifier_config, "state_source"),
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
        state_source=_optional_symbol(modifier_config, "state_source"),
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
        state_source=_optional_symbol(modifier_config, "state_source"),
    )


def cardinal_water_activity_modifier_from_config(
    modifier_config: Mapping[str, Any],
) -> CardinalWaterActivityModifier:
    """Build a Rosso and Robinson cardinal water-activity modifier from explicit config fields."""

    modifier_type = "water_activity_cardinal_rosso_robinson"
    return CardinalWaterActivityModifier(
        minimum_water_activity_symbol=_required_symbol(
            modifier_config,
            "minimum_water_activity_symbol",
            "minimum_water_activity",
            field_name="minimum_water_activity_symbol",
            modifier_type=modifier_type,
        ),
        optimum_water_activity_symbol=_required_symbol(
            modifier_config,
            "optimum_water_activity_symbol",
            "optimum_water_activity",
            field_name="optimum_water_activity_symbol",
            modifier_type=modifier_type,
        ),
        source=_modifier_source(
            modifier_config, "Explicit configured Rosso and Robinson cardinal water-activity modifier."
        ),
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


def _modifier_condition(modifier: Any) -> str:
    """The declared condition of a modifier; environment-only legacy classes are tabled, others refused."""

    condition = getattr(modifier, "condition", None)
    if condition is None:
        for modifier_class, tabled in _ENVIRONMENT_ONLY_MODIFIER_CONDITIONS:
            if isinstance(modifier, modifier_class):
                return tabled
        raise ValueError(
            f"Modifier {getattr(modifier, 'name', modifier)!r} declares no condition; every rate modifier "
            f"must declare one of {list(MODIFIER_CONDITIONS)}."
        )
    if condition not in MODIFIER_CONDITIONS:
        raise ValueError(
            f"Modifier {getattr(modifier, 'name', modifier)!r} declares condition {condition!r}; "
            f"expected one of {list(MODIFIER_CONDITIONS)}."
        )
    return str(condition)


def _modifier_read_states(modifier: Any) -> tuple[tuple[str, str], ...]:
    """Every ``(state, units)`` pair a modifier reads; environment-only legacy classes read none."""

    read_states = getattr(modifier, "read_states", None)
    if read_states is None:
        if _modifier_condition(modifier) != CONDITION_STATE:
            return ()
        raise ValueError(
            f"Modifier {getattr(modifier, 'name', modifier)!r} declares condition 'state' but no read_states."
        )
    return tuple((str(name), str(units)) for name, units in read_states)


def _reads_no_state(modifier: Any) -> bool:
    return not _modifier_read_states(modifier)


def _activity_gradient(modifier: Any, context: KernelContext) -> JacobianKernel | None:
    """A modifier's analytic activity gradient; zero when it reads no state; ``None`` when it offers none."""

    compile_gradient = getattr(modifier, "compile_activity_gradient", None)
    if compile_gradient is not None:
        return compile_gradient(context)
    if _reads_no_state(modifier):
        return zero_activity_gradient(context)
    return None


def _stacked_conditions(modifiers: tuple[Any, ...]) -> tuple[str, ...]:
    """Environment conditions declared by more than one modifier, in first-seen order."""

    seen: list[str] = []
    stacked: list[str] = []
    for modifier in modifiers:
        condition = _modifier_condition(modifier)
        if condition == CONDITION_STATE:
            continue
        if condition in seen and condition not in stacked:
            stacked.append(condition)
        seen.append(condition)
    return tuple(stacked)


def _stacking_limitations(stacked: tuple[str, ...]) -> tuple[str, ...]:
    if not stacked:
        return ()
    return (
        "Stacked environment laws were allowed explicitly for "
        f"{list(stacked)}: their factors multiply and double-count that condition; the combined response "
        "is the declarer's hypothesis, not a sourced law.",
    )


def _required_state_variables(
    base_process: Process,
    modifiers: tuple[Any, ...],
) -> tuple[StateVariableSpec, ...]:
    """Declare every state a modifier reads so assembly, compilation and the Jacobian see it."""

    specs = list(base_process.required_state_variables)
    existing = {spec.name for spec in base_process.state_variables}
    for modifier in modifiers:
        state_source = getattr(modifier, "state_source", None)
        if state_source is not None and state_source not in existing:
            # BIO-004 state-driven environment authority: keep the pH or
            # dissolved-oxygen role, sign domain and bounds of the declared state.
            is_ph = getattr(modifier, "condition", None) == CONDITION_PH
            specs.append(StateVariableSpec(
                state_source,
                "dimensionless" if is_ph else modifier.oxygen_units,
                role="ph" if is_ph else "dissolved_oxygen",
                domain="signed" if is_ph else "non_negative",
                lower_bound=0 if is_ph else None,
                upper_bound=14 if is_ph else None,
            ))
            existing.add(state_source)
        for name, units in _modifier_read_states(modifier):
            if name in existing:
                continue
            specs.append(
                StateVariableSpec(
                    name,
                    units,
                    role="modifier_input",
                    description=(
                        f"State read by rate modifier {getattr(modifier, 'name', modifier)!r} "
                        f"({getattr(modifier, 'to_dict', dict)().get('type', type(modifier).__name__)})."
                    ),
                )
            )
            existing.add(name)
    return tuple(specs)


def _modifier_limitations(modifiers: tuple[Any, ...]) -> tuple[str, ...]:
    limitations = ["Rate is scaled only by explicitly configured generic modifiers."]
    limitations.extend(_cardinal_modifier_limitations(modifiers))
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
    if any(isinstance(modifier, MixedInhibitionModifier) for modifier in modifiers):
        limitations.append(
            "General reversible inhibition supports independent competitive, uncompetitive, noncompetitive "
            "or mixed inhibitors on one explicitly matched homogeneous Michaelis-Menten substrate; no "
            "cooperative, irreversible or surface-adsorption inhibition."
        )
    if any(isinstance(modifier, SubstrateReactivityModifier) for modifier in modifiers):
        limitations.append(
            "Conversion dependence (S / S_ref)^n is an empirical factor of unattributed origin; it reads an "
            "explicit substrate state that the model must carry and initialise."
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
    for modifier in modifiers:
        # Modifiers that state their own limitation text (the cardinal
        # water-activity and temperature-optimum laws) contribute it here.
        limitation = getattr(modifier, "limitation", None)
        if isinstance(limitation, str) and limitation and limitation not in limitations:
            limitations.append(limitation)
    return tuple(limitations)


def _cardinal_modifier_limitations(modifiers: tuple[Any, ...]) -> tuple[str, ...]:
    limitations: list[str] = []
    if any(isinstance(modifier, CardinalTemperatureModifier) for modifier in modifiers):
        limitations.append(
            "Temperature scaling uses the Rosso cardinal temperature model: an empirical growth-level "
            "shape with zero activity outside the cardinal range and no thermal-history or injury effects."
        )
    if any(isinstance(modifier, CardinalPHModifier) for modifier in modifiers):
        limitations.append(
            "pH scaling uses the Rosso cardinal pH model: an empirical growth-level shape with zero "
            "activity outside the cardinal range and no ionization, buffer, or ionic-strength chemistry."
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
    if any(isinstance(modifier, MixedInhibitionModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing or negative mixed-inhibition substrate or inhibitor state",
                "missing, non-positive, or unit-incompatible K_ic or K_iu inhibition constant",
                "mixed inhibition attached to a non-Michaelis-Menten process",
            )
        )
    if any(isinstance(modifier, SubstrateReactivityModifier) for modifier in modifiers):
        modes.extend(
            (
                "missing, negative, or non-finite conversion-dependence substrate state",
                "missing, non-positive, or unit-incompatible reference concentration or negative exponent",
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
    """True when a modifier reads a static environment condition (state-driven laws read a state instead)."""

    return any(
        _modifier_condition(modifier) != CONDITION_STATE and getattr(modifier, "state_source", None) is None
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
        elif isinstance(modifier, MixedInhibitionModifier):
            for term in modifier.inhibitors:
                if term.competitive_constant_symbol is not None:
                    _add_requirement(
                        requirements,
                        existing_units,
                        symbol=term.competitive_constant_symbol,
                        units=term.units,
                        name=f"competitive inhibition constant K_ic for {term.state}",
                        description="Positive K_ic (alpha term) of the general reversible-inhibition law.",
                    )
                if term.uncompetitive_constant_symbol is not None:
                    _add_requirement(
                        requirements,
                        existing_units,
                        symbol=term.uncompetitive_constant_symbol,
                        units=term.units,
                        name=f"uncompetitive inhibition constant K_iu for {term.state}",
                        description="Positive K_iu (beta term) of the general reversible-inhibition law.",
                    )
        elif isinstance(modifier, SubstrateReactivityModifier):
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.reference_concentration_symbol,
                units=modifier.substrate_units,
                name="conversion-dependence reference concentration",
                description="Positive S_ref (the loading of the same state) for the (S / S_ref)^n factor.",
            )
            _add_requirement(
                requirements,
                existing_units,
                symbol=modifier.exponent_symbol,
                units="dimensionless",
                name="conversion-dependence exponent",
                description="Non-negative exponent n of the empirical (S / S_ref)^n factor.",
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
        elif isinstance(modifier, CardinalTemperatureModifier):
            for symbol, name in (
                (modifier.minimum_temperature_symbol, "cardinal minimum temperature"),
                (modifier.optimum_temperature_symbol, "cardinal optimum temperature"),
                (modifier.maximum_temperature_symbol, "cardinal maximum temperature"),
            ):
                _add_requirement(
                    requirements,
                    existing_units,
                    symbol=symbol,
                    units="kelvin",
                    name=name,
                    description="Cardinal temperature of the explicit configured Rosso CTMI modifier.",
                )
        elif isinstance(modifier, CardinalPHModifier):
            for symbol, name in (
                (modifier.minimum_ph_symbol, "cardinal minimum pH"),
                (modifier.optimum_ph_symbol, "cardinal optimum pH"),
                (modifier.maximum_ph_symbol, "cardinal maximum pH"),
            ):
                _add_requirement(
                    requirements,
                    existing_units,
                    symbol=symbol,
                    units="dimensionless",
                    name=name,
                    description="Cardinal pH of the explicit configured Rosso CPM modifier.",
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
        else:
            # Modifiers that declare their own requirements (the cardinal
            # water-activity and temperature-optimum laws) list them as
            # ``{symbol, units, name, description}`` records.
            for entry in getattr(modifier, "parameter_requirements", ()) or ():
                _add_requirement(
                    requirements,
                    existing_units,
                    symbol=str(entry["symbol"]),
                    units=str(entry["units"]),
                    name=str(entry["name"]),
                    description=str(entry["description"]),
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
    "GAMMA_CONCEPT_SOURCE",
    "RateModifierProcess",
    "competitive_inhibition_modifier_from_config",
    "coupled_substrate_product_inhibition_modifier_from_config",
    "gamma_concept_assumption",
    "mixed_inhibition_modifier_from_config",
    "oxygen_modifier_from_config",
    "ph_modifier_from_config",
    "product_inhibition_modifier_from_config",
    "substrate_reactivity_modifier_from_config",
    "substrate_inhibition_modifier_from_config",
    "temperature_modifier_from_config",
    "cardinal_water_activity_modifier_from_config",
    "water_activity_modifier_from_config",
]
