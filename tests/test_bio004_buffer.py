"""Synthetic acidifying and alkalising systems, never biological measurements."""

from dataclasses import replace
import numpy as np
import pytest
from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.numerics import SolverSettings
from fungal_model.entities.environment import Environment
from fungal_model.processes import FirstOrderDecayProcess, ModelBuilder, ProcessRegistry
from fungal_model.processes.buffer import ProtonBalanceProcess, buffer_value
from fungal_model.modifiers import PHModifier, CardinalPHModifier
from fungal_model.processes.rate_modifiers import RateModifierProcess
from fungal_model.solvers import ProcessODESolver, RunRequest

SOURCE = "Artificial software benchmark; law doi:10.1021/ed074p937; no empirical validation."


def params(sign=1.0, concentration=0.1, pka=7.0):
    values = {
        "k": (0.1, "1/hour"),
        "nu": (sign, "dimensionless"),
        "C": (concentration, "mol/L"),
        "pka": (pka, "dimensionless"),
        "Kw": (1e-14, "(mol/L)**2"),
        "standard": (1.0, "mol/L"),
        "T": (298.15, "kelvin"),
        "opt": (7.0, "dimensionless"),
        "width": (2.0, "dimensionless"),
        "low": (2.0, "dimensionless"),
        "high": (12.0, "dimensionless"),
    }
    return ParameterSet([Parameter(k, k, v, u, None, SOURCE, "testing", "Synthetic") for k, (v, u) in values.items()])


def driver(modified=False):
    p = FirstOrderDecayProcess(
        name="reaction",
        substrate_state="A",
        product_state="B",
        rate_constant_symbol="k",
        state_units="mol/L",
        source=SOURCE,
    )
    return (
        RateModifierProcess(base_process=p, rate_modifiers=(PHModifier("opt", "width", SOURCE, state_source="ph"),))
        if modified
        else p
    )


def balance(p, mode="ph"):
    return ProtonBalanceProcess(
        name="balance_" + mode,
        driver=p,
        ph_state="ph",
        output_state="ph" if mode in {"ph", "held_ph"} else "ledger",
        buffer_symbols=(("C", "pka"),),
        proton_coefficient_symbol="nu",
        water_ion_product_symbol="Kw",
        standard_concentration_symbol="standard",
        temperature_symbol="T",
        concentration_units="mol/L",
        time_units="hour",
        ph_bounds=(2.0, 12.0),
        mode=mode,
        source=SOURCE,
    )


def model(sign=1, concentration=0.1, pka=7, stat=False, modified=False):
    p = driver(modified)
    result = ModelBuilder(
        process_library=ProcessRegistry(
            (p, balance(p, "held_ph" if stat else "ph"), balance(p, "titrant" if stat else "proton_ledger"))
        ),
        parameters=params(sign, concentration, pka),
        allow_unsourced_for_testing=True,
    ).assemble()
    return replace(result, solver_settings=SolverSettings(rtol=1e-10, atol=1e-12))


def run(m, ph=7):
    return m.run(
        initial_state={
            "A": Q_(0.01, "mol/L"),
            "B": Q_(0, "mol/L"),
            "ph": Q_(ph, "dimensionless"),
            "ledger": Q_(0, "mol/L"),
        },
        t_span=(Q_(0, "hour"), Q_(2, "hour")),
        t_eval=Q_(np.linspace(0, 2, 41), "hour"),
    )


@pytest.mark.parametrize("sign,pka,initial", [(1, 7, 7), (-1, 5, 5)])
def test_titration_and_signed_proton_conservation(sign, pka, initial):
    result = run(model(sign, pka=pka), initial)
    ph = np.asarray(result.states["ph"].magnitude)
    ledger = np.asarray(result.states["ledger"].magnitude)
    h = 10.0 ** (-ph)
    h0 = 10.0 ** (-initial)
    ka = 10.0 ** (-pka)
    acid = (h - h0) - (1e-14 / h - 1e-14 / h0) + 0.1 * (h / (ka + h) - h0 / (ka + h0))
    np.testing.assert_allclose(acid, ledger, rtol=2e-8, atol=2e-11)
    np.testing.assert_allclose(ledger, sign * result.states["B"].magnitude, rtol=1e-10, atol=1e-12)
    assert ph[-1] < ph[0] if sign > 0 else ph[-1] > ph[0]


@pytest.mark.parametrize("sign", [1, -1, 0])
def test_ph_stat_reports_signed_titrant(sign):
    result = run(model(sign, stat=True))
    np.testing.assert_array_equal(result.states["ph"].magnitude, 7.0)
    np.testing.assert_allclose(result.states["ledger"].magnitude, sign * result.states["B"].magnitude, atol=1e-13)


