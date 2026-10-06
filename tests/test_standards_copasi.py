"""COPASI reproduction of a FungMod-exported PEtab problem (optional ``copasi`` extra)."""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")
from fungal_model.standards import copasi as copasi_module  # noqa: E402

if not copasi_module.copasi_available():
    pytest.skip("requires the optional 'copasi' extra", allow_module_level=True)

from fungal_model.core.units import Q_
from fungal_model.standards import conditions_to_petab
from fungal_model.standards.copasi import (
    CopasiReproductionError,
    petab_objective,
    read_petab_tables,
    reproduce_in_copasi,
)
from tests.test_standards_petab import OBSERVABLES, PARAMETERS, TIMES_MIN, _decay_model, _two_conditions

K_TRUE = 0.08
K_NOMINAL = 0.12


def _fungmod_predictor(k: float):
    initial = {"low": 2.0, "high": 8.0}

    def predict(condition_id: str, seconds: np.ndarray) -> dict[str, np.ndarray]:
        result = _decay_model(k).run(
            initial_state={"A": Q_(initial[condition_id], "millimolar"), "B": Q_(0.0, "millimolar")},
            t_span=(Q_(0.0, "second"), Q_(float(seconds[-1]), "second")),
            t_eval=Q_(np.asarray(seconds, dtype=float), "second"),
            label=condition_id,
        )
        return {
            "observable_a_conc": result.state("A").to("micromolar").magnitude,
            "observable_b_conc": result.state("B").to("millimolar").magnitude,
        }

    return predict


@pytest.fixture(scope="module")
def reproduction(tmp_path_factory):
    root = tmp_path_factory.mktemp("copasi")
    export = conditions_to_petab(
        _two_conditions(K_NOMINAL, K_TRUE), observables=OBSERVABLES, parameters=PARAMETERS,
        output_dir=root / "petab", model_id="toy_two_conditions",
    )
    result = reproduce_in_copasi(
        export.problem_yaml, root / "copasi", predictor=_fungmod_predictor(K_NOMINAL), starts=2, seed=7,
    )
    return export, result, root


def test_copasi_recovers_the_generating_parameter_from_the_nominal_and_random_starts(reproduction):
    _, result, _ = reproduction
    assert result.local_fit["values"]["k"] == pytest.approx(K_TRUE, rel=1e-4)
    assert all(run["values"]["k"] == pytest.approx(K_TRUE, rel=1e-4) for run in result.starts)
    assert result.best["objective"] < 1e-6
    assert result.best["values"]["k"] == pytest.approx(K_TRUE, rel=1e-4)
    assert {run["start"]["k"] for run in result.starts} != {K_NOMINAL}


def test_copasi_and_fungmod_agree_on_the_petab_objective_at_the_nominal_point(reproduction):
    export, result, _ = reproduction
    simulation = result.simulation_at_nominal
    assert simulation["objective_relative_difference"] < 1e-5
    assert max(simulation["max_abs_difference_over_sigma"].values()) < 1e-5
    # The nominal objective is the closed-form weighted misfit of k = 0.12 against data from k = 0.08.
    expected = 0.0
    for a0 in (2.0, 8.0):
        b_true = a0 * (1 - np.exp(-K_TRUE * TIMES_MIN))
        b_nominal = a0 * (1 - np.exp(-K_NOMINAL * TIMES_MIN))
        expected += np.sum((((a0 - b_nominal) - (a0 - b_true)) * 1000.0 / 100.0) ** 2) + np.sum(((b_nominal - b_true) / 0.05) ** 2)
    assert simulation["fungmod"]["objective"] == pytest.approx(expected, rel=1e-6)
    assert simulation["copasi"]["objective"] == pytest.approx(expected, rel=1e-5)
    assert simulation["copasi"]["measurements"] == 20


def test_copasi_weights_are_rewritten_from_sigma_to_inverse_variance(reproduction):
    _, result, root = reproduction
    by_observable = {(row["condition"], row["observable"]): row for row in result.weights}
    assert by_observable[("low", "observable_a_conc")]["importer_weight"] == pytest.approx(100.0)
    assert by_observable[("low", "observable_a_conc")]["weight"] == pytest.approx(1e-4)
    assert by_observable[("high", "observable_b_conc")]["weight"] == pytest.approx(400.0)
    # COPASI's own objective at the fitted point equals the PEtab objective re-evaluated from its time courses.
    assert result.local_fit["copasi_objective"] == pytest.approx(result.local_fit["objective"], rel=1e-3, abs=1e-6)
    recorded = json.loads((root / "copasi" / "copasi_reproduction.json").read_text(encoding="utf-8"))
    assert recorded["best"]["values"]["k"] == pytest.approx(K_TRUE, rel=1e-4)
    assert recorded["versions"]["copasi"]
    assert recorded["method"]["name"] == "Levenberg - Marquardt"


def test_petab_objective_matches_a_hand_computation(reproduction):
    export, _, _ = reproduction
    tables = read_petab_tables(export.problem_yaml)
    predictions = {
        condition_id: {
            "observable_a_conc": np.zeros(len(tables.measurement_times(condition_id))),
            "observable_b_conc": np.zeros(len(tables.measurement_times(condition_id))),
        }
        for condition_id in tables.condition_ids
    }
    score = petab_objective(tables, predictions)
    expected = sum(
        np.sum(((a0 - a0 * (1 - np.exp(-K_TRUE * TIMES_MIN))) * 1000.0 / 100.0) ** 2)
        + np.sum((a0 * (1 - np.exp(-K_TRUE * TIMES_MIN)) / 0.05) ** 2)
        for a0 in (2.0, 8.0)
    )
    assert score["objective"] == pytest.approx(expected, rel=1e-12)
    assert set(score["per_observable"]) == {"observable_a_conc", "observable_b_conc"}


def test_reader_refuses_observable_formulas_fungmod_never_writes(tmp_path):
    export = conditions_to_petab(_two_conditions(), observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path)
    text = export.observables.read_text(encoding="utf-8").replace("1000 * A", "A + B")
    export.observables.write_text(text, encoding="utf-8")
    with pytest.raises(CopasiReproductionError, match="not '\\[factor \\*\\] species'"):
        read_petab_tables(export.problem_yaml)


def test_requiring_copasi_leaves_the_process_text_encoding_alone() -> None:
    """Importing COPASI resets the C locale; the helper restores LC_CTYPE so later text reads keep their encoding."""

    script = (
        "import locale, sys\n"
        "before = locale.getpreferredencoding(False)\n"
        "from fungal_model.standards.copasi import copasi_available\n"
        "assert copasi_available()\n"
        "after = locale.getpreferredencoding(False)\n"
        "print(before, after)\n"
        "sys.exit(0 if before == after else 1)\n"
    )
    completed = subprocess.run([sys.executable, "-X", "utf8=0", "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
