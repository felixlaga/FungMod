"""Evidence-bearing pH input and command workflows on synthetic data."""

from pathlib import Path
import csv
import shutil
import numpy as np
import pytest
import yaml
from fungal_model import load_user_dataset, virtual_experiment, UserDataError
from fungal_model.api.user_data_medium import read_medium_csv, augment_config_with_medium
from fungal_model.cli import main, EXIT_OK, EXIT_USAGE

ROOT = Path(__file__).resolve().parents[1]


def medium(path, *, stat=False):
    rows = read_medium_csv(ROOT / "data/mechanism_examples/buffered_ph/medium.csv")
    for row in rows:
        row.update(
            source="Illustrative inputs; no empirical measurements.",
            notes="Illustrative estimates for this medium only.",
        )
        if row["quantity"] in {"initial_ph", "buffer_pka"}:
            row["value"] = 6.0
        if row["quantity"] == "temperature":
            row["value"] = 298.15
        if row["quantity"] == "proton_coefficient":
            row.update(process="substrate_consumption", value=0.0001, units="mol/g")
    if stat:
        rows.append(dict(rows[2], quantity="ph_stat_setpoint", value=6.0, titrant="synthetic strong base"))
    keys = sorted(set().union(*(r.keys() for r in rows)))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    return rows


@pytest.mark.parametrize("stat", [False, True])
def test_public_user_tables_propagate_medium_evidence_and_signed_ledgers(tmp_path, stat):
    path = tmp_path / "dataset"
    shutil.copytree(ROOT / "tests/fixtures/user_data/culture_estimates", path)
    medium(path / "medium.csv", stat=stat)
    dataset = load_user_dataset(path)
    assert dataset.records["case_templates"][0]["process_state_metadata"]["medium_rows"]
    study = virtual_experiment(fungi="strain_x1", substrates="xylan_lot_x1", environments="c25", user_data=dataset)
    assert study.preflight(mode="scientific")[0].status == "underparameterized"
    assert study.preflight()[0].status == "exploratory"
    result = study.simulate(mode="exploratory", n_samples=1, seed=3, output_dir=tmp_path / "run", quicklook=False)
    rows = list(csv.DictReader(Path(result.tables.paths["time_series_long"]).open()))
    roles = {
        role: np.array([float(r["value"]) for r in rows if r["state_role"] == role and r["value"]])
        for role in {r["state_role"] for r in rows}
    }
    assert roles["ph"][0] == 6.0
    if stat:
        np.testing.assert_array_equal(roles["ph"], 6.0)
    else:
        assert roles["ph"][-1] < 6.0
    metric_rows = list(csv.DictReader(Path(result.tables.paths["final_metrics"]).open()))
    assert any("final_ph" in row.values() for row in metric_rows)
    ledger = roles["ledger_titrant" if stat else "proton_excess"]
    np.testing.assert_allclose(ledger, 0.0001 * (roles["substrate"][0] - roles["substrate"]), atol=1e-10)


@pytest.mark.parametrize("bad", ["missing_pka", "bad_units", "missing_value", "missing_source"])
def test_incomplete_medium_is_reported_during_check_data(tmp_path, bad):
    path = tmp_path / "dataset"
    shutil.copytree(ROOT / "tests/fixtures/user_data/culture_estimates", path)
    rows = medium(path / "medium.csv")
    if bad == "missing_pka":
        rows = [r for r in rows if r["quantity"] != "buffer_pka"]
    elif bad == "bad_units":
        rows[0]["units"] = "kelvin"
    elif bad == "missing_value":
        rows[0]["value"] = ""
    else:
        rows[0]["source"] = ""
    with (path / "medium.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(UserDataError, match="medium.csv"):
        load_user_dataset(path)


def test_cli_explicit_mechanisms_and_buffer_config_are_runnable(tmp_path, capsys):
    explicit = tmp_path / "peroxide.yml"
    assert (
        main(
            [
                "assemble-mechanisms",
                "--user-data",
                str(ROOT / "data/user_mechanisms/peroxide_oxidation"),
                "--output",
                str(explicit),
            ]
        )
        == EXIT_OK
    )
    assert main(["run-config", str(explicit), "--output", str(tmp_path / "oxidation")]) == EXIT_OK
    assert main(["run-config", str(explicit), "--output", str(tmp_path / "oxidation")]) == EXIT_USAGE
    ph = tmp_path / "ph.yml"
    assert (
        main(
            [
                "add-medium",
                str(ROOT / "data/mechanism_examples/buffered_ph/reaction.yml"),
                "--medium",
                str(ROOT / "data/mechanism_examples/buffered_ph/medium.csv"),
                "--output",
                str(ph),
            ]
        )
        == EXIT_OK
    )
    assert main(["run-config", str(ph), "--output", str(tmp_path / "ph")]) == EXIT_OK
    assert "empirical validation" in capsys.readouterr().out


def test_medium_rejects_conflicting_environment_and_estimated_scientific_config():
    config = yaml.safe_load((ROOT / "data/mechanism_examples/buffered_ph/reaction.yml").read_text())
    rows = read_medium_csv(ROOT / "data/mechanism_examples/buffered_ph/medium.csv")
    config["mode"] = "scientific"
    with pytest.raises(ValueError, match="exploratory"):
        augment_config_with_medium(config, rows)
    config["mode"] = "toy"
    config["entities"]["environment"]["data"]["conditions"]["temperature"]["value"] = 1
    with pytest.raises(ValueError, match="temperature"):
        augment_config_with_medium(config, rows)
