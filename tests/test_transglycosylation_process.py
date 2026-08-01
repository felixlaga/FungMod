from __future__ import annotations

from dataclasses import replace

import pytest

from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.io import ProcessConfig
from fungal_model.processes import (
    ProcessBuildContext,
    ProcessLibrary,
    ProductReleaseMap,
    SubstrateTransglycosylationProcess,
)
from fungal_model.processes.transglycosylation import TransglycosylationBranch


PRIMARY_SOURCE = "https://doi.org/10.1016/j.carres.2004.09.019"
MATURITY = "literature_backed_software_tested"


def test_coupled_branch_rates_match_published_substrate_transfer_law() -> None:
    hydrolysis = _process(
        branch="hydrolysis",
        product_map=ProductReleaseMap(
            reactants={"S": 1.0},
            products={"G": 2.0},
        ),
    )
    transglycosylation = _process(
        branch="transglycosylation",
        product_map=ProductReleaseMap(
            reactants={"S": 2.0},
            products={"G": 1.0, "T": 1.0},
        ),
    )
    state = {
        "S": Q_(2.0, "millimolar"),
        "E": Q_(0.1, "millimolar"),
        "G": Q_(0.0, "millimolar"),
        "T": Q_(0.0, "millimolar"),
    }
    parameters = _parameters()

    hydrolysis_rate = hydrolysis.rate(state, Q_(0.0, "second"), parameters)
    transfer_rate = transglycosylation.rate(state, Q_(0.0, "second"), parameters)

    denominator = 0.5 + 2.0 + 2.0**2 / 4.0
    assert hydrolysis_rate.magnitude == pytest.approx(0.1 * 10.0 * 2.0 / denominator)
    assert transfer_rate.magnitude == pytest.approx(0.1 * 2.0 * (2.0**2 / 4.0) / denominator)
    assert hydrolysis.contributions(hydrolysis_rate)["G"].magnitude == pytest.approx(
        2.0 * hydrolysis_rate.magnitude
    )
    assert transglycosylation.contributions(transfer_rate)["S"].magnitude == pytest.approx(
        -2.0 * transfer_rate.magnitude
    )
    assert transglycosylation.contributions(transfer_rate)["T"].magnitude == pytest.approx(
        transfer_rate.magnitude
    )


def test_substrate_transfer_rate_is_zero_without_donor_acceptor_substrate() -> None:
    process = _process(
        branch="transglycosylation",
        product_map=ProductReleaseMap(
            reactants={"S": 2.0},
            products={"G": 1.0, "T": 1.0},
        ),
    )
    state = {
        "S": Q_(0.0, "millimolar"),
        "E": Q_(0.1, "millimolar"),
        "G": Q_(0.0, "millimolar"),
        "T": Q_(0.0, "millimolar"),
    }

    rate = process.rate(state, Q_(0.0, "second"), _parameters())

    assert rate.magnitude == pytest.approx(0.0)


def test_transglycosylation_process_rejects_unsourced_or_mismatched_stoichiometry() -> None:
    product_map = ProductReleaseMap(
        reactants={"S": 2.0},
        products={"G": 1.0, "T": 1.0},
    )

    with pytest.raises(InvalidMechanismError, match="primary_source"):
        _process(branch="transglycosylation", product_map=product_map, primary_source="")
    with pytest.raises(InvalidMechanismError, match="maturity"):
        _process(branch="transglycosylation", product_map=product_map, maturity="exploratory")
    with pytest.raises(InvalidMechanismError, match="consume exactly 2"):
        _process(
            branch="transglycosylation",
            product_map=ProductReleaseMap(reactants={"S": 1.0}, products={"T": 1.0}),
        )


def test_factory_builds_both_branches_and_fails_closed_on_unsupported_composition() -> None:
    context = ProcessBuildContext(
        state_units={
            "S": "millimolar",
            "E": "millimolar",
            "G": "millimolar",
            "T": "millimolar",
        },
        product_maps={
            "hydrolysis": ProductReleaseMap(reactants={"S": 1.0}, products={"G": 2.0}),
            "transfer": ProductReleaseMap(
                reactants={"S": 2.0},
                products={"G": 1.0, "T": 1.0},
            ),
        },
    )
    hydrolysis_config = _process_config(branch="hydrolysis", product_map="hydrolysis")
    transfer_config = _process_config(branch="transglycosylation", product_map="transfer")

    processes = ProcessLibrary.default_foundation().build_processes(
        context,
        (hydrolysis_config, transfer_config),
    )

    assert [process.branch for process in processes] == ["hydrolysis", "transglycosylation"]
    assert all(isinstance(process, SubstrateTransglycosylationProcess) for process in processes)
    assert processes[0].to_dict()["primary_source"] == PRIMARY_SOURCE
    assert "r_t = E*kcat_t" in processes[1].to_dict()["equation"]

    unsupported = replace(
        transfer_config,
        modifiers=({"type": "product_inhibition", "product_state": "G"},),
    )
    decision = ProcessLibrary.default_foundation().build_decisions(context, (unsupported,))[0]
    assert not decision.can_build
    assert "process.modifiers" in decision.incompatible_entities


def _process(
    *,
    branch: TransglycosylationBranch,
    product_map: ProductReleaseMap,
    primary_source: str = PRIMARY_SOURCE,
    maturity: str = MATURITY,
) -> SubstrateTransglycosylationProcess:
    return SubstrateTransglycosylationProcess(
        name=f"benchmark {branch}",
        branch=branch,
        substrate_state="S",
        enzyme_state="E",
        substrate_units="millimolar",
        enzyme_units="millimolar",
        rate_units="millimolar / second",
        hydrolysis_km_symbol="Km_h",
        transglycosylation_km_symbol="Km_t",
        hydrolysis_kcat_symbol="kcat_h",
        transglycosylation_kcat_symbol="kcat_t",
        product_release_map=product_map,
        primary_source=primary_source,
        maturity=maturity,
    )


def _parameters() -> ParameterSet:
    return ParameterSet(
        [
            _parameter("Km_h", 0.5, "millimolar"),
            _parameter("Km_t", 4.0, "millimolar"),
            _parameter("kcat_h", 10.0, "1 / second"),
            _parameter("kcat_t", 2.0, "1 / second"),
        ]
    )


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial transglycosylation software benchmark; no scientific claim.",
        confidence_level="testing",
        notes="Used only to verify the generic coupled branch equation.",
        measurement_method="defined benchmark value",
    )


def _process_config(*, branch: str, product_map: str) -> ProcessConfig:
    return ProcessConfig.from_mapping(
        {
            "id": f"benchmark_{branch}",
            "process_type": "substrate_transglycosylation",
            "branch": branch,
            "primary_source": PRIMARY_SOURCE,
            "maturity": MATURITY,
            "states": {"substrate": "S", "enzyme": "E"},
            "parameters": {
                "hydrolysis_km": "Km_h",
                "transglycosylation_km": "Km_t",
                "hydrolysis_kcat": "kcat_h",
                "transglycosylation_kcat": "kcat_t",
                "rate_units": "millimolar / second",
            },
            "product_map": product_map,
        }
    )
