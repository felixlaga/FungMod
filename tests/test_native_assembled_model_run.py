from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.processes import (
    AccessibleSitePool,
    AccessibleSurfaceAreaModel,
    FirstOrderDecayProcess,
    LangmuirAdsorptionModel,
    ModelBuilder,
    ProcessRegistry,
    ProductReleaseMap,
    SurfaceCatalysisModel,
    SurfaceCatalysisProcess,
)
from fungal_model.results import SimulationResult


def parameter(*, name: str, symbol: str, value, units: str) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial native model-run benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only to test native AssembledModel.run.",
        measurement_method="defined benchmark value",
    )


def test_assembled_model_run_solves_first_order_benchmark() -> None:
    process = FirstOrderDecayProcess(
        name="generic first-order A to B",
        substrate_state="A",
        product_state="B",
        rate_constant_symbol="k",
        state_units="mole / liter",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet(
            [parameter(name="rate constant", symbol="k", value=0.1, units="1 / second")]
        ),
        validators=[
            validate_non_negative,
            lambda result: validate_mass_balance(result, conserved_weights={"A": 1.0, "B": 1.0}),
        ],
    ).assemble()

    result = model.run(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(5.0, "second")),
        t_eval=Q_(np.linspace(0.0, 5.0, 11), "second"),
        name="native_first_order",
    )

    assert isinstance(result, SimulationResult)
    assert result.state("A").magnitude[-1] < result.state("A").magnitude[0]
    assert result.state("B").magnitude[-1] > result.state("B").magnitude[0]
    assert result.rate("generic first-order A to B").units == Q_(1, "mole / liter / second").units
    assert len(result.validation_results) == 2
    assert all(validation.passed for validation in result.validation_results)
    assert result.assembly_report.success
    assert result.solver_metadata["backend"] == "scipy.solve_ivp"


def test_assembled_model_run_solves_generic_surface_benchmark() -> None:
    process = SurfaceCatalysisProcess(
        name="dummy surface catalysis",
        substrate_state="solid_substrate_amount",
        enzyme_state="free_catalyst_concentration",
        substrate_units="kilogram",
        enzyme_units="mole / liter",
        accessible_site_pool=AccessibleSitePool(
            name="dummy accessible sites",
            bond_type="generic_linkage",
        ),
        accessible_surface_model=AccessibleSurfaceAreaModel.from_parameter(
            name="dummy accessible area",
            parameter_symbol="A_dummy",
        ),
        adsorption_model=LangmuirAdsorptionModel(
            adsorption_symbol="K_ads_dummy",
            enzyme_units="mole / liter",
            source="Artificial native surface benchmark.",
        ),
        catalytic_model=SurfaceCatalysisModel(
            surface_rate_symbol="k_surface_dummy",
            rate_units="kilogram / second",
            source="Artificial native surface benchmark.",
        ),
        product_release_map=ProductReleaseMap.one_to_one(
            substrate_state="solid_substrate_amount",
            product_state="released_product_amount",
        ),
        state_units={
            "solid_substrate_amount": "kilogram",
            "released_product_amount": "kilogram",
            "free_catalyst_concentration": "mole / liter",
        },
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("surface_catalysis",),
        parameters=ParameterSet(
            [
                parameter(name="adsorption", symbol="K_ads_dummy", value=1.0, units="liter / mole"),
                parameter(
                    name="surface rate",
                    symbol="k_surface_dummy",
                    value=1.0e-6,
                    units="kilogram / meter ** 2 / second",
                ),
                parameter(name="area", symbol="A_dummy", value=0.2, units="meter ** 2"),
            ]
        ),
    ).assemble()

    result = model.run(
        initial_state={
            "solid_substrate_amount": Q_(1.0e-4, "kilogram"),
            "released_product_amount": Q_(0.0, "kilogram"),
            "free_catalyst_concentration": Q_(1.0, "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_(np.linspace(0.0, 10.0, 11), "second"),
        validators=[
            lambda raw: validate_mass_balance(
                raw,
                conserved_weights={
                    "solid_substrate_amount": 1.0,
                    "released_product_amount": 1.0,
                },
            )
        ],
        name="native_surface",
    )

    assert result.state("solid_substrate_amount").magnitude[-1] < result.state("solid_substrate_amount").magnitude[0]
    assert result.state("released_product_amount").magnitude[-1] > 0.0
    assert result.rate("dummy surface catalysis").magnitude[0] > 0.0
    assert result.validation_results[0].passed


def test_assembled_model_run_rejects_missing_initial_state() -> None:
    process = FirstOrderDecayProcess(
        name="generic first-order A to B",
        substrate_state="A",
        product_state="B",
        rate_constant_symbol="k",
        state_units="mole / liter",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet(
            [parameter(name="rate constant", symbol="k", value=0.1, units="1 / second")]
        ),
    ).assemble()

    with pytest.raises(ValueError, match="Initial state mismatch"):
        model.run(
            initial_state={"A": Q_(1.0, "mole / liter")},
            t_span=(Q_(0.0, "second"), Q_(1.0, "second")),
        )


def test_assembled_model_run_rejects_unsupported_geometry() -> None:
    process = FirstOrderDecayProcess(
        name="generic first-order A to B",
        substrate_state="A",
        product_state="B",
        rate_constant_symbol="k",
        state_units="mole / liter",
    )
    model = ModelBuilder(
        geometry=SimpleNamespace(geometry_type="film_1d"),
        process_library=ProcessRegistry([process]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet(
            [parameter(name="rate constant", symbol="k", value=0.1, units="1 / second")]
        ),
    ).assemble()

    with pytest.raises(ValueError, match="supports only well_mixed"):
        model.run(
            initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
            t_span=(Q_(0.0, "second"), Q_(1.0, "second")),
        )
