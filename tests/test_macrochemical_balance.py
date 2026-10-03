from __future__ import annotations

import pytest

from fungal_model.chemistry import (
    MACROCHEMICAL_BALANCE_MATURITY,
    ElementalComposition,
    MacrochemicalBalance,
    MacrochemicalBalanceError,
    MacrochemicalSpecies,
)
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, UnitError
from fungal_model.core.validators import validate_charge_balance, validate_elemental_balance


FORMULA_SOURCE = "Molecular formula; exact chemical identity, not a measured parameter."
ARTIFICIAL_SOURCE = "Artificial macrochemical benchmark; no organism or physical claim."
CONDITIONS = "Artificial benchmark conditions; no physical standard state is claimed."

# Artificial formation energies in kJ/mol, chosen for hand-checkable arithmetic.
ARTIFICIAL_GIBBS = {
    "substrate": -150.0,
    "nitrogen_source": -20.0,
    "oxygen": 0.0,
    "biomass": -70.0,
    "carbon_dioxide": -400.0,
    "water": -240.0,
}
ARTIFICIAL_ENTHALPY = {
    "substrate": -210.0,
    "nitrogen_source": -80.0,
    "oxygen": 0.0,
    "biomass": -90.0,
    "carbon_dioxide": -390.0,
    "water": -290.0,
}


def test_complete_oxidation_stoichiometry_follows_from_conservation_alone() -> None:
    balance = MacrochemicalBalance(
        name="glucose complete oxidation",
        species=(
            _species("glucose", "C6H12O6"),
            _species("oxygen", "O2"),
            _species("carbon_dioxide", "CO2"),
            _species("water", "H2O"),
        ),
        source=FORMULA_SOURCE,
    )

    solution = balance.solve({"glucose": -1.0})

    assert solution.coefficients == pytest.approx(
        {"glucose": -1.0, "oxygen": -6.0, "carbon_dioxide": 6.0, "water": 6.0}
    )
    assert solution.fixed_species == ("glucose",)
    assert set(solution.residuals) == {"C", "H", "O", "charge"}
    assert all(abs(value) <= 1e-12 for value in solution.residuals.values())


def test_charged_inorganic_redox_is_solved_with_the_charge_balance() -> None:
    balance = MacrochemicalBalance(
        name="ferrous iron oxidation",
        species=(
            _species("ferrous", "Fe", charge=2.0),
            _species("ferric", "Fe", charge=3.0),
            _species("oxygen", "O2"),
            _species("proton", "H", charge=1.0),
            _species("water", "H2O"),
        ),
        source=FORMULA_SOURCE,
    )

    solution = balance.solve({"oxygen": -1.0})

    assert solution.coefficients == pytest.approx(
        {"ferrous": -4.0, "ferric": 4.0, "oxygen": -1.0, "proton": -4.0, "water": 2.0}
    )


def test_growth_exchange_stoichiometry_is_determined_by_one_yield_coefficient() -> None:
    solution = _growth_balance().solve({"biomass": 1.0, "substrate": -2.0})

    assert solution.coefficients == pytest.approx(
        {
            "substrate": -2.0,
            "nitrogen_source": -0.2,
            "oxygen": -0.95,
            "biomass": 1.0,
            "carbon_dioxide": 1.0,
            "water": 1.4,
        }
    )


def test_solved_reaction_passes_the_existing_static_balance_validators() -> None:
    metadata = _growth_balance().solve({"biomass": 1.0, "substrate": -2.0}).stoichiometric_metadata()

    assert {term.species for term in metadata.reactants} == {"substrate", "nitrogen_source", "oxygen"}
    assert {term.species for term in metadata.products} == {"biomass", "carbon_dioxide", "water"}
    assert validate_elemental_balance(metadata).passed
    assert validate_charge_balance(metadata).passed


def test_underdetermined_balance_reports_missing_degrees_of_freedom() -> None:
    with pytest.raises(MacrochemicalBalanceError, match="1 degree"):
        _growth_balance().solve({"biomass": 1.0})


