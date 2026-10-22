"""The general reversible-inhibition law: limits, the four mechanisms, kernel parity and refusals."""

from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.modifiers import (
    CORNISH_BOWDEN_2012_SOURCE,
    InhibitorTerm,
    MixedInhibitionModifier,
    ProductInhibitionModifier,
)
from fungal_model.modifiers.enzyme_inhibition import _law_metadata
from fungal_model.processes.rate_modifiers import mixed_inhibition_modifier_from_config

SOURCE = "artificial inhibition benchmark; not biological evidence"
MATURITY = "framework_benchmark"
STATE_UNITS = {"S": "millimolar", "P": "millimolar", "G": "millimolar"}


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol, symbol=symbol, value=value, units=units, uncertainty=None,
        source=SOURCE, confidence_level="testing", notes=SOURCE,
    )


def _parameters(**values: float) -> ParameterSet:
    return ParameterSet([_parameter(symbol, value, "millimolar") for symbol, value in values.items()])


def _modifier(*terms: InhibitorTerm) -> MixedInhibitionModifier:
    return MixedInhibitionModifier(
        substrate_state="S", michaelis_constant_symbol="K_m", substrate_units="millimolar",
        inhibitors=terms, primary_source=SOURCE, maturity=MATURITY,
    )


def _competitive(ki: str = "K_ic") -> InhibitorTerm:
    return InhibitorTerm(state="P", units="millimolar", mechanism="competitive", competitive_constant_symbol=ki)


def _uncompetitive(ki: str = "K_iu") -> InhibitorTerm:
    return InhibitorTerm(state="P", units="millimolar", mechanism="uncompetitive", uncompetitive_constant_symbol=ki)


def _noncompetitive(ki: str = "K_i") -> InhibitorTerm:
    return InhibitorTerm(
        state="P", units="millimolar", mechanism="noncompetitive",
        competitive_constant_symbol=ki, uncompetitive_constant_symbol=ki,
    )


def _mixed() -> InhibitorTerm:
    return InhibitorTerm(
        state="P", units="millimolar", mechanism="mixed",
        competitive_constant_symbol="K_ic", uncompetitive_constant_symbol="K_iu",
    )


def _activity(modifier: MixedInhibitionModifier, parameters: ParameterSet, **state: float) -> float:
    quantity = modifier.activity(
        parameters=parameters, environment=None,  # type: ignore[arg-type]
        state={name: Q_(value, "millimolar") for name, value in state.items()},
    )
    return float(quantity.magnitude)


UNIT_CONSTANTS = _parameters(K_m=1.0, K_ic=1.0, K_iu=1.0, K_i=1.0)


def test_cornish_bowden_limits() -> None:
    parameters = _parameters(K_m=0.4, K_ic=0.5, K_iu=1.5, K_i=0.7)
    for term in (_competitive(), _uncompetitive(), _noncompetitive(), _mixed()):
        assert _activity(_modifier(term), parameters, S=0.8, P=0.0) == pytest.approx(1.0)
    competitive = _modifier(_competitive())
    assert _activity(competitive, parameters, S=1e9, P=5.0) == pytest.approx(1.0, abs=1e-8)
    assert _activity(competitive, parameters, S=0.0, P=5.0) == pytest.approx(1.0 / (1.0 + 5.0 / 0.5))
    uncompetitive = _modifier(_uncompetitive())
    assert _activity(uncompetitive, parameters, S=0.0, P=5.0) == pytest.approx(1.0)
    assert _activity(uncompetitive, parameters, S=1e9, P=5.0) == pytest.approx(1.0 / (1.0 + 5.0 / 1.5), abs=1e-8)


