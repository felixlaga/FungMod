"""Explicit illustrative chemistry/kinetics, NOT organism-calibrated parameters.

Used only for mechanistic demonstrations and numerical verification. The C6
polymer repeat and sugar chemistry are identities; empirical biomass/protein
formulas, yields, capacities, affinities and operating state are assumptions.
These values must not enter a registry as measured fungal parameters.
"""
from __future__ import annotations

from dataclasses import replace

from fungal_model.chemistry import ElementalComposition, MacrochemicalBalance, MacrochemicalSpecies
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity
from fungal_model.fungi import DegradingCulture, ResourceLimitedCulture, RespiratoryGrowthModel

ASSUMPTION = "Explicit illustrative assumption for a homogeneous degradation feedback example; not measured or calibrated."


def assumed(name: str, value: float, units: str) -> Parameter:
    return Parameter(name, name, value, units, None, ASSUMPTION, "low", "Unknown empirical uncertainty; no organism claim.")


def illustrative_culture(*, allocation: float, gas_transfer_per_h: float,
                         catalytic_per_h: float, inactivation_per_h: float) -> DegradingCulture:
    def species(name, formula, charge=0):
        composition = (ElementalComposition.from_formula(formula, source="Chemical formula identity: " + formula)
                       if isinstance(formula, str) else ElementalComposition.from_elements(formula, source=ASSUMPTION))
        return MacrochemicalSpecies(name, composition, charge, ASSUMPTION)

    sugar = species("sugar", "C6H12O6")
    nitrogen, oxygen = species("ammonium", "NH4", 1), species("oxygen", "O2")
    co2, water, proton = species("carbon_dioxide", "CO2"), species("water", "H2O"), species("proton", "H", 1)
    biomass = species("biomass", {"C": 1, "H": 1.8, "N": .2, "O": .5})
    enzyme = species("active_protein", {"C": 1, "H": 1.6, "N": .3, "O": .3})
    inactive, polymer = replace(enzyme, name="inactive_protein"), species("polymer", "C6H10O5")
    growth = MacrochemicalBalance("illustrative growth chemistry", (sugar, nitrogen, oxygen, biomass, co2, water, proton), ASSUMPTION)
    metabolism = RespiratoryGrowthModel(growth, "sugar", "biomass", assumed("Y_XS", 3, "mol/mol"),
                                       assumed("m_S", .001, "1/h"), ASSUMPTION)
    culture = ResourceLimitedCulture(metabolism, "ammonium", "oxygen", ("carbon_dioxide", "water", "proton"),
        assumed("uptake_capacity", .1, "1/h"), assumed("K_S", .001, "mol/L"), assumed("K_N", .0001, "mol/L"),
        assumed("K_O", .00001, "mol/L"), assumed("dilution", 0, "1/h"), assumed("kLa", gas_transfer_per_h, "1/h"),
        assumed("oxygen_saturation", .00025, "mol/L"), {n: Q_(0, "mol/L") for n in ("sugar", "ammonium", "oxygen")}, ASSUMPTION)
    hydrolysis = MacrochemicalBalance("illustrative repeat-unit hydrolysis", (polymer, sugar, water), ASSUMPTION).solve({"polymer": -1})
    secretion = MacrochemicalBalance("illustrative protein synthesis", (sugar, nitrogen, oxygen, enzyme, co2, water, proton),
                                    ASSUMPTION).solve({"active_protein": 1, "sugar": -.5})
    return DegradingCulture(culture, polymer, enzyme, inactive, hydrolysis, secretion,
        assumed("substrate_allocation", allocation, "dimensionless"), assumed("catalytic_capacity", catalytic_per_h, "1/h"),
        assumed("K_polymer", .002, "mol/L"), assumed("inactivation_rate", inactivation_per_h, "1/h"), Q_(0, "mol/L"), ASSUMPTION)


def illustrative_initial_state(*, nitrogen_mol_L: float) -> dict[str, Quantity]:
    return {n: Q_(v, "mol/L") for n, v in {"sugar": .001, "biomass": .001, "ammonium": nitrogen_mol_L,
            "oxygen": .00025, "polymer": .02, "active_protein": 0, "inactive_protein": 0}.items()}
