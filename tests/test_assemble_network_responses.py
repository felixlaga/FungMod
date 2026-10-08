"""Response laws carried into an enzyme-network draft (ASSEMBLE-003).

``assemble_user_tables(network=True, responses=...)`` (``fungmod assemble
--network --responses FILE``) and the ``responses.csv`` rows of a
``user_data`` dataset write each temperature or pH law to the draft's
``responses.csv`` against the network member (strain, enzyme class and pool) it
names, with the validation of a single-class draft plus two network refusals: a
law on a class that is no member of the network, and a law on a pool its class
does not act on. Per member the report says whether the drafted kinetic
constants sit at each law's reference condition; a law carries a member's
kinetics to another requested condition (an ``EnvironmentGrid`` condition) only
from there, exactly as a single-class draft carries a case.

The loader of this version (``load_user_dataset``) refuses ``responses.csv`` in
an ``enzyme_network`` dataset: binding laws to network processes is NETWORK-003
(open pull request #125). The draft content is asserted here; the load of a
drafted network with laws is a strict ``xfail`` until that loader lands, and a
separate test pins the loader's existing refusal while it stands.

Inputs: the ``network_chain`` fixture without its ``enzyme_network`` block (two
user-defined classes on a soluble polymer-like substrate and the oligomer-like
pool it releases; illustrative estimates at 30 degC, pH 5), the illustrative
``oxidase_case`` dataset, the frozen SABIO-RK Reaction 618 export, and law rows
written by the tests with the illustrative values of NETWORK-003's
``network_chain_laws`` fixture (a cardinal temperature law 5/30/45 degC and a
cardinal pH law 3/5/8 on the first class, an Arrhenius law of 50 kJ/mol at
30 degC on the second). Nothing here is a measurement.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import shutil
import socket
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from fungal_model import UserDataError, assemble_user_tables, load_user_dataset
from fungal_model.api.user_data_assembly import (
    _LOADER_NETWORK_LAW_REFUSAL,
    NETWORK_BLOCKED,
    NETWORK_COMPLETE,
    NETWORK_REFERENCE_STATUSES,
    REFERENCE_AT,
    REFERENCE_NO_LAW,
    REFERENCE_NOT_AT,
    AssembledTablesDraft,
    UserTablesAssemblyError,
)
from fungal_model.cli import EXIT_OK, EXIT_USAGE
from fungal_model.registry import load_registry
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from tests.test_assemble_network import (
    C30_PH5,
    C40_PH5,
    OXIDASE,
    REGISTRY_INDEX,
    _cli,
    _draft_digest,
    _only,
    _registry_chain_draft,
    _review,
    _with_registry_chain,
)
from tests.test_fetch_kinetics import _plain_chain

C50_PH5 = {"temperature": 50, "temperature_units": "degC", "ph": 5}
C50_PH6 = {"temperature": 50, "temperature_units": "degC", "ph": 6}
NOTE_T = "Illustrative test note NW-2 p. 5"
NOTE_PH = "Illustrative test note NW-2 p. 6"
NOTE_EA = "Illustrative test note NW-2 p. 7"
LAW_COLUMNS = (
    "enzyme_class",
    "substrate",
    "law",
    "parameter",
    "value",
    "units",
    "evidence_type",
    "method",
    "source",
    "reference_tolerance",
    "kinetics_at_reference",
)


def _law(enzyme_class: str, substrate: str, law: str, parameter: str, value: float, units: str, source: str) -> dict:
    return {
        "enzyme_class": enzyme_class,
        "substrate": substrate,
        "law": law,
        "parameter": parameter,
        "value": value,
        "units": units,
        "evidence_type": "estimate",
        "source": source,
    }


# The illustrative laws of NETWORK-003's network_chain_laws fixture, given as the responses argument.
CARDINAL_T = [
    _law("depolymerase_like", "polymer_p1", "temperature_cardinal_rosso", name, value, "degC", NOTE_T)
    for name, value in (("minimum_temperature", 5), ("optimum_temperature", 30), ("maximum_temperature", 45))
]
CARDINAL_PH = [
    _law("depolymerase_like", "polymer_p1", "ph_cardinal_rosso", name, value, "dimensionless", NOTE_PH)
    for name, value in (("minimum_ph", 3), ("optimum_ph", 5), ("maximum_ph", 8))
]
ARRHENIUS = [
    _law(
        "oligomer_hydrolase_like",
        "oligomer_o1",
        "temperature_arrhenius_reference",
        "activation_energy",
        50,
        "kJ/mol",
        NOTE_EA,
    ),
    _law(
        "oligomer_hydrolase_like",
        "oligomer_o1",
        "temperature_arrhenius_reference",
        "reference_temperature",
        30,
        "degC",
        NOTE_EA,
    ),
]
LAWS = [*CARDINAL_T, *CARDINAL_PH, *ARRHENIUS]

# SHA-256 (tests/test_assemble_network.py's _draft_digest) of drafts WITHOUT the new combination (a network draft with
# response laws), computed at 524df39, the base of ASSEMBLE-003: single-class drafts with laws, and network drafts
# without laws, stay byte-identical.
DRAFT_DIGESTS_524DF39 = {
    "ox_args": "865ceba603e567b62340f08876eab1351172e7c44cf80babcd15550d3395f85b",
    "ox_t_only": "98561abe0d76ae866143a258e819577a712633af9c919d9b137976a98263a585",
    "chain_laws": "99ed2720d5016c57877a2d4364a88df910a0735b36ba12b7d0a9bafe1e47a839",
    "chain_off_ref": "7fe5be38914fa2a6cd846c7c66b2d33f5667c7f8db2463374cfef953ca8ff24a",
    "chain_net_3": "df1d3821f62864f88688906db25b23f4bbb57699f3e32078ae1b46f7c611322b",
    "reg_chain_2": "0b78fa5b735b45a1f3e3c20cbe836ae4b704e87b5921caabbf0e73e3305001f2",
}
# SHA-256 of the stdout of a single-class assemble --responses of the plain chain, run in an empty directory at 524df39.
CLI_RESPONSES_STDOUT_DIGEST_524DF39 = "e7fbe4851f65e428e92dee90dcda2d29efeb1d65a8b488607499f4f5bfa3ccef"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def fail_if_network_is_used(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Assembling an enzyme network with response laws must not touch the network.")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_network_is_used)
    monkeypatch.setattr(sabiork_fetch, "urlopen", fail_if_network_is_used)
    monkeypatch.setattr(socket.socket, "connect", fail_if_network_is_used)
    yield


# ---------------------------------------------------------------------------
# Helpers


def _rows_of(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_laws(path: Path, laws: Sequence[Mapping[str, Any]]) -> Path:
    """A --responses CSV of the given law rows, written with LF line ends on every platform."""

    lines = [",".join(LAW_COLUMNS)]
    for law in laws:
        lines.append(",".join(str(law.get(column, "")) for column in LAW_COLUMNS))
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def _without_laws(tmp_path: Path, source: Path) -> Path:
    target = tmp_path / f"{source.name}_without_laws"
    shutil.copytree(source, target)
    (target / "responses.csv").unlink()
    return target


def _with(laws: Sequence[Mapping[str, Any]], parameter: str, **changes: Any) -> list[dict[str, Any]]:
    """A copy of law rows with the cells of one parameter's row changed."""

    return [{**law, **changes} if law["parameter"] == parameter else dict(law) for law in laws]