@pytest.mark.parametrize(
    ("substrate", "noncompetitive", "competitive", "uncompetitive"),
    [(0.1, 0.0455, 0.0476, 0.0833), (1.0, 0.2500, 0.3333, 0.3333), (10.0, 0.4545, 0.8333, 0.4762)],
)
def test_the_four_forms_reproduce_the_audit_rate_table(
    substrate: float, noncompetitive: float, competitive: float, uncompetitive: float
) -> None:
    # Processes audit table 2.7: V_max = K_m = K_i = 1, P = 1; rate = V_max S / (K_m + S) * activity.
    base_rate = substrate / (1.0 + substrate)
    forms = {
        "noncompetitive": (_modifier(_noncompetitive()), noncompetitive),
        "competitive": (_modifier(_competitive()), competitive),
        "uncompetitive": (_modifier(_uncompetitive()), uncompetitive),
    }
    for _, (modifier, expected) in forms.items():
        assert base_rate * _activity(modifier, UNIT_CONSTANTS, S=substrate, P=1.0) == pytest.approx(expected, abs=5e-5)
    mixed = _parameters(K_m=1.0, K_ic=1.0, K_iu=2.0)
    expected_mixed = substrate / (1.0 * (1.0 + 1.0 / 1.0) + substrate * (1.0 + 1.0 / 2.0))
    assert base_rate * _activity(_modifier(_mixed()), mixed, S=substrate, P=1.0) == pytest.approx(expected_mixed)
    product = ProductInhibitionModifier(product_state="P", inhibition_constant_symbol="K_i", product_units="millimolar")
    legacy = float(
        product.activity(parameters=UNIT_CONSTANTS, environment=None, state={"P": Q_(1.0, "millimolar")}).magnitude  # type: ignore[arg-type]
    )
    assert base_rate * legacy == pytest.approx(noncompetitive, abs=5e-5)
    assert product.to_dict()["mechanism"] == "noncompetitive"


def _context(parameters: ParameterSet, units: str) -> KernelContext:
    names = ("S", "P", "G")
    return KernelContext(
        state_index={name: index for index, name in enumerate(names)},
        state_units={name: units for name in names},
        time_units="second",
        parameters=parameters,
    )


@pytest.mark.parametrize("units", ["millimolar", "micromolar", "mole / liter"])
def test_compiled_kernel_and_gradient_equal_the_unit_aware_activity_across_units(units: str) -> None:
    parameters = _parameters(K_m=0.4, K_ic=0.5, K_iu=1.5, K_g=0.25)
    modifier = _modifier(
        _mixed(),
        InhibitorTerm(state="G", units="millimolar", mechanism="noncompetitive",
                      competitive_constant_symbol="K_g", uncompetitive_constant_symbol="K_g"),
    )
    context = _context(parameters, units)
    kernel = modifier.compile_activity(context)
    gradient = modifier.compile_activity_gradient(context)
    assert kernel is not None and gradient is not None
    factor = float(Q_(1.0, "millimolar").to(units).magnitude)
    for state_mm in ({"S": 0.8, "P": 0.3, "G": 0.2}, {"S": 0.0, "P": 0.3, "G": 0.0}, {"S": 1e-9, "P": 0.0, "G": 2.0}):
        vector = np.array([state_mm[name] * factor for name in ("S", "P", "G")])
        assert kernel(0.0, vector) == pytest.approx(_activity(modifier, parameters, **state_mm), rel=1e-12)
        step = 1e-4 * factor
        for index in range(3):
            unit = np.zeros(3)
            unit[index] = 1.0
            if vector[index] - step < 0.0:
                forward = lambda h: (kernel(0.0, vector + h * unit) - kernel(0.0, vector)) / h  # noqa: E731
                reference = 2.0 * forward(step / 2.0) - forward(step)
                tolerance = 1e-4
            else:
                central = lambda h: (kernel(0.0, vector + h * unit) - kernel(0.0, vector - h * unit)) / (2.0 * h)  # noqa: E731
                reference = (4.0 * central(step / 2.0) - central(step)) / 3.0
                tolerance = 1e-7
            assert gradient(0.0, vector)[index] == pytest.approx(reference, rel=tolerance, abs=1e-12 / factor)


def test_nan_negative_and_infinite_states_are_refused() -> None:
    parameters = _parameters(K_m=0.4, K_ic=0.5)
    modifier = _modifier(_competitive())
    for bad in (float("nan"), -1.0, float("inf")):
        with pytest.raises(ValueError, match="finite and nonnegative"):
            _activity(modifier, parameters, S=0.5, P=bad)
        with pytest.raises(ValueError, match="finite and nonnegative"):
            _activity(modifier, parameters, S=bad, P=0.5)
    context = _context(parameters, "millimolar")
    kernel = modifier.compile_activity(context)
    assert kernel is not None
    with pytest.raises(ValueError, match="finite and nonnegative"):
        kernel(0.0, np.array([0.5, float("nan"), 0.0]))
    product = ProductInhibitionModifier(product_state="P", inhibition_constant_symbol="K_ic", product_units="millimolar")
    with pytest.raises(ValueError, match="must be non-negative and finite"):
        product.activity(parameters=parameters, environment=None, state={"P": Q_(float("nan"), "millimolar")})  # type: ignore[arg-type]