def test_inconsistent_species_set_is_rejected_with_residuals() -> None:
    balance = MacrochemicalBalance(
        name="oxidation without a hydrogen sink",
        species=(
            _species("glucose", "C6H12O6"),
            _species("oxygen", "O2"),
            _species("carbon_dioxide", "CO2"),
        ),
        source=FORMULA_SOURCE,
    )

    with pytest.raises(MacrochemicalBalanceError, match="cannot satisfy conservation.*'H'"):
        balance.solve({"glucose": -1.0})


def test_fixed_coefficients_must_name_known_species_and_set_a_scale() -> None:
    balance = _growth_balance()

    with pytest.raises(MacrochemicalBalanceError, match="unknown species"):
        balance.solve({"methane": -1.0})
    with pytest.raises(MacrochemicalBalanceError, match="nonzero coefficient"):
        balance.solve({"biomass": 0.0, "substrate": 0.0})
    with pytest.raises(MacrochemicalBalanceError, match="finite"):
        balance.solve({"biomass": 1.0, "substrate": float("nan")})


def test_missing_provenance_fails_closed() -> None:
    unsourced_formula = MacrochemicalSpecies(
        name="water",
        composition=ElementalComposition.from_formula("H2O", source=None),
        charge=0.0,
        charge_source=FORMULA_SOURCE,
    )
    unsourced_charge = MacrochemicalSpecies(
        name="water",
        composition=ElementalComposition.from_formula("H2O", source=FORMULA_SOURCE),
        charge=0.0,
        charge_source=None,
    )
    oxygen = _species("oxygen", "O2")
    hydrogen = _species("hydrogen", "H2")

    for water in (unsourced_formula, unsourced_charge):
        balance = MacrochemicalBalance(
            name="water formation", species=(hydrogen, oxygen, water), source=FORMULA_SOURCE
        )
        with pytest.raises(ProvenanceError):
            balance.solve({"oxygen": -1.0})
    with pytest.raises(ProvenanceError, match="missing a source"):
        MacrochemicalBalance(
            name="water formation",
            species=(hydrogen, oxygen, _species("water", "H2O")),
            source=None,
        ).solve({"oxygen": -1.0})


def test_reaction_energies_are_coefficient_weighted_formation_energies() -> None:
    solution = _growth_balance().solve({"biomass": 1.0, "substrate": -2.0})

    # delta_r G = -490 * s + 478 and delta_r H = -470 * s + 490 in kJ/mol for s = 2.
    assert solution.reaction_gibbs().to("kilojoule / mole").magnitude == pytest.approx(-502.0)
    assert solution.reaction_enthalpy().to("kilojoule / mole").magnitude == pytest.approx(-450.0)


def test_reaction_energy_requires_conditions_and_every_formation_energy() -> None:
    undeclared = _growth_balance(conditions=None).solve({"biomass": 1.0, "substrate": -2.0})
    with pytest.raises(MacrochemicalBalanceError, match="thermodynamic_conditions"):
        undeclared.reaction_gibbs()

    partial = _growth_balance(without_gibbs="water").solve({"biomass": 1.0, "substrate": -2.0})
    with pytest.raises(MacrochemicalBalanceError, match="'water' has no formation_gibbs"):
        partial.reaction_gibbs()

    formulas_only = _growth_balance(with_energies=False).solve({"biomass": 1.0, "substrate": -2.0})
    with pytest.raises(MacrochemicalBalanceError, match="formation_enthalpy"):
        formulas_only.reaction_enthalpy()


def test_entropy_budget_splits_production_into_heat_export_and_matter_change() -> None:
    solution = _growth_balance().solve({"biomass": 1.0, "substrate": -2.0})

    budget = solution.entropy_budget(
        extent_rate=Q_(2.0e-3, "mole / second"),
        temperature=Q_(300.0, "kelvin"),
        include_heat=True,
    )

    assert budget.entropy_production_rate.to("watt / kelvin").magnitude == pytest.approx(502.0e3 * 2.0e-3 / 300.0)
    assert budget.heat_release_rate is not None
    assert budget.heat_entropy_export_rate is not None
    assert budget.matter_entropy_change_rate is not None
    assert budget.heat_release_rate.to("watt").magnitude == pytest.approx(900.0)
    assert budget.heat_entropy_export_rate.magnitude == pytest.approx(3.0)
    assert budget.entropy_production_rate.magnitude == pytest.approx(
        budget.heat_entropy_export_rate.magnitude + budget.matter_entropy_change_rate.magnitude
    )
    assert budget.is_second_law_consistent
    assert budget.to_dict()["is_second_law_consistent"] is True