def _chain(plain: Path, **overrides: Any) -> AssembledTablesDraft:
    arguments: dict[str, Any] = {
        "dataset_id": "chain_laws_draft",
        "fungus": "strain_n1",
        "substrates": ["polymer_p1"],
        "conditions": [C30_PH5, C40_PH5],
        "user_data": plain,
        "registry": REGISTRY_INDEX,
        "network": True,
    }
    arguments.update(overrides)
    return assemble_user_tables(**arguments)


# ---------------------------------------------------------------------------
# Without the new combination nothing changes


def _baseline_drafts(tmp_path: Path) -> dict[str, Callable[[], AssembledTablesDraft]]:
    plain = _plain_chain(tmp_path)
    oxidase = _without_laws(tmp_path, OXIDASE)
    oxidase_laws = [
        {"substrate": row["substrate_id"], **{k: v for k, v in row.items() if k not in {"strain_id", "substrate_id"}}}
        for row in _rows_of(OXIDASE / "responses.csv")
    ]
    single_class = {"substrates": ["polymer_p1", "oligomer_o1"], "network": False}
    return {
        "ox_args": lambda: assemble_user_tables(
            dataset_id="oxidase_assembly",
            fungus="strain_l1",
            substrates=["syringaldazine_like"],
            conditions=[C50_PH5, C40_PH5],
            user_data=oxidase,
            responses=oxidase_laws,
            registry=REGISTRY_INDEX,
        ),
        "ox_t_only": lambda: assemble_user_tables(
            dataset_id="oxidase_assembly",
            fungus="strain_l1",
            substrates=["syringaldazine_like"],
            conditions=[C50_PH5, C40_PH5, C50_PH6],
            user_data=oxidase,
            responses=[law for law in oxidase_laws if law["law"] == "temperature_cardinal_rosso"],
            registry=REGISTRY_INDEX,
        ),
        "chain_laws": lambda: _chain(plain, responses=LAWS, **single_class),
        "chain_off_ref": lambda: _chain(
            plain, responses=_with(LAWS, "reference_temperature", value=25), **single_class
        ),
        "chain_net_3": lambda: _chain(plain, conditions=[C30_PH5, C40_PH5, {**C30_PH5, "ph": 6}]),
        "reg_chain_2": lambda: _registry_chain_draft(
            _with_registry_chain(load_registry(REGISTRY_INDEX)), conditions=[C30_PH5, C40_PH5]
        ),
    }


@pytest.mark.parametrize("name", sorted(DRAFT_DIGESTS_524DF39))
def test_drafts_without_the_new_combination_are_byte_identical_to_the_base_commit(name: str, tmp_path: Path) -> None:
    draft = _baseline_drafts(tmp_path)[name]()
    assert _draft_digest(draft) == DRAFT_DIGESTS_524DF39[name]
    if "network" in draft.assembly:
        assert not draft.responses
        assert all(
            "response_laws" not in member
            for item in draft.assembly["network"]["networks"]
            for member in item["members"]
        )


