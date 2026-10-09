"""Explicit table routes require all physical inputs and preserve old imports."""

from __future__ import annotations

import csv
from pathlib import Path
import shutil

import pytest
import yaml

from fungal_model.api.user_data import UserDataError, load_user_dataset
from fungal_model.api.user_data_oxidative import MechanismTablesError, assemble_mechanism_tables, write_mechanism_config
from fungal_model.capability import CazymeFamilyMap
from fungal_model.capability.mechanism_scope import mechanism_family_map_path
from fungal_model.core.units import UnitError
from fungal_model.io.model_config import ModelConfig, load_model_config
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "data/user_mechanisms"


def copied(tmp_path, mechanism="peroxide_oxidation"):
    path = tmp_path / mechanism
    shutil.copytree(EXAMPLES / mechanism, path)
    return path


@pytest.mark.parametrize("mechanism", ["chain_scission", "peroxide_oxidation"])
def test_explicit_tables_compile_integrate_and_conserve(mechanism, tmp_path):
    folder = copied(tmp_path, mechanism)
    mapping = assemble_mechanism_tables(folder)
    assert mapping["provenance"]["input_sha256"]["kinetics.csv"]
    output = write_mechanism_config(folder, tmp_path / "case.yml")
    config = load_model_config(output)
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    result = model.run(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    assert all(v.passed for v in result.validation_results)
    if mechanism == "peroxide_oxidation":
        assert result.states["mechanism_peroxide_feed"].magnitude[-1] == pytest.approx(1.2)
    with pytest.raises(FileExistsError):
        write_mechanism_config(folder, output)


@pytest.mark.parametrize(
    "file,column,new_value,error",
    [
        ("kinetics.csv", "source", "", MechanismTablesError),
        ("kinetics.csv", "value", "nan", MechanismTablesError),
        ("states.csv", "value", "-1", MechanismTablesError),
        ("feeds.csv", "units", "millimolar", UnitError),
        ("feeds.csv", "state", "nonexistent", MechanismTablesError),
    ],
)
def test_missing_sources_invalid_values_and_feed_dimensions_refused(tmp_path, file, column, new_value, error):
    folder = copied(tmp_path)
    with (folder / file).open() as stream:
        reader = csv.DictReader(stream)
        names = reader.fieldnames
        rows = list(reader)
    rows[0][column] = new_value
    with (folder / file).open("w") as stream:
        writer = csv.DictWriter(stream, names)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(error):
        assemble_mechanism_tables(folder)


def test_omitted_peroxide_km_is_not_invented(tmp_path):
    folder = copied(tmp_path)
    lines = (folder / "kinetics.csv").read_text().splitlines()
    (folder / "kinetics.csv").write_text(
        "\n".join(line for line in lines if not line.startswith("peroxide_km,")) + "\n"
    )
    with pytest.raises(MechanismTablesError, match="peroxide_km"):
        assemble_mechanism_tables(folder)


def test_structural_inputs_are_required_not_inferred_from_bulk_substrate(tmp_path):
    folder = copied(tmp_path, "chain_scission")
    manifest = yaml.safe_load((folder / "mechanism.yml").read_text())
    del manifest["structure_source"]
    (folder / "mechanism.yml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(MechanismTablesError, match="structure_source"):
        assemble_mechanism_tables(folder)


def test_batch_without_feed_is_explicitly_recorded(tmp_path):
    folder = copied(tmp_path)
    (folder / "feeds.csv").unlink()
    config = ModelConfig.from_mapping(assemble_mechanism_tables(folder))
    rows = config.parameters[0].parameters
    feed = next(p for p in rows if p["symbol"] == "peroxide_feed")
    assert feed["value"] == 0 and "Batch experiment" in feed["source"]


def test_enriched_family_map_is_opt_in_and_conservative():
    old = CazymeFamilyMap.load()
    new = CazymeFamilyMap.load(mechanism_family_map_path())
    assert old.for_family("GH5")[0].enzyme_class == "cellulase_generic"
    for family in ("GH5", "GH12", "GH45"):
        record = new.for_family(family)[0]
        assert record.enzyme_class == "endoglucanase" and record.specificity == "family_polyspecific"
    for family in ("AA9", "AA10"):
        record = new.for_family(family)[0]
        assert (
            record.enzyme_class == "lytic_polysaccharide_monooxygenase" and record.specificity == "family_polyspecific"
        )
    assert old.for_family("AA10") == ()


@pytest.mark.parametrize("enzyme_class", ["endoglucanase", "lytic_polysaccharide_monooxygenase"])
def test_ordinary_enzyme_tables_refuse_missing_mechanism_states(tmp_path, enzyme_class):
    folder = tmp_path / "ordinary"
    shutil.copytree(ROOT / "tests/fixtures/user_data/solid_case", folder)
    (folder / "enzymes.csv").write_text(
        "strain_id,enzyme_class,evidence,source\n"
        f"strain_p1,{enzyme_class},explicit enzyme activity,Synthetic test input\n"
    )
    with pytest.raises(UserDataError, match="assemble-mechanisms"):
        load_user_dataset(folder)