def test_large_buffer_and_zero_production_limits():
    np.testing.assert_allclose(run(model(concentration=1e11)).states["ph"].magnitude, 7, atol=1e-12, rtol=0)
    np.testing.assert_array_equal(run(model(sign=0)).states["ph"].magnitude, 7)


def test_coupled_rate_tracks_ph_and_analytic_jacobian():
    m = model(modified=True)
    result = run(m)
    expected = 0.1 * result.states["A"].magnitude * np.exp(-0.5 * ((result.states["ph"].magnitude - 7) / 2) ** 2)
    np.testing.assert_allclose(result.process_rates["reaction"].to("mol/L/hour").magnitude, expected, rtol=1e-12)
    compiled = ProcessODESolver(m).compile(
        RunRequest(
            initial_state={name: Q_(values.magnitude[0], str(values.units)) for name, values in result.states.items()},
            t_span=(Q_(0, "hour"), Q_(1, "hour")),
        )
    )
    y = np.array([float(result.states[name].magnitude[10]) for name in compiled.state_names])
    jac = compiled.jacobian(0, y)
    finite = np.column_stack(
        [
            (compiled.rhs(0, y + np.eye(len(y))[i] * 1e-7) - compiled.rhs(0, y - np.eye(len(y))[i] * 1e-7)) / (2e-7)
            for i in range(len(y))
        ]
    )
    np.testing.assert_allclose(jac, finite, rtol=1e-7, atol=1e-9)


@pytest.mark.parametrize(
    "modifier",
    [
        PHModifier("opt", "width", SOURCE, state_source="ph"),
        CardinalPHModifier("low", "opt", "high", SOURCE, state_source="ph"),
    ],
)
def test_state_modifiers_equal_static_and_have_exact_gradient(modifier):
    p = params()
    env = Environment(name="static", ph=Q_(6, "dimensionless"))
    static = replace(modifier, state_source=None).activity(parameters=p, environment=env)
    context = KernelContext({"ph": 0}, {"ph": "dimensionless"}, "hour", p)
    kernel = modifier.compile_activity(context)
    grad = modifier.compile_activity_jacobian(context)
    assert kernel(0, np.array([6.0])) == pytest.approx(static.magnitude, rel=1e-12)
    delta = 1e-5
    assert grad(0, np.array([6.0]))[0] == pytest.approx(
        (kernel(0, np.array([6 + delta])) - kernel(0, np.array([6 - delta]))) / (2 * delta), rel=1e-7
    )
    with pytest.raises(ValueError, match="both"):
        modifier.compile_activity(replace(context, environment=env))
    with pytest.raises(ValueError, match="domain"):
        kernel(0, np.array([15.0]))


def test_buffer_derivative_and_required_inputs():
    kw = dict(
        concentrations=np.array([0.1, 0.2]),
        pka=np.array([6.0, 8.0]),
        water_ion_product=1e-14,
        standard_concentration=1.0,
    )
    beta, derivative = buffer_value(6.3, **kw)
    assert beta > 0
    assert derivative == pytest.approx(
        (buffer_value(6.30001, **kw)[0] - buffer_value(6.29999, **kw)[0]) / 2e-5, rel=1e-8
    )
    with pytest.raises(ValueError):
        buffer_value(6, **dict(kw, pka=np.array([6.0])))
    with pytest.raises(ValueError):
        buffer_value(6, **dict(kw, water_ion_product=0))


def test_declared_ph_bounds_fail_closed():
    with pytest.raises(ValueError, match="bounds|domain"):
        run(model(), ph=13)


@pytest.mark.parametrize("ph",[4.1,5.7,7.7])
def test_state_ionization_matches_deposited_formula_and_derivatives(ph):
    from tests.test_ph_ionization_process import _process, _parameters, deposited_law, CONSTANTS
    process=_process(state_source="ph")
    p=_parameters()
    context=KernelContext({"S":0,"E":1,"P":2,"ph":3},{"S":"millimolar","E":"millimolar","P":"millimolar","ph":"dimensionless"},"second",p)
    y=np.array([3.,.02,0.,ph])
    rate=process.compile_rate(context)
    jac=process.compile_jacobian(context)
    assert rate(0,y)==pytest.approx(deposited_law(.02,3,ph,**CONSTANTS),rel=1e-12)
    finite=np.array([(rate(0,y+np.eye(4)[i]*1e-6)-rate(0,y-np.eye(4)[i]*1e-6))/2e-6 for i in range(4)])
    np.testing.assert_allclose(jac(0,y),finite,rtol=1e-7,atol=1e-10)
