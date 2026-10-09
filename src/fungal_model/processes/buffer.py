"""Declared dilute-buffer pH balance and signed proton/titrant ledgers.

Law: Chiriac & Balea (1997), doi:10.1021/ed074p937, equations 1 and 11.
A driver supplies an already implemented process rate; its material changes
remain on that process. This wrapper contributes only the declared balance.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
import math
import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec, ValidityDomain

PROTON_BALANCE_PROCESS_TYPE = "proton_balance_ph"


def buffer_value(
    ph: float, *, concentrations: np.ndarray, pka: np.ndarray, water_ion_product: float, standard_concentration: float
) -> tuple[float, float]:
    """Return beta and d(beta)/d(pH) in a single declared molar basis.

    Kw has concentration-squared units, C and c_standard concentration units.
    Numerical inputs must already be converted to one basis at build time.
    """
    if not math.isfinite(ph) or not 0 <= ph <= 14:
        raise ValueError("pH must stay within 0 to 14.")
    c = np.asarray(concentrations, dtype=float)
    pk = np.asarray(pka, dtype=float)
    if c.ndim != 1 or c.size == 0 or c.shape != pk.shape:
        raise ValueError("Every declared buffer requires a concentration and pKa.")
    if np.any(~np.isfinite(c)) or np.any(c < 0) or np.any(~np.isfinite(pk)):
        raise ValueError("Buffer concentrations must be finite/non-negative and pKa finite.")
    if not math.isfinite(water_ion_product) or water_ion_product <= 0:
        raise ValueError("The water ion product must be explicit, finite and positive.")
    if not math.isfinite(standard_concentration) or standard_concentration <= 0:
        raise ValueError("The pH standard concentration must be explicit, finite and positive.")
    h = standard_concentration * 10.0 ** (-ph)
    if h <= 0:
        raise ValueError("Buffer hydrogen concentration underflows in the declared concentration basis.")
    oh = water_ion_product / h
    # Ratio <= 1 is stable even for finite pKa values far outside the pH domain.
    # C*Ka*H/(Ka+H)^2 = C*r/(1+r)^2, r=10^(-abs(pH-pKa)).
    ratio = np.power(10.0, -np.abs(ph - pk))
    terms = (c * ratio) / (1.0 + ratio) ** 2
    skew = np.where(ph >= pk, (ratio - 1.0) / (ratio + 1.0), (1.0 - ratio) / (1.0 + ratio))
    with np.errstate(over="ignore", invalid="ignore"):
        beta = math.log(10) * (h + oh + float(np.sum(terms)))
        derivative = math.log(10) ** 2 * (-h + oh + float(np.sum(terms * skew)))
    if not math.isfinite(beta) or beta <= 0 or not math.isfinite(derivative):
        raise ValueError("Buffer capacity and derivative must be finite with positive capacity.")
    return beta, derivative


@dataclass(frozen=True, init=False)
class ProtonBalanceProcess(Process):
    """pH motion or a signed molar ledger driven by one explicit process.

    Compose a ``ph`` process and a ``proton_ledger`` process for each driver.
    In pH-stat mode compose ``held_ph`` and ``titrant`` instead. Positive
    titrant is base required to offset acid; negative is acid required for base.
    """

    driver: Process
    ph_state: str
    output_state: str
    mode: str
    buffer_symbols: tuple[tuple[str, str], ...]
    proton_coefficient_symbol: str
    water_ion_product_symbol: str
    standard_concentration_symbol: str
    temperature_symbol: str
    concentration_units: str
    time_units: str
    rate_units: str
    ph_bounds: tuple[float, float]

    def __init__(
        self,
        *,
        name: str,
        driver: Process,
        ph_state: str,
        buffer_symbols: tuple[tuple[str, str], ...],
        proton_coefficient_symbol: str,
        water_ion_product_symbol: str,
        standard_concentration_symbol: str,
        temperature_symbol: str,
        concentration_units: str,
        time_units: str,
        ph_bounds: tuple[float, float],
        mode: str,
        output_state: str,
        source: str,
    ) -> None:
        if not source.strip() or not buffer_symbols:
            raise ValueError("A pH balance requires a law source and explicit buffers.")
        if mode not in {"ph", "held_ph", "proton_ledger", "titrant"}:
            raise ValueError("Unknown pH balance mode.")
        if not 0 <= ph_bounds[0] < ph_bounds[1] <= 14:
            raise ValueError("pH bounds must be ordered within 0 to 14.")
        if (mode in {"ph", "held_ph"}) != (output_state == ph_state):
            raise ValueError("pH modes change ph_state; ledger modes require a distinct output state.")
        assert_compatible(Q_(1, concentration_units), "mol/liter", name="proton concentration")
        driver_units = getattr(driver, "rate_units", None)
        if not isinstance(driver_units, str):
            raise ValueError("pH driver must declare rate_units.")
        acid_rate_units = f"({concentration_units})/({time_units})"
        coefficient_units = f"({acid_rate_units})/({driver_units})"
        requirements = list(driver.required_parameters)
        requirements.extend(
            [
                ParameterRequirement(proton_coefficient_symbol, coefficient_units),
                ParameterRequirement(water_ion_product_symbol, f"({concentration_units})**2"),
                ParameterRequirement(standard_concentration_symbol, concentration_units),
                ParameterRequirement(temperature_symbol, "kelvin"),
            ]
        )
        for c, pk in buffer_symbols:
            requirements.extend(
                [ParameterRequirement(c, concentration_units), ParameterRequirement(pk, "dimensionless")]
            )
        unique = {requirement.symbol: requirement for requirement in requirements}
        ph_spec = StateVariableSpec(
            ph_state, "dimensionless", role="ph", domain="signed", lower_bound=ph_bounds[0], upper_bound=ph_bounds[1]
        )
        output_spec = (
            ph_spec
            if mode in {"ph", "held_ph"}
            else StateVariableSpec(output_state, concentration_units, role="ledger", domain="signed")
        )
        states = {spec.name: spec for spec in driver.state_variables}
        states[ph_state] = ph_spec
        Process.__init__(
            self,
            name=name,
            process_type=PROTON_BALANCE_PROCESS_TYPE,
            required_state_variables=tuple(states.values()),
            changed_state_variables=(output_spec,),
            required_parameters=tuple(unique.values()),
            assumptions=(
                *driver.assumptions,
                Assumption(
                    name="dilute monoprotic buffer value",
                    description="beta=dB/dpH; dpH/dt=-acid_rate/beta.",
                    justification="Chiriac and Balea 1997 equations 1 and 11.",
                    known_limitations="Fixed volume/temperature, ideal independent buffers; no full speciation or inferred proton yield.",
                    source=source,
                ),
            ),
            validity=ValidityDomain(
                labels=("software_tested", "buffer_balance"),
                limitations=(
                    "All proton stoichiometry, pKa, Kw and temperature inputs are explicit; no physiological constants inferred.",
                ),
            ),
            source=source,
        )
        for key, value in locals().copy().items():
            if key in self.__annotations__:
                object.__setattr__(self, key, value)
        object.__setattr__(self, "rate_units", f"1/({time_units})" if mode in {"ph", "held_ph"} else acid_rate_units)

    def _compiled(self, context: KernelContext) -> tuple[RateKernel, JacobianKernel | None]:
        driver = self.driver.compile_rate(context)
        gradient = self.driver.compile_jacobian(context)
        if driver is None:
            raise ValueError("pH balance driver must expose a numeric rate kernel.")
        driver_units = str(getattr(self.driver, "rate_units"))
        acid_units = f"({self.concentration_units})/({self.time_units})"
        coefficient = context.parameter(self.proton_coefficient_symbol, f"({acid_units})/({driver_units})")
        temperature = context.parameter(self.temperature_symbol, "kelvin")
        if not math.isfinite(temperature) or temperature <= 0:
            raise ValueError("Buffer temperature must be finite and positive.")
        environment_temperature = getattr(context.environment, "temperature", None)
        if environment_temperature is not None and not math.isclose(
            float(assert_compatible(environment_temperature, "kelvin", name="environment temperature").magnitude),
            temperature, rel_tol=1e-12,
        ):
            raise ValueError("Buffer pKa temperature must match the configured environment temperature.")
        concentration = np.array([context.parameter(c, self.concentration_units) for c, _ in self.buffer_symbols])
        pka = np.array([context.parameter(pk, "dimensionless") for _, pk in self.buffer_symbols])
        kw = context.parameter(self.water_ion_product_symbol, f"({self.concentration_units})**2")
        standard = context.parameter(self.standard_concentration_symbol, self.concentration_units)
        idx, factor = context.state_slot(self.ph_state, "dimensionless")

        def capacity(y: np.ndarray) -> tuple[float, float]:
            ph = y[idx] * factor
            if not self.ph_bounds[0] <= ph <= self.ph_bounds[1]:
                raise ValueError("pH left the declared buffer/response domain.")
            return buffer_value(
                ph, concentrations=concentration, pka=pka, water_ion_product=kw, standard_concentration=standard
            )

        buffer_value(
            sum(self.ph_bounds) / 2,
            concentrations=concentration,
            pka=pka,
            water_ion_product=kw,
            standard_concentration=standard,
        )
        if not math.isfinite(coefficient):
            raise ValueError("Proton coefficient must be finite.")

        def rate(t: float, y: np.ndarray) -> float:
            beta, _ = capacity(y)
            if self.mode == "held_ph":
                return 0.0
            acid = coefficient * driver(t, y)
            return -acid / beta if self.mode == "ph" else acid

        def jac(t: float, y: np.ndarray) -> np.ndarray:
            beta, dbeta = capacity(y)
            if self.mode == "held_ph":
                return np.zeros(len(y))
            assert gradient is not None
            result = coefficient * gradient(t, y)
            if self.mode == "ph":
                result = -result / beta
                result[idx] += coefficient * driver(t, y) * dbeta / beta**2 * factor
            return result

        return rate, jac if gradient is not None or self.mode == "held_ph" else None

    def compile_rate(self, context: KernelContext) -> RateKernel:
        return self._compiled(context)[0]

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel | None:
        return self._compiled(context)[1]

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        names = tuple(state)
        context = KernelContext(
            {name: i for i, name in enumerate(names)},
            {name: str(value.units) for name, value in state.items()},
            str(time.units),
            parameters,
            environment,
            geometry,
        )
        value = self.compile_rate(context)(
            float(time.magnitude), np.array([float(state[name].magnitude) for name in names])
        )
        return Q_(value, self.rate_units)

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        return {self.output_state: assert_compatible(rate, self.rate_units, name=self.name)}

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update(
            {
                "driver": self.driver.to_dict(),
                "ph_state": self.ph_state,
                "output_state": self.output_state,
                "mode": self.mode,
                "buffer_symbols": [list(item) for item in self.buffer_symbols],
                "maturity": "software_tested",
                "validated": False,
            }
        )
        return result
