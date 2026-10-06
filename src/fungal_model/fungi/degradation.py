"""Conserved extracellular digestion coupled to resource-limited physiology.

The closure is explicit: after maintenance, a supplied fraction of assimilated
substrate is allocated to secretion and the rest to biomass synthesis. This is
an exploratory allocation hypothesis, not an inferred gene-regulatory network.
Protein formation, extracellular hydrolysis and enzyme inactivation all carry
chemical stoichiometry; no enzyme/activity/mass conversion is implicit.

Biological motivation: Jorgensen et al. (2009), doi:10.1186/1471-2164-10-44,
and Pakula et al. (2016), doi:10.1186/s13068-016-0547-5. These studies do not
validate this complete dynamic closure or supply arbitrary missing parameters.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.chemistry.macrochemistry import MacrochemicalBalance, MacrochemicalSolution, MacrochemicalSpecies
from fungal_model.core.numerics import IntegrationError, SolverSettings, solve_checked
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity
from fungal_model.fungi.respiration import (
    CONCENTRATION_UNITS,
    NATIVE_ENGINE,
    RATE_UNITS,
    TIME_UNITS,
    ResourceLimitedCulture,
    _dynamic_stoichiometry,
    _number,
    _parameter,
    _parameter_set,
    _run_compiled,
    _time_grid,
)
from fungal_model.processes.base import Process
from fungal_model.processes.culture import (
    CostedSecretionProcess,
    ResourceLimitedGrowthProcess,
    ResourceLimitedMaintenanceProcess,
)
from fungal_model.processes.homogeneous import HomogeneousMichaelisMentenProcess, MassActionProcess

DEGRADING_CULTURE_MATURITY = "exploratory_software_tested"
SECRETION_YIELD_SYMBOL = "secretion_yield"
EXTENT_RATE_UNITS = f"({CONCENTRATION_UNITS}) / ({TIME_UNITS})"


def secretion_allocation(*, protein_per_biomass: Parameter, biomass_formula_mass: Parameter,
                         protein_formula_mass: Parameter, growth_yield: Parameter,
                         secretion_yield: Parameter) -> Parameter:
    """Convert an explicit g-protein/g-new-biomass ratio to a substrate share.

    This conversion is conditional on both synthesis yields and formula masses.
    The ratio must describe the synthesized protein represented by the enzyme
    pool. Measured total extracellular protein cannot be substituted without
    resolving active fraction, composition, losses and observation mapping.
    The returned allocation uncertainty remains unknown; none is manufactured.
    """
    ratio = _parameter(protein_per_biomass, "dimensionless")
    mx = _parameter(biomass_formula_mass, "g/mol", positive=True)
    me = _parameter(protein_formula_mass, "g/mol", positive=True)
    yx = _parameter(growth_yield, "dimensionless", positive=True)
    ye = _parameter(secretion_yield, "dimensionless", positive=True)
    molar_ratio = ratio * mx / me
    fraction = molar_ratio / (ye / yx + molar_ratio)
    return Parameter("fraction of post-maintenance substrate allocated to secretion", "f_secretion", fraction,
        "dimensionless", None, "; ".join(str(p.source) for p in (protein_per_biomass, biomass_formula_mass,
            protein_formula_mass, growth_yield, secretion_yield)), "low",
        "Conditional conversion f = (r M_X/M_E)/(Y_E/Y_X + r M_X/M_E). "
        "Requires the represented synthesized-protein ratio; total measured protein needs an explicit observation mapping. "
        "Does not identify yields, enzyme composition, activity or a regulatory mechanism.")


@dataclass(frozen=True)
class DegradingCultureTrajectory:
    time: Quantity
    concentrations: dict[str, Quantity]
    process_rates: dict[str, Quantity]
    cumulative_reaction_exchange: dict[str, Quantity]
    cumulative_boundary_exchange: dict[str, Quantity]
    unmet_maintenance_rate: Quantity
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]

    def batch_degradation(self, substrate: str, *, fractions: tuple[float, ...] = (.5, .9)) -> dict[str, Any]:
        """Net batch substrate loss and grid-interpolated threshold times.

        Rejects a flowing culture: concentration loss through dilution is not
        enzymatic degradation. No threshold outside the simulated span is guessed.
        """
        if self.diagnostics["dilution_rate_per_h"] != 0:
            raise ValueError("Batch degradation summaries require zero dilution.")
        if substrate != self.provenance["degradable_substrate"]:
            raise ValueError("A degradation summary must name the configured degradable substrate.")
        values = np.asarray(self.concentrations[substrate].to(CONCENTRATION_UNITS).magnitude)
        if values[0] <= 0:
            raise ValueError("A positive initial degradable substrate is required.")
        removed = 1 - values / values[0]
        if any(not np.isfinite(f) or not 0 < f <= 1 for f in fractions) or len(set(fractions)) != len(fractions):
            raise ValueError("Threshold fractions must be distinct and in (0, 1].")
        times = np.asarray(self.time.to("hour").magnitude)
        thresholds: dict[str, float | None] = {}
        for f in fractions:
            indices = np.flatnonzero(removed >= f)
            value = None
            if indices.size:
                i = int(indices[0])
                value = float(times[i-1] + (times[i]-times[i-1]) * (f-removed[i-1]) / (removed[i]-removed[i-1]))
            thresholds[str(f)] = value
        return {"final_fraction_removed": float(removed[-1]), "threshold_times_hour": thresholds,
                "threshold_method": "First crossing, linear interpolation of the requested output grid; not an event solve.",
                "maximum_output_step_hour": float(np.diff(times).max()),
                "unreached_thresholds": "null means not reached during this simulation, not infinite degradation time."}


@dataclass(frozen=True)
class DegradingCulture:
    """One shared material budget for digestion, secretion, growth and respiration.

    Hydrolysis must consume only the declared substrate and explicit reservoirs,
    and produce only the assimilable product and reservoirs. It is catalysed by
    the active extracellular enzyme pool. Inactivation moves that pool to an
    explicitly declared, chemically identical inactive pool: material never
    disappears. No proteolysis/recycling, starvation death, hyphae or pellets
    are inferred. Substrate accessibility is the caller's effective saturation
    law, not a geometric model of an insoluble surface.

    The secretion reaction is normalized to one mole of the declared protein
    formula. All kinetics and allocation parameters must be explicit and sourced.
    Extracellular pools follow the same dilution as the well-mixed culture;
    attached/retained solids are outside this model's scope.

    ``compiled_processes`` and ``compiled_parameters`` express the five
    pathways and the boundary exchanges as generic processes, which
    ``simulate_compiled`` integrates on the compiled process core; ``simulate``
    keeps the native right-hand side with its analytic piecewise Jacobian.
    """

    culture: ResourceLimitedCulture
    degradable_substrate: MacrochemicalSpecies
    active_enzyme: MacrochemicalSpecies
    inactive_enzyme: MacrochemicalSpecies
    hydrolysis: MacrochemicalSolution
    secretion: MacrochemicalSolution
    allocation_fraction: Parameter
    catalytic_capacity: Parameter
    substrate_half_saturation: Parameter
    enzyme_inactivation_rate: Parameter
    feed_substrate: Quantity
    source: str
    maturity: str = DEGRADING_CULTURE_MATURITY
    _balance: MacrochemicalBalance = field(init=False, repr=False)
    _stoichiometry: np.ndarray = field(init=False, repr=False)
    _secretion_yield: float = field(init=False, repr=False)

    @property
    def names(self) -> tuple[str, ...]:
        return (*self.culture.names, self.degradable_substrate.name, self.active_enzyme.name, self.inactive_enzyme.name)

    @property
    def processes(self) -> tuple[str, ...]:
        return ("growth", "maintenance", "secretion", "hydrolysis", "inactivation")

    def __post_init__(self) -> None:
        if not has_text(self.source):
            raise ProvenanceError("Integrated degradation requires a mechanism and assumption source.")
        if self.maturity != DEGRADING_CULTURE_MATURITY:
            raise ValueError(f"Maturity must be {DEGRADING_CULTURE_MATURITY!r}.")
        if len(set(self.names)) != 7:
            raise ValueError("All seven dynamic pool names must be distinct.")
        extras = (self.degradable_substrate, self.active_enzyme, self.inactive_enzyme)
        base = self.culture.metabolism.balance
        if set(s.name for s in extras) & set(s.name for s in base.species):
            raise ValueError("New pools must not alias existing chemical species or reservoirs.")
        for s in extras:
            s.validate()
        if (self.active_enzyme.composition.elements != self.inactive_enzyme.composition.elements
                or self.active_enzyme.charge != self.inactive_enzyme.charge):
            raise ValueError("Inactivation requires chemically identical active/inactive protein pools.")
        fraction = _parameter(self.allocation_fraction, "dimensionless")
        if fraction > 1:
            raise ValueError("Allocation must be a fraction in [0, 1].")
        _parameter(self.catalytic_capacity, RATE_UNITS)
        _parameter(self.substrate_half_saturation, CONCENTRATION_UNITS, positive=True)
        _parameter(self.enzyme_inactivation_rate, RATE_UNITS)
        _number(self.feed_substrate, CONCENTRATION_UNITS, "feed_substrate")
        balance = MacrochemicalBalance("integrated culture material ledger", (*base.species, *extras), self.source)
        species = {s.name: s for s in balance.species}
        solutions = (self.culture.metabolism.growth_reaction, self.culture.metabolism.maintenance_reaction,
                     self.secretion, self.hydrolysis)
        columns = []
        for reaction in solutions:
            reaction.balance.validate()
            if set(reaction.coefficients) != {s.name for s in reaction.balance.species}:
                raise ValueError("A reaction must provide every coefficient in its declared balance.")
            for s in reaction.balance.species:
                if (s.name not in species or s.composition.elements != species[s.name].composition.elements
                        or s.charge != species[s.name].charge):
                    raise ValueError(f"Conflicting or unknown species composition/charge for {s.name!r}.")
            columns.append([reaction.coefficients.get(s.name, 0.) for s in balance.species])
        columns.append([-1. if s.name == self.active_enzyme.name else 1. if s.name == self.inactive_enzyme.name
                        else 0. for s in balance.species])
        matrix = np.array(columns).T
        _, elements = balance.conservation_matrix()
        if not np.isfinite(matrix).all() or np.any(np.abs(elements @ matrix) > 1e-12 * np.maximum(1, np.abs(matrix).max(axis=0))):
            raise ValueError("Every integrated pathway must independently conserve elements and charge.")
        hydro = self.hydrolysis.coefficients
        if hydro.get(self.degradable_substrate.name) != -1 or hydro.get(self.culture.metabolism.substrate, 0) <= 0:
            raise ValueError("Hydrolysis must consume one substrate formula unit and produce assimilable product.")
        permitted = {self.degradable_substrate.name, self.culture.metabolism.substrate, *self.culture.reservoir_species}
        if any(abs(v) > 1e-12 and n not in permitted for n, v in hydro.items()):
            raise ValueError("Hydrolysis may only exchange substrate, assimilable product and explicit reservoirs.")
        secreted = self.secretion.coefficients
        if secreted.get(self.active_enzyme.name) != 1 or secreted.get(self.culture.metabolism.substrate, 0) >= 0:
            raise ValueError("Secretion must consume assimilable product and produce one protein formula unit.")
        if secreted.get(self.culture.nitrogen, 0) >= 0 or secreted.get(self.culture.oxidant, 0) >= 0:
            raise ValueError("This secretion closure requires explicit nitrogen and oxidant consumption.")
        permitted = {self.culture.metabolism.substrate, self.culture.nitrogen, self.culture.oxidant,
                     self.active_enzyme.name, *self.culture.reservoir_species}
        if any(abs(v) > 1e-12 and n not in permitted for n, v in secreted.items()):
            raise ValueError("Secretion cannot create/consume undeclared biomass or extracellular pools.")
        object.__setattr__(self, "_balance", balance)
        object.__setattr__(self, "_stoichiometry", matrix)
        object.__setattr__(self, "_secretion_yield", -1 / secreted[self.culture.metabolism.substrate])

    def _rate_kernel(self):
        # Reuse the respiration closure exactly; allocation divides its common
        # post-maintenance substrate budget instead of adding a second uptake.
        constants = self.culture._constants()
        fraction = _parameter(self.allocation_fraction, "dimensionless")
        catalytic = _parameter(self.catalytic_capacity, RATE_UNITS)
        half = _parameter(self.substrate_half_saturation, CONCENTRATION_UNITS, positive=True)
        inactivation = _parameter(self.enzyme_inactivation_rate, RATE_UNITS)

        def rates(state):
            positive = np.maximum(state[:7], 0)
            potential_mu, maintenance, unmet = self.culture._rates(positive, constants)
            biomass, polymer, enzyme = positive[1], positive[4], positive[5]
            growth = (1-fraction) * potential_mu * biomass
            secretion = fraction * potential_mu / constants[0] * self._secretion_yield * biomass
            hydrolysis = catalytic * enzyme * polymer / (half+polymer)
            return np.array([growth, maintenance*biomass, secretion, hydrolysis, inactivation*enzyme]), unmet
        return rates

    def _rate_jacobian_kernel(self):
        constants = self.culture._constants()
        fraction = _parameter(self.allocation_fraction, "dimensionless")
        catalytic = _parameter(self.catalytic_capacity, RATE_UNITS)
        half = _parameter(self.substrate_half_saturation, CONCENTRATION_UNITS, positive=True)
        inactivation = _parameter(self.enzyme_inactivation_rate, RATE_UNITS)

        def jacobian(state):
            positive = np.maximum(state[:7], 0)
            mu, maintenance, _ = self.culture._rates(positive, constants)
            physiology = self.culture._rate_jacobian(state, constants)[:2] * positive[1]
            physiology[:, 1] += np.array([mu, maintenance]) * (state[1] >= 0)
            matrix = np.zeros((5, 7))
            matrix[0, :4] = (1-fraction)*physiology[0]
            matrix[1, :4] = physiology[1]
            matrix[2, :4] = fraction/constants[0]*self._secretion_yield*physiology[0]
            matrix[3, 4] = catalytic*positive[5]*half/(half+positive[4])**2 * (state[4] >= 0)
            matrix[3, 5] = catalytic*positive[4]/(half+positive[4]) * (state[5] >= 0)
            matrix[4, 5] = inactivation * (state[5] >= 0)
            return matrix
        return jacobian

    def _initial(self, concentrations: Mapping[str, Quantity]) -> np.ndarray:
        if set(concentrations) != set(self.names):
            raise ValueError("Concentrations must exactly cover the seven dynamic pools.")
        return np.array([_number(concentrations[n], CONCENTRATION_UNITS, n) for n in self.names])

    def rates(self, concentrations: Mapping[str, Quantity]) -> dict[str, Quantity]:
        flux, _ = self._rate_kernel()(self._initial(concentrations))
        return {n: Q_(v, "mol/L/h") for n, v in zip(self.processes, flux, strict=True)}

    def _ledger_names(self) -> tuple[str, ...]:
        names = (*self.names, *(f"extent:{n}" for n in self.processes), *(f"boundary:{n}" for n in self.names))
        if len(set(names)) != len(names):
            raise ValueError("Pool names collide with reserved ledger names.")
        return names

    def _pathway_source(self, pathway: MacrochemicalSolution) -> str:
        """The solved pathway's own balance source, or the class source when the balance carries none."""
        source = pathway.balance.source
        if isinstance(source, str) and has_text(source):
            return source
        return self.source

    def _feed(self) -> dict[str, Quantity | None]:
        """Declared feed of every pool; ``None`` marks pools without external supply."""
        return {n: self.culture.feed[n] if n in self.culture.feed else
                self.feed_substrate if n == self.degradable_substrate.name else None for n in self.names}

    def compiled_processes(self) -> tuple[Process, ...]:
        """The five pathways and the boundary exchanges as generic processes.

        Growth, maintenance and secretion are the Pirt/Monod closure processes
        with the dynamic-pool stoichiometry of the solved pathways; hydrolysis
        is enzyme-explicit Michaelis-Menten in the degradable substrate;
        inactivation is first-order mass action from the active to the inactive
        pool. Each carries an extent ledger and every exchange a boundary ledger,
        so the compiled run integrates the same 19 states as ``simulate``.
        """
        culture = self.culture
        kwargs = culture._closure_kwargs()
        fraction = self.allocation_fraction.symbol
        polymer, enzyme, inactive = self.degradable_substrate.name, self.active_enzyme.name, self.inactive_enzyme.name
        growth = ResourceLimitedGrowthProcess(
            name="growth", stoichiometry=_dynamic_stoichiometry(culture.metabolism.growth_reaction.coefficients, self.names),
            extent_state="extent:growth", allocation_fraction_symbol=fraction, source=culture.source,
            notes="Biomass-forming share of the post-maintenance budget; reservoir species are ledgered, not integrated.",
            **kwargs)
        maintenance = ResourceLimitedMaintenanceProcess(
            name="maintenance",
            stoichiometry=_dynamic_stoichiometry(culture.metabolism.maintenance_reaction.coefficients, self.names),
            extent_state="extent:maintenance", source=culture.source,
            notes="Maintenance extent of the solved maintenance pathway; unmet demand is reported, not consumed.", **kwargs)
        secretion = CostedSecretionProcess(
            name="secretion", stoichiometry=_dynamic_stoichiometry(self.secretion.coefficients, self.names),
            extent_state="extent:secretion", allocation_fraction_symbol=fraction,
            secretion_yield_symbol=SECRETION_YIELD_SYMBOL, source=self._pathway_source(self.secretion),
            notes="Secreted share of the post-maintenance budget in protein formula units of the solved secretion pathway.",
            **kwargs)
        hydrolysis = HomogeneousMichaelisMentenProcess(
            name="hydrolysis", substrate_state=polymer, km_symbol=self.substrate_half_saturation.symbol,
            rate_units=EXTENT_RATE_UNITS, substrate_units=CONCENTRATION_UNITS, enzyme_state=enzyme,
            enzyme_units=CONCENTRATION_UNITS, kcat_symbol=self.catalytic_capacity.symbol,
            product_coefficients={**_dynamic_stoichiometry(self.hydrolysis.coefficients, [n for n in self.names if n != polymer]),
                                  "extent:hydrolysis": 1.0},
            source=self._pathway_source(self.hydrolysis),
            notes="Effective saturation in the degradable substrate catalysed by the active enzyme pool; "
                  "reservoir exchanges stay in the ledger.")
        inactivation = MassActionProcess(
            name="inactivation", reactants={enzyme: 1.0}, products={inactive: 1.0, "extent:inactivation": 1.0},
            state_units={enzyme: CONCENTRATION_UNITS, inactive: CONCENTRATION_UNITS, "extent:inactivation": CONCENTRATION_UNITS},
            rate_constant_symbol=self.enzyme_inactivation_rate.symbol, rate_constant_units=f"1 / ({TIME_UNITS})",
            rate_units=EXTENT_RATE_UNITS, source=self.source,
            notes="First-order inactivation moving active protein to the chemically identical inactive pool.")
        return (growth, maintenance, secretion, hydrolysis, inactivation, *culture._exchange_processes(self.names))

    def compiled_parameters(self) -> ParameterSet:
        """The two classes' parameters, the secretion yield of the solved pathway and one feed parameter per pool."""
        secretion_yield = Parameter(
            "protein formula units per assimilable-substrate formula unit of the secretion pathway", SECRETION_YIELD_SYMBOL,
            Q_(self._secretion_yield, "dimensionless"), "dimensionless", None, self._pathway_source(self.secretion), "high",
            "Derived from the solved secretion stoichiometry as -1 / (substrate coefficient per protein formula unit); "
            "a chemical conversion, not a measured yield.")
        return _parameter_set((*self.culture._closure_parameters(), self.allocation_fraction, self.catalytic_capacity,
                               self.substrate_half_saturation, self.enzyme_inactivation_rate, secretion_yield,
                               *self.culture._exchange_parameters(self._feed())), owner=type(self).__name__)

    def simulate(self, *, initial_state: Mapping[str, Quantity], times: Quantity,
                 solver_settings: SolverSettings | None = None) -> DegradingCultureTrajectory:
        """Integrate the native right-hand side with its analytic piecewise Jacobian."""
        initial = self._initial(initial_state)
        grid = _time_grid(times)
        settings = solver_settings or SolverSettings()
        values, diagnostics = self._integrate_native(grid, initial, settings)
        return self._trajectory(grid, values, initial, settings, diagnostics)

    def simulate_compiled(self, *, initial_state: Mapping[str, Quantity], times: Quantity,
                          solver_settings: SolverSettings | None = None) -> DegradingCultureTrajectory:
        """Integrate ``compiled_processes`` on the compiled process core; same trajectory type as ``simulate``."""
        initial = self._initial(initial_state)
        grid = _time_grid(times)
        settings = solver_settings or SolverSettings()
        names = self._ledger_names()
        values, diagnostics = _run_compiled(self.compiled_processes(), self.compiled_parameters(),
                                            pools=dict(zip(self.names, initial.tolist(), strict=True)),
                                            ledgers=names[len(self.names):], grid=grid, settings=settings,
                                            name="degrading_culture")
        return self._trajectory(grid, values, initial, settings, diagnostics)

    def _integrate_native(self, grid: np.ndarray, initial: np.ndarray,
                          settings: SolverSettings) -> tuple[np.ndarray, dict[str, Any]]:
        rates = self._rate_kernel()
        rate_jacobian = self._rate_jacobian_kernel()
        species_names = tuple(s.name for s in self._balance.species)
        indices = [species_names.index(n) for n in self.names]
        dynamic_matrix = self._stoichiometry[indices]
        dilution = _parameter(self.culture.dilution_rate, RATE_UNITS)
        transfer = _parameter(self.culture.gas_transfer_rate, RATE_UNITS)
        saturation = _parameter(self.culture.oxidant_saturation, CONCENTRATION_UNITS)
        feed = np.array([0. if q is None else _number(q, CONCENTRATION_UNITS, n) for n, q in self._feed().items()])
        units = dict.fromkeys(self._ledger_names(), CONCENTRATION_UNITS)

        def rhs(_time, state):
            flux, _ = rates(state)
            boundary = dilution * (feed-state[:7])
            boundary[3] += transfer * (saturation-state[3])
            return np.r_[dynamic_matrix @ flux + boundary, flux, boundary]

        boundary_jacobian = -dilution*np.eye(7)
        boundary_jacobian[3, 3] -= transfer

        def jacobian(_time, state):
            flux_jacobian = rate_jacobian(state)
            matrix = np.zeros((19, 19))
            matrix[:7, :7] = dynamic_matrix @ flux_jacobian + boundary_jacobian
            matrix[7:12, :7] = flux_jacobian
            matrix[12:, :7] = boundary_jacobian
            return matrix

        options = settings.scipy_options(units, time_units=TIME_UNITS)
        if settings.method in {"BDF", "Radau", "LSODA"}:
            options["jac"] = jacobian
        result = solve_checked(rhs, (grid[0], grid[-1]), np.r_[initial, np.zeros(12)], t_eval=grid,
                               **options)
        return result.y, {"nfev": int(result.nfev),
                          "jacobian": "analytic piecewise" if "jac" in options else "unused by explicit method",
                          "engine": NATIVE_ENGINE}

    def _trajectory(self, grid: np.ndarray, values: np.ndarray, initial: np.ndarray, settings: SolverSettings,
                    diagnostics: Mapping[str, Any]) -> DegradingCultureTrajectory:
        rates = self._rate_kernel()
        species_names = tuple(s.name for s in self._balance.species)
        indices = [species_names.index(n) for n in self.names]
        units = dict.fromkeys(self._ledger_names(), CONCENTRATION_UNITS)
        atols = np.broadcast_to(settings.absolute_tolerances(units), (len(units),))
        if np.any(values[:7] < -10 * atols[:7, None]):
            raise IntegrationError("Integrated culture returned a negative pool beyond 10 absolute tolerances.")
        exchanges = self._stoichiometry @ values[7:12]
        boundary = np.zeros_like(exchanges)
        boundary[indices] = values[12:]
        for name in self.culture.reservoir_species:
            i = species_names.index(name)
            boundary[i] = -exchanges[i]
        delta = np.zeros_like(exchanges)
        delta[indices] = values[:7]-initial[:, None]
        labels, matrix = self._balance.conservation_matrix()
        residual = matrix @ (delta-boundary)
        fluxes, unmet = zip(*(rates(v) for v in values.T), strict=True)
        return DegradingCultureTrajectory(
            Q_(grid, "h"), {n: Q_(values[i], CONCENTRATION_UNITS) for i, n in enumerate(self.names)},
            {n: Q_(np.asarray(fluxes)[:, i], "mol/L/h") for i, n in enumerate(self.processes)},
            {n: Q_(exchanges[i], CONCENTRATION_UNITS) for i, n in enumerate(species_names)},
            {n: Q_(boundary[i], CONCENTRATION_UNITS) for i, n in enumerate(species_names)}, Q_(np.array(unmet), RATE_UNITS),
            {"maturity": self.maturity, "empirical_validation": False,
             "dilution_rate_per_h": _parameter(self.culture.dilution_rate, RATE_UNITS),
             "maximum_absolute_balance_residual_mol_L": {n: float(np.abs(r).max()) for n, r in zip(labels, residual, strict=True)},
             "minimum_pool_mol_L": float(values[:7].min()), **dict(diagnostics), "solver_settings": settings.to_dict(),
             "thermodynamics": "Unavailable in this trajectory: no activity model or complete common-state formation-energy set is assumed."},
            self.to_dict(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"maturity": self.maturity, "source": self.source, "culture": self.culture.to_dict(),
                "degradable_substrate": self.degradable_substrate.name,
                "species": [s.to_dict() for s in self._balance.species],
                "pathway_coefficients": {n: dict(zip((s.name for s in self._balance.species), self._stoichiometry[:, i].tolist(), strict=True))
                                         for i, n in enumerate(self.processes)},
                "hydrolysis_source": self.hydrolysis.balance.source, "secretion_source": self.secretion.balance.source,
                "parameters": {n: getattr(self, n).to_dict() for n in ("allocation_fraction", "catalytic_capacity",
                    "substrate_half_saturation", "enzyme_inactivation_rate")},
                "feed_substrate": {"value": float(self.feed_substrate.to(CONCENTRATION_UNITS).magnitude), "units": CONCENTRATION_UNITS},
                "claim_boundary": "Explicit homogeneous allocation and effective hydrolysis hypothesis; not an organism-validated whole fungus. "
                    "No transcription, enzyme-mixture activity conversion, adsorption, geometry, death, recycling or pH dynamics. "
                    "Nonliving inactive protein is retained chemically; it is not an active enzyme or biomass."}


__all__ = ["DegradingCulture", "DegradingCultureTrajectory", "DEGRADING_CULTURE_MATURITY", "SECRETION_YIELD_SYMBOL",
           "secretion_allocation"]