@pytest.mark.skipif(os.name == "nt", reason="printed commands quote arguments for cmd on Windows")
def test_a_single_class_assemble_with_responses_prints_what_it_printed_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plain_chain(tmp_path)
    _write_laws(tmp_path / "laws.csv", LAWS)
    monkeypatch.chdir(tmp_path)
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_n1",
        "--user-data",
        "my_chain",
        "--substrate",
        "polymer_p1",
        "--substrate",
        "oligomer_o1",
        "--temperature-c",
        "30",
        "--temperature-c",
        "40",
        "--ph",
        "5",
        "--responses",
        "laws.csv",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "chain_laws_draft",
        "--output",
        "chain_laws_draft",
    )
    assert code == EXIT_OK, err
    assert hashlib.sha256(out.encode("utf-8")).hexdigest() == CLI_RESPONSES_STDOUT_DIGEST_524DF39


# ---------------------------------------------------------------------------
# Laws written against the network members they name


# responses.csv of the draft from LAWS: (enzyme_class, substrate_id, law, parameter, value, units, source).
DRAFTED_LAWS = [
    ("depolymerase_like", "polymer_p1", "temperature_cardinal_rosso", "minimum_temperature", "5", "degC", NOTE_T),
    ("depolymerase_like", "polymer_p1", "temperature_cardinal_rosso", "optimum_temperature", "30", "degC", NOTE_T),
    ("depolymerase_like", "polymer_p1", "temperature_cardinal_rosso", "maximum_temperature", "45", "degC", NOTE_T),
    ("depolymerase_like", "polymer_p1", "ph_cardinal_rosso", "minimum_ph", "3", "dimensionless", NOTE_PH),
    ("depolymerase_like", "polymer_p1", "ph_cardinal_rosso", "optimum_ph", "5", "dimensionless", NOTE_PH),
    ("depolymerase_like", "polymer_p1", "ph_cardinal_rosso", "maximum_ph", "8", "dimensionless", NOTE_PH),
    (
        "oligomer_hydrolase_like",
        "oligomer_o1",
        "temperature_arrhenius_reference",
        "activation_energy",
        "50",
        "kJ/mol",
        NOTE_EA,
    ),
    (
        "oligomer_hydrolase_like",
        "oligomer_o1",
        "temperature_arrhenius_reference",
        "reference_temperature",
        "30",
        "degC",
        NOTE_EA,
    ),
]
ORIGIN = "the responses argument"
AT_C30 = {"condition": "c30_ph5", "condition_text": "30 degC, pH 5.0", "at_reference": True}


def _drafted_rows() -> list[dict[str, str]]:
    columns = ("enzyme_class", "substrate_id", "law", "parameter", "value", "units", "source")
    return [
        {
            "strain_id": "strain_n1",
            **dict(zip(columns[:6], row[:6], strict=True)),
            "evidence_type": "estimate",
            "method": "",
            "source": row[6],
            "reference_tolerance": "",
            "kinetics_at_reference": "",
        }
        for row in DRAFTED_LAWS
    ]


def _members(draft: AssembledTablesDraft) -> dict[str, Mapping[str, Any]]:
    network = _only(draft.assembly["network"]["networks"])
    return {member["enzyme_class"]: member for member in network["members"]}


def _verdicts(draft: AssembledTablesDraft) -> dict[str, Mapping[str, Any]]:
    network = _only(draft.assembly["network"]["networks"])
    return {verdict["condition"]: verdict for verdict in network["conditions"]}


def _cases(draft: AssembledTablesDraft) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {(case["enzyme_class"], case["condition"]): case for case in draft.assembly["cases"]}


