"""Thermodynamic bounds on growth energetics.

Biomass yield is not a free parameter. Growth couples an exergonic catabolic
reaction to an endergonic anabolic one, and the coupled system cannot create
free energy. If forming one unit of biomass requires `dG_anabolic > 0` and
consuming one unit of substrate releases `|dG_catabolic|`, then

    Y_max = |dG_catabolic| / dG_anabolic

is a hard ceiling on biomass produced per substrate consumed. Every real
organism sits strictly below it, because real growth dissipates energy rather
than operating reversibly.

This is the one place where fundamental thermodynamics does useful predictive
work in FungMod. It cannot supply a reaction rate, because rate depends on an
enzyme's activation barrier rather than on the reaction's Gibbs energy. It can
bound an organism-level parameter that is otherwise left entirely free, and it
does so without any organism-specific measurement.

The bound is an upper limit, never an estimate. A model that sets its yield at
the bound is claiming reversible, zero-dissipation growth, which is
thermodynamically permitted and biologically false. Both Gibbs energies must be
supplied as sourced parameters; nothing here invents an energy value. The bound
also knows nothing about atoms: when the yield basis admits a conservation
limit (for example one C-mol of biomass per C-mol of substrate), pass it as
``carbon_limit`` so the tighter of the two ceilings is applied.

The predictive black-box tool is the Gibbs energy dissipation correlation of
Heijnen and van Dijken (1992): growth dissipates a characteristic amount of
Gibbs energy per C-mol of biomass formed, fixed by the carbon chain length and
degree of reduction of the carbon source. Combined with a conserved
macrochemical balance and sourced formation energies, that dissipation fixes
the substrate coefficient and hence the yield, the oxygen demand, and every
other exchange coefficient. ``DissipationYieldPrediction`` does exactly that
and nothing more.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

from fungal_model.chemistry.macrochemistry import (
    MacrochemicalBalance,
    MacrochemicalBalanceError,
    MacrochemicalSolution,
)
from fungal_model.chemistry.stoichiometry import ElementalComposition, degree_of_reduction
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.core.validators import ValidationResult

HEIJNEN_DISSIPATION_MATURITY = "literature_backed_software_tested"
HEIJNEN_DISSIPATION_SOURCE = (
    "Gibbs energy dissipation per C-mol biomass for heterotrophic growth without reversed "
    "electron transport, D_e = 200 + 18 (6 - C)^1.8 + exp{[(3.8 - gamma_S)^2]^0.16 (3.6 + 0.4 C)} "
    "kJ/Cmol X; Heijnen and van Dijken 1992, Biotechnology and Bioengineering 39:833-858; "
    "Heijnen, van Loosdrecht and Tijhuis 1992, Biotechnology and Bioengineering 40:1139-1154; "
    "compared in Liu, Vojinovic, Patino, Maskow and von Stockar 2007, Thermochimica Acta 458:38-46."
)
HEIJNEN_DISSIPATION_VALIDITY = (
    "Carbon source with 1 to 6 carbon atoms per molecule and degree of reduction 0 to 8 per "
    "C-mol; ammonium as nitrogen source; heterotrophic growth without reversed electron "
    "transport; the source reports about 13 percent error in predicted yields over 0.01 to "
    "0.80 Cmol/Cmol. Not for autotrophic, photosynthetic, or reversed-electron-transport growth."
)
_DISSIPATION_UNITS = "kilojoule / mole"


def _constant(name: str, symbol: str, value: float, units: str, notes: str) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source=HEIJNEN_DISSIPATION_SOURCE,
        confidence_level="medium",
        notes=notes,
        measurement_method="empirical correlation fitted to published yield data",
        validity_range=HEIJNEN_DISSIPATION_VALIDITY,
    )


HEIJNEN_DISSIPATION_CONSTANTS: dict[str, Parameter] = {
    "baseline": _constant(
        "dissipation baseline", "D_0", 200.0, _DISSIPATION_UNITS, "Constant term, kJ per C-mol biomass."
    ),
    "chain_length_coefficient": _constant(
        "chain-length coefficient", "k_C", 18.0, _DISSIPATION_UNITS, "Multiplies (C_ref - C)^n_C."
    ),
    "chain_length_exponent": _constant(
        "chain-length exponent", "n_C", 1.8, "dimensionless", "Exponent of (C_ref - C)."
    ),
    "chain_length_reference": _constant(
        "chain-length reference", "C_ref", 6.0, "dimensionless", "Carbon atoms per molecule at which the chain term vanishes."
    ),
    "degree_of_reduction_reference": _constant(
        "degree of reduction reference",
        "gamma_ref",
        3.8,
        "dimensionless",
        "Degree of reduction per C-mol at which the exponential term is smallest.",
    ),
    "degree_of_reduction_exponent": _constant(
        "degree of reduction exponent", "n_gamma", 0.16, "dimensionless", "Exponent applied to (gamma_ref - gamma_S)^2."
    ),
    "exponent_intercept": _constant(
        "exponent intercept", "a_exp", 3.6, "dimensionless", "Intercept of the exponent's linear factor in C."
    ),
    "exponent_slope": _constant(
        "exponent slope", "b_exp", 0.4, "dimensionless", "Slope per carbon atom of the exponent's linear factor."
    ),
    "exponential_unit": _constant(
        "exponential term unit", "D_exp_unit", 1.0, _DISSIPATION_UNITS, "The exponential term is in kJ per C-mol biomass."
    ),
}
_HEIJNEN_CARBON_ATOMS_DOMAIN = (1.0, 6.0)
_HEIJNEN_DEGREE_OF_REDUCTION_DOMAIN = (0.0, 8.0)


def heijnen_dissipation_assumption() -> Assumption:
    return Assumption(
        name="heijnen_van_dijken_dissipation_correlation",
        description=(
            "The Gibbs energy dissipated per C-mol of biomass formed is a function of the "
            "carbon source's chain length and degree of reduction only."
        ),
        justification=(
            "Empirical correlation across published chemotrophic growth yields; the "
            "dissipation reflects the biochemical cost of converting the carbon source "
            "into biomass monomers, which depends on carbon chain length and oxidation state."
        ),
        known_limitations=(
            "Organism-independent by construction; does not resolve ATP yields, electron-"
            "transport efficiency, nitrogen sources other than ammonium, reversed electron "
            "transport, maintenance, or growth-rate effects. " + HEIJNEN_DISSIPATION_VALIDITY
        ),
        source=HEIJNEN_DISSIPATION_SOURCE,
    )


def _constant_value(key: str) -> float:
    return float(cast(Quantity, HEIJNEN_DISSIPATION_CONSTANTS[key].quantity).magnitude)


def heijnen_dissipation_per_cmol_biomass(
    *,
    carbon_atoms: float,
    degree_of_reduction_per_carbon: float,
) -> Parameter:
    """Gibbs energy dissipation per C-mol biomass from the carbon source.

    ``carbon_atoms`` is the number of carbon atoms per molecule of the carbon
    source and ``degree_of_reduction_per_carbon`` its degree of reduction per
    C-mol with ammonia as nitrogen reference. Inputs outside the transcribed
    validity domain are refused. Returns a sourced, positive dissipation in
    kJ per mole of carbon atoms of biomass.
    """

    carbon = float(carbon_atoms)
    gamma = float(degree_of_reduction_per_carbon)
    if not math.isfinite(carbon) or not math.isfinite(gamma):
        raise GrowthEnergeticsError("carbon_atoms and degree_of_reduction_per_carbon must be finite.")
    low, high = _HEIJNEN_CARBON_ATOMS_DOMAIN
    if not low <= carbon <= high:
        raise GrowthEnergeticsError(
            f"carbon_atoms {carbon!r} is outside the correlation's validity domain [{low}, {high}]. "
            + HEIJNEN_DISSIPATION_VALIDITY
        )
    low, high = _HEIJNEN_DEGREE_OF_REDUCTION_DOMAIN
    if not low <= gamma <= high:
        raise GrowthEnergeticsError(
            f"degree_of_reduction_per_carbon {gamma!r} is outside the correlation's validity domain "
            f"[{low}, {high}]. " + HEIJNEN_DISSIPATION_VALIDITY
        )
    chain_term = _constant_value("chain_length_coefficient") * (
        _constant_value("chain_length_reference") - carbon
    ) ** _constant_value("chain_length_exponent")
    exponent = ((_constant_value("degree_of_reduction_reference") - gamma) ** 2) ** _constant_value(
        "degree_of_reduction_exponent"
    ) * (_constant_value("exponent_intercept") + _constant_value("exponent_slope") * carbon)
    dissipation = (
        _constant_value("baseline") + chain_term + _constant_value("exponential_unit") * math.exp(exponent)
    )
    return Parameter(
        name="Gibbs energy dissipation per C-mol biomass",
        symbol="D_e",
        value=dissipation,
        units=_DISSIPATION_UNITS,
        uncertainty=None,
        source=HEIJNEN_DISSIPATION_SOURCE,
        confidence_level="medium",
        notes=(
            f"Evaluated for carbon_atoms = {carbon!r}, degree of reduction per C-mol = {gamma!r} "
            "(ammonia nitrogen reference). Positive value: energy dissipated per mole of biomass "
            "carbon; the reaction Gibbs energy target is its negative."
        ),
        measurement_method="empirical correlation",
        validity_range=HEIJNEN_DISSIPATION_VALIDITY,
    )


def heijnen_dissipation_from_composition(
    composition: ElementalComposition,
    charge: float,
    *,
    nitrogen_reference: str = "ammonia",
) -> Parameter:
    """Evaluate the dissipation correlation from a carbon source composition."""

    carbon = float(composition.elements.get("C", 0.0))
    if carbon <= 0.0:
        raise GrowthEnergeticsError(
            f"The dissipation correlation needs a carbon source; {composition.formula!r} has no carbon."
        )
    return heijnen_dissipation_per_cmol_biomass(
        carbon_atoms=carbon,
        degree_of_reduction_per_carbon=degree_of_reduction(
            composition, charge, nitrogen_reference=nitrogen_reference, per_carbon=True
        ),
    )


@dataclass(frozen=True)
class DissipationYieldPrediction:
    """Yield and exchange coefficients fixed by a stated dissipation per C-mol biomass.

    The macrochemical balance is solved with the biomass coefficient fixed at
    +1 formula unit, the substrate coefficient free, and the reaction Gibbs
    energy set to ``-D_e * C_X`` where ``C_X`` is the carbon count of the
    biomass formula unit. Conservation then fixes every other coefficient.
    """

    balance_name: str
    biomass_species: str
    substrate_species: str
    oxygen_species: str | None
    dissipation_per_cmol_biomass: Parameter
    solution: MacrochemicalSolution
    biomass_carbon_atoms: float
    substrate_carbon_atoms: float
    maturity: str = HEIJNEN_DISSIPATION_MATURITY

    @classmethod
    def predict(
        cls,
        balance: MacrochemicalBalance,
        *,
        biomass_species: str,
        substrate_species: str,
        dissipation_per_cmol_biomass: Parameter,
        oxygen_species: str | None = None,
        absolute_tolerance: float | None = None,
        max_condition_number: float | None = None,
    ) -> "DissipationYieldPrediction":
        names = {species.name: species for species in balance.species}
        for label, name in (("biomass_species", biomass_species), ("substrate_species", substrate_species)):
            if name not in names:
                raise GrowthEnergeticsError(f"{label} {name!r} is not in balance {balance.name!r}.")
        if biomass_species == substrate_species:
            raise GrowthEnergeticsError("biomass_species and substrate_species must differ.")
        if oxygen_species is not None and oxygen_species not in names:
            raise GrowthEnergeticsError(f"oxygen_species {oxygen_species!r} is not in balance {balance.name!r}.")
        biomass_carbon = float(names[biomass_species].composition.elements.get("C", 0.0))
        substrate_carbon = float(names[substrate_species].composition.elements.get("C", 0.0))
        if biomass_carbon <= 0.0 or substrate_carbon <= 0.0:
            raise GrowthEnergeticsError("Both biomass and substrate must contain carbon for a C-mol yield.")
        dissipation = _positive_dissipation(dissipation_per_cmol_biomass)
        target = Parameter(
            name="reaction Gibbs energy target per biomass formula unit",
            symbol="delta_r_G_target",
            value=-float(dissipation.to(_DISSIPATION_UNITS).magnitude) * biomass_carbon,
            units=_DISSIPATION_UNITS,
            uncertainty=None,
            source=dissipation_per_cmol_biomass.source,
            confidence_level=dissipation_per_cmol_biomass.confidence_level,
            notes=f"-D_e times {biomass_carbon!r} carbon atoms per formula unit of {biomass_species!r}.",
        )
        try:
            solution = balance.solve_for_reaction_gibbs(
                fixed_coefficients={biomass_species: 1.0},
                free_species=substrate_species,
                reaction_gibbs=target,
                absolute_tolerance=absolute_tolerance,
                max_condition_number=max_condition_number,
            )
        except MacrochemicalBalanceError as error:
            raise GrowthEnergeticsError(f"Dissipation yield prediction failed: {error}") from error
        substrate_coefficient = solution.coefficients[substrate_species]
        if not substrate_coefficient < 0.0:
            raise GrowthEnergeticsError(
                f"The stated dissipation requires substrate coefficient {substrate_coefficient!r} "
                f"for {substrate_species!r}, which is not consumption; the formation energies or the "
                "dissipation are inconsistent with growth on this substrate."
            )
        prediction = cls(
            balance_name=balance.name,
            biomass_species=biomass_species,
            substrate_species=substrate_species,
            oxygen_species=oxygen_species,
            dissipation_per_cmol_biomass=dissipation_per_cmol_biomass,
            solution=solution,
            biomass_carbon_atoms=biomass_carbon,
            substrate_carbon_atoms=substrate_carbon,
        )
        # Exact comparison: the atom-residual tolerance of the solve is not a
        # yield tolerance, and the correlation never predicts a yield at the
        # ceiling (D_e >= 200 kJ/Cmol), so no round-off allowance is needed.
        if prediction.yield_per_carbon > 1.0:
            raise GrowthEnergeticsError(
                f"Predicted yield {prediction.yield_per_carbon!r} Cmol/Cmol exceeds the carbon ceiling of 1; "
                "the formation energies or the dissipation are inconsistent with conservation."
            )
        return prediction

    @property
    def yield_per_substrate(self) -> float:
        """Biomass formula units per substrate formula unit, ``Y_SX = -1 / nu_S``."""

        return -1.0 / self.solution.coefficients[self.substrate_species]

    @property
    def yield_per_carbon(self) -> float:
        """C-mol biomass per C-mol substrate."""

        return self.yield_per_substrate * self.biomass_carbon_atoms / self.substrate_carbon_atoms

    @property
    def carbon_ceiling_per_substrate(self) -> float:
        """Largest conservation-admissible ``Y_SX``: ``C_S / C_X``."""

        return self.substrate_carbon_atoms / self.biomass_carbon_atoms

    @property
    def oxygen_per_cmol_biomass(self) -> float | None:
        """Mole O2 per C-mol biomass (negative = consumed), or None without an oxygen species."""

        if self.oxygen_species is None:
            return None
        return self.solution.coefficients[self.oxygen_species] / self.biomass_carbon_atoms

    @property
    def assumptions(self) -> list[Assumption]:
        return [heijnen_dissipation_assumption()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "balance_name": self.balance_name,
            "biomass_species": self.biomass_species,
            "substrate_species": self.substrate_species,
            "oxygen_species": self.oxygen_species,
            "dissipation_per_cmol_biomass": self.dissipation_per_cmol_biomass.to_dict(),
            "yield_per_substrate": self.yield_per_substrate,
            "yield_per_substrate_units": "biomass formula unit / substrate formula unit",
            "yield_per_carbon": self.yield_per_carbon,
            "yield_per_carbon_units": "C-mol biomass / C-mol substrate",
            "carbon_ceiling_per_substrate": self.carbon_ceiling_per_substrate,
            "oxygen_per_cmol_biomass": self.oxygen_per_cmol_biomass,
            "coefficients_per_biomass_formula_unit": dict(self.solution.coefficients),
            "solution": self.solution.to_dict(),
            "maturity": self.maturity,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "limitations": (
                "A black-box prediction: the dissipation is an empirical correlation and the "
                "formation energies are used as given for their declared conditions. No rate, "
                "maintenance, product formation, or organism-specific physiology is represented."
            ),
        }


def _positive_dissipation(parameter: Parameter) -> Quantity:
    parameter.validate_provenance()
    parameter.validate_value()
    quantity = assert_compatible(cast(Quantity, parameter.quantity), _DISSIPATION_UNITS, name=parameter.symbol)
    value = float(quantity.magnitude)
    if not math.isfinite(value) or value <= 0.0:
        raise GrowthEnergeticsError(
            f"dissipation_per_cmol_biomass {parameter.symbol!r} must be finite and positive; got {value!r}."
        )
    return quantity


class GrowthEnergeticsError(ValueError):
    """Raised when a growth-energetics bound cannot be formed or is violated."""


@dataclass(frozen=True)
class GibbsEnergyYieldBound:
    """A thermodynamic upper bound on biomass yield from sourced Gibbs energies.

    `catabolic_delta_gibbs` is the free energy released per unit of substrate or
    degradation product catabolised and must be negative. `anabolic_delta_gibbs`
    is the free energy required per unit of biomass formed and must be positive.
    The resulting bound carries units of biomass per substrate.
    """

    catabolic_delta_gibbs: Parameter
    anabolic_delta_gibbs: Parameter

    def __post_init__(self) -> None:
        for parameter in (self.catabolic_delta_gibbs, self.anabolic_delta_gibbs):
            if parameter.value is None:
                raise GrowthEnergeticsError(
                    f"Gibbs energy {parameter.symbol!r} must have an explicit value."
                )
            if not has_text(parameter.source):
                raise ProvenanceError(
                    f"Gibbs energy {parameter.symbol!r} requires a source; this bound "
                    "does not invent energy values."
                )
        if self._catabolic_magnitude() >= 0.0:
            raise GrowthEnergeticsError(
                "catabolic_delta_gibbs must be negative: catabolism must release free energy."
            )
        if self._anabolic_magnitude() <= 0.0:
            raise GrowthEnergeticsError(
                "anabolic_delta_gibbs must be positive: biomass synthesis must require free energy."
            )

    @staticmethod
    def _quantity(parameter: Parameter) -> Quantity:
        """Return a parameter's quantity, narrowing away the optional value."""

        quantity = parameter.quantity
        if quantity is None:
            raise GrowthEnergeticsError(
                f"Gibbs energy {parameter.symbol!r} must have an explicit value with units."
            )
        return quantity

    def _catabolic_magnitude(self) -> float:
        return float(self._quantity(self.catabolic_delta_gibbs).magnitude)

    def _anabolic_magnitude(self) -> float:
        return float(self._quantity(self.anabolic_delta_gibbs).magnitude)

    def maximum_yield(self) -> Quantity:
        """Return the reversible-limit yield ceiling, biomass per substrate."""

        catabolic = self._quantity(self.catabolic_delta_gibbs)
        anabolic = self._quantity(self.anabolic_delta_gibbs)
        return abs(catabolic) / anabolic

    def validate_yield(
        self,
        declared_yield: Quantity,
        *,
        symbol: str = "Y_B",
        carbon_limit: Quantity | None = None,
    ) -> ValidationResult:
        """Check a declared yield against the thermodynamic and conservation ceilings.

        ``carbon_limit`` is the largest yield element conservation admits on the
        same basis as the Gibbs energies (for example 1 C-mol/C-mol, or C_S/C_X
        formula units per formula unit). The effective ceiling is the smaller of
        the two; the Gibbs bound alone knows nothing about atoms.
        """

        bound = self.maximum_yield()
        declared = assert_compatible(declared_yield, str(bound.units), name=symbol)
        declared_value = float(declared.to(bound.units).magnitude)
        thermodynamic_value = float(bound.magnitude)
        if not math.isfinite(declared_value) or declared_value < 0.0:
            raise GrowthEnergeticsError(f"{symbol} must be finite and non-negative.")
        carbon_value: float | None = None
        if carbon_limit is not None:
            carbon_value = float(
                assert_compatible(carbon_limit, str(bound.units), name="carbon_limit").to(bound.units).magnitude
            )
            if not math.isfinite(carbon_value) or carbon_value <= 0.0:
                raise GrowthEnergeticsError("carbon_limit must be finite and positive.")
        if carbon_value is not None and carbon_value < thermodynamic_value:
            bound_value, binding = carbon_value, "carbon_conservation"
        else:
            bound_value, binding = thermodynamic_value, "thermodynamic"
        passed = declared_value <= bound_value
        fraction = declared_value / bound_value if bound_value > 0 else math.inf
        return ValidationResult(
            name="gibbs_energy_yield_bound",
            passed=passed,
            message=(
                f"{symbol} is within the thermodynamic and conservation ceilings."
                if passed
                else (
                    f"{symbol} exceeds the thermodynamic ceiling: the configured growth "
                    "would create free energy, which is impossible."
                    if binding == "thermodynamic"
                    else f"{symbol} exceeds the carbon conservation limit: the configured growth "
                    "would create carbon, which is impossible."
                )
            ),
            details={
                "symbol": symbol,
                "declared_yield": declared_value,
                "maximum_yield": bound_value,
                "thermodynamic_ceiling": thermodynamic_value,
                "carbon_limit": carbon_value,
                "binding_limit": binding,
                "units": str(bound.units),
                "fraction_of_ceiling": fraction,
                "catabolic_delta_gibbs_source": self.catabolic_delta_gibbs.source,
                "anabolic_delta_gibbs_source": self.anabolic_delta_gibbs.source,
                "interpretation": (
                    "The ceiling assumes reversible, zero-dissipation growth. Real "
                    "organisms operate strictly below it, so a declared yield close to "
                    "the ceiling should itself be treated as suspect."
                ),
            },
        )

    def enforce_yield(
        self,
        declared_yield: Quantity,
        *,
        symbol: str = "Y_B",
        carbon_limit: Quantity | None = None,
    ) -> ValidationResult:
        """Validate a declared yield and raise when it exceeds the ceiling."""

        result = self.validate_yield(declared_yield, symbol=symbol, carbon_limit=carbon_limit)
        if not result.passed:
            raise GrowthEnergeticsError(
                f"{result.message} declared={result.details['declared_yield']!r} "
                f"maximum={result.details['maximum_yield']!r} {result.details['units']}"
            )
        return result

    def to_dict(self) -> dict[str, Any]:
        bound = self.maximum_yield()
        return {
            "catabolic_delta_gibbs": self.catabolic_delta_gibbs.to_dict(),
            "anabolic_delta_gibbs": self.anabolic_delta_gibbs.to_dict(),
            "maximum_yield": float(bound.magnitude),
            "maximum_yield_units": str(bound.units),
            "claim_boundary": (
                "Upper bound only. Thermodynamics constrains yield; it does not "
                "predict a reaction rate, which depends on an enzyme's activation "
                "barrier rather than the reaction's Gibbs energy. The bound ignores "
                "element conservation unless validate_yield receives a carbon_limit."
            ),
        }


__all__ = [
    "DissipationYieldPrediction",
    "GibbsEnergyYieldBound",
    "GrowthEnergeticsError",
    "HEIJNEN_DISSIPATION_CONSTANTS",
    "HEIJNEN_DISSIPATION_MATURITY",
    "HEIJNEN_DISSIPATION_SOURCE",
    "HEIJNEN_DISSIPATION_VALIDITY",
    "heijnen_dissipation_assumption",
    "heijnen_dissipation_from_composition",
    "heijnen_dissipation_per_cmol_biomass",
]
