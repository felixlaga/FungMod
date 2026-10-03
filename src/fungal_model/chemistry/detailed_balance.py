"""Closed, ideal-dilute, isothermal mass-action networks with detailed balance.

Chemical potentials generate every reverse rate, enforcing cycle consistency
without independent equilibrium constants. This is an explicit mechanistic
model, not an inference of biology or kinetics from maximum entropy production.
Theory: Rao & Esposito (2016), https://doi.org/10.1103/PhysRevX.6.041064.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from scipy.special import xlogy
from scipy.optimize import least_squares

from fungal_model.chemistry.macrochemistry import MacrochemicalBalance
from fungal_model.core.numerics import IntegrationError, SolverSettings, solve_checked
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible

NETWORK_MATURITY = "exploratory_software_tested"
NETWORK_SOURCE = "https://doi.org/10.1103/PhysRevX.6.041064"


@dataclass(frozen=True)
class DetailedBalanceReaction:
    """One elementary reversible reaction, with explicit forward kinetic scale.

    The scale multiplies dimensionless reactant activities and has concentration
    per time units irrespective of molecularity. Catalysts may appear on both
    sides. Only nonnegative integer molecularities are supported.
    """

    name: str
    reactants: Mapping[str, int]
    products: Mapping[str, int]
    forward_scale: Parameter
    source: str


@dataclass(frozen=True)
class DetailedBalanceTrajectory:
    time: Quantity
    concentrations: Mapping[str, Quantity]
    reaction_rates: Mapping[str, Quantity]
    free_energy_density: Quantity
    entropy_production_density: Quantity | None
    diagnostics: Mapping[str, Any]
    provenance: Mapping[str, Any]
    maturity: str = NETWORK_MATURITY


class DetailedBalanceNetwork:
    """Element/charge-balanced closed network at fixed T and solvent volume.

    ``f = sum(c_i * [mu_i_standard + RT*(ln(c_i/c_standard)-1)])`` is the
    ideal-dilute chemical free-energy density (solvent reference omitted).
    Its time derivative is ``-T*sigma`` for this closed model. This expression
    is not the full Gibbs energy of a concentrated, variable-volume solution.

    Formation energies must refer to the declared common temperature, pressure,
    species definitions and standard state. The caller is responsible for this
    evidence; no temperature/pH/speciation correction or formation energy is
    invented. No chemostats, gas phase, nonideal activities, heat balance, or
    organism physiology are inferred.
    """

    def __init__(self, *, balance: MacrochemicalBalance,
                 reactions: tuple[DetailedBalanceReaction, ...], temperature: Parameter,
                 gas_constant: Parameter, standard_concentration: Parameter):
        balance.validate()
        if not has_text(balance.thermodynamic_conditions):
            raise ProvenanceError("Network formation energies require declared thermodynamic_conditions.")
        self.balance, self.reactions = deepcopy(balance), deepcopy(tuple(reactions))
        self.temperature, self.gas_constant = temperature, gas_constant
        self.standard_concentration = standard_concentration
        self.names = tuple(s.name for s in balance.species)
        self.temperature_K = _number(temperature, "kelvin", positive=True)
        self.rt = self.temperature_K * _number(gas_constant, "joule/mole/kelvin", positive=True)
        self.c_standard = _number(standard_concentration, "mole/liter", positive=True)
        self.mu_standard = np.array([_number(s.formation_gibbs, "joule/mole") for s in balance.species])
        if not self.reactions or len({r.name for r in self.reactions}) != len(self.reactions):
            raise ValueError("Network requires nonempty reactions with unique names.")
        reactants, products, scales = [], [], []
        for reaction in self.reactions:
            if not has_text(reaction.name) or not has_text(reaction.source):
                raise ProvenanceError("Every network reaction requires a name and source.")
            for side in (reaction.reactants, reaction.products):
                if not side or set(side).difference(self.names):
                    raise ValueError("Reaction participants must be explicit known species on both sides.")
                if any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0 for v in side.values()):
                    raise ValueError("Elementary reaction molecularities must be positive integers.")
            reactants.append([reaction.reactants.get(n, 0) for n in self.names])
            products.append([reaction.products.get(n, 0) for n in self.names])
            scales.append(_number(reaction.forward_scale, "mole/liter/second", positive=True))
        self.reactant_orders = np.asarray(reactants, dtype=int)
        self.product_orders = np.asarray(products, dtype=int)
        self.stoichiometry = (self.product_orders - self.reactant_orders).T
        if np.any(np.all(self.stoichiometry == 0, axis=0)):
            raise ValueError("A network reaction must change at least one species.")
        self.conserved_names, self.conservation = balance.conservation_matrix()
        residual = self.conservation @ self.stoichiometry
        # Roundoff criterion only, scaled by the actual elemental terms.
        scale = np.maximum(1.0, np.abs(self.conservation) @ np.abs(self.stoichiometry))
        if np.any(np.abs(residual) > 100 * np.finfo(float).eps * scale):
            raise ValueError("Network reactions violate element or charge conservation.")
        self.log_forward = np.log(scales)
        self.standard_reaction_gibbs = self.stoichiometry.T @ self.mu_standard
        self.log_reverse = self.log_forward + self.standard_reaction_gibbs / self.rt
        with np.errstate(over="ignore", under="ignore"):
            self.forward_scales, self.reverse_scales = np.exp(self.log_forward), np.exp(self.log_reverse)
        if (not np.isfinite(self.reverse_scales).all() or np.any(self.reverse_scales == 0)
                or not np.isfinite(self.rt)):
            raise ValueError("Thermodynamic rate scales exceed representable floating-point range.")

    def _vector(self, state: Mapping[str, Quantity]) -> np.ndarray:
        if set(state) != set(self.names):
            raise ValueError("Concentrations must cover exactly all network species.")
        scalars = [np.asarray(assert_compatible(state[n], "mole/liter", name=n).magnitude, dtype=float) for n in self.names]
        if any(v.ndim for v in scalars):
            raise ValueError("Concentrations must be finite nonnegative scalars.")
        values = np.array([float(v) for v in scalars])
        if not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError("Concentrations must be finite nonnegative scalars.")
        return values

    def _fluxes(self, concentrations: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        activity = concentrations / self.c_standard
        forward = self.forward_scales * np.prod(activity[None, :] ** self.reactant_orders, axis=1)
        reverse = self.reverse_scales * np.prod(activity[None, :] ** self.product_orders, axis=1)
        net = forward - reverse
        # log1p retains relative concentration differences near equilibrium;
        # expm1 avoids subtracting almost equal one-way rates.
        if np.all(activity > 0):
            logs = np.log(activity)
            near_one = np.abs(activity - 1) < 0.5
            logs[near_one] = np.log1p(activity[near_one] - 1)
            log_ratio = self.standard_reaction_gibbs / self.rt + self.stoichiometry.T @ logs
            negative = log_ratio <= 0
            net[negative] = forward[negative] * (-np.expm1(log_ratio[negative]))
            net[~negative] = reverse[~negative] * np.expm1(-log_ratio[~negative])
        if not np.isfinite(np.concatenate((forward, reverse, net))).all():
            raise IntegrationError("Network flux exceeded floating-point range.")
        return forward, reverse, net

    def _jacobian(self, concentrations: np.ndarray) -> np.ndarray:
        activity = concentrations / self.c_standard
        gradient = np.zeros((len(self.reactions), len(self.names)))
        # Polynomial derivatives also work exactly at zero concentration.
        for orders, scales, sign in ((self.reactant_orders, self.forward_scales, 1),
                                      (self.product_orders, self.reverse_scales, -1)):
            for i in range(len(self.names)):
                active = orders[:, i] > 0
                reduced = orders[active].copy()
                reduced[:, i] -= 1
                gradient[active, i] += (sign * scales[active] * orders[active, i] / self.c_standard
                                       * np.prod(activity[None, :] ** reduced, axis=1))
        return self.stoichiometry @ gradient

    def evaluate(self, state: Mapping[str, Quantity]) -> dict[str, Any]:
        """Return free energy, fluxes, affinities and entropy in canonical units.

        At zero concentrations the free energy uses the exact x*log(x) limit.
        Chemical potentials are singular, so Gibbs/entropy diagnostics remain
        explicitly unavailable rather than inventing a positive activity floor.
        """
        c = self._vector(state)
        forward, reverse, flux = self._fluxes(c)
        f = float(c @ self.mu_standard + self.rt * np.sum(xlogy(c, c / self.c_standard) - c))
        positive = bool(np.all(c > 0))
        gibbs = (self.rt * (self.standard_reaction_gibbs/self.rt + self.stoichiometry.T @ np.log(c/self.c_standard))
                 if positive else None)
        entropy = None if gibbs is None else -flux * gibbs / self.temperature_K
        derivative = None if gibbs is None else float(flux @ gibbs)
        if not np.isfinite(f) or (entropy is not None and not np.isfinite(entropy).all()):
            raise IntegrationError("Network energy or entropy exceeded floating-point range.")
        return {"free_energy_density_J_L": f, "forward_rates_mol_L_s": forward.tolist(),
                "reverse_rates_mol_L_s": reverse.tolist(), "net_rates_mol_L_s": flux.tolist(),
                "reaction_gibbs_J_mol": None if gibbs is None else gibbs.tolist(),
                "entropy_production_J_L_K_s": None if entropy is None else entropy.tolist(),
                "free_energy_derivative_J_L_s": derivative,
                "thermodynamic_status": "available" if positive else "boundary_chemical_potential_singular"}

    def equilibrium(self, initial_state: Mapping[str, Quantity], *, relative_tolerance: float = 1e-10) -> dict[str, Any]:
        """Minimize the convex dilute free energy on the closed compatibility class.

        Solve zero reaction affinities together with *all* left-nullspace
        conservation laws, including disconnected pools, in log concentrations.
        This independent equilibrium calculation uses no kinetic scales. It
        requires strictly positive initial concentrations (interior class);
        boundary equilibria are not silently approximated with a floor.
        """
        initial = self._vector(initial_state)
        if np.any(initial <= 0):
            raise ValueError("Equilibrium calculation requires strictly positive initial concentrations.")
        if not np.isfinite(relative_tolerance) or not 1e-13 <= relative_tolerance < 1:
            raise ValueError("Equilibrium relative_tolerance must be finite and in [1e-13, 1).")
        basis, singular, _ = np.linalg.svd(self.stoichiometry.astype(float), full_matrices=True)
        rank = int(np.sum(singular > max(self.stoichiometry.shape)*np.finfo(float).eps*singular[0]))
        directions, invariants = basis[:, :rank].T, basis[:, rank:].T
        total = invariants @ initial
        scale = np.linalg.norm(initial)

        def residual(log_activity):
            c = self.c_standard*np.exp(log_activity)
            return np.concatenate((directions @ (self.mu_standard/self.rt + log_activity),
                                   (invariants @ c - total)/scale))

        def jacobian(log_activity):
            return np.vstack((directions, invariants*(self.c_standard*np.exp(log_activity))[None, :]/scale))

        # Bounds are numerical representability limits, not concentration floors.
        solution = least_squares(residual, np.log(initial/self.c_standard), jac=cast(Any, jacobian),
                                 bounds=(-700, 700), xtol=1e-13, ftol=1e-13, gtol=1e-13, max_nfev=2000)
        maximum = float(np.max(np.abs(residual(solution.x))))
        if not solution.success or maximum > relative_tolerance:
            raise IntegrationError(f"Equilibrium did not satisfy affinities and conservation: residual={maximum}.")
        c = self.c_standard*np.exp(solution.x)
        state = dict(zip(self.names, [Q_(v, "mole/liter") for v in c], strict=True))
        evaluation = self.evaluate(state)
        return {"concentrations": state, "free_energy_density": Q_(evaluation["free_energy_density_J_L"], "J/L"),
                "maximum_scaled_residual": maximum, "stoichiometric_rank": rank,
                "conservation_law_count": len(self.names)-rank,
                "method": "convex_free_energy_stationarity_with_all_stoichiometric_invariants",
                "maturity": NETWORK_MATURITY}

    def simulate(self, *, initial_state: Mapping[str, Quantity], times: Quantity,
                 solver_settings: SolverSettings | None = None) -> DetailedBalanceTrajectory:
        """Integrate from the first supplied time with an analytic stiff Jacobian.

        Polynomial rate evaluation extends trial negative values by zero only
        inside the solver. Returned concentrations are never clipped: any
        negative output rejects the trajectory and requests tighter controls.
        """
        grid = np.asarray(assert_compatible(times, "second", name="times").magnitude, dtype=float)
        if grid.ndim != 1 or grid.size < 2:
            raise ValueError("Network times require at least two increasing values.")
        initial = self._vector(initial_state)
        settings = solver_settings or SolverSettings(method="Radau")
        options = settings.scipy_options(dict.fromkeys(self.names, "mole/liter"), "second")

        def rhs(_t, y):
            return self.stoichiometry @ self._fluxes(np.maximum(y, 0))[2]

        if settings.method in {"Radau", "BDF", "LSODA"}:
            def jac(_t, y):
                matrix = self._jacobian(np.maximum(y, 0))
                matrix[:, y < 0] = 0  # derivative of the declared trial extension
                return matrix
            options["jac"] = jac
        solution = solve_checked(rhs, (grid[0], grid[-1]), initial, t_eval=grid, **options)
        if np.any(solution.y < 0):
            raise IntegrationError("Negative network output; tighten tolerances or change method. No clipping applied.")
        concentrations = {n: Q_(solution.y[i], "mole/liter") for i, n in enumerate(self.names)}
        rows = [self.evaluate({n: Q_(solution.y[i, k], "mole/liter") for i, n in enumerate(self.names)})
                for k in range(grid.size)]
        energy = np.array([r["free_energy_density_J_L"] for r in rows])
        available = all(r["entropy_production_J_L_K_s"] is not None for r in rows)
        entropy = np.array([sum(r["entropy_production_J_L_K_s"]) for r in rows]) if available else None
        invariants = self.conservation @ solution.y
        drift = np.max(np.abs(invariants - (self.conservation @ initial)[:, None]), axis=1)
        return DetailedBalanceTrajectory(
            time=Q_(solution.t, "second"), concentrations=concentrations,
            reaction_rates={r.name: Q_([row["net_rates_mol_L_s"][j] for row in rows], "mole/liter/second")
                            for j, r in enumerate(self.reactions)},
            free_energy_density=Q_(energy, "joule/liter"),
            entropy_production_density=None if entropy is None else Q_(entropy, "joule/liter/kelvin/second"),
            diagnostics={"method": settings.method, "settings": settings.to_dict(), "success": True,
                         "nfev": int(solution.nfev), "njev": int(solution.njev), "nlu": int(solution.nlu),
                         "jacobian": "analytic" if "jac" in options else "unused_by_explicit_method",
                         "max_conserved_drift_mol_L": dict(zip(self.conserved_names, drift.tolist(), strict=True)),
                         "maximum_free_energy_increment_J_L": float(np.max(np.diff(energy))),
                         "minimum_entropy_production_J_L_K_s": None if entropy is None else float(entropy.min()),
                         "boundary_diagnostic_count": sum(r["thermodynamic_status"] != "available" for r in rows)},
            provenance=self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"maturity": NETWORK_MATURITY, "theory_source": NETWORK_SOURCE,
                "balance": self.balance.to_dict(), "temperature": self.temperature.to_dict(),
                "gas_constant": self.gas_constant.to_dict(), "standard_concentration": self.standard_concentration.to_dict(),
                "reactions": [{"name": r.name, "reactants": dict(r.reactants), "products": dict(r.products),
                               "forward_scale": r.forward_scale.to_dict(), "source": r.source} for r in self.reactions],
                "limitations": ["Closed, fixed-volume ideal-dilute isothermal model only.",
                                "Elementary integer-order mass action must be justified per mechanism.",
                                "No inferred kinetics, speciation, biomass chemistry or empirical validation.",
                                "Zero concentrations leave chemical-potential diagnostics unavailable.",
                                "Caller must source formation energies at the common declared conditions."]}


def _number(parameter: Parameter | None, units: str, *, positive: bool = False) -> float:
    if parameter is None:
        raise ValueError("All species require explicit formation Gibbs energies.")
    parameter.validate_provenance()
    parameter.validate_value()
    value = parameter.quantity
    if value is None:
        raise ValueError("Unknown network parameter.")
    array = np.asarray(assert_compatible(value, units, name=parameter.symbol).magnitude, dtype=float)
    if array.ndim or not np.isfinite(array) or (positive and array <= 0):
        raise ValueError("Network parameters must be finite scalars (positive for scales and standards).")
    return float(array)


__all__ = ["DetailedBalanceNetwork", "DetailedBalanceReaction", "DetailedBalanceTrajectory"]