def test_laws_are_written_against_the_members_they_name_and_carry_kinetics_from_the_reference(tmp_path: Path) -> None:
    plain = _plain_chain(tmp_path)
    draft = _chain(plain, responses=LAWS)

    # The laws are rows of the draft's responses.csv, against the strain, member class and pool they name: the
    # entry's class on the entry, the intermediate's class on the intermediate pool (not a requested substrate).
    assert [dict(row) for row in draft.responses] == _drafted_rows()
    assert draft.file_texts()["responses.csv"].splitlines()[0] == ",".join(
        ("strain_id", "enzyme_class", "substrate_id", *LAW_COLUMNS[2:])
    )
    assert draft.manifest["enzyme_network"] == {"entry_substrates": ["polymer_p1"]}
    # The user's kinetics rows are kept unchanged at their one condition; 40 degC is no conditions.csv row.
    user_rows = _rows_of(plain / "kinetics.csv")
    assert [{key: row[key] for key in user_rows[0]} for row in draft.kinetics] == user_rows
    assert [row["condition_id"] for row in draft.conditions] == ["c30_ph5"]
    requested = {item["condition_id"]: item for item in draft.assembly["requested_conditions"]}
    assert requested["c40_ph5"]["in_conditions_csv"] is False
    assert requested["c40_ph5"]["environment_grid"] == {"temperature_C": [40.0], "ph": [5.0]}

    # Members: each carried to 40 degC by its own law, from kinetics stated at the law's reference condition.
    members = _members(draft)
    assert {key: member["kinetics_status"] for key, member in members.items()} == {
        "depolymerase_like": {"c30_ph5": "user_data", "c40_ph5": "user_data"},
        "oligomer_hydrolase_like": {"c30_ph5": "user_data", "c40_ph5": "user_data"},
    }
    assert members["depolymerase_like"]["reference_condition"] == REFERENCE_AT
    assert members["depolymerase_like"]["response_laws"] == [
        {
            "law": "temperature_cardinal_rosso",
            "reads": "temperature",
            "reference": "optimum_temperature 30 degC",
            "origin": ORIGIN,
            "kinetics": [{**AT_C30, "reason": "30 degC equals optimum_temperature 30 degC"}],
        },
        {
            "law": "ph_cardinal_rosso",
            "reads": "ph",
            "reference": "optimum_ph 5",
            "origin": ORIGIN,
            "kinetics": [{**AT_C30, "reason": "pH 5 equals optimum_ph 5"}],
        },
    ]
    assert members["oligomer_hydrolase_like"]["reference_condition"] == REFERENCE_AT
    assert members["oligomer_hydrolase_like"]["response_laws"] == [
        {
            "law": "temperature_arrhenius_reference",
            "reads": "temperature",
            "reference": "reference_temperature 30 degC",
            "origin": ORIGIN,
            "kinetics": [{**AT_C30, "reason": "30 degC equals reference_temperature 30 degC"}],
        }
    ]
    cases = _cases(draft)
    for member, law in (
        ("depolymerase_like", "temperature_cardinal_rosso"),
        ("oligomer_hydrolase_like", ARRHENIUS[0]["law"]),
    ):
        carried = cases[(member, "c40_ph5")]
        assert (carried["kinetics_status"], carried["condition_route"]) == ("user_data", "response_law")
        assert carried["measured_condition"] == {"condition_id": "c30_ph5", "condition": "30 degC, pH 5.0"}
        assert f"carried to 40 degC, pH 5 by {law} from {ORIGIN}" in carried["reason"]
        assert cases[(member, "c30_ph5")]["condition_route"] == "same_condition"

    # Per condition: 30 degC is the conditions.csv row; 40 degC an EnvironmentGrid condition that reuses its values.
    verdicts = _verdicts(draft)
    assert verdicts["c30_ph5"] == {
        "condition": "c30_ph5",
        "status": NETWORK_COMPLETE,
        "initial_concentration": "stated",
        "blocked_by": [],
        "in_conditions_csv": True,
        "carried_from": None,
    }
    assert verdicts["c40_ph5"] == {
        "condition": "c40_ph5",
        "status": NETWORK_COMPLETE,
        "initial_concentration": "stated",
        "blocked_by": [],
        "in_conditions_csv": False,
        "carried_from": "c30_ph5",
    }
    network = draft.assembly["network"]
    assert network["reference_condition_meaning"] == dict(NETWORK_REFERENCE_STATUSES)
    assert network["loader_refusal"] == (_LOADER_NETWORK_LAW_REFUSAL or None)

    # The limitations say what the laws scale, and (while it does) that this loader refuses them, in its words.
    limitations = draft.assembly["limitations"]
    assert any(
        text.startswith("Response laws in an enzyme network draft: each responses.csv law") for text in limitations
    )
    assert not any(text.startswith("Response laws, the pH-ionization form") for text in limitations)
    assert any(text.startswith("The pH-ionization form, cultures and time courses") for text in limitations)
    refused = [text for text in limitations if text.startswith("load_user_dataset of this version refuses")]
    assert len(refused) == (1 if _LOADER_NETWORK_LAW_REFUSAL else 0)
    assert all(_LOADER_NETWORK_LAW_REFUSAL in text for text in refused)

    review = draft.review.split("## Enzyme network", 1)[1].split("\n## ", 1)[0]
    assert (
        "- depolymerase_like on polymer_p1: temperature_cardinal_rosso (optimum_temperature 30 degC) and "
        "ph_cardinal_rosso (optimum_ph 5), from the responses argument; at_reference, kinetics at c30_ph5 (30 degC, "
        "pH 5.0): 30 degC equals optimum_temperature 30 degC and pH 5 equals optimum_ph 5."
    ) in review
    assert (
        "- c40_ph5: all_members_have_kinetics (initial concentration of `polymer_p1`: stated; an EnvironmentGrid "
        "condition, not a conditions.csv row: the laws carry the kinetics of c30_ph5)."
    ) in review
    assert "environment_grid(temperature_C=[40.0], ph=[5.0])" in draft.review

    # The draft is complete apart from the reviewer: no REVIEW field in the laws or elsewhere.
    assert [item["column"] for item in draft.review_fields] == ["contributor"]


