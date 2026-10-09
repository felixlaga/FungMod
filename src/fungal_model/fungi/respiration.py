"""Conserved growth and non-growth-associated substrate respiration.

This opt-in physiology layer separates Pirt maintenance from biomass death.
The true yield and maintenance demand are supplied, never inferred from
thermodynamics. Each pathway is solved by element and charge conservation.
Kinetic limitation/priority in ``ResourceLimitedCulture`` is an explicit
exploratory closure, not a claim about fungal regulation or starvation survival.

References: Pirt (1965), doi:10.1098/rspb.1965.0069; Monod (1949),
doi:10.1146/annurev.mi.03.100149.002103. The particular multiplicative resource
and maintenance-first allocation below is a model assumption, not their data.
All amounts use moles of the caller's empirical species formula (e.g. one
carbon mole for biomass whose formula contains one carbon atom).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np

from fungal_model.chemistry.macrochemistry import MacrochemicalBalance, MacrochemicalSolution
from fungal_model.core.numerics import IntegrationError, SolverSettings, solve_checked
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.processes.base import Process
from fungal_model.processes.culture import (
    DilutionExchangeProcess,
    GasTransferProcess,
    ResourceLimitedGrowthProcess,
    ResourceLimitedMaintenanceProcess,
)

RESPIRATION_MATURITY = "exploratory_software_tested"
RATE_UNITS = "1 / hour"
CONCENTRATION_UNITS = "mole / liter"
TIME_UNITS = "hour"
NATIVE_ENGINE = "native_right_hand_side"
COMPILED_ENGINE = "compiled_process_core"
FEED_SYMBOL_PREFIX = "feed:"


def _number(value: Quantity, units: str, name: str, *, positive: bool = False) -> float:
    array = np.asarray(assert_compatible(require_quantity(value, name=name), units, name=name).magnitude)
    if array.ndim or not np.isfinite(array) or (array <= 0 if positive else array < 0):
        raise ValueError(f"{name} must be a finite {'positive' if positive else 'nonnegative'} scalar.")
    return float(array)


def _parameter(value: Parameter, units: str, *, positive: bool = False) -> float:
    value.validate_provenance()
    value.validate_value()
    assert value.quantity is not None
    return _number(value.quantity, units, value.symbol, positive=positive)


def _time_grid(times: Quantity) -> np.ndarray:
    grid = np.asarray(assert_compatible(require_quantity(times, name="times"), TIME_UNITS).magnitude, dtype=float)
    if grid.ndim != 1 or grid.size < 2 or not np.isfinite(grid).all() or np.any(np.diff(grid) <= 0):
        raise ValueError("At least two finite strictly increasing times are required.")
    return grid


def _dynamic_stoichiometry(coefficients: Mapping[str, float], pools: Sequence[str]) -> dict[str, float]:
    """Coefficients of one pathway restricted to the dynamic pools; exact zeros are dropped.

    Reservoir species are not model states: their exchanges are reconstructed
    from the integrated extents by the trajectory, exactly as ``simulate`` does.
    """
    return {name: float(coefficients[name]) for name in pools if float(coefficients.get(name, 0.0)) != 0.0}


def _parameter_set(parameters: Iterable[Parameter], *, owner: str) -> ParameterSet:
    collected = ParameterSet()
    for parameter in parameters:
        if parameter.symbol in collected:
            raise ValueError(f"{owner}: parameter symbol {parameter.symbol!r} is used twice; "
                             "the compiled representation needs one symbol per parameter.")
        collected.add(parameter)
    return collected


def _run_compiled(processes: Sequence[Process], parameters: ParameterSet, *, pools: Mapping[str, float],
                  ledgers: Sequence[str], grid: np.ndarray, settings: SolverSettings,
                  name: str) -> tuple[np.ndarray, dict[str, Any]]:
    """Integrate ``processes`` on the compiled process core from zero ledgers.

    Returns the trajectory (states x times) in ``(*pools, *ledgers)`` order and
    the diagnostics the native path records (``nfev``, ``jacobian``) plus the
    engine and the kernel summary of the compiled model.
    """
    from fungal_model.processes.assembly import ModelBuilder
    from fungal_model.processes.registry import ProcessRegistry
    from fungal_model.solvers.process_ode import ProcessODESolver, RunRequest

    model = ModelBuilder(process_library=ProcessRegistry(processes), requested_processes=tuple(p.name for p in processes),
                         parameters=parameters, solver_settings=settings).assemble()
    names = (*pools, *ledgers)
    initial = {n: Q_(v, CONCENTRATION_UNITS) for n, v in pools.items()}
    initial.update({n: Q_(0.0, CONCENTRATION_UNITS) for n in ledgers})
    result = ProcessODESolver(model).run(RunRequest(
        initial_state=initial, t_span=(Q_(float(grid[0]), TIME_UNITS), Q_(float(grid[-1]), TIME_UNITS)),
        t_eval=Q_(grid, TIME_UNITS), name=name, label="exploratory"))
    kernel = dict(result.solver_metadata["kernel"])
    values = np.vstack([np.asarray(result.states[n].to(CONCENTRATION_UNITS).magnitude, dtype=float) for n in names])
    return values, {"nfev": int(result.solver_metadata["nfev"]), "jacobian": str(kernel["jacobian"]),
                    "engine": COMPILED_ENGINE, "kernel": kernel}


@dataclass(frozen=True)
class RespiratoryGrowthModel:
    """Two balanced pathways, normalized to one biomass or one substrate mole.

    ``true_yield`` is mol biomass formula / mol substrate, not necessarily a
    mass fraction and not restricted to <= 1. ``maintenance_demand`` is mol
    substrate / (mol biomass formula * time). Names carry the chemical basis
    that ordinary SI mole units alone cannot distinguish.
    """

    balance: MacrochemicalBalance
    substrate: str
    biomass: str
    true_yield: Parameter
    maintenance_demand: Parameter
    source: str
    maturity: str = RESPIRATION_MATURITY
    growth_reaction: MacrochemicalSolution = field(init=False)
    maintenance_reaction: MacrochemicalSolution = field(init=False)

    def __post_init__(self) -> None:
        if not has_text(self.source):
            raise ProvenanceError("Respiratory growth requires an explicit mechanism/assumption source.")
        if self.maturity != RESPIRATION_MATURITY:
            raise ValueError(f"Respiration maturity must be {RESPIRATION_MATURITY!r}.")
        if self.substrate == self.biomass:
            raise ValueError("Substrate and biomass must be distinct species.")
        yield_value = _parameter(self.true_yield, "dimensionless", positive=True)
        _parameter(self.maintenance_demand, RATE_UNITS)
        growth = self.balance.solve({self.substrate: -1 / yield_value, self.biomass: 1})
        maintenance = self.balance.solve({self.substrate: -1, self.biomass: 0})
        object.__setattr__(self, "growth_reaction", growth)
        object.__setattr__(self, "maintenance_reaction", maintenance)

    def specific_exchange(self, growth_rate: Quantity, *, maintenance_rate: Quantity | None = None) -> dict[str, Quantity]:
        """Signed mol species / (mol biomass * hour); negative means uptake.

        Default maintenance assumes substrate/oxidant sufficiency. A caller may
        explicitly supply a realized maintenance flux for resource limitation.
        Neither invocation estimates a growth rate or a maintenance parameter.
        """
        mu = _number(growth_rate, RATE_UNITS, "growth_rate")
        demand = _parameter(self.maintenance_demand, RATE_UNITS)
        maintenance = (demand if maintenance_rate is None
                       else _number(maintenance_rate, RATE_UNITS, "maintenance_rate"))
        if maintenance > demand:
            raise ValueError("Realized maintenance cannot exceed the configured maintenance demand.")
        return {name: Q_(mu * value + maintenance * self.maintenance_reaction.coefficients[name], RATE_UNITS)
                for name, value in self.growth_reaction.coefficients.items()}

    def entropy_production(self, *, growth_extent_rate: Quantity, maintenance_extent_rate: Quantity,
                           temperature: Quantity) -> Quantity:
        """Require complete sourced formation energies and reject uphill pathways.

        Uses the balance's declared conditions; no activity correction is
        inferred. Returns the sum of pathway entropy production. Heat requires
        the separate MacrochemicalSolution.entropy_budget API and enthalpies.
        """
        total: Quantity | None = None
        for reaction, rate in ((self.growth_reaction, growth_extent_rate),
                               (self.maintenance_reaction, maintenance_extent_rate)):
            quantity = require_quantity(rate, name="extent_rate")
            if np.asarray(quantity.magnitude).ndim or not np.isfinite(quantity.magnitude) or quantity.magnitude < 0:
                raise ValueError("Pathway extent rates must be finite nonnegative scalars.")
            budget = reaction.entropy_budget(extent_rate=quantity, temperature=temperature, include_heat=False)
            if not budget.is_second_law_consistent:
                raise ValueError("A configured forward pathway would produce negative entropy.")
            total = budget.entropy_production_rate if total is None else cast(Quantity, total + budget.entropy_production_rate)
        assert total is not None
        return total

    def to_dict(self) -> dict[str, Any]:
        return {"maturity": self.maturity, "source": self.source, "balance": self.balance.to_dict(),
                "substrate": self.substrate, "biomass": self.biomass,
                "true_yield": self.true_yield.to_dict(), "maintenance_demand": self.maintenance_demand.to_dict(),
                "growth_coefficients": dict(self.growth_reaction.coefficients),
                "maintenance_coefficients": dict(self.maintenance_reaction.coefficients),
                "claim_boundary": "Conserved supplied-yield growth and respiration, not a whole-organism model."}


@dataclass(frozen=True)
class CultureTrajectory:
    time: Quantity
    concentrations: dict[str, Quantity]
    specific_growth_rate: Quantity
    specific_maintenance_rate: Quantity
    unmet_maintenance_rate: Quantity
    cumulative_reaction_exchange: dict[str, Quantity]
    cumulative_boundary_exchange: dict[str, Quantity]
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ResourceLimitedCulture:
    """Well-mixed batch/chemostat with substrate, nitrogen and oxidant limitation.

    Capacity = q_max S/(K_S+S) O/(K_O+O). Maintenance consumes min(capacity,m).
    Growth = Y max(capacity-m,0) N/(K_N+N); unused capacity is not consumed.
    No death, storage, secretion, intracellular regulation, or pH solver exists.
    Unmet maintenance is explicitly reported and does not silently become death.

    Every species outside the four dynamic pools must be explicitly assigned
    to a reservoir: e.g. CO2 export, water solvent and buffered protons. Their
    signed exchanges close the matter/charge ledger; their concentrations and
    activities are not predictions. No external source supplies biomass.

    The same closure is available as generic processes (``compiled_processes``
    and ``compiled_parameters``) that ``simulate_compiled`` integrates on the
    compiled process core; ``simulate`` keeps the native right-hand side with
    its analytic piecewise Jacobian. Both return the same trajectory type and
    are tested for parity.
    """

    metabolism: RespiratoryGrowthModel
    nitrogen: str
    oxidant: str
    reservoir_species: tuple[str, ...]
    uptake_capacity: Parameter
    substrate_half_saturation: Parameter
    nitrogen_half_saturation: Parameter
    oxidant_half_saturation: Parameter
    dilution_rate: Parameter
    gas_transfer_rate: Parameter
    oxidant_saturation: Parameter
    feed: Mapping[str, Quantity]
    source: str

    @property
    def names(self) -> tuple[str, ...]:
        return (self.metabolism.substrate, self.metabolism.biomass, self.nitrogen, self.oxidant)

    def __post_init__(self) -> None:
        if not has_text(self.source):
            raise ProvenanceError("Resource limitation and reservoir assumptions require a source.")
        if len(set(self.names)) != 4:
            raise ValueError("Four distinct dynamic species are required.")
        all_names = set(self.metabolism.growth_reaction.coefficients)
        if not set(self.names) <= all_names:
            raise ValueError("Dynamic species must exist in the macrochemical balance.")
        if (len(set(self.reservoir_species)) != len(self.reservoir_species)
                or set(self.reservoir_species) != all_names - set(self.names)):
            raise ValueError("reservoir_species must exactly cover all non-dynamic species.")
        if set(self.feed) != {self.metabolism.substrate, self.nitrogen, self.oxidant}:
            raise ValueError("Feed must explicitly specify substrate, nitrogen and oxidant concentrations.")
        for name, value in self.feed.items():
            _number(value, CONCENTRATION_UNITS, f"feed[{name}]")
        for parameter, units, positive in (
            (self.uptake_capacity, RATE_UNITS, True),
            (self.substrate_half_saturation, CONCENTRATION_UNITS, True),
            (self.nitrogen_half_saturation, CONCENTRATION_UNITS, True),
            (self.oxidant_half_saturation, CONCENTRATION_UNITS, True),
            (self.dilution_rate, RATE_UNITS, False), (self.gas_transfer_rate, RATE_UNITS, False),
            (self.oxidant_saturation, CONCENTRATION_UNITS, False),
        ):
            _parameter(parameter, units, positive=positive)
        growth, maintenance = self.metabolism.growth_reaction.coefficients, self.metabolism.maintenance_reaction.coefficients
        if growth[self.nitrogen] >= 0 or abs(maintenance[self.nitrogen]) > 1e-12:
            raise ValueError("This closure requires nitrogen-consuming growth and nitrogen-free maintenance.")
        if growth[self.oxidant] >= 0 or maintenance[self.oxidant] >= 0:
            raise ValueError("Both configured pathways must consume the limiting oxidant.")

    def _constants(self) -> tuple[float, ...]:
        return (_parameter(self.metabolism.true_yield, "dimensionless", positive=True),
                _parameter(self.metabolism.maintenance_demand, RATE_UNITS),
                _parameter(self.uptake_capacity, RATE_UNITS, positive=True),
                _parameter(self.substrate_half_saturation, CONCENTRATION_UNITS, positive=True),
                _parameter(self.nitrogen_half_saturation, CONCENTRATION_UNITS, positive=True),
                _parameter(self.oxidant_half_saturation, CONCENTRATION_UNITS, positive=True))

    @staticmethod
    def _rates(state: np.ndarray, constants: tuple[float, ...]) -> tuple[float, float, float]:
        # Zero extension of the constitutive law for negative solver trial
        # iterates; returned trajectories are checked and NEVER clipped.
        substrate, _, nitrogen, oxidant = np.maximum(state[:4], 0)
        yield_value, demand, capacity, ks, kn, ko = constants
        available = capacity * substrate / (ks + substrate) * oxidant / (ko + oxidant)
        maintenance = min(demand, available)
        growth = yield_value * max(available - demand, 0) * nitrogen / (kn + nitrogen)
        return growth, maintenance, demand - maintenance

    @staticmethod
    def _rate_jacobian(state: np.ndarray, constants: tuple[float, ...]) -> np.ndarray:
        """Piecewise derivatives of the closure, including its zero extension.

        At zero pools the right derivative is used. At capacity == demand,
        growth/maintenance select zero derivatives; the closure has a kink.
        """
        substrate, _, nitrogen, oxidant = np.maximum(state[:4], 0)
        yield_value, demand, capacity, ks, kn, ko = constants
        available = capacity * substrate / (ks+substrate) * oxidant / (ko+oxidant)
        derivative = np.zeros(4)
        derivative[0] = capacity * ks / (ks+substrate)**2 * oxidant / (ko+oxidant) * (state[0] >= 0)
        derivative[3] = capacity * substrate / (ks+substrate) * ko / (ko+oxidant)**2 * (state[3] >= 0)
        growth = yield_value * nitrogen / (kn+nitrogen) * derivative * (available > demand)
        growth[2] += yield_value * max(available-demand, 0) * kn / (kn+nitrogen)**2 * (state[2] >= 0)
        maintenance = derivative * (available < demand)
        return np.array([growth, maintenance, -maintenance])

    def rates(self, concentrations: Mapping[str, Quantity]) -> dict[str, Quantity]:
        if set(concentrations) != set(self.names):
            raise ValueError("Concentrations must exactly cover the four dynamic species.")
        state = np.array([_number(concentrations[n], CONCENTRATION_UNITS, n) for n in self.names])
        growth, maintenance, unmet = self._rates(state, self._constants())
        return {"growth": Q_(growth, RATE_UNITS), "maintenance": Q_(maintenance, RATE_UNITS),
                "unmet_maintenance": Q_(unmet, RATE_UNITS)}

    def _ledger_names(self) -> tuple[str, ...]:
        names = (*self.names, "extent:growth", "extent:maintenance", *(f"boundary:{n}" for n in self.names))
        if len(set(names)) != len(names):
            raise ValueError("Species names collide with reserved ledger names.")
        return names

    def _closure_kwargs(self) -> dict[str, Any]:
        """Pool names, units and parameter symbols shared by the closure processes."""
        return {"substrate_state": self.metabolism.substrate, "biomass_state": self.metabolism.biomass,
                "nutrient_state": self.nitrogen, "oxidant_state": self.oxidant,
                "concentration_units": CONCENTRATION_UNITS, "time_units": TIME_UNITS,
                "true_yield_symbol": self.metabolism.true_yield.symbol,
                "maintenance_demand_symbol": self.metabolism.maintenance_demand.symbol,
                "uptake_capacity_symbol": self.uptake_capacity.symbol,
                "substrate_half_saturation_symbol": self.substrate_half_saturation.symbol,
                "nutrient_half_saturation_symbol": self.nitrogen_half_saturation.symbol,
                "oxidant_half_saturation_symbol": self.oxidant_half_saturation.symbol}

    def _closure_parameters(self) -> tuple[Parameter, ...]:
        return (self.metabolism.true_yield, self.metabolism.maintenance_demand, self.uptake_capacity,
                self.substrate_half_saturation, self.nitrogen_half_saturation, self.oxidant_half_saturation)

    def _exchange_processes(self, pools: Sequence[str]) -> tuple[Process, ...]:
        """Dilution of every pool against its feed symbol and gas transfer into the oxidant, with boundary ledgers."""
        processes: list[Process] = [DilutionExchangeProcess(
            name=f"dilution:{n}", pool_state=n, concentration_units=CONCENTRATION_UNITS, time_units=TIME_UNITS,
            dilution_rate_symbol=self.dilution_rate.symbol, feed_symbol=f"{FEED_SYMBOL_PREFIX}{n}",
            ledger_state=f"boundary:{n}", source=self.source,
            notes="Every pool of the well-mixed culture leaves with the effluent and enters with its declared feed.")
            for n in pools]
        processes.append(GasTransferProcess(
            name=f"gas_transfer:{self.oxidant}", pool_state=self.oxidant, concentration_units=CONCENTRATION_UNITS,
            time_units=TIME_UNITS, transfer_rate_symbol=self.gas_transfer_rate.symbol,
            saturation_symbol=self.oxidant_saturation.symbol, ledger_state=f"boundary:{self.oxidant}",
            source=self.source, notes="Gas transfer into the dissolved oxidant shares the oxidant's boundary ledger with its dilution."))
        return tuple(processes)

    def _exchange_parameters(self, feed: Mapping[str, Quantity | None]) -> tuple[Parameter, ...]:
        """The exchange constants plus one feed parameter per pool (``None``: no external supply)."""
        declared = []
        for name, quantity in feed.items():
            if quantity is None:
                value = 0.0
                note = "No external supply of this pool: it only leaves with the effluent (assumption of the class)."
            else:
                value = _number(quantity, CONCENTRATION_UNITS, f"feed[{name}]")
                note = "Feed concentration declared by the caller, restated as a parameter for the compiled representation."
            declared.append(Parameter(f"feed concentration of {name}", f"{FEED_SYMBOL_PREFIX}{name}",
                                      Q_(value, CONCENTRATION_UNITS), CONCENTRATION_UNITS, None, self.source, "high", note))
        return (self.dilution_rate, self.gas_transfer_rate, self.oxidant_saturation, *declared)

    def compiled_processes(self) -> tuple[Process, ...]:
        """The closure as generic processes: growth, maintenance, dilution of every pool, gas transfer.

        Growth and maintenance carry the dynamic-pool stoichiometry of the
        solved macrochemical pathways and an extent ledger each; every exchange
        process carries a boundary ledger, so the compiled run integrates the
        same 10 states as ``simulate``.
        """
        kwargs = self._closure_kwargs()
        growth = ResourceLimitedGrowthProcess(
            name="growth", stoichiometry=_dynamic_stoichiometry(self.metabolism.growth_reaction.coefficients, self.names),
            extent_state="extent:growth", source=self.source,
            notes="Biomass-forming extent of the solved growth pathway; reservoir species are ledgered, not integrated.", **kwargs)
        maintenance = ResourceLimitedMaintenanceProcess(
            name="maintenance",
            stoichiometry=_dynamic_stoichiometry(self.metabolism.maintenance_reaction.coefficients, self.names),
            extent_state="extent:maintenance", source=self.source,
            notes="Maintenance extent of the solved maintenance pathway; unmet demand is reported, not consumed.", **kwargs)
        return (growth, maintenance, *self._exchange_processes(self.names))

    def compiled_parameters(self) -> ParameterSet:
        """The class's own parameters plus one feed parameter per pool, keyed by their symbols."""
        feed: dict[str, Quantity | None] = {n: None if n == self.metabolism.biomass else self.feed[n] for n in self.names}
        return _parameter_set((*self._closure_parameters(), *self._exchange_parameters(feed)), owner=type(self).__name__)

    def simulate(self, *, initial_state: Mapping[str, Quantity], times: Quantity,
                 solver_settings: SolverSettings | None = None) -> CultureTrajectory:
        """Integrate the native right-hand side with its analytic piecewise Jacobian."""
        self.rates(initial_state)  # Validate every initial value and name.
        grid = _time_grid(times)
        settings = solver_settings or SolverSettings()
        initial = np.array([_number(initial_state[n], CONCENTRATION_UNITS, n) for n in self.names])
        values, diagnostics = self._integrate_native(grid, initial, settings)
        return self._trajectory(grid, values, initial, settings, diagnostics)

    def simulate_compiled(self, *, initial_state: Mapping[str, Quantity], times: Quantity,
                          solver_settings: SolverSettings | None = None) -> CultureTrajectory:
        """Integrate ``compiled_processes`` on the compiled process core; same trajectory type as ``simulate``."""
        self.rates(initial_state)
        grid = _time_grid(times)
        settings = solver_settings or SolverSettings()
        initial = np.array([_number(initial_state[n], CONCENTRATION_UNITS, n) for n in self.names])
        names = self._ledger_names()
        values, diagnostics = _run_compiled(self.compiled_processes(), self.compiled_parameters(),
                                            pools=dict(zip(self.names, initial.tolist(), strict=True)),
                                            ledgers=names[len(self.names):], grid=grid, settings=settings,
                                            name="resource_limited_culture")
        return self._trajectory(grid, values, initial, settings, diagnostics)

    def _integrate_native(self, grid: np.ndarray, initial: np.ndarray,
                          settings: SolverSettings) -> tuple[np.ndarray, dict[str, Any]]:
        constants = self._constants()
        growth = np.array([self.metabolism.growth_reaction.coefficients[n] for n in self.names])
        maintenance = np.array([self.metabolism.maintenance_reaction.coefficients[n] for n in self.names])
        dilution = _parameter(self.dilution_rate, RATE_UNITS)
        transfer = _parameter(self.gas_transfer_rate, RATE_UNITS)
        saturation = _parameter(self.oxidant_saturation, CONCENTRATION_UNITS)
        feed = np.array([0. if n == self.metabolism.biomass else
                         _number(self.feed[n], CONCENTRATION_UNITS, n) for n in self.names])
        # Separate integrated boundary flows and reaction extents provide an
        # open-system conservation check, including exported reservoir species.
        units = dict.fromkeys(self._ledger_names(), CONCENTRATION_UNITS)

        def rhs(_time, state):
            mu, m, _ = self._rates(state, constants)
            extents = max(state[1], 0) * np.array([mu, m])
            boundary = dilution * (feed - state[:4])
            boundary[3] += transfer * (saturation - state[3])
            return np.r_[growth * extents[0] + maintenance * extents[1] + boundary, extents, boundary]

        boundary_jacobian = -dilution*np.eye(4)
        boundary_jacobian[3, 3] -= transfer

        def jacobian(_time, state):
            mu, m, _ = self._rates(state, constants)
            flux_jacobian = self._rate_jacobian(state, constants)[:2] * max(state[1], 0)
            flux_jacobian[:, 1] += np.array([mu, m]) * (state[1] >= 0)
            matrix = np.zeros((10, 10))
            matrix[:4, :4] = np.column_stack((growth, maintenance)) @ flux_jacobian + boundary_jacobian
            matrix[4:6, :4] = flux_jacobian
            matrix[6:, :4] = boundary_jacobian
            return matrix

        options = settings.scipy_options(units, time_units=TIME_UNITS)
        if settings.method in {"BDF", "Radau", "LSODA"}:
            options["jac"] = jacobian
        result = solve_checked(rhs, (grid[0], grid[-1]), np.r_[initial, np.zeros(6)], t_eval=grid,
                               **options)
        return result.y, {"nfev": int(result.nfev),
                          "jacobian": "analytic piecewise" if "jac" in options else "unused by explicit method",
                          "engine": NATIVE_ENGINE}

    def _trajectory(self, grid: np.ndarray, values: np.ndarray, initial: np.ndarray, settings: SolverSettings,
                    diagnostics: Mapping[str, Any]) -> CultureTrajectory:
        constants = self._constants()
        units = dict.fromkeys(self._ledger_names(), CONCENTRATION_UNITS)
        atol = np.broadcast_to(settings.absolute_tolerances(units), (len(units),))
        if np.any(values[:4] < -10 * atol[:4, None]):
            raise IntegrationError("Culture integration returned a negative pool beyond 10 absolute tolerances.")
        reaction = {n: self.metabolism.growth_reaction.coefficients[n] * values[4]
                    + self.metabolism.maintenance_reaction.coefficients[n] * values[5]
                    for n in self.metabolism.growth_reaction.coefficients}
        boundary = {n: values[6 + i] for i, n in enumerate(self.names)}
        # Reservoir output leaves the culture; reaction production is positive.
        boundary.update({n: -reaction[n] for n in self.reservoir_species})
        net_material = np.array([values[self.names.index(s.name)] - initial[self.names.index(s.name)] - boundary[s.name]
                                 if s.name in self.names else -boundary[s.name]
                                 for s in self.metabolism.balance.species])
        labels, matrix = self.metabolism.balance.conservation_matrix()
        residuals = matrix @ net_material
        rates = np.array([self._rates(v, constants) for v in values.T]).T
        return CultureTrajectory(
            Q_(grid, "hour"), {n: Q_(values[i], CONCENTRATION_UNITS) for i, n in enumerate(self.names)},
            Q_(rates[0], RATE_UNITS), Q_(rates[1], RATE_UNITS), Q_(rates[2], RATE_UNITS),
            {n: Q_(v, CONCENTRATION_UNITS) for n, v in reaction.items()},
            {n: Q_(v, CONCENTRATION_UNITS) for n, v in boundary.items()},
            {"maximum_absolute_balance_residual_mol_L": {n: float(np.max(np.abs(v)))
                for n, v in zip(labels, residuals, strict=True)}, "minimum_dynamic_pool_mol_L": float(np.min(values[:4])),
             "maximum_unmet_maintenance_per_h": float(np.max(rates[2])), **dict(diagnostics),
             "solver_settings": settings.to_dict(), "empirical_validation": False},
            self.to_dict(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"metabolism": self.metabolism.to_dict(), "source": self.source, "nitrogen": self.nitrogen,
                "oxidant": self.oxidant, "reservoir_species": list(self.reservoir_species),
                "parameters": {n: getattr(self, n).to_dict() for n in (
                    "uptake_capacity", "substrate_half_saturation", "nitrogen_half_saturation",
                    "oxidant_half_saturation", "dilution_rate", "gas_transfer_rate", "oxidant_saturation")},
                "feed": {n: {"value": float(v.to(CONCENTRATION_UNITS).magnitude), "units": CONCENTRATION_UNITS}
                         for n, v in self.feed.items()},
                "claim_boundary": "Exploratory single-substrate well-mixed physiology; no morphology, death, "
                    "regulation, secretion, intracellular energetics, or empirical kinetic validation. "
                    "Unmet maintenance is a missing-physiology diagnostic, not predicted viability."}


__all__ = ["RESPIRATION_MATURITY", "COMPILED_ENGINE", "NATIVE_ENGINE", "RespiratoryGrowthModel",
           "ResourceLimitedCulture", "CultureTrajectory"]
