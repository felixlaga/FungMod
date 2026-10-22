"""Thermodynamic metadata interfaces and the dynamic Gibbs constraint.

Records approximate Gibbs free energy estimates with provenance, and couples one
forward process rate to its dynamic reaction Gibbs energy either as a hard
feasibility gate or as the continuous flux-force factor ``1 - exp(dG / (R T))``.
Full thermodynamic flux analysis across a reaction network is not enforced here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible


@dataclass(frozen=True)
class GibbsFreeEnergyEstimate:
    """Approximate Gibbs free energy estimate with provenance."""

    reaction_name: str
    delta_gibbs: Parameter
    conditions: ParameterSet = field(default_factory=ParameterSet)
    source: str | None = None
    notes: str = ""

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_value: bool = False,
    ) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Gibbs free energy estimate for {self.reaction_name!r} is missing a source.")
        self.delta_gibbs.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
        if require_value:
            self.delta_gibbs.validate_value()
        if self.delta_gibbs.quantity is not None:
            assert_compatible(self.delta_gibbs.quantity, "joule / mole", name=self.delta_gibbs.symbol)
        self.conditions.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=False,
        )

    def value(self) -> Quantity:
        quantity = self.delta_gibbs.quantity
        if quantity is None:
            raise UnknownParameterError(f"Delta G for {self.reaction_name} is unknown.")
        return assert_compatible(quantity, "joule / mole", name=self.delta_gibbs.symbol)

    def is_exergonic(self) -> bool | None:
        if self.delta_gibbs.quantity is None:
            return None
        value = self.value()
        return bool(np.all(np.asarray(value.magnitude, dtype=float) < 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reaction_name": self.reaction_name,
            "delta_gibbs": self.delta_gibbs.to_dict(),
            "conditions": self.conditions.to_dict(),
            "source": self.source,
            "notes": self.notes,
        }


ENFORCEMENT_BLOCK = "block_unfavorable_forward_rate"
ENFORCEMENT_DRIVING_FORCE = "driving_force"
ENFORCEMENT_MODES = (ENFORCEMENT_BLOCK, ENFORCEMENT_DRIVING_FORCE)
DRIVING_FORCE_MATURITY = "literature_backed_software_tested"
DRIVING_FORCE_PROVENANCE = (
    "Beard DA, Qian H (2007) Relationship between thermodynamic driving force "
    "and one-way fluxes in reversible processes. PLoS ONE 2:e144.",
    "Noor E, Flamholz A, Liebermeister W, Bar-Even A, Milo R (2013) A note on "
    "the kinetics of enzyme action: a decomposition that highlights "
    "thermodynamic effects. FEBS Lett 587:2772-2777.",
)
TEMPERATURE_DEPENDENCE_NONE = "none_declared"
TEMPERATURE_DEPENDENCE_CONSTANT_ENTHALPY = "constant_enthalpy_gibbs_helmholtz"
TEMPERATURE_DEPENDENCE_PROVENANCE = (
    "Tewari YB, Goldberg RN (1989) Thermodynamics of hydrolysis of "
    "disaccharides: cellobiose, gentiobiose, isomaltose, and maltose. "
    "J Biol Chem 264:3966-3971.",
    "Du B, Zhang Z, Grubner S, Yurkovich JT, Palsson BO, Zielinski DC (2018) "
    "Temperature-dependent estimation of Gibbs energies using an updated "
    "group-contribution method. Biophys J 114:2691-2702.",
)
ACTIVITY_BASIS_STATE = "trajectory_state"
ACTIVITY_BASIS_FIXED = "fixed_activity"
# exp(x) overflows double precision above about 709.8; the driving-force factor
# -expm1(x) is refused beyond this exponent instead of returning -inf.
DRIVING_FORCE_EXPONENT_LIMIT = 700.0


@dataclass(frozen=True)
class DynamicActivityParticipant:
    """One participant of a reaction quotient.

    A trajectory participant binds a solver state (``state_name``) whose
    activity is ``max(c / c0, a_min)``. A fixed participant has
    ``state_name == ""`` and a declared, sourced ``fixed_activity`` (for
    example the solvent at unit activity under the biochemical standard
    state); it contributes a constant to ``ln Q`` and nothing to the gradient.
    """

    state_name: str
    species_id: str
    signed_coefficient: float
    fixed_activity: float | None = None
    activity_source: str | None = None

    @property
    def is_fixed(self) -> bool:
        return self.fixed_activity is not None

    @property
    def activity_key(self) -> str:
        """Key under which the activity is reported: state name, or species id when fixed."""

        return self.species_id if self.is_fixed else self.state_name

    def validate(self) -> None:
        if not has_text(self.species_id):
            raise ValueError("Dynamic thermodynamic participants require a nonblank species id.")
        if not np.isfinite(self.signed_coefficient) or self.signed_coefficient == 0.0:
            raise ValueError(
                f"Dynamic thermodynamic participant {self.species_id!r} requires a "
                "finite nonzero signed coefficient."
            )
        if self.is_fixed:
            assert self.fixed_activity is not None
            if self.state_name != "":
                raise ValueError(
                    f"Fixed-activity participant {self.species_id!r} must not bind a "
                    "state name."
                )
            if not np.isfinite(self.fixed_activity) or self.fixed_activity <= 0.0:
                raise ValueError(
                    f"Fixed-activity participant {self.species_id!r} requires a finite "
                    "positive activity."
                )
            if not has_text(self.activity_source):
                raise ProvenanceError(
                    f"Fixed-activity participant {self.species_id!r} requires a "
                    "nonblank activity_source."
                )
        elif not has_text(self.state_name):
            raise ValueError(
                f"Dynamic thermodynamic participant {self.species_id!r} requires a "
                "nonblank state name or a fixed activity."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_name": self.state_name,
            "species_id": self.species_id,
            "signed_coefficient": self.signed_coefficient,
            "role": "reactant" if self.signed_coefficient < 0.0 else "product",
            "activity_basis": ACTIVITY_BASIS_FIXED if self.is_fixed else ACTIVITY_BASIS_STATE,
            "fixed_activity": self.fixed_activity,
            "activity_source": self.activity_source,
        }


@dataclass(frozen=True)
class DynamicThermodynamicEvaluation:
    """One state-specific activity, quotient, and Gibbs evaluation."""

    constraint_id: str
    process_id: str
    reaction_id: str
    activities: Mapping[str, float]
    log_reaction_quotient: float
    reaction_quotient: float
    standard_delta_gibbs: float
    delta_gibbs: float
    temperature_kelvin: float
    absolute_tolerance: float
    favorable: bool
    rate_blocked: bool
    driving_force_factor: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "constraint_id": self.constraint_id,
            "process_id": self.process_id,
            "reaction_id": self.reaction_id,
            "activities": dict(self.activities),
            "log_reaction_quotient": self.log_reaction_quotient,
            "reaction_quotient": self.reaction_quotient,
            "standard_delta_gibbs": self.standard_delta_gibbs,
            "standard_delta_gibbs_units": "joule / mole",
            "delta_gibbs": self.delta_gibbs,
            "delta_gibbs_units": "joule / mole",
            "temperature_K": self.temperature_kelvin,
            "absolute_tolerance": self.absolute_tolerance,
            "absolute_tolerance_units": "joule / mole",
            "favorable": self.favorable,
            "rate_blocked": self.rate_blocked,
        }
        if self.driving_force_factor is not None:
            data["driving_force_factor"] = self.driving_force_factor
        return data


@dataclass(frozen=True)
class _ResolvedConstants:
    """Unit-resolved constants shared by evaluation and compiled kernels."""

    standard_units: str
    standard_value: float
    floor_value: float
    temperature_k: float
    gas_constant_value: float
    standard_delta_g: float
    tolerance_value: float

    @property
    def rt(self) -> float:
        return self.gas_constant_value * self.temperature_k


def driving_force_factor(delta_gibbs: float, rt: float) -> float:
    """Flux-force factor ``phi = 1 - exp(dG / RT)`` (Beard and Qian 2007; Noor et al. 2013).

    ``phi`` is 1 far from equilibrium in the forward direction, 0 at
    equilibrium, and negative (reverse net flux) above it. Exponents beyond
    :data:`DRIVING_FORCE_EXPONENT_LIMIT` are refused rather than overflowing.
    """

    exponent = delta_gibbs / rt
    if not np.isfinite(exponent):
        raise ValueError("Thermodynamic driving force requires a finite dG / (R T).")
    if exponent > DRIVING_FORCE_EXPONENT_LIMIT:
        raise ValueError(
            f"Thermodynamic driving force exponent dG / (R T) = {exponent:.3g} exceeds "
            f"{DRIVING_FORCE_EXPONENT_LIMIT:g}; the factor is not representable."
        )
    return float(-np.expm1(exponent))


@dataclass(frozen=True)
class DynamicThermodynamicConstraint:
    """Provenance-bound dynamic Gibbs constraint for one forward process rate.

    ``enforcement_mode`` selects how the forward law ``r_fwd`` is coupled to
    ``dG = dG0(T) + R T ln Q``:

    * ``block_unfavorable_forward_rate``: ``r = r_fwd * 1[dG < -tol]``. The
      legacy indicator; no reverse flux, a dead zone of width ``tol``.
    * ``driving_force``: ``r_net = r_fwd * (1 - exp(dG / (R T)))``; continuous,
      zero at equilibrium, negative above it. The reverse flux inherits the
      forward law's saturation (reverse saturation is not represented).

    ``dG0(T) = dH0 - T (dH0 - dG0(T_ref)) / T_ref`` when ``standard_enthalpy``
    and ``reference_temperature`` are both declared (constant enthalpy,
    Gibbs-Helmholtz); otherwise ``dG0`` is used as given at every temperature.
    """

    constraint_id: str
    process_id: str
    reaction_id: str
    electron_balance_check_id: str
    participants: tuple[DynamicActivityParticipant, ...]
    standard_energy_method: str
    temperature: Parameter
    gas_constant: Parameter
    standard_concentration: Parameter
    minimum_activity: Parameter
    absolute_tolerance: Parameter
    provenance_refs: tuple[str, ...]
    standard_delta_gibbs: Parameter | None = None
    standard_redox_potential: Parameter | None = None
    electron_transfer_number: Parameter | None = None
    faraday_constant: Parameter | None = None
    enforcement_mode: str = ENFORCEMENT_BLOCK
    standard_enthalpy: Parameter | None = None
    reference_temperature: Parameter | None = None

    @property
    def temperature_dependence(self) -> str:
        if self.standard_enthalpy is None and self.reference_temperature is None:
            return TEMPERATURE_DEPENDENCE_NONE
        return TEMPERATURE_DEPENDENCE_CONSTANT_ENTHALPY

    def validate(self) -> None:
        for field_name, value in (
            ("constraint_id", self.constraint_id),
            ("process_id", self.process_id),
            ("reaction_id", self.reaction_id),
            ("electron_balance_check_id", self.electron_balance_check_id),
        ):
            if not has_text(value):
                raise ValueError(f"Dynamic thermodynamic {field_name} must be nonblank.")
        if self.enforcement_mode not in ENFORCEMENT_MODES:
            raise ValueError(
                "Dynamic thermodynamic enforcement_mode must be one of "
                f"{list(ENFORCEMENT_MODES)}; got {self.enforcement_mode!r}."
            )
        if not self.participants:
            raise ValueError("Dynamic thermodynamic constraint requires reaction participants.")
        for participant in self.participants:
            participant.validate()
        state_names = [
            participant.state_name for participant in self.participants if not participant.is_fixed
        ]
        species_ids = [participant.species_id for participant in self.participants]
        if len(set(state_names)) != len(state_names):
            raise ValueError(
                "Dynamic thermodynamic reaction participants must bind distinct state names."
            )
        if len(set(species_ids)) != len(species_ids):
            raise ValueError(
                "Dynamic thermodynamic reaction participants must bind distinct species ids."
            )
        if not state_names:
            raise ValueError(
                "Dynamic thermodynamic reaction requires at least one trajectory participant."
            )
        if not any(participant.signed_coefficient < 0.0 for participant in self.participants):
            raise ValueError("Dynamic thermodynamic reaction requires at least one reactant.")
        if not any(participant.signed_coefficient > 0.0 for participant in self.participants):
            raise ValueError("Dynamic thermodynamic reaction requires at least one product.")
        if not self.provenance_refs or any(not has_text(value) for value in self.provenance_refs):
            raise ProvenanceError(
                "Dynamic thermodynamic constraint requires nonblank provenance_refs."
            )
        parameters = [
            self.temperature,
            self.gas_constant,
            self.standard_concentration,
            self.minimum_activity,
            self.absolute_tolerance,
        ]
        if self.standard_energy_method == "standard_delta_gibbs":
            if self.standard_delta_gibbs is None:
                raise ValueError(
                    "standard_delta_gibbs method requires standard_delta_gibbs."
                )
            if any(
                item is not None
                for item in (
                    self.standard_redox_potential,
                    self.electron_transfer_number,
                    self.faraday_constant,
                )
            ):
                raise ValueError(
                    "standard_delta_gibbs method cannot also declare redox energy inputs."
                )
            parameters.append(self.standard_delta_gibbs)
        elif self.standard_energy_method == "redox_potential":
            redox_parameters = (
                self.standard_redox_potential,
                self.electron_transfer_number,
                self.faraday_constant,
            )
            if any(parameter is None for parameter in redox_parameters):
                raise ValueError(
                    "redox_potential method requires standard_redox_potential, "
                    "electron_transfer_number, and faraday_constant."
                )
            if self.standard_delta_gibbs is not None:
                raise ValueError(
                    "redox_potential method cannot also declare standard_delta_gibbs."
                )
            parameters.extend(
                parameter
                for parameter in redox_parameters
                if parameter is not None
            )
        else:
            raise ValueError(
                "Dynamic thermodynamic standard_energy.method must be "
                "'standard_delta_gibbs' or 'redox_potential'."
            )
        if (self.standard_enthalpy is None) != (self.reference_temperature is None):
            raise ValueError(
                "Temperature-dependent standard Gibbs energy requires both "
                "standard_enthalpy and reference_temperature, or neither."
            )
        if self.standard_enthalpy is not None:
            assert self.reference_temperature is not None
            parameters.extend((self.standard_enthalpy, self.reference_temperature))
        for parameter in parameters:
            parameter.validate_provenance()
            parameter.validate_value()
            _finite_scalar(parameter)
        _positive_value(self.temperature, "kelvin")
        _positive_value(self.gas_constant, "joule / mole / kelvin")
        standard_concentration_quantity = self.standard_concentration.quantity
        assert standard_concentration_quantity is not None
        assert_compatible(
            standard_concentration_quantity,
            "mole / liter",
            name=self.standard_concentration.symbol,
        )
        _positive_value(self.standard_concentration, str(self.standard_concentration.units))
        minimum_activity = _positive_value(self.minimum_activity, "dimensionless")
        if minimum_activity > 1.0:
            raise ValueError("minimum_activity must be positive and no greater than 1.")
        tolerance = _nonnegative_value(self.absolute_tolerance, "joule / mole")
        if not np.isfinite(tolerance):
            raise ValueError("absolute_tolerance must be finite.")
        if self.standard_energy_method == "standard_delta_gibbs":
            assert self.standard_delta_gibbs is not None
            _finite_value(self.standard_delta_gibbs, "joule / mole")
        else:
            assert self.standard_redox_potential is not None
            assert self.electron_transfer_number is not None
            assert self.faraday_constant is not None
            _finite_value(self.standard_redox_potential, "volt")
            _positive_value(self.electron_transfer_number, "dimensionless")
            _positive_value(self.faraday_constant, "coulomb / mole")
        if self.standard_enthalpy is not None:
            assert self.reference_temperature is not None
            _finite_value(self.standard_enthalpy, "joule / mole")
            _positive_value(self.reference_temperature, "kelvin")

    def reference_standard_delta_gibbs_value(self) -> float:
        """Standard Gibbs energy as declared (or redox-derived), in J/mol, before any temperature transform."""

        self.validate()
        if self.standard_energy_method == "standard_delta_gibbs":
            assert self.standard_delta_gibbs is not None
            return _finite_value(self.standard_delta_gibbs, "joule / mole")
        assert self.standard_redox_potential is not None
        assert self.electron_transfer_number is not None
        assert self.faraday_constant is not None
        potential = assert_compatible(
            self.standard_redox_potential.quantity,
            "volt",
            name=self.standard_redox_potential.symbol,
        )
        transfer_number = assert_compatible(
            self.electron_transfer_number.quantity,
            "dimensionless",
            name=self.electron_transfer_number.symbol,
        )
        faraday = assert_compatible(
            self.faraday_constant.quantity,
            "coulomb / mole",
            name=self.faraday_constant.symbol,
        )
        delta_g = -(transfer_number * faraday * potential)
        return float(np.asarray(delta_g.to("joule / mole").magnitude, dtype=float))

    def standard_delta_gibbs_value(self) -> float:
        """Standard Gibbs energy at the constraint temperature, in J/mol.

        With ``standard_enthalpy`` and ``reference_temperature`` declared this is
        the constant-enthalpy Gibbs-Helmholtz form
        ``dG0(T) = dH0 - T (dH0 - dG0(T_ref)) / T_ref`` (Tewari and Goldberg
        1989; Du et al. 2018). Without them the declared value is returned.
        """

        reference = self.reference_standard_delta_gibbs_value()
        if self.standard_enthalpy is None:
            return reference
        assert self.reference_temperature is not None
        enthalpy = _finite_value(self.standard_enthalpy, "joule / mole")
        reference_k = _positive_value(self.reference_temperature, "kelvin")
        temperature_k = _positive_value(self.temperature, "kelvin")
        return enthalpy - temperature_k * (enthalpy - reference) / reference_k

    def _resolved(self) -> _ResolvedConstants:
        self.validate()
        standard_concentration = self.standard_concentration.quantity
        minimum_activity = self.minimum_activity.quantity
        temperature = self.temperature.quantity
        gas_constant = self.gas_constant.quantity
        tolerance = self.absolute_tolerance.quantity
        assert standard_concentration is not None
        assert minimum_activity is not None
        assert temperature is not None
        assert gas_constant is not None
        assert tolerance is not None
        return _ResolvedConstants(
            standard_units=str(standard_concentration.units),
            standard_value=float(standard_concentration.magnitude),
            floor_value=float(minimum_activity.to("dimensionless").magnitude),
            temperature_k=float(temperature.to("kelvin").magnitude),
            gas_constant_value=float(gas_constant.to("joule / mole / kelvin").magnitude),
            standard_delta_g=self.standard_delta_gibbs_value(),
            tolerance_value=float(tolerance.to("joule / mole").magnitude),
        )

    def _check_quotient(self, log_quotient: float) -> float:
        quotient = float(np.exp(log_quotient))
        if not np.isfinite(log_quotient) or not np.isfinite(quotient) or quotient <= 0.0:
            raise ValueError(
                f"Dynamic thermodynamic constraint {self.constraint_id!r} "
                "produced a non-finite or non-positive reaction quotient."
            )
        return quotient

    def evaluate(
        self,
        state: Mapping[str, Quantity],
        *,
        rate_blocked: bool = False,
    ) -> DynamicThermodynamicEvaluation:
        """Evaluate activities, Q, delta G, and (in driving-force mode) the factor for one solver state."""

        constants = self._resolved()
        activities: dict[str, float] = {}
        log_quotient = 0.0
        for participant in self.participants:
            if participant.is_fixed:
                assert participant.fixed_activity is not None
                activity = float(participant.fixed_activity)
            else:
                if participant.state_name not in state:
                    raise ValueError(
                        f"Dynamic thermodynamic constraint {self.constraint_id!r} "
                        f"requires missing state {participant.state_name!r}."
                    )
                concentration = assert_compatible(
                    state[participant.state_name],
                    constants.standard_units,
                    name=participant.state_name,
                )
                concentration_value = float(concentration.magnitude)
                if not np.isfinite(concentration_value) or concentration_value < 0.0:
                    raise ValueError(
                        f"Dynamic thermodynamic state {participant.state_name!r} "
                        "must be a finite nonnegative concentration."
                    )
                activity = max(concentration_value / constants.standard_value, constants.floor_value)
            activities[participant.activity_key] = activity
            log_quotient += participant.signed_coefficient * float(np.log(activity))
        quotient = self._check_quotient(log_quotient)
        delta_g = constants.standard_delta_g + constants.rt * log_quotient
        factor = (
            driving_force_factor(delta_g, constants.rt)
            if self.enforcement_mode == ENFORCEMENT_DRIVING_FORCE
            else None
        )
        return DynamicThermodynamicEvaluation(
            constraint_id=self.constraint_id,
            process_id=self.process_id,
            reaction_id=self.reaction_id,
            activities=activities,
            log_reaction_quotient=log_quotient,
            reaction_quotient=quotient,
            standard_delta_gibbs=constants.standard_delta_g,
            delta_gibbs=delta_g,
            temperature_kelvin=constants.temperature_k,
            absolute_tolerance=constants.tolerance_value,
            favorable=delta_g < -constants.tolerance_value,
            rate_blocked=rate_blocked,
            driving_force_factor=factor,
        )

    def _compiled_participants(
        self,
        context: KernelContext,
        constants: _ResolvedConstants,
    ) -> tuple[list[tuple[str, int, float, float]], float]:
        """State participants as ``(name, index, unit factor, coefficient)`` plus the fixed ``ln Q`` offset."""

        participants: list[tuple[str, int, float, float]] = []
        fixed_log_quotient = 0.0
        for participant in self.participants:
            if participant.is_fixed:
                assert participant.fixed_activity is not None
                fixed_log_quotient += participant.signed_coefficient * float(
                    np.log(participant.fixed_activity)
                )
                continue
            if participant.state_name not in context.state_index:
                raise ValueError(
                    f"Dynamic thermodynamic constraint {self.constraint_id!r} "
                    f"requires missing state {participant.state_name!r}."
                )
            index, factor = context.state_slot(participant.state_name, constants.standard_units)
            participants.append(
                (participant.state_name, index, factor, float(participant.signed_coefficient))
            )
        return participants, fixed_log_quotient

    def _compiled_delta_gibbs(
        self,
        context: KernelContext,
    ) -> Callable[[np.ndarray], tuple[float, list[tuple[int, float, bool]]]]:
        """Closure returning ``dG`` and, per state participant, ``(index, coefficient / y, floor inactive)``."""

        constants = self._resolved()
        participants, fixed_log_quotient = self._compiled_participants(context, constants)
        constraint_id = self.constraint_id
        standard_value = constants.standard_value
        floor_value = constants.floor_value
        standard_delta_g = constants.standard_delta_g
        rt = constants.rt

        def delta_gibbs(state: np.ndarray) -> tuple[float, list[tuple[int, float, bool]]]:
            log_quotient = fixed_log_quotient
            terms: list[tuple[int, float, bool]] = []
            for name, index, factor, coefficient in participants:
                raw_value = float(state[index])
                concentration_value = raw_value * factor
                if not np.isfinite(concentration_value) or concentration_value < 0.0:
                    raise ValueError(
                        f"Dynamic thermodynamic state {name!r} "
                        "must be a finite nonnegative concentration."
                    )
                ratio = concentration_value / standard_value
                floor_inactive = ratio > floor_value
                activity = ratio if floor_inactive else floor_value
                log_quotient += coefficient * float(np.log(activity))
                terms.append((index, coefficient / raw_value if floor_inactive else 0.0, floor_inactive))
            quotient = float(np.exp(log_quotient))
            if not np.isfinite(log_quotient) or not np.isfinite(quotient) or quotient <= 0.0:
                raise ValueError(
                    f"Dynamic thermodynamic constraint {constraint_id!r} "
                    "produced a non-finite or non-positive reaction quotient."
                )
            return standard_delta_g + rt * log_quotient, terms

        return delta_gibbs

    def compile_feasibility(self, context: KernelContext) -> Callable[[np.ndarray], bool] | None:
        """Numeric favorability test over a state vector, mirroring :meth:`evaluate`.

        Block mode only: every constant is resolved once and the closure
        recomputes the state-dependent reaction quotient. Driving-force mode
        returns ``None`` because its enforcement is a continuous factor, not a
        feasibility gate; callers then use :meth:`enforce` or
        :meth:`compile_rate_factor`.
        """

        self.validate()
        if self.enforcement_mode == ENFORCEMENT_DRIVING_FORCE:
            return None
        delta_gibbs = self._compiled_delta_gibbs(context)
        tolerance_value = self._resolved().tolerance_value

        def favorable(state: np.ndarray) -> bool:
            return delta_gibbs(state)[0] < -tolerance_value

        return favorable

    def compile_rate_factor(
        self,
        context: KernelContext,
    ) -> Callable[[np.ndarray], tuple[float, np.ndarray | None]] | None:
        """Numeric multiplier ``phi`` on the forward rate and its state gradient.

        Block mode: ``phi`` is the indicator ``1[dG < -tol]`` and the gradient
        is ``None`` (the indicator is not differentiable). Driving-force mode:
        ``phi = 1 - exp(dG / (R T))`` with
        ``d phi / d y_k = -exp(dG / (R T)) nu_k / y_k`` where the activity floor
        is inactive, 0 where it is active, and 0 for fixed participants.
        """

        self.validate()
        delta_gibbs = self._compiled_delta_gibbs(context)
        constants = self._resolved()
        size = len(context.state_index)
        tolerance_value = constants.tolerance_value
        rt = constants.rt
        limit = DRIVING_FORCE_EXPONENT_LIMIT

        if self.enforcement_mode == ENFORCEMENT_BLOCK:

            def indicator(state: np.ndarray) -> tuple[float, np.ndarray | None]:
                return (1.0 if delta_gibbs(state)[0] < -tolerance_value else 0.0), None

            return indicator

        def factor(state: np.ndarray) -> tuple[float, np.ndarray | None]:
            delta_g, terms = delta_gibbs(state)
            exponent = delta_g / rt
            if not np.isfinite(exponent):
                raise ValueError("Thermodynamic driving force requires a finite dG / (R T).")
            if exponent > limit:
                raise ValueError(
                    f"Thermodynamic driving force exponent dG / (R T) = {exponent:.3g} "
                    f"exceeds {limit:g}; the factor is not representable."
                )
            exponential = float(np.exp(exponent))
            gradient = np.zeros(size, dtype=float)
            for index, inverse_term, floor_inactive in terms:
                if floor_inactive:
                    gradient[index] = -exponential * inverse_term
            return float(-np.expm1(exponent)), gradient

        return factor

    def enforce(
        self,
        rate: Quantity,
        state: Mapping[str, Quantity],
    ) -> tuple[Quantity, DynamicThermodynamicEvaluation]:
        """Couple a nonnegative forward rate to the dynamic Gibbs energy.

        Block mode returns the rate unchanged when favorable and zero
        otherwise. Driving-force mode returns ``rate * phi``; a negative result
        is reverse net flux and ``rate_blocked`` stays ``False``.
        """

        rate_values = np.asarray(rate.magnitude, dtype=float)
        if rate_values.ndim != 0 or not np.isfinite(rate_values).all():
            raise ValueError(
                "Dynamic thermodynamic enforcement requires a finite scalar process rate."
            )
        if float(rate_values) < 0.0:
            raise ValueError(
                "Dynamic thermodynamic enforcement supports nonnegative forward rates only."
            )
        evaluation = self.evaluate(state)
        if self.enforcement_mode == ENFORCEMENT_DRIVING_FORCE:
            assert evaluation.driving_force_factor is not None
            return rate * evaluation.driving_force_factor, evaluation
        if evaluation.favorable:
            return rate, evaluation
        blocked = self.evaluate(state, rate_blocked=True)
        return Q_(0.0, rate.units), blocked

    def assumptions(self) -> tuple[Assumption, ...]:
        """Explicit modelling assumptions of the configured enforcement mode."""

        records: list[Assumption] = []
        if self.enforcement_mode == ENFORCEMENT_DRIVING_FORCE:
            records.append(
                Assumption(
                    name=f"{self.constraint_id}.driving_force_flux_force",
                    description=(
                        "Net rate r_net = r_fwd * (1 - exp(dG / (R T))) with the "
                        "configured irreversible forward law as r_fwd; zero at "
                        "equilibrium, negative (reverse net flux) above it."
                    ),
                    justification=(
                        "One-way flux ratio J+/J- = exp(-dG / (R T)) for a dilute "
                        "process (Beard and Qian 2007); capacity x saturation x "
                        "(1 - exp(dG / (R T))) decomposition (Noor et al. 2013)."
                    ),
                    known_limitations=(
                        "reverse_saturation: not_represented. The reverse flux "
                        "inherits the forward law's saturation, so a saturable "
                        "forward law is not Haldane-consistent near and above "
                        "equilibrium. A forward law that vanishes at zero reactant "
                        "gives r_net = 0 there, so a reactant-free boundary state "
                        "is a fixed point. Ideal-dilute activities with an "
                        "explicit floor; no activity coefficients."
                    ),
                    source="; ".join(DRIVING_FORCE_PROVENANCE),
                )
            )
        else:
            records.append(
                Assumption(
                    name=f"{self.constraint_id}.block_unfavorable_forward_rate",
                    description=(
                        "Forward rate r = r_fwd * 1[dG < -absolute_tolerance]; "
                        "no reverse flux is represented."
                    ),
                    justification=(
                        "Legacy feasibility gate: a forward process cannot run "
                        "against its Gibbs energy."
                    ),
                    known_limitations=(
                        "reverse_flux: not_represented; reverse_saturation: "
                        "not_represented. A state above equilibrium is frozen "
                        "rather than relaxing back. The indicator is "
                        "discontinuous at dG = -absolute_tolerance. A positive "
                        "absolute_tolerance creates a dead zone: exergonic rates "
                        "with |dG| below the tolerance are blocked."
                    ),
                    source=None,
                )
            )
        if self.standard_enthalpy is None:
            records.append(
                Assumption(
                    name=f"{self.constraint_id}.standard_gibbs_temperature_dependence",
                    description=(
                        "none_declared: the declared standard Gibbs energy is used "
                        "unchanged at the constraint temperature."
                    ),
                    justification="No standard enthalpy or reference temperature was declared.",
                    known_limitations=(
                        "Temperature changes do not move the equilibrium constant."
                    ),
                    source=None,
                )
            )
        else:
            records.append(
                Assumption(
                    name=f"{self.constraint_id}.standard_gibbs_temperature_dependence",
                    description=(
                        "constant_enthalpy_gibbs_helmholtz: dG0(T) = dH0 - T (dH0 - "
                        "dG0(T_ref)) / T_ref."
                    ),
                    justification=(
                        "Gibbs-Helmholtz integration with a temperature-independent "
                        "reaction enthalpy (van 't Hoff form)."
                    ),
                    known_limitations=(
                        "Zero heat-capacity change; valid over modest temperature "
                        "ranges around the reference temperature only."
                    ),
                    source="; ".join(TEMPERATURE_DEPENDENCE_PROVENANCE),
                )
            )
        fixed = [participant for participant in self.participants if participant.is_fixed]
        if fixed:
            records.append(
                Assumption(
                    name=f"{self.constraint_id}.fixed_activity_participants",
                    description=(
                        "Participants with declared constant activity: "
                        + ", ".join(
                            f"{participant.species_id} = {participant.fixed_activity}"
                            for participant in fixed
                        )
                        + "."
                    ),
                    justification=(
                        "Declared standard-state convention for each fixed "
                        "participant (for example unit solvent activity)."
                    ),
                    known_limitations=(
                        "The fixed activity does not respond to the trajectory; "
                        "it is a convention, not a measurement of the run."
                    ),
                    source="; ".join(
                        str(participant.activity_source) for participant in fixed
                    ),
                )
            )
        return tuple(records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.constraint_id,
            "process_id": self.process_id,
            "reaction_id": self.reaction_id,
            "electron_balance_check_id": self.electron_balance_check_id,
            "enforcement_mode": self.enforcement_mode,
            "participants": [participant.to_dict() for participant in self.participants],
            "standard_energy_method": self.standard_energy_method,
            "standard_delta_gibbs": (
                None
                if self.standard_delta_gibbs is None
                else self.standard_delta_gibbs.to_dict()
            ),
            "standard_redox_potential": (
                None
                if self.standard_redox_potential is None
                else self.standard_redox_potential.to_dict()
            ),
            "electron_transfer_number": (
                None
                if self.electron_transfer_number is None
                else self.electron_transfer_number.to_dict()
            ),
            "faraday_constant": (
                None if self.faraday_constant is None else self.faraday_constant.to_dict()
            ),
            "standard_enthalpy": (
                None if self.standard_enthalpy is None else self.standard_enthalpy.to_dict()
            ),
            "reference_temperature": (
                None
                if self.reference_temperature is None
                else self.reference_temperature.to_dict()
            ),
            "temperature_dependence": self.temperature_dependence,
            "temperature": self.temperature.to_dict(),
            "gas_constant": self.gas_constant.to_dict(),
            "standard_concentration": self.standard_concentration.to_dict(),
            "minimum_activity": self.minimum_activity.to_dict(),
            "absolute_tolerance": self.absolute_tolerance.to_dict(),
            "provenance_refs": list(self.provenance_refs),
            "reverse_saturation": "not_represented",
            "maturity": (
                DRIVING_FORCE_MATURITY
                if self.enforcement_mode == ENFORCEMENT_DRIVING_FORCE
                else "software_tested_legacy_gate"
            ),
            "law_provenance": (
                list(DRIVING_FORCE_PROVENANCE)
                if self.enforcement_mode == ENFORCEMENT_DRIVING_FORCE
                else []
            )
            + (
                list(TEMPERATURE_DEPENDENCE_PROVENANCE)
                if self.standard_enthalpy is not None
                else []
            ),
            "assumptions": [assumption.to_dict() for assumption in self.assumptions()],
        }


def _finite_scalar(parameter: Parameter) -> float:
    quantity = parameter.quantity
    assert quantity is not None
    value = np.asarray(quantity.magnitude, dtype=float)
    if value.ndim != 0 or not np.isfinite(value).all():
        raise ValueError(f"Parameter {parameter.symbol!r} must be a finite scalar.")
    return float(value)


def _finite_value(parameter: Parameter, units: str) -> float:
    quantity = parameter.quantity
    assert quantity is not None
    value = float(
        assert_compatible(quantity, units, name=parameter.symbol).magnitude
    )
    if not np.isfinite(value):
        raise ValueError(f"Parameter {parameter.symbol!r} must be finite.")
    return value


def _positive_value(parameter: Parameter, units: str) -> float:
    value = _finite_value(parameter, units)
    if value <= 0.0:
        raise ValueError(f"Parameter {parameter.symbol!r} must be positive.")
    return value


def _nonnegative_value(parameter: Parameter, units: str) -> float:
    value = _finite_value(parameter, units)
    if value < 0.0:
        raise ValueError(f"Parameter {parameter.symbol!r} must be nonnegative.")
    return value


__all__ = [
    "ACTIVITY_BASIS_FIXED",
    "ACTIVITY_BASIS_STATE",
    "DRIVING_FORCE_EXPONENT_LIMIT",
    "DRIVING_FORCE_MATURITY",
    "DRIVING_FORCE_PROVENANCE",
    "DynamicActivityParticipant",
    "DynamicThermodynamicConstraint",
    "DynamicThermodynamicEvaluation",
    "ENFORCEMENT_BLOCK",
    "ENFORCEMENT_DRIVING_FORCE",
    "ENFORCEMENT_MODES",
    "GibbsFreeEnergyEstimate",
    "TEMPERATURE_DEPENDENCE_CONSTANT_ENTHALPY",
    "TEMPERATURE_DEPENDENCE_NONE",
    "TEMPERATURE_DEPENDENCE_PROVENANCE",
    "driving_force_factor",
]