def test_entropy_budget_without_heat_needs_only_gibbs_and_flags_second_law_violation() -> None:
    solution = _growth_balance(with_enthalpy=False).solve({"biomass": 1.0, "substrate": -2.0})

    reversed_budget = solution.entropy_budget(
        extent_rate=Q_(-1.0, "mole / second / meter ** 3"),
        temperature=Q_(300.0, "kelvin"),
        include_heat=False,
    )

    assert reversed_budget.heat_release_rate is None
    assert str(reversed_budget.entropy_production_rate.units) == "watt / kelvin / meter ** 3"
    assert not reversed_budget.is_second_law_consistent
    with pytest.raises(MacrochemicalBalanceError, match="formation_enthalpy"):
        solution.entropy_budget(
            extent_rate=Q_(1.0, "mole / second"),
            temperature=Q_(300.0, "kelvin"),
            include_heat=True,
        )


def test_entropy_budget_rejects_non_rate_units_and_non_positive_temperature() -> None:
    solution = _growth_balance().solve({"biomass": 1.0, "substrate": -2.0})

    with pytest.raises(UnitError, match="amount rate"):
        solution.entropy_budget(
            extent_rate=Q_(1.0, "kilogram / second"),
            temperature=Q_(300.0, "kelvin"),
            include_heat=False,
        )
    with pytest.raises(MacrochemicalBalanceError, match="temperature"):
        solution.entropy_budget(
            extent_rate=Q_(1.0, "mole / second"),
            temperature=Q_(0.0, "kelvin"),
            include_heat=False,
        )


def test_reversible_limit_and_stated_dissipation_fix_the_substrate_requirement() -> None:
    balance = _growth_balance()

    reversible = balance.solve_for_reaction_gibbs(
        fixed_coefficients={"biomass": 1.0},
        free_species="substrate",
        reaction_gibbs=_energy("delta_r_G_target", 0.0),
    )
    dissipative = balance.solve_for_reaction_gibbs(
        fixed_coefficients={"biomass": 1.0},
        free_species="substrate",
        reaction_gibbs=_energy("delta_r_G_target", -300.0),
    )

    assert reversible.coefficients["substrate"] == pytest.approx(-478.0 / 490.0)
    assert reversible.reaction_gibbs().magnitude == pytest.approx(0.0, abs=1e-6)
    assert dissipative.coefficients["substrate"] == pytest.approx(-778.0 / 490.0)
    assert dissipative.reaction_gibbs().to("kilojoule / mole").magnitude == pytest.approx(-300.0)
    # Dissipation costs substrate: the yield ceiling is the reversible limit.
    assert abs(dissipative.coefficients["substrate"]) > abs(reversible.coefficients["substrate"])


def test_gibbs_target_solve_rejects_fixed_free_overlap_unsourced_and_flat_energy() -> None:
    balance = _growth_balance()

    with pytest.raises(MacrochemicalBalanceError, match="both fixed and free"):
        balance.solve_for_reaction_gibbs(
            fixed_coefficients={"biomass": 1.0, "substrate": -2.0},
            free_species="substrate",
            reaction_gibbs=_energy("delta_r_G_target", 0.0),
        )
    with pytest.raises(ProvenanceError):
        balance.solve_for_reaction_gibbs(
            fixed_coefficients={"biomass": 1.0},
            free_species="substrate",
            reaction_gibbs=_energy("delta_r_G_target", 0.0, source=None),
        )
    with pytest.raises(MacrochemicalBalanceError, match="does not depend"):
        _growth_balance(gibbs_scale=0.0).solve_for_reaction_gibbs(
            fixed_coefficients={"biomass": 1.0},
            free_species="substrate",
            reaction_gibbs=_energy("delta_r_G_target", -300.0),
        )