def test_missing_or_contradictory_constants_are_refused() -> None:
    with pytest.raises(ValueError, match="requires competitive_constant_symbol"):
        InhibitorTerm(state="P", units="millimolar", mechanism="competitive")
    with pytest.raises(ValueError, match="requires uncompetitive_constant_symbol"):
        InhibitorTerm(state="P", units="millimolar", mechanism="uncompetitive", competitive_constant_symbol="K")
    with pytest.raises(ValueError, match="one symbol declared for both"):
        InhibitorTerm(state="P", units="millimolar", mechanism="noncompetitive",
                      competitive_constant_symbol="K_a", uncompetitive_constant_symbol="K_b")
    with pytest.raises(ValueError, match="requires both"):
        InhibitorTerm(state="P", units="millimolar", mechanism="mixed", competitive_constant_symbol="K_a")
    with pytest.raises(ValueError, match="declare mechanism 'noncompetitive'"):
        InhibitorTerm(state="P", units="millimolar", mechanism="mixed",
                      competitive_constant_symbol="K_a", uncompetitive_constant_symbol="K_a")
    with pytest.raises(ValueError, match="mechanism must be one of"):
        InhibitorTerm(state="P", units="millimolar", mechanism="allosteric", competitive_constant_symbol="K_a")
    with pytest.raises(ValueError, match="more than once"):
        _modifier(_competitive(), _uncompetitive())
    with pytest.raises(ValueError, match="at least one inhibitor"):
        _modifier()
    with pytest.raises(ValueError, match="maturity must be one of"):
        MixedInhibitionModifier(
            substrate_state="S", michaelis_constant_symbol="K_m", substrate_units="millimolar",
            inhibitors=(_competitive(),), primary_source=SOURCE, maturity="literature_backed",
        )
    assert _law_metadata(primary_source=SOURCE, maturity="framework_benchmark")[1] == "framework_benchmark"
    assert _law_metadata(primary_source=SOURCE, maturity="literature_backed_software_tested")[1] == (
        "literature_backed_software_tested"
    )
    modifier = _modifier(_competitive())
    with pytest.raises(ValueError, match="requires configured states"):
        modifier.activity(parameters=_parameters(K_m=1.0, K_ic=1.0), environment=None, state={"S": Q_(1.0, "millimolar")})  # type: ignore[arg-type]


def test_config_builder_declares_mechanisms_and_refuses_ambiguous_entries() -> None:
    config = {
        "type": "mixed_inhibition",
        "substrate_state": "S",
        "michaelis_constant": "K_m",
        "inhibitors": [
            {"state": "P", "mechanism": "mixed", "competitive_constant": "K_ic", "uncompetitive_constant": "K_iu"},
            {"state": "G", "mechanism": "noncompetitive", "inhibition_constant": "K_g"},
        ],
        "primary_source": SOURCE,
        "maturity": MATURITY,
    }
    modifier = mixed_inhibition_modifier_from_config(config, state_units=STATE_UNITS)
    data = modifier.to_dict()
    assert data["type"] == "mixed_inhibition" and data["mechanism"] == "mixed+noncompetitive"
    assert data["law_source"] == CORNISH_BOWDEN_2012_SOURCE and data["primary_source"] == SOURCE
    assert data["maturity"] == MATURITY
    assert data["inhibitors"][1] == {
        "state": "G", "units": "millimolar", "mechanism": "noncompetitive",
        "competitive_constant_symbol": "K_g", "uncompetitive_constant_symbol": "K_g",
    }
    assert modifier.read_states == (("S", "millimolar"), ("P", "millimolar"), ("G", "millimolar"))
    assert modifier.condition == "state"
    with pytest.raises(ValueError, match="nonempty inhibitors list"):
        mixed_inhibition_modifier_from_config({**config, "inhibitors": []}, state_units=STATE_UNITS)
    with pytest.raises(ValueError, match="unknown state"):
        mixed_inhibition_modifier_from_config(
            {**config, "inhibitors": [{"state": "X", "mechanism": "competitive", "competitive_constant": "K"}]},
            state_units=STATE_UNITS,
        )
    with pytest.raises(ValueError, match="inhibition_constant is the single noncompetitive constant"):
        mixed_inhibition_modifier_from_config(
            {**config, "inhibitors": [{"state": "P", "mechanism": "competitive", "inhibition_constant": "K"}]},
            state_units=STATE_UNITS,
        )
    with pytest.raises(ValueError, match="requires competitive_constant_symbol"):
        mixed_inhibition_modifier_from_config(
            {**config, "inhibitors": [{"state": "P", "mechanism": "competitive"}]}, state_units=STATE_UNITS
        )
    with pytest.raises(ValueError, match="requires primary_source"):
        mixed_inhibition_modifier_from_config({**config, "primary_source": ""}, state_units=STATE_UNITS)
