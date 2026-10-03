"""Public data fidelity, units and held-out-strain boundaries."""
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, UnitError
from fungal_model.research.secretion_benchmark import DATA_PATH, fit_protein_output, load_secretion_data, strain_holdouts

ROOT = Path(__file__).resolve().parents[1]


def test_primary_extract_is_reproducible_with_preserved_sd_and_dependence():
    spec = importlib.util.spec_from_file_location("extract_secretion", ROOT / "scripts/prepare_secretion_data.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.prepare(ROOT / DATA_PATH, check=True)
    data = load_secretion_data()
    assert data["license"] == "CC-BY-2.0"
    assert "six culture runs" in data["dependence"]
    assert len(data["records"]) == 4
    assert [r["extracellular_protein_mg_gDW_h"]["value"] for r in data["records"]] == [.68, .72, 1.98, 1.69]
    assert [r["extracellular_protein_mg_gDW_h"]["sd"] for r in data["records"]] == [.01, .02, .28, .24]
    assert data["records"][2]["extracellular_protein_mg_gDW_h"]["published_significance_marker"] == "*"
    assert "glucose equivalents" in data["limitations"][3]


def test_calibration_converts_mg_to_g_without_implying_activity():
    fit = fit_protein_output(growth_rates=Q_([.16], "1/h"), protein_output=Q_([.68], "mg/g/h"),
                            condition_ids=["one-condition"], source="Explicit calibration test")
    assert fit.protein_per_biomass.value == pytest.approx(.00425)
    np.testing.assert_allclose(fit.predict(Q_([.16/3600, 0], "1/s")), [.00068, 0])
    assert fit.to_dict()["residual_degrees_of_freedom"] == 0
    assert fit.protein_per_biomass.uncertainty is None
    assert "not active enzyme" in fit.protein_per_biomass.notes


@pytest.mark.parametrize("mu,qp,ids", [([], [], []), ([0], [1], ["a"]), ([-1], [1], ["a"]),
    ([1], [np.nan], ["a"]), ([1], [1, 2], ["a"]), ([1, 2], [1, 2], ["a", "a"]), ([1], [1], [""])])
def test_invalid_calibration_arrays_are_rejected(mu, qp, ids):
    with pytest.raises(ValueError):
        fit_protein_output(growth_rates=Q_(mu, "1/h"), protein_output=Q_(qp, "mg/g/h"), condition_ids=ids, source="test")


def test_wrong_units_and_missing_provenance_are_rejected():
    with pytest.raises(ProvenanceError):
        fit_protein_output(growth_rates=Q_([1], "1/h"), protein_output=Q_([1], "mg/g/h"), condition_ids=["a"], source="")
    with pytest.raises(UnitError):
        fit_protein_output(growth_rates=Q_([1], "1/h"), protein_output=Q_([1], "mol/L"), condition_ids=["a"], source="test")


def test_holdouts_exclude_entire_strain_and_reproduce_primary_means():
    data = load_secretion_data()
    result = strain_holdouts(data)
    assert len(result["predictions"]) == 8
    for prediction in result["predictions"]:
        assert all(prediction["strain"] not in n for n in prediction["fit"]["training_conditions"])
    assert result["rmse_mg_gDW_h"]["pooled"] == pytest.approx(.58693057511089)
    assert result["rmse_mg_gDW_h"]["carbon_source_conditioned"] == pytest.approx(.20700241544484446)
    # Changing both outcomes of the target strain must not change its predictions.
    changed = json.loads(json.dumps(data))
    for row in changed["records"]:
        if row["strain"] == "AB94-85":
            row["extracellular_protein_mg_gDW_h"]["value"] *= 100
    after = strain_holdouts(changed)
    before = [p["predicted_mg_gDW_h"] for p in result["predictions"] if p["strain"] == "AB94-85"]
    np.testing.assert_array_equal(before, [p["predicted_mg_gDW_h"] for p in after["predictions"] if p["strain"] == "AB94-85"])


def test_holdouts_require_training_coverage_and_unique_conditions():
    data = load_secretion_data()
    for records in (data["records"] + data["records"][:1], data["records"][:1], data["records"][1:3]):
        with pytest.raises(ValueError):
            strain_holdouts({**data, "records": records})


def test_modified_source_or_unbound_extract_is_rejected(tmp_path):
    destination = tmp_path / DATA_PATH
    shutil.copytree(ROOT / DATA_PATH, destination)
    source = destination / "PMC2639373.xml"
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        load_secretion_data(tmp_path)
    shutil.copyfile(ROOT / DATA_PATH / "PMC2639373.xml", source)
    manifest = json.loads((destination / "manifest.json").read_text())
    manifest["files"] = [e for e in manifest["files"] if e["path"] != "observations.json"]
    (destination / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="bound"):
        load_secretion_data(tmp_path)
    manifest["files"][0]["path"] = "../escape.xml"
    (destination / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="within"):
        load_secretion_data(tmp_path)