# LOAD EXPECTATION. The draft above is what a loader that binds responses.csv laws to the network process of their
# class and pool reads (NETWORK-003, open pull request #125). The loader of this version refuses responses.csv in an
# enzyme_network dataset with its existing message (pinned below by
# test_check_data_refuses_the_drafted_laws_with_the_loaders_message), so this load fails here with UserDataError.
# When #125 lands it passes, the strict xfail flips, and the marker is removed then.
@pytest.mark.xfail(strict=True, raises=UserDataError, reason="loader binds network laws only with NETWORK-003 (#125)")
def test_a_reviewed_network_draft_with_laws_loads_with_each_law_on_its_process(tmp_path: Path) -> None:
    directory = tmp_path / "chain_laws_draft"
    _chain(_plain_chain(tmp_path), responses=LAWS).write(directory)
    _review(directory)
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    network = _only(dataset.enzyme_networks)
    assert {
        (process["enzyme_class"], process["pool"]): list(process["response_laws"]) for process in network["processes"]
    } == {
        ("depolymerase_like", "polymer_p1"): ["temperature_cardinal_rosso", "ph_cardinal_rosso"],
        ("oligomer_hydrolase_like", "oligomer_o1"): ["temperature_arrhenius_reference"],
    }


@pytest.mark.skipif(not _LOADER_NETWORK_LAW_REFUSAL, reason="the loader binds laws to network processes (NETWORK-003)")
def test_check_data_refuses_the_drafted_laws_with_the_loaders_message(tmp_path: Path) -> None:
    directory = tmp_path / "chain_laws_draft"
    _chain(_plain_chain(tmp_path), responses=LAWS).write(directory)
    _review(directory)
    code, _out, err = _cli("check-data", directory, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    # The only issue is the loader's existing refusal of responses.csv in an enzyme_network dataset.
    assert "is invalid. 1 issue(s):" in err
    assert f"responses.csv:-:-: {_LOADER_NETWORK_LAW_REFUSAL}" in err
    # Without the laws the same draft loads as a network (the rest of it is what the loader reads today).
    (directory / "responses.csv").unlink()
    code, out, err = _cli("check-data", directory, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "Enzyme networks (user_dataset.yml enzyme_network" in out


# ---------------------------------------------------------------------------
# Kinetic constants at the law's reference condition


@pytest.mark.parametrize(
    ("changes", "status", "reason"),
    [
        (
            {"value": 25},
            REFERENCE_NOT_AT,
            "30 degC differs from reference_temperature 25 degC by 5 degC; no reference_tolerance is given",
        ),
        (
            {"value": 25, "reference_tolerance": 4},
            REFERENCE_NOT_AT,
            "30 degC differs from reference_temperature 25 degC by 5 degC; its reference_tolerance is 4 degC",
        ),
        (
            {"value": 25, "reference_tolerance": 5},
            REFERENCE_AT,
            "30 degC is within the reference_tolerance 5 degC of reference_temperature 25 degC",
        ),
        (
            {"value": 25, "kinetics_at_reference": "yes"},
            REFERENCE_AT,
            "kinetics_at_reference = yes on the reference_temperature row declares them reference values (recorded, "
            "not checked)",
        ),
        (
            {"value": 303.15, "units": "kelvin"},
            REFERENCE_AT,
            "303.15 kelvin equals reference_temperature 303.15 kelvin",
        ),
    ],
    ids=["off", "tol_short", "tol", "declared", "kelvin"],
)
def test_the_reference_condition_is_reported_per_member_and_bounds_the_law(
    changes: Mapping[str, Any], status: str, reason: str, tmp_path: Path
) -> None:
    draft = _chain(_plain_chain(tmp_path), responses=_with(LAWS, "reference_temperature", **changes))
    members = _members(draft)
    (law,) = members["oligomer_hydrolase_like"]["response_laws"]
    assert members["oligomer_hydrolase_like"]["reference_condition"] == status
    assert law["kinetics"] == [{**AT_C30, "at_reference": status == REFERENCE_AT, "reason": reason}]
    # The other member's laws are untouched by the change.
    assert members["depolymerase_like"]["reference_condition"] == REFERENCE_AT
    # The laws are written as given, whatever the reference check finds; load_user_dataset decides on them.
    reference_rows = [row for row in draft.responses if row["parameter"] == "reference_temperature"]
    assert [row["value"] for row in reference_rows] == [str(changes["value"])]
    cases = _cases(draft)
    verdicts = _verdicts(draft)
    if status == REFERENCE_AT:
        assert [row["condition_id"] for row in draft.conditions] == ["c30_ph5"]
        assert cases[("oligomer_hydrolase_like", "c40_ph5")]["condition_route"] == "response_law"
        assert verdicts["c40_ph5"]["status"] == NETWORK_COMPLETE
        return
    # Not at the reference: the law carries nothing, so the member is a gap at 40 degC whose requests name c30_ph5 ...
    gap = cases[("oligomer_hydrolase_like", "c40_ph5")]
    assert (gap["kinetics_status"], gap["condition_route"]) == ("gap", "none")
    assert gap["measured_condition"] == {"condition_id": "c30_ph5", "condition": "30 degC, pH 5.0"}
    assert gap["reason"] == (
        "temperature_arrhenius_reference of oligomer_hydrolase_like on oligomer_o1 rescales the rate from its "
        f"reference condition (reference_temperature 25 degC), and the kinetics it would carry to 40 degC, pH 5 are "
        f"stated at c30_ph5 (30 degC, pH 5.0): {reason}; FungMod carries kinetics through a law only from the law's "
        "reference condition; the case is left as a gap"
    )
    # ... 40 degC becomes a conditions.csv row for its gaps, so the other member's law cannot carry it there either
    # (as in a single-class draft), and the network is blocked at 40 degC; 30 degC still runs on the stated rows.
    assert [row["condition_id"] for row in draft.conditions] == ["c30_ph5", "c40_ph5"]
    other = cases[("depolymerase_like", "c40_ph5")]
    assert other["kinetics_status"] == "gap"
    assert other["reason"] == (
        "a response law applies only at EnvironmentGrid conditions, and 40 degC, pH 5 must be a conditions.csv row "
        "here because oligomer_hydrolase_like on oligomer_o1 needs it; the case is left as a gap"
    )
    assert verdicts["c40_ph5"]["status"] == NETWORK_BLOCKED and verdicts["c40_ph5"]["in_conditions_csv"] is True
    assert verdicts["c30_ph5"]["status"] == NETWORK_COMPLETE
    assert (
        "- oligomer_hydrolase_like on oligomer_o1: temperature_arrhenius_reference (reference_temperature 25 degC), "
        f"from the responses argument; not_at_reference, kinetics at c30_ph5 (30 degC, pH 5.0): {reason}."
    ) in draft.review


def test_a_member_without_a_law_keeps_the_condition_of_its_rows(tmp_path: Path) -> None:
    draft = _chain(_plain_chain(tmp_path), responses=CARDINAL_T)
    members = _members(draft)
    assert members["oligomer_hydrolase_like"]["reference_condition"] == REFERENCE_NO_LAW
    assert members["oligomer_hydrolase_like"]["response_laws"] == []
    assert members["depolymerase_like"]["reference_condition"] == REFERENCE_AT
    assert [row["parameter"] for row in draft.responses] == [
        "minimum_temperature",
        "optimum_temperature",
        "maximum_temperature",
    ]
    cases = _cases(draft)
    # The single-class rule, per member: kinetics are not reused at another condition without a law ...
    gap = cases[("oligomer_hydrolase_like", "c40_ph5")]
    assert gap["kinetics_status"] == "gap"
    assert gap["reason"].endswith(
        "FungMod does not reuse them at 40 degC, pH 5 without a temperature response law, so this condition is a gap "
        "whose measurement requests name c30_ph5"
    )
    # ... so 40 degC is a conditions.csv row, and the law of the other member cannot carry its kinetics there.
    assert cases[("depolymerase_like", "c40_ph5")]["kinetics_status"] == "gap"
    assert _verdicts(draft)["c40_ph5"]["status"] == NETWORK_BLOCKED
    assert (
        "- oligomer_hydrolase_like on oligomer_o1: no response law (no_law); its kinetics hold at the condition of "
        "their rows."
    ) in draft.review


def test_an_environment_grid_condition_takes_the_design_loading_on_the_row_it_reuses(tmp_path: Path) -> None:
    plain = _plain_chain(tmp_path)
    rows = [row for row in _rows_of(plain / "kinetics.csv") if row["quantity"] != "substrate_initial_concentration"]
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (plain / "kinetics.csv").write_bytes(text.getvalue().encode("utf-8"))
    design = {"substrate_initial_concentration": {"value": 5, "units": "mM"}}

    # Only 40 degC is requested: both members are carried there from c30_ph5, the draft's one conditions.csv row,
    # whose values an EnvironmentGrid condition reuses; the entry's design loading is written on that row.
    draft = _chain(plain, responses=LAWS, conditions=[C40_PH5], design=design)
    assert [row["condition_id"] for row in draft.conditions] == ["c30_ph5"]
    loading = [row for row in draft.kinetics if row["quantity"] == "substrate_initial_concentration"]
    assert [
        (row["enzyme_class"], row["substrate_id"], row["condition_id"], row["value"], row["units"]) for row in loading
    ] == [("depolymerase_like", "polymer_p1", "c30_ph5", "5", "mM")]
    assert _verdicts(draft)["c40_ph5"] == {
        "condition": "c40_ph5",
        "status": NETWORK_COMPLETE,
        "initial_concentration": "stated",
        "blocked_by": [],
        "in_conditions_csv": False,
        "carried_from": "c30_ph5",
    }
    # Without the design loading nothing states it, and the network is blocked at the grid condition.
    blocked = _verdicts(_chain(plain, responses=LAWS, conditions=[C40_PH5]))["c40_ph5"]
    assert (blocked["status"], blocked["initial_concentration"]) == (NETWORK_BLOCKED, "missing")


def test_a_user_datasets_laws_are_carried_into_a_network_draft() -> None:
    draft = assemble_user_tables(
        dataset_id="oxidase_network",
        fungus="strain_l1",
        substrates=["syringaldazine_like"],
        conditions=[C50_PH5, C40_PH5],
        user_data=OXIDASE,
        registry=REGISTRY_INDEX,
        network=True,
    )
    # The dataset's responses.csv rows are kept unchanged, against the one member of the one-pool network.
    assert [dict(row) for row in draft.responses] == _rows_of(OXIDASE / "responses.csv")
    member = _only(_only(draft.assembly["network"]["networks"])["members"])
    assert (member["enzyme_class"], member["pool"], member["reference_condition"]) == (
        "laccase_like_oxidase",
        "syringaldazine_like",
        REFERENCE_AT,
    )
    assert [(law["law"], law["origin"]) for law in member["response_laws"]] == [
        ("temperature_cardinal_rosso", "user dataset oxidase_demo responses.csv"),
        ("ph_cardinal_rosso", "user dataset oxidase_demo responses.csv"),
    ]
    assert member["kinetics_status"] == {"c50_ph5": "user_data", "c40_ph5": "user_data"}
    assert [row["condition_id"] for row in draft.conditions] == ["c50_ph5"]
    assert _verdicts(draft)["c40_ph5"]["carried_from"] == "c50_ph5"


# ---------------------------------------------------------------------------
# Refused: a law on a class that is no member, or on a pool its class does not act on


ASSERTED_XYLANASE = [{"enzyme_class": "endo_xylanase", "evidence": "test assertion", "source": "test"}]


@pytest.mark.parametrize(
    ("laws", "message"),
    [
        (
            [{**law, "enzyme_class": "endo_xylanase"} for law in CARDINAL_T],
            r"responses\[0\] binds a law to 'endo_xylanase' on 'polymer_p1', but 'endo_xylanase' is no member of the "
            r"enzyme network that holds 'polymer_p1': it acts on none of its pools \(polymer_p1, oligomer_o1; on "
            r"polymer_p1: substrate class 'soluble_polymer_like' is not among the class's substrate classes",
        ),
        (
            [{**law, "enzyme_class": "beta_glucosidase"} for law in CARDINAL_T],
            r"binds a law to enzyme class 'beta_glucosidase', which has no evidence in Illustrative network strain N1\. "
            r"It is no member of the enzyme network\.",
        ),
        (
            [{**law, "substrate": "oligomer_o1"} for law in CARDINAL_T],
            r"responses\[0\] binds a law to 'depolymerase_like' on 'oligomer_o1', but that class does not act on that "
            r"pool \(substrate class 'oligomer_like' is not among .*\); in the enzyme network it is the member on "
            r"polymer_p1\. A response law scales the rate of one member's process, on the pool it acts on",
        ),
        (
            [{**law, "substrate": "monomer_m1"} for law in CARDINAL_T],
            r"responses\[0\]\['substrate'\] 'monomer_m1' is no pool of the enzyme network: neither a requested "
            r"substrate nor a pool one releases through a stated product \(pools: polymer_p1, oligomer_o1\)",
        ),
        ([{**CARDINAL_T[0], "law": "ph_gaussian"}], r"'ph_gaussian' is not a law user data binds"),
        ([{"law": "temperature_cardinal_rosso"}], r"responses\[0\] needs enzyme_class"),
    ],
    ids=["non_member", "no_evidence", "wrong_pool", "not_a_pool", "law", "columns"],
)
def test_a_law_on_what_is_no_member_process_is_refused(
    laws: Sequence[Mapping[str, Any]], message: str, tmp_path: Path
) -> None:
    with pytest.raises(UserTablesAssemblyError, match=message):
        _chain(_plain_chain(tmp_path), responses=laws, enzyme_classes=ASSERTED_XYLANASE)


def test_a_law_the_user_dataset_already_binds_is_refused_in_a_network_too() -> None:
    laws = [
        {"substrate": row["substrate_id"], **{k: v for k, v in row.items() if k not in {"strain_id", "substrate_id"}}}
        for row in _rows_of(OXIDASE / "responses.csv")
    ]
    with pytest.raises(UserTablesAssemblyError, match=r"which the user dataset already binds; edit the dataset's"):
        assemble_user_tables(
            dataset_id="oxidase_network",
            fungus="strain_l1",
            substrates=["syringaldazine_like"],
            conditions=[C50_PH5],
            user_data=OXIDASE,
            responses=laws,
            registry=REGISTRY_INDEX,
            network=True,
        )


# ---------------------------------------------------------------------------
# No law is derived from kinetics measured at several conditions


def test_kinetics_measured_at_several_conditions_never_become_a_law() -> None:
    registry = _with_registry_chain(load_registry(REGISTRY_INDEX))
    # Reaction 618 holds beta-glucosidase entries on cellobiose at 30, 35, 37 and 40 degC and several pH values.
    without = _registry_chain_draft(registry, conditions=[C30_PH5, C40_PH5], entry_ids=None)
    assert not without.responses
    gap = _cases(without)[("beta_glucosidase", "c40_ph5")]
    assert gap["kinetics_status"] == "gap"
    assert gap["reason"].startswith("no kinetics at 40 degC, pH 5; kinetics are stated only at other conditions (")
    assert gap["reason"].endswith("which FungMod does not reuse here without a response law")
    listed = {item["entry_id"]: item for item in without.assembly["entries"]}
    for entry_id in ("38521", "39245", "44888", "60725"):
        assert listed[entry_id]["use"] == "listed"
        assert listed[entry_id]["reason"] == gap["reason"]
    # A stated law is written as given; the entries at several conditions still make no law and no reference:
    # several candidates could be carried, and FungMod does not choose one.
    law = [
        _law(
            "beta_glucosidase", "cellobiose", "temperature_cardinal_rosso", name, value, "degC", "Test-only stated law"
        )
        for name, value in (("minimum_temperature", 10), ("optimum_temperature", 30), ("maximum_temperature", 60))
    ]
    stated = _registry_chain_draft(registry, conditions=[C30_PH5, C40_PH5], entry_ids=None, responses=law)
    assert [(row["enzyme_class"], row["substrate_id"], row["parameter"], row["value"]) for row in stated.responses] == [
        ("beta_glucosidase", "cellobiose", "minimum_temperature", "10"),
        ("beta_glucosidase", "cellobiose", "optimum_temperature", "30"),
        ("beta_glucosidase", "cellobiose", "maximum_temperature", "60"),
    ]
    conflict = _cases(stated)[("beta_glucosidase", "c40_ph5")]
    assert conflict["kinetics_status"] == "conflict"
    assert "several measured kinetics could be carried here by the response law" in conflict["reason"]
    assert conflict["reason"].endswith("and FungMod does not choose the reference (select one with entry_ids)")
    member = _members(stated)["beta_glucosidase"]
    assert member["reference_condition"] == "no_kinetic_constants"
    assert not any(
        row["quantity"] in {"km", "kcat"} for row in stated.kinetics if row["enzyme_class"] == "beta_glucosidase"
    )


# ---------------------------------------------------------------------------
# The command line


def test_the_command_line_drafts_a_network_with_laws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _plain_chain(tmp_path)
    _write_laws(tmp_path / "laws.csv", LAWS)
    monkeypatch.chdir(tmp_path)
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_n1",
        "--user-data",
        "my_chain",
        "--substrate",
        "polymer_p1",
        "--temperature-c",
        "30",
        "--temperature-c",
        "40",
        "--ph",
        "5",
        "--network",
        "--responses",
        "laws.csv",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "chain_laws_draft",
        "--output",
        "chain_laws_draft",
    )
    assert code == EXIT_OK, err
    assert _rows_of(tmp_path / "chain_laws_draft" / "responses.csv") == _drafted_rows()
    assert "  condition c40_ph5: 40 degC, pH 5 (an EnvironmentGrid condition, not a conditions.csv row)" in out
    assert "  depolymerase_like        polymer_p1 (entry)          user_data  user_data" in out
    assert "  response laws (responses.csv; each scales its member's rate from the law's reference condition):" in out
    assert (
        "    depolymerase_like on polymer_p1: temperature_cardinal_rosso (optimum_temperature 30 degC), "
        "ph_cardinal_rosso (optimum_ph 5) from the responses argument; at_reference: c30_ph5: 30 degC equals "
        "optimum_temperature 30 degC; c30_ph5: pH 5 equals optimum_ph 5"
    ) in out
    assert (
        "    oligomer_hydrolase_like on oligomer_o1: temperature_arrhenius_reference (reference_temperature 30 degC) "
        "from the responses argument; at_reference: c30_ph5: 30 degC equals reference_temperature 30 degC"
    ) in out
    assert (
        "  c40_ph5: all_members_have_kinetics (initial concentration of polymer_p1: stated; an EnvironmentGrid "
        "condition, not a conditions.csv row: the laws carry the kinetics of c30_ph5)"
    ) in out
    assert ("  check-data: load_user_dataset of this version refuses responses.csv" in out) == bool(
        _LOADER_NETWORK_LAW_REFUSAL
    )
    # The next steps run the conditions.csv row and the EnvironmentGrid condition; nothing is blocked.
    run_lines = [line.strip() for line in out.splitlines() if line.strip().startswith("fungmod run ")]
    assert len(run_lines) == 2
    assert run_lines[0].endswith("--condition c30_ph5 \\")
    assert run_lines[1].endswith("--temperature-c 40 --ph 5 \\")
    assert "--runnable-only" not in out


def test_the_command_line_refuses_a_law_on_a_pool_its_class_does_not_act_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plain_chain(tmp_path)
    _write_laws(tmp_path / "laws.csv", [{**law, "substrate": "oligomer_o1"} for law in CARDINAL_T])
    monkeypatch.chdir(tmp_path)
    code, _out, err = _cli(
        "assemble",
        "--fungus",
        "strain_n1",
        "--user-data",
        "my_chain",
        "--substrate",
        "polymer_p1",
        "--temperature-c",
        "30",
        "--ph",
        "5",
        "--network",
        "--responses",
        "laws.csv",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "chain_laws_draft",
        "--output",
        "chain_laws_draft",
    )
    assert code == EXIT_USAGE
    assert "but that class does not act on that pool" in err
    assert not (tmp_path / "chain_laws_draft").exists()


def test_assemble_help_documents_laws_in_a_network() -> None:
    code, out, _err = _cli("assemble", "--help")
    assert code == EXIT_OK
    text = " ".join(out.split())
    assert (
        "--responses (and the responses.csv rows of --user-data) bind each temperature or pH law to the member" in text
    )
    assert "only from the law's reference condition" in text
