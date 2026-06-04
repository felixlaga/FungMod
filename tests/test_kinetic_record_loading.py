from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model.data import KineticRecordLoadError, load_kinetic_record


ROOT = Path(__file__).resolve().parents[1]
CURATED_RECORD = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "curated"
    / "kinetic_record.yml"
)


def test_valid_curated_kinetic_record_loads() -> None:
    record = load_kinetic_record(CURATED_RECORD)

    assert record.kind == "kinetic_record"
    assert record.source_database == "SABIO-RK"
    assert record.source_kinetic_law_id == "35622"
    assert record.enzyme.name == "beta-glucosidase"
    assert record.parameters[0].symbol == "Km_cellobiose"
    assert record.conditions.temperature["value"] == 303.15


def test_missing_source_database_fails(tmp_path: Path) -> None:
    data = _record_data()
    data["source_database"] = ""

    with pytest.raises(KineticRecordLoadError, match="source_database"):
        load_kinetic_record(_write_record(tmp_path, data))


def test_missing_source_kinetic_law_id_fails(tmp_path: Path) -> None:
    data = _record_data()
    data["source_kinetic_law_id"] = ""

    with pytest.raises(KineticRecordLoadError, match="source_kinetic_law_id"):
        load_kinetic_record(_write_record(tmp_path, data))


def test_missing_reaction_equation_fails(tmp_path: Path) -> None:
    data = _record_data()
    data["reaction"]["equation"] = ""

    with pytest.raises(KineticRecordLoadError, match="reaction.equation"):
        load_kinetic_record(_write_record(tmp_path, data))


def test_missing_parameter_units_fails(tmp_path: Path) -> None:
    data = _record_data()
    data["parameters"][0]["units"] = ""

    with pytest.raises(KineticRecordLoadError, match="parameters.Km_cellobiose.units"):
        load_kinetic_record(_write_record(tmp_path, data))


def test_null_parameter_value_is_allowed_and_becomes_unknown_value_spec(tmp_path: Path) -> None:
    data = _record_data()
    data["parameters"][0]["value"] = None

    record = load_kinetic_record(_write_record(tmp_path, data))
    value_spec = record.parameters[0].to_value_spec()

    assert record.parameters[0].value is None
    assert value_spec.is_unknown
    assert value_spec.units == "mM"


def test_original_units_are_preserved() -> None:
    record = load_kinetic_record(CURATED_RECORD)

    by_symbol = {parameter.symbol: parameter for parameter in record.parameters}
    assert by_symbol["Km_cellobiose"].original_units == "mM"
    assert by_symbol["kcat_cellobiose"].original_units == "s^(-1)"
    assert record.conditions.temperature["original_units"] == "°C"


def test_to_dict_is_json_safe() -> None:
    record = load_kinetic_record(CURATED_RECORD)

    as_dict = record.to_dict()

    assert as_dict["record_id"] == "sabiork_reaction_618_selected_kinetic_law"
    json.dumps(as_dict)


def _record_data() -> dict[str, Any]:
    return deepcopy(yaml.safe_load(CURATED_RECORD.read_text(encoding="utf-8")))


def _write_record(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "kinetic_record.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path