def test_balance_reports_fixed_maturity_and_claim_boundary() -> None:
    balance = _growth_balance()

    assert balance.to_dict()["maturity"] == MACROCHEMICAL_BALANCE_MATURITY
    assert "No rate, yield" in balance.to_dict()["limitations"]
    assert "sign_convention" in balance.solve({"biomass": 1.0, "substrate": -2.0}).to_dict()
    with pytest.raises(ValueError, match="maturity"):
        MacrochemicalBalance(
            name="overclaimed",
            species=balance.species,
            source=ARTIFICIAL_SOURCE,
            maturity="validated",
        )
    with pytest.raises(ValueError, match="distinct"):
        MacrochemicalBalance(
            name="duplicate",
            species=(_species("water", "H2O"), _species("water", "H2O")),
            source=FORMULA_SOURCE,
        )


def _energy(symbol: str, kilojoule_per_mole: float, *, source: str | None = ARTIFICIAL_SOURCE) -> Parameter:
    return Parameter(
        name=symbol,
        symbol=symbol,
        value=kilojoule_per_mole,
        units="kilojoule / mole",
        uncertainty=None,
        source=source,
        confidence_level="testing",
        notes="Artificial benchmark value.",
    )


def _species(
    name: str,
    formula: str,
    *,
    charge: float = 0.0,
    gibbs: float | None = None,
    enthalpy: float | None = None,
) -> MacrochemicalSpecies:
    return MacrochemicalSpecies(
        name=name,
        composition=ElementalComposition.from_formula(formula, source=FORMULA_SOURCE),
        charge=charge,
        charge_source=FORMULA_SOURCE,
        formation_gibbs=None if gibbs is None else _energy(f"delta_f_G_{name}", gibbs),
        formation_enthalpy=None if enthalpy is None else _energy(f"delta_f_H_{name}", enthalpy),
    )


def _growth_balance(
    *,
    conditions: str | None = CONDITIONS,
    with_energies: bool = True,
    with_enthalpy: bool = True,
    without_gibbs: str | None = None,
    gibbs_scale: float = 1.0,
) -> MacrochemicalBalance:
    """Artificial aerobic growth per carbon-mole of an artificial biomass composition."""

    formulas = {
        "substrate": "CH2O",
        "nitrogen_source": "NH3",
        "oxygen": "O2",
        "carbon_dioxide": "CO2",
        "water": "H2O",
    }

    def energies(name: str) -> dict[str, float | None]:
        if not with_energies:
            return {"gibbs": None, "enthalpy": None}
        return {
            "gibbs": None if name == without_gibbs else gibbs_scale * ARTIFICIAL_GIBBS[name],
            "enthalpy": ARTIFICIAL_ENTHALPY[name] if with_enthalpy else None,
        }

    biomass_energies = energies("biomass")
    biomass = MacrochemicalSpecies(
        name="biomass",
        composition=ElementalComposition.from_elements(
            {"C": 1.0, "H": 1.8, "O": 0.5, "N": 0.2},
            source=ARTIFICIAL_SOURCE,
            formula="artificial_biomass_per_carbon_mole",
        ),
        charge=0.0,
        charge_source=ARTIFICIAL_SOURCE,
        formation_gibbs=(
            None if biomass_energies["gibbs"] is None else _energy("delta_f_G_biomass", biomass_energies["gibbs"])
        ),
        formation_enthalpy=(
            None
            if biomass_energies["enthalpy"] is None
            else _energy("delta_f_H_biomass", biomass_energies["enthalpy"])
        ),
    )
    return MacrochemicalBalance(
        name="artificial aerobic growth",
        species=(
            *(_species(name, formula, **energies(name)) for name, formula in formulas.items()),
            biomass,
        ),
        source=ARTIFICIAL_SOURCE,
        thermodynamic_conditions=conditions,
    )
