"""An enzyme network drafted for "fungus X on substrate Y at conditions Z" (ASSEMBLE-002).

``assemble_user_tables(network=True)`` (``fungmod assemble --network``) drafts
one USERDATA-010 enzyme network per requested substrate instead of single-class
cases: the pools a requested substrate releases are followed only through
stated products that equal a ``substrate_id`` of the user dataset or a registry
substrate ID, every class of the repertoire acting on a pool is a member with
the existing per-case kinetics status, and the loader's network rules are
applied while drafting.

Inputs are existing repository data and illustrative tables written by the
tests: the ``network_chain`` fixture with its ``enzyme_network`` block removed
(a non-network user dataset whose two user-defined classes act on a soluble
polymer-like substrate and the oligomer-like pool it releases; illustrative
estimates), the hand-written dbCAN format fixture of ``genome_case`` (synthetic
gene identifiers) with the frozen SABIO-RK Reaction 618 export, the FETCH-001
synthetic UniProt responses (served through a patched ``urlopen``; not UniProt
data), the ``network_parallel`` and ``bgl1a_ph_ionization`` fixtures, and one
test-only in-memory registry: a dissolved oligomer record whose single registry
product is the shipped ``cellobiose`` record, with the shipped
``cellobiohydrolase`` class widened in memory to its substrate class (neither is
shipped; both say so in their provenance). Nothing here is a measurement.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import os
import shutil
import socket
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import assemble_user_tables, load_user_dataset, virtual_experiment
from fungal_model.api.user_data import REVIEW_MARKER
from fungal_model.api.user_data_assembly import (
    NETWORK_BLOCKED,
    NETWORK_COMPLETE,
    NETWORK_CONDITION_STATUSES,
    NETWORK_KINETICS_COLUMNS,
    _NETWORK_LIMITATIONS,
    AssembledTablesDraft,
    UserTablesAssemblyError,
    _Assembler,
    _Candidate,
    _EntryInfo,
    _Measured,
    _Target,
)
from fungal_model.cli import EXIT_OK, EXIT_PARTIAL, EXIT_USAGE, main
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from tests.test_fetch_by_name import EXPORT_B2, NAME_B2, _FakeUniprot, _served_b2

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
CHAIN = FIXTURES / "network_chain"
PARALLEL = FIXTURES / "network_parallel"
OXIDASE = FIXTURES / "oxidase_case"
LITERATURE = FIXTURES / "literature_reentry"
PH_IONIZATION = FIXTURES / "bgl1a_ph_ionization"
ANNOTATION = FIXTURES / "genome_case" / "annotations" / "strain_g1_overview.txt"
ANNOTATION_TOOL = "dbCAN 3 overview format (hand-written fixture; no dbCAN run)"
ANNOTATION_SOURCE = "FungMod genome-route format fixture; synthetic gene identifiers, not a real genome"
EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
CACHE = ROOT / "data" / "source_snapshots" / "sabiork"
G1 = "Genome-annotated strain G1"
C30_PH5 = {"temperature": 30, "temperature_units": "degC", "ph": 5}
C40_PH5 = {"temperature": 40, "temperature_units": "degC", "ph": 5}
C25_PH7 = {"temperature": 25, "temperature_units": "degC", "ph": 7}
TIME_GRID = {"duration": 10, "units": "hour", "points": 61}
DESIGN = {
    # The virtual assay of these tests: one entry loading and one enzyme concentration, stated by the test.
    "substrate_initial_concentration": {"value": 5, "units": "mM"},
    "enzyme_concentration": {"value": 1e-3, "units": "mM"},
}
TEST_OLIGOMER = "test_cellotetraose_like"
TEST_OLIGOMER_CLASS = "test_cello_oligosaccharide_like"

# SHA-256 over the files, annotation digests and to_dict() of drafts WITHOUT network, computed at 56c8df4 (the base
# of ASSEMBLE-002, before network drafts existed): an assembly without network=True stays byte-identical.
DRAFT_DIGESTS_56C8DF4 = {
    "g1_transfer": "741f173e386203b1a5f8405577204a6febcc59e420a58e66bfd1c20ef70bd27f",
    "g1_two_conditions_gap": "204368ca656cd11ba24b4914b67c39b0ba839f1787408659623fdc1f4ab2f21b",
    "g1_conflict": "7f993e715e3696c06e436ad31cb9bc90568b93cbcc9454c227e83a50c0faaffa",
    "pc_literature_design": "3d4fb72b3e960caf7546fc600910f107f5c0f646bf227427aa55a6b7ca54cc95",
    "oxidase_law": "575cf51757313b67cb6aef9db827fff71804e327b180aa85528688495ecd05d1",
    "reentry_user_data": "4be26d5f8c6c90f5ad6be3f35bcbf578ccf5696b8a645b08b18177b4c1037b2c",
    "b2_uniprot_annotation": "b0a3cfa814d970e81a51ec1152557759849448bcafb947ea14a907af808fa32b",
}
# SHA-256 of the stdout of the docs/cli.md assemble example (no --network), run in an empty directory at 56c8df4.
CLI_STDOUT_DIGEST_56C8DF4 = "fe91cd0d865a8d7b892438714b23b9c4f3a6d034c2323f621e0c8e636f93076e"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def fail_if_network_is_used(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Assembling an enzyme network must not touch the network.")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_network_is_used)
    monkeypatch.setattr(sabiork_fetch, "urlopen", fail_if_network_is_used)
    monkeypatch.setattr(socket.socket, "connect", fail_if_network_is_used)
    yield


@pytest.fixture
def uniprot(monkeypatch: pytest.MonkeyPatch) -> _FakeUniprot:
    fake = _FakeUniprot()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


# ---------------------------------------------------------------------------
# Helpers


def _cli(*args: str | Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _without_network_block(tmp_path: Path, source: Path, name: str | None = None) -> Path:
    """A copy of a network fixture as a plain (single-class) user dataset: the enzyme_network block removed."""

    target = tmp_path / (name or f"{source.name}_plain")
    shutil.copytree(source, target)
    manifest = yaml.safe_load((target / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest.pop("enzyme_network")
    (target / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return target


def _review(directory: Path, answers: Mapping[tuple[str, str], str] | None = None) -> None:
    """Fill a written draft's REVIEW fields with the test reviewer's answers (contributor and time grid included)."""

    path = directory / "user_dataset.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    if isinstance(manifest["simulation"]["duration"], str):
        manifest["simulation"] = dict(TIME_GRID)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    for table in sorted(directory.glob("*.csv")):
        with table.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            rows = list(reader)
        changed = False
        for row in rows:
            for column in columns:
                if row[column].startswith(REVIEW_MARKER):
                    row[column] = (answers or {})[(table.name, column)]
                    changed = True
        if changed:
            _write_csv(table, rows, columns)
    assert REVIEW_MARKER not in "".join(p.read_text(encoding="utf-8") for p in directory.glob("*.csv"))


def _network_shape(dataset: Any) -> list[dict[str, Any]]:
    """The loaded networks without the dataset-specific generated ids."""

    return [
        {
            "entry_substrate": item["entry_substrate"],
            "pools": list(item["pools"]),
            "product": item["product"],
            "links": [dict(link) for link in item["links"]],
            "processes": [
                {key: value for key, value in process.items() if key != "process_id"} for process in item["processes"]
            ],
            "enzyme_classes": list(item["enzyme_classes"]),
            "strains": list(item["strains"]),
        }
        for item in dataset.enzyme_networks
    ]


def _only(items: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    (item,) = items
    return item


def _with_registry_chain(base: FungModRegistry) -> FungModRegistry:
    """The shipped registry plus a TEST-ONLY dissolved oligomer whose single registry product is ``cellobiose``.

    The record is a copy of the shipped cellobiose record with another ID, name
    and substrate class, and the shipped ``cellobiohydrolase`` class is widened
    in memory to that class, as ``tests/test_user_data_assembly.py`` widens
    glucoamylase. Neither is a shipped record and neither carries a rate; they
    exist so that a registry record's product links two registry pools.
    """

    shipped_substrate = base.substrates["cellobiose"]
    oligomer = replace(
        shipped_substrate,
        record_id=TEST_OLIGOMER,
        name="Test-only cellotetraose-like oligomer",
        aliases=(),
        maturity="exploratory_metadata",
        substrate_class=TEST_OLIGOMER_CLASS,
        products=("cellobiose",),
        provenance={"test_only": "in-memory record of tests/test_assemble_network.py; not a shipped record"},
        notes="Test-only record; not a shipped registry substrate.",
    )
    shipped_class = base.enzyme_classes["cellobiohydrolase"]
    widened = replace(
        shipped_class,
        maturity="exploratory_metadata",
        compatible_substrate_classes=(*shipped_class.compatible_substrate_classes, TEST_OLIGOMER_CLASS),
        provenance={
            **shipped_class.provenance,
            "test_only_change": f"{TEST_OLIGOMER_CLASS} added in memory by tests/test_assemble_network.py",
        },
    )
    return FungModRegistry.build(
        registry_id=base.registry_id,
        version=base.version,
        maturity=base.maturity,
        provenance=base.provenance,
        fungi=base.fungi.values(),
        enzyme_classes=(
            *(record for record in base.enzyme_classes.values() if record.record_id != "cellobiohydrolase"),
            widened,
        ),
        substrates=(*base.substrates.values(), oligomer),
        environments=base.environments.values(),
        process_compatibility=base.process_compatibility.values(),
        parameters=base.parameters.values(),
        case_templates=base.case_templates.values(),
        product_maps=base.product_maps.values(),
    )


@pytest.fixture(scope="module")
def registry_chain() -> FungModRegistry:
    return _with_registry_chain(load_registry(REGISTRY_INDEX))


def _registry_chain_draft(registry: FungModRegistry, **overrides: Any) -> AssembledTablesDraft:
    arguments: dict[str, Any] = {
        "dataset_id": "registry_chain",
        "fungus": G1,
        "substrates": [TEST_OLIGOMER],
        "conditions": [C30_PH5],
        "annotation": ANNOTATION,
        "annotation_tool": ANNOTATION_TOOL,
        "annotation_source": ANNOTATION_SOURCE,
        "kinetics_sources": [EXPORT],
        "entry_ids": ["35622"],
        "design": DESIGN,
        "time_grid": TIME_GRID,
        "registry": registry,
        "cache_dir": CACHE,
        "network": True,
    }
    arguments.update(overrides)
    return assemble_user_tables(**arguments)


# ---------------------------------------------------------------------------
# Without network nothing changes


def _baseline_drafts() -> dict[str, Any]:
    from tests.test_user_data_assembly import C30_PH6_5
    from tests.test_user_data_assembly import DESIGN as ASSEMBLY_DESIGN
    from tests.test_user_data_assembly import TIME_GRID as ASSEMBLY_TIME_GRID
    from tests.test_user_data_assembly import _g1

    return {
        "g1_transfer": lambda: _g1(),
        "g1_two_conditions_gap": lambda: _g1(conditions=[C30_PH5, C40_PH5]),
        "g1_conflict": lambda: _g1(entry_ids=None),
        "pc_literature_design": lambda: _g1(
            dataset_id="pc_assembly",
            fungus="Phanerochaete chrysosporium",
            conditions=[C30_PH6_5],
            entry_ids=None,
            design=ASSEMBLY_DESIGN,
            time_grid=ASSEMBLY_TIME_GRID,
            annotation_source=ANNOTATION_SOURCE,
        ),
        "oxidase_law": lambda: assemble_user_tables(
            dataset_id="oxidase_assembly",
            fungus="Oxidase source strain L1",
            substrates=["syringaldazine_like"],
            conditions=[{**C40_PH5, "temperature": 50}, C40_PH5],
            user_data=OXIDASE,
        ),
        "reentry_user_data": lambda: assemble_user_tables(
            dataset_id="reentry_assembly",
            fungus="Os3BGlu6 source",
            substrates=["cellobiose"],
            conditions=[C30_PH5],
            user_data=LITERATURE,
            kinetics_sources=[EXPORT],
        ),
        "b2_uniprot_annotation": lambda: assemble_user_tables(
            dataset_id="b2_from_file",
            fungus="Strain B2",
            substrates=["cellobiose"],
            conditions=[C30_PH5],
            registry=REGISTRY_INDEX,
            annotation=EXPORT_B2,
            annotation_tool="UniProt downloaded 2026-10-07",
        ),
    }


# The last limitation of a network draft without response laws until ASSEMBLE-003. Since NETWORK-003 binds
# responses.csv laws to network processes and ASSEMBLE-003 carries them into drafts, a network draft without laws says
# instead that no law is bound (_NETWORK_LIMITATIONS[-1], NETWORK-003's wording). Network drafts pinned before then are
# compared with this one sentence put back (``put_back=True``), which shows that nothing else changed.
NETWORK_LIMITATION_BEFORE_ASSEMBLE_003 = (
    "Response laws, the pH-ionization form, cultures and time courses are not combined with an enzyme network in "
    "this version; the network's kinetics apply at the condition of their rows."
)


def _with_network_limitation_put_back(text: str, *, count: int) -> str:
    """``text`` with the no-law network limitation of ASSEMBLE-003 replaced by the sentence it replaced."""

    new, old = (
        json.dumps(sentence)[1:-1] for sentence in (_NETWORK_LIMITATIONS[-1], NETWORK_LIMITATION_BEFORE_ASSEMBLE_003)
    )
    assert text.count(new) == count and old not in text
    return text.replace(new, old)


def _draft_digest(draft: AssembledTablesDraft, *, put_back: bool = False) -> str:
    payload = {
        "files": draft.file_texts(),
        "annotations": {
            name: hashlib.sha256(data).hexdigest() for name, data in sorted(draft.annotation_files.items())
        },
        "dict": draft.to_dict(),
    }
    text = json.dumps(payload, sort_keys=True)
    if put_back:
        # The sentence is in review.md and in assembly["limitations"], nowhere else.
        text = _with_network_limitation_put_back(text, count=2)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("name", sorted(DRAFT_DIGESTS_56C8DF4))
def test_drafts_without_network_are_byte_identical_to_the_base_commit(name: str) -> None:
    draft = _baseline_drafts()[name]()
    assert _draft_digest(draft) == DRAFT_DIGESTS_56C8DF4[name]
    assert "network" not in draft.assembly
    assert "enzyme_network" not in draft.manifest
    assert all("network_role" not in item for item in draft.assembly["substrates"])


@pytest.mark.skipif(os.name == "nt", reason="printed commands quote arguments for cmd on Windows")
def test_the_assemble_command_without_network_prints_what_it_printed_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code, out, err = _cli(
        "assemble",
        "--fungus",
        G1,
        "--substrate",
        "cellobiose",
        "--temperature-c",
        "30",
        "--temperature-c",
        "40",
        "--ph",
        "5",
        "--annotation",
        ANNOTATION,
        "--annotation-tool",
        ANNOTATION_TOOL,
        "--kinetics-source",
        EXPORT,
        "--entry-id",
        "35622",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "g1_draft",
        "--output",
        "g1_draft",
    )
    assert code == EXIT_OK, err
    assert hashlib.sha256(out.encode("utf-8")).hexdigest() == CLI_STDOUT_DIGEST_56C8DF4


def test_network_must_be_a_boolean() -> None:
    with pytest.raises(UserTablesAssemblyError, match="network must be True or False"):
        assemble_user_tables(
            dataset_id="x_draft",
            fungus="strain_n1",
            substrates=["polymer_p1"],
            conditions=[C30_PH5],
            user_data=CHAIN,
            network="yes",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# A chain of user substrates linked by their stated products


def test_a_user_chain_is_drafted_from_the_stated_products_and_loads_as_the_same_network(tmp_path: Path) -> None:
    plain = _without_network_block(tmp_path, CHAIN)
    assert load_user_dataset(plain, registry=REGISTRY_INDEX).enzyme_networks == ()

    draft = assemble_user_tables(
        dataset_id="chain_draft",
        fungus="strain_n1",
        substrates=["polymer_p1"],
        conditions=[C30_PH5],
        user_data=plain,
        registry=REGISTRY_INDEX,
        network=True,
    )

    assert draft.manifest["enzyme_network"] == {"entry_substrates": ["polymer_p1"]}
    # The intermediate pool is the user dataset's row, reached only because polymer_p1's product IS its substrate_id.
    assert [dict(row) for row in draft.substrates] == _csv_rows(plain / "substrates.csv")
    substrates = {item["substrate_id"]: item for item in draft.assembly["substrates"]}
    assert (substrates["polymer_p1"]["network_role"], substrates["polymer_p1"]["released_by"]) == ("entry", None)
    assert (substrates["oligomer_o1"]["network_role"], substrates["oligomer_o1"]["released_by"]) == (
        "intermediate",
        "polymer_p1",
    )
    # The user's rows are kept unchanged, in the network draft's columns (with the inhibitor column).
    assert draft.file_texts()["kinetics.csv"].splitlines()[0] == ",".join(NETWORK_KINETICS_COLUMNS)
    assert [{key: row[key] for key in _csv_rows(plain / "kinetics.csv")[0]} for row in draft.kinetics] == _csv_rows(
        plain / "kinetics.csv"
    )

    network = draft.assembly["network"]
    assert network["entry_substrates"] == ["polymer_p1"]
    assert network["status_meaning"] == dict(NETWORK_CONDITION_STATUSES)
    item = _only(network["networks"])
    assert item["pools"] == ["polymer_p1", "oligomer_o1"]
    assert [
        (link["substrate_id"], link["product"], link["product_yield"], link["releases_pool"]) for link in item["links"]
    ] == [
        ("polymer_p1", "oligomer_o1", "4", True),
        ("oligomer_o1", "monomer_m1", "2", False),
    ]
    assert item["final_product"] == "monomer_m1"
    assert item["links"][0]["stated_by"] == "user dataset network_chain substrates.csv (substrate polymer_p1)"
    assert [
        (member["enzyme_class"], member["pool"], member["pool_role"], member["kinetics_status"])
        for member in item["members"]
    ] == [
        ("depolymerase_like", "polymer_p1", "entry", {"c30_ph5": "user_data"}),
        ("oligomer_hydrolase_like", "oligomer_o1", "intermediate", {"c30_ph5": "user_data"}),
    ]
    assert item["not_members"] == []
    assert item["conditions"] == [
        {"condition": "c30_ph5", "status": NETWORK_COMPLETE, "initial_concentration": "stated", "blocked_by": []}
    ]
    # The same cases and statuses as a single-class draft, one per member class and pool.
    assert [
        (case["enzyme_class"], case["substrate_id"], case["kinetics_status"]) for case in draft.assembly["cases"]
    ] == [
        ("depolymerase_like", "polymer_p1", "user_data"),
        ("oligomer_hydrolase_like", "oligomer_o1", "user_data"),
    ]
    assert any("`oligomer_o1` is added to the draft as an intermediate pool" in text for text in draft.decisions)
    assert "## Enzyme network" in draft.review
    assert (
        "- Pools and links: `polymer_p1` -> `oligomer_o1` (4 mol/mol); `oligomer_o1` -> `monomer_m1` (2 mol/mol, final product)."
        in draft.review
    )
    assert "| oligomer_hydrolase_like | oligomer_o1 (intermediate) | user_data |" in draft.review
    assert any(
        text.startswith("Enzyme network draft: the member classes act together")
        for text in draft.assembly["limitations"]
    )
    assert [item["column"] for item in draft.review_fields] == ["contributor"]

    directory = tmp_path / "draft"
    draft.write(directory)
    _review(directory)
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    assert _network_shape(dataset) == _network_shape(load_user_dataset(CHAIN, registry=REGISTRY_INDEX))


def test_the_command_line_drafts_checks_and_runs_a_user_chain(tmp_path: Path) -> None:
    plain = _without_network_block(tmp_path, CHAIN)
    draft_dir = tmp_path / "chain_draft"
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_n1",
        "--user-data",
        plain,
        "--substrate",
        "polymer_p1",
        "--temperature-c",
        "30",
        "--temperature-c",
        "40",
        "--ph",
        "5",
        "--network",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "chain_draft",
        "--output",
        draft_dir,
    )
    assert code == EXIT_OK, err
    assert (
        "  pool oligomer_o1 -> Oligomer-like pool O1 (user_data; released by polymer_p1, an intermediate of the enzyme network)"
        in out
    )
    assert (
        "Enzyme network (--network; user_dataset.yml enzyme_network, entry substrates polymer_p1): the member classes "
        "act together, all or nothing per condition"
    ) in out
    assert (
        "  from polymer_p1: polymer_p1 -> oligomer_o1 (4 mol/mol), oligomer_o1 -> monomer_m1 (2 mol/mol, final product)"
        in out
    )
    assert "  depolymerase_like        polymer_p1 (entry)          user_data  gap" in out
    assert "  oligomer_hydrolase_like  oligomer_o1 (intermediate)  user_data  gap" in out
    assert "  c30_ph5: all_members_have_kinetics (initial concentration of polymer_p1: stated)" in out
    assert (
        "  c40_ph5: blocked (initial concentration of polymer_p1: missing): depolymerase_like on polymer_p1 (gap); "
        in out
    )
    # The next commands: check-data, then run the entry substrate with --runnable-only because c40_ph5 is blocked.
    run_lines = [line.strip() for line in out.splitlines() if line.strip().startswith("fungmod run ")]
    (run_line,) = run_lines
    assert "--condition c30_ph5 --condition c40_ph5 --runnable-only" in run_line
    assert run_line.count("--substrate") == 1 and "oligomer" not in run_line
    assert (
        "--runnable-only because 1 enzyme-network case(s) of this command are blocked (the network from polymer_p1 at c40_ph5"
        in out
    )
    assert "fungmod check-data" in out
    assert yaml.safe_load((draft_dir / "user_dataset.yml").read_text(encoding="utf-8"))["enzyme_network"] == {
        "entry_substrates": ["polymer_p1"]
    }

    _review(draft_dir)
    code, out, err = _cli("check-data", draft_dir, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "Enzyme networks (user_dataset.yml enzyme_network" in out
    assert (
        "from polymer_p1: polymer_p1 -> oligomer_o1 (4 mol/mol), oligomer_o1 -> monomer_m1 (2 mol/mol); strains strain_n1"
        in out
    )
    assert "chain_draft__network__polymer_p1__strain_n1__c40_ph5__substrate_initial_concentration__gap" in out

    run = [
        "run",
        "--user-data",
        draft_dir,
        "--fungus",
        "strain_n1",
        "--substrate",
        "polymer_p1",
        "--registry",
        REGISTRY_INDEX,
        "--mode",
        "exploratory",
        "--samples",
        "1",
        "--seed",
        "3",
        "--no-plots",
    ]
    code, out, err = _cli(
        *run, "--condition", "c30_ph5", "--condition", "c40_ph5", "--runnable-only", "--output", tmp_path / "partial"
    )
    assert code == EXIT_PARTIAL, err
    assert "Partial run: 1 of 2 requested case(s) were blocked by the preflight and not simulated" in out
    code, out, err = _cli(*run, "--condition", "c30_ph5", "--output", tmp_path / "complete")
    assert code == EXIT_OK, err
    assert "time_to_50_percent_substrate_degradation" in out
    with (tmp_path / "complete" / "mechanism_summary.csv").open(encoding="utf-8", newline="") as handle:
        kinds = [row["mechanism_kind"] for row in csv.DictReader(handle)]
    assert kinds == ["process_law", "process_law", "process_law"]


def test_each_requested_substrate_is_an_entry_and_an_intermediate_may_start_its_own_network(tmp_path: Path) -> None:
    plain = _without_network_block(tmp_path, CHAIN)
    draft = assemble_user_tables(
        dataset_id="two_entries",
        fungus="strain_n1",
        substrates=["polymer_p1", "oligomer_o1"],
        conditions=[C30_PH5],
        user_data=plain,
        registry=REGISTRY_INDEX,
        design={"substrate_initial_concentration": {"value": 3, "units": "mM"}},
        network=True,
    )
    assert draft.manifest["enzyme_network"] == {"entry_substrates": ["polymer_p1", "oligomer_o1"]}
    assert [item["pools"] for item in draft.assembly["network"]["networks"]] == [
        ["polymer_p1", "oligomer_o1"],
        ["oligomer_o1"],
    ]
    # The design loading starts the second network; the first network's entry keeps the user's 5 mM.
    initials = {
        (row["substrate_id"], row["value"])
        for row in draft.kinetics
        if row["quantity"] == "substrate_initial_concentration"
    }
    assert initials == {("polymer_p1", "5"), ("oligomer_o1", "3")}
    directory = tmp_path / "draft"
    draft.write(directory)
    _review(directory)
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    assert [item["pools"] for item in dataset.enzyme_networks] == [["polymer_p1", "oligomer_o1"], ["oligomer_o1"]]


# ---------------------------------------------------------------------------
# A chain of registry substrates linked by a registry record's product


def test_a_registry_chain_follows_the_registry_product_and_keeps_every_member(
    registry_chain: FungModRegistry, tmp_path: Path
) -> None:
    draft = _registry_chain_draft(registry_chain)

    assert draft.manifest["enzyme_network"] == {"entry_substrates": [TEST_OLIGOMER]}
    assert [row["substrate_id"] for row in draft.substrates] == [TEST_OLIGOMER, "cellobiose"]
    item = _only(draft.assembly["network"]["networks"])
    assert item["pools"] == [TEST_OLIGOMER, "cellobiose"]
    assert [(link["product"], link["releases_pool"]) for link in item["links"]] == [
        ("cellobiose", True),
        ("beta_D_glucose", False),
    ]
    assert item["final_product"] == "beta_D_glucose"
    # Registry records state both products; cellobiose's yield and source come from the converted SABIO-RK entry.
    assert [link["stated_by"] for link in item["links"]] == [
        f"registry substrate record {TEST_OLIGOMER}",
        "registry substrate record cellobiose",
    ]
    assert item["links"][1]["source"] == "SABIO-RK Reaction 618 equation: H2O + Cellobiose = 2 beta-D-Glucose"
    assert [(member["enzyme_class"], member["pool"], member["kinetics_status"]) for member in item["members"]] == [
        ("cellobiohydrolase", TEST_OLIGOMER, {"c30_ph5": "gap"}),
        ("beta_glucosidase", "cellobiose", {"c30_ph5": "transferred_estimate"}),
    ]
    # Classes of the annotation that act on no pool are listed, not members, with each pool's reason.
    not_members = {member["enzyme_class"]: member["reasons"] for member in item["not_members"]}
    assert set(not_members) == {"cellulase_generic", "endo_xylanase", "glucoamylase"}
    assert all(len(reasons) == 2 for reasons in not_members.values())
    assert not_members["endo_xylanase"][1] == (
        "cellobiose: substrate class 'cellobiose' is not among the class's substrate classes ['xylan']"
    )
    # All or nothing: the member without kinetics blocks the network; it is a gap, never left out.
    assert item["conditions"] == [
        {
            "condition": "c30_ph5",
            "status": NETWORK_BLOCKED,
            "initial_concentration": "stated",
            "blocked_by": [f"cellobiohydrolase on {TEST_OLIGOMER} (gap)"],
        }
    ]
    # The intermediate pool takes no initial concentration: the converted entry's row is listed, not written.
    assert not any(
        row["substrate_id"] == "cellobiose" and row["quantity"] == "substrate_initial_concentration"
        for row in draft.kinetics
    )
    assert any(
        item["entry_id"] == "35622"
        and item["parameter"] == "substrate_initial_concentration (5 mM)"
        and "is an intermediate pool of the enzyme network" in item["reason"]
        for item in draft.not_converted_parameters
    )
    # The entry's design loading is written once, on the gap case of the class acting on it.
    entry_rows = [row for row in draft.kinetics if row["substrate_id"] == TEST_OLIGOMER]
    assert [(row["enzyme_class"], row["quantity"], row["value"]) for row in entry_rows] == [
        ("cellobiohydrolase", "substrate_initial_concentration", "5")
    ]
    transfer = {row["quantity"]: row for row in draft.kinetics if row["enzyme_class"] == "beta_glucosidase"}
    assert transfer["km"]["evidence_type"] == "estimate"
    assert transfer["km"]["method"].startswith("transferred from Oryza sativa enzyme, SABIO-RK entry 35622")
    gaps = draft.review.split("## Gaps and measurement requests", 1)[1].split("\n## ", 1)[0]
    assert f"cellobiohydrolase on {TEST_OLIGOMER} at c30_ph5" in gaps
    assert (
        "is the entry pool of an enzyme network, which runs at this condition only when every member class has kinetics"
        in gaps
    )
    review_fields = {(field["file"], field["column"]) for field in draft.review_fields}
    assert review_fields == {
        ("user_dataset.yml", "contributor"),
        ("substrates.csv", "product_yield"),
        ("substrates.csv", "source"),
    }

    directory = tmp_path / "draft"
    draft.write(directory)
    _review(
        directory,
        {
            ("substrates.csv", "product_yield"): "2",
            ("substrates.csv", "source"): "Test reviewer's stoichiometry of the test-only oligomer record",
        },
    )
    dataset = load_user_dataset(directory, registry=registry_chain)
    (network,) = dataset.enzyme_networks
    assert network["pools"] == [TEST_OLIGOMER, "cellobiose"]
    assert [process["enzyme_class"] for process in network["processes"]] == ["cellobiohydrolase", "beta_glucosidase"]
    study = virtual_experiment(
        fungi=G1, substrates=TEST_OLIGOMER, environments="c30_ph5", registry=registry_chain, user_data=dataset
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "underparameterized"
    assert any(
        "Cellobiohydrolase" in text and "Test-only cellotetraose-like oligomer" in text
        for text in report.suggested_experiments
    )


def test_a_product_named_by_name_is_not_a_link(registry_chain: FungModRegistry) -> None:
    draft = _registry_chain_draft(
        registry_chain,
        substrates=[
            {"substrate": TEST_OLIGOMER, "product": "Cellobiose", "product_yield": 2, "source": "Test reviewer"}
        ],
    )
    item = _only(draft.assembly["network"]["networks"])
    assert item["pools"] == [TEST_OLIGOMER]
    assert item["final_product"] == "Cellobiose"
    assert any(
        "names registry substrate `cellobiose` by its name or alias, not by its ID" in text for text in draft.decisions
    )


def test_a_registry_fungus_network_of_literature_values_reaches_scientific_mode(tmp_path: Path) -> None:
    from tests.test_user_data_assembly import C30_PH6_5

    draft = assemble_user_tables(
        dataset_id="pc_network",
        fungus="Phanerochaete chrysosporium",
        substrates=["cellobiose"],
        conditions=[C30_PH6_5],
        kinetics_sources=[EXPORT],
        design={
            "substrate_initial_concentration": {"value": 10, "units": "mM"},
            "enzyme_concentration": {"value": 1e-3, "units": "mM"},
        },
        time_grid=TIME_GRID,
        registry=REGISTRY_INDEX,
        cache_dir=CACHE,
        network=True,
    )
    item = _only(draft.assembly["network"]["networks"])
    assert [(member["enzyme_class"], member["kinetics_status"]) for member in item["members"]] == [
        ("beta_glucosidase", {"c30_ph6_5": "literature_same_organism"})
    ]
    assert item["conditions"][0]["status"] == NETWORK_COMPLETE
    assert draft.assembly["stored_registry_cases"], "the registry fungus's stored cases are listed, not copied"
    directory = tmp_path / "draft"
    draft.write(directory)
    _review(directory)
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    study = virtual_experiment(
        fungi=draft.strains[0]["name"], substrates="cellobiose", environments="c30_ph6_5", user_data=dataset
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "modelable"


def test_a_pool_under_review_leaves_the_network_undetermined() -> None:
    draft = assemble_user_tables(
        dataset_id="undescribed_network",
        fungus=G1,
        substrates=["Undescribed dissolved substrate U1"],
        conditions=[C30_PH5],
        annotation=ANNOTATION,
        annotation_tool=ANNOTATION_TOOL,
        annotation_source=ANNOTATION_SOURCE,
        registry=REGISTRY_INDEX,
        network=True,
    )
    item = _only(draft.assembly["network"]["networks"])
    assert item["undetermined_pools"] == ["undescribed_dissolved_substrate_u1"]
    assert item["members"] == []
    assert item["final_product"] is None
    assert item["conditions"][0]["status"] == "undetermined"
    assert draft.manifest["enzyme_network"] == {"entry_substrates": ["undescribed_dissolved_substrate_u1"]}
    review_columns = {field["column"] for field in draft.review_fields if field["file"] == "substrates.csv"}
    assert {"substrate_class", "bond_classes", "product"} <= review_columns


# ---------------------------------------------------------------------------
# A proteome snapshot (FETCH-001 synthetic responses) and a registry substrate


def test_a_proteome_found_by_name_gives_a_network_that_lists_the_classes_on_no_pool_and_runs(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    _served_b2(uniprot)
    draft_dir = tmp_path / "b2_network"
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "Strain B2",
        "--scientific-name",
        NAME_B2,
        "--fetch-proteome",
        "--fetch",
        "--snapshot-dir",
        tmp_path / "snapshots",
        "--substrate",
        "cellobiose",
        "--temperature-c",
        "30",
        "--ph",
        "5",
        "--kinetics-source",
        EXPORT,
        "--entry-id",
        "35622",
        "--cache-dir",
        CACHE,
        "--design",
        "substrate_initial_concentration=5",
        "mM",
        "--design",
        "enzyme_concentration=0.001",
        "mM",
        "--time-grid",
        "10",
        "hour",
        "61",
        "--network",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "b2_network",
        "--output",
        draft_dir,
    )
    assert code == EXIT_OK, err
    assert uniprot.requested[0].startswith("https://rest.uniprot.org/proteomes/search?"), (
        "the proteome is found by name"
    )
    assert "  from cellobiose: cellobiose -> beta_D_glucose (2 mol/mol, final product)" in out
    assert "  beta_glucosidase  cellobiose (entry)  transferred_estimate" in out
    assert "  c30_ph5: all_members_have_kinetics (initial concentration of cellobiose: stated)" in out
    assert (
        "  not a member (acts on no pool of this network): endo_xylanase: cellobiose: substrate class 'cellobiose' is "
        "not among the class's substrate classes ['xylan']"
    ) in out
    assert "  not a member (acts on no pool of this network): chitinase: cellobiose: " in out
    run_line = next(line.strip() for line in out.splitlines() if line.strip().startswith("fungmod run "))
    assert run_line.endswith("--substrate cellobiose --condition c30_ph5 \\"), "no --runnable-only: nothing is blocked"

    _review(draft_dir)
    code, out, err = _cli("check-data", draft_dir, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "from cellobiose: cellobiose -> beta_D_glucose (2 mol/mol); strains strain_b2" in out
    code, out, err = _cli(
        "run",
        "--user-data",
        draft_dir,
        "--fungus",
        "Strain B2",
        "--substrate",
        "cellobiose",
        "--condition",
        "c30_ph5",
        "--registry",
        REGISTRY_INDEX,
        "--mode",
        "exploratory",
        "--samples",
        "2",
        "--seed",
        "1",
        "--output",
        tmp_path / "run",
        "--no-plots",
    )
    assert code == EXIT_OK, err
    assert "Simulated 1 case(s) in exploratory mode" in out


# ---------------------------------------------------------------------------
# An existing network dataset as user_data


def test_a_network_dataset_is_kept_with_its_ki_rows_when_network_is_requested(tmp_path: Path) -> None:
    with pytest.raises(UserTablesAssemblyError, match=r"declares enzyme networks.*Pass network=True"):
        assemble_user_tables(
            dataset_id="parallel_draft",
            fungus="strain_q2",
            substrates=["ester_s2"],
            conditions=[C25_PH7],
            user_data=PARALLEL,
        )
    draft = assemble_user_tables(
        dataset_id="parallel_draft",
        fungus="strain_q2",
        substrates=["ester_s2"],
        conditions=[C25_PH7],
        user_data=PARALLEL,
        registry=REGISTRY_INDEX,
        network=True,
    )
    source = _csv_rows(PARALLEL / "kinetics.csv")
    assert [{key: row[key] for key in source[0]} for row in draft.kinetics] == source
    ki = next(row for row in draft.kinetics if row["quantity"] == "ki")
    assert ki["inhibitor"] == "acid_a2"
    item = _only(draft.assembly["network"]["networks"])
    assert [(member["enzyme_class"], member["pool"]) for member in item["members"]] == [
        ("cleaver_a_like", "ester_s2"),
        ("cleaver_b_like", "ester_s2"),
    ]
    directory = tmp_path / "draft"
    draft.write(directory)
    _review(directory)
    assert _network_shape(load_user_dataset(directory, registry=REGISTRY_INDEX)) == _network_shape(
        load_user_dataset(PARALLEL, registry=REGISTRY_INDEX)
    )


# ---------------------------------------------------------------------------
# The loader's rules, applied while drafting


def _user_class_on_cellobiose(tmp_path: Path) -> Path:
    """The literature_reentry strain with a second, user-defined class on cellobiose (illustrative estimates).

    Its beta-glucosidase keeps its enzymes.csv row and loses its kinetics rows,
    so that its kinetics come from the SABIO-RK entry while the user-defined
    class states its own initial cellobiose concentration.
    """

    target = tmp_path / "two_classes"
    shutil.copytree(LITERATURE, target)
    (target / "enzyme_classes.csv").write_text(
        "class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source\n"
        "cleaver_t1_like,Illustrative cleaver-like class T1,,beta_1_4_glycosidic,cellobiose,"
        "Illustrative user-defined class of tests/test_assemble_network.py\n",
        encoding="utf-8",
    )
    with (target / "enzymes.csv").open("a", encoding="utf-8", newline="") as handle:
        handle.write("os3bglu6_source,cleaver_t1_like,illustrative assertion,tests/test_assemble_network.py\n")
    columns = list(_csv_rows(LITERATURE / "kinetics.csv")[0])
    base = {column: "" for column in columns}
    rows = [
        {
            **base,
            "strain_id": "os3bglu6_source",
            "enzyme_class": "cleaver_t1_like",
            "substrate_id": "cellobiose",
            "condition_id": "c30_ph5",
            "quantity": quantity,
            "value": value,
            "units": units,
            "evidence_type": "estimate",
            "method": "illustrative estimate",
            "source": "tests/test_assemble_network.py",
        }
        for quantity, value, units in (
            ("km", "2", "mM"),
            ("vmax", "0.05", "mM/min"),
            ("substrate_initial_concentration", "10", "mM"),
        )
    ]
    _write_csv(target / "kinetics.csv", rows, columns)
    return target


def test_the_user_initial_concentration_of_an_entry_wins_and_the_assay_value_is_listed(tmp_path: Path) -> None:
    dataset = _user_class_on_cellobiose(tmp_path)
    draft = assemble_user_tables(
        dataset_id="two_class_network",
        fungus="os3bglu6_source",
        substrates=["cellobiose"],
        conditions=[C30_PH5],
        user_data=dataset,
        kinetics_sources=[EXPORT],
        entry_ids=["35622"],
        registry=REGISTRY_INDEX,
        cache_dir=CACHE,
        network=True,
    )
    item = _only(draft.assembly["network"]["networks"])
    assert [(member["enzyme_class"], member["kinetics_status"]["c30_ph5"]) for member in item["members"]] == [
        ("beta_glucosidase", "literature_same_organism"),
        ("cleaver_t1_like", "user_data"),
    ]
    initials = [row for row in draft.kinetics if row["quantity"] == "substrate_initial_concentration"]
    assert [(row["enzyme_class"], row["value"], row["units"]) for row in initials] == [("cleaver_t1_like", "10", "mM")]
    assert any(
        item["entry_id"] == "35622"
        and item["parameter"] == "substrate_initial_concentration (3.06 to 76.5 mM)"
        and "which the user dataset states (10 mM)" in item["reason"]
        for item in draft.not_converted_parameters
    )
    directory = tmp_path / "draft"
    draft.write(directory)
    _review(
        directory,
        {
            ("kinetics.csv", "value"): "0.001",
            ("kinetics.csv", "units"): "mM",
            ("kinetics.csv", "source"): "Test reviewer",
        },
    )
    (network,) = load_user_dataset(directory, registry=REGISTRY_INDEX).enzyme_networks
    assert [(process["enzyme_class"], process["rate_form"]) for process in network["processes"]] == [
        ("beta_glucosidase", "kcat"),
        ("cleaver_t1_like", "Vmax"),
    ]


def test_disagreeing_source_initial_concentrations_become_one_review_field() -> None:
    """The assay concentrations of two converted entries on one entry pool disagree: one REVIEW row replaces them.

    Two SABIO-RK classes on one substrate at one condition do not occur in the
    repository's snapshots, so the rule is exercised on the assembler directly.
    """

    assembler = _Assembler(dataset_id="unit_draft", base=load_registry(REGISTRY_INDEX), design=None, cache_dir=CACHE)
    assembler.network = True
    target = _Target(
        index=0,
        input="entry_e1",
        substrate_id="entry_e1",
        registry_id="",
        name="Entry pool E1",
        substrate_class="entry_like",
        bond_classes=("bond_like",),
        resolved_as="new",
        spec={"substrate": "entry_e1"},
        network_role="entry",
    )
    measured = _Measured(
        condition_id="c30_ph5",
        temperature="30",
        temperature_units="degC",
        ph="5",
        notes="",
        kelvin=303.15,
        ph_value=5.0,
    )

    def candidate(order: int, class_key: str, entry_id: str, value: str) -> tuple[dict[str, str], _Candidate]:
        row = {
            "strain_id": "strain_u",
            "enzyme_class": class_key,
            "substrate_id": "entry_e1",
            "condition_id": "c30_ph5",
            "quantity": "substrate_initial_concentration",
            "value": value,
            "lower": "",
            "upper": "",
            "units": "mM",
            "evidence_type": "estimate",
            "method": "assay",
            "source": f"entry {entry_id}",
            "sd": "",
        }
        info = _EntryInfo(entry_id=entry_id, organism="Organism", host="", enzyme="Enzyme", source_label="s")
        return row, _Candidate(
            order=order,
            level=2,
            status="transferred_estimate",
            class_key=class_key,
            target=target,
            measured=measured,
            rows=[row],
            form="vmax",
            source_ids=(f"SABIO-RK EntryID {entry_id}",),
            label=f"SABIO-RK EntryID {entry_id} (Organism)",
            entry=info,
        )

    agreeing = assembler._consolidated_entry_initials(
        [candidate(0, "class_a", "1", "5"), candidate(1, "class_b", "2", "5.0")], {"entry_e1": "Entry pool E1"}
    )
    assert [row["value"] for row in agreeing] == ["5", "5.0"], "equal numbers agree, as the loader compares them"
    rows = assembler._consolidated_entry_initials(
        [candidate(0, "class_a", "1", "5"), candidate(1, "class_b", "2", "8")], {"entry_e1": "Entry pool E1"}
    )
    (row,) = rows
    assert (row["enzyme_class"], row["evidence_type"]) == ("class_a", "design")
    assert row["value"].startswith(
        f"{REVIEW_MARKER} initial concentration of Entry pool E1 in the enzyme network at c30_ph5"
    )
    assert (
        "5 mM from SABIO-RK EntryID 1 (Organism) for class_a; 8 mM from SABIO-RK EntryID 2 (Organism) for class_b"
        in row["value"]
    )
    assert row["units"].startswith(REVIEW_MARKER) and row["source"].startswith(REVIEW_MARKER)
    assert {item["entry_id"] for item in assembler.not_converted_parameters} == {"1", "2"}


def test_the_ph_ionization_form_is_a_gap_in_a_network() -> None:
    draft = assemble_user_tables(
        dataset_id="ph_network",
        fungus="bgl1a_source",
        substrates=["cellobiose"],
        conditions=[C30_PH5],
        user_data=PH_IONIZATION,
        registry=REGISTRY_INDEX,
        network=True,
    )
    (case,) = draft.assembly["cases"]
    assert case["kinetics_status"] == "gap"
    assert "states the pH-ionization rate form, which an enzyme network does not bind" in case["reason"]
    assert draft.kinetics == ()
    assert any("pH-ionization rate form" in text for text in draft.assembly["unused_user_rows"])
    item = _only(draft.assembly["network"]["networks"])
    assert item["conditions"][0]["status"] == NETWORK_BLOCKED


def _chain_variant(tmp_path: Path, *, substrates: str | None = None, classes: str | None = None) -> Path:
    plain = _without_network_block(tmp_path, CHAIN)
    if substrates is not None:
        (plain / "substrates.csv").write_text(substrates, encoding="utf-8")
    if classes is not None:
        (plain / "enzyme_classes.csv").write_text(classes, encoding="utf-8")
    return plain


def _chain_draft(user_data: Path, **overrides: Any) -> AssembledTablesDraft:
    arguments: dict[str, Any] = {
        "dataset_id": "chain_draft",
        "fungus": "strain_n1",
        "substrates": ["polymer_p1"],
        "conditions": [C30_PH5],
        "user_data": user_data,
        "registry": REGISTRY_INDEX,
        "network": True,
    }
    arguments.update(overrides)
    return assemble_user_tables(**arguments)


def test_what_a_network_cannot_run_is_refused(tmp_path: Path) -> None:
    substrates = (CHAIN / "substrates.csv").read_text(encoding="utf-8")
    classes = (CHAIN / "enzyme_classes.csv").read_text(encoding="utf-8")

    # A cycle of stated products.
    cycle = _chain_variant(
        tmp_path / "cycle",
        substrates=substrates.replace(
            "oligomer_like,dissolved,inner_glycosidic_like,monomer_m1,2,",
            "oligomer_like,dissolved,inner_glycosidic_like,polymer_p1,0.25,",
        ),
    )
    with pytest.raises(UserTablesAssemblyError, match=r"form a cycle .*polymer_p1 -> oligomer_o1 -> polymer_p1"):
        _chain_draft(cycle)

    # A product that is the registry substrate of a row with another substrate_id.
    ambiguous = _chain_variant(
        tmp_path / "ambiguous",
        substrates=substrates.replace("inner_glycosidic_like,monomer_m1,2,", "inner_glycosidic_like,cellobiose,2,")
        + "cb_pool,cellobiose,,,,,beta_D_glucose,2,mol/mol,Illustrative registry reference\n",
    )
    with pytest.raises(
        UserTablesAssemblyError, match=r"is the registry substrate of 'cb_pool' but not its substrate_id"
    ):
        _chain_draft(ambiguous)

    # A class acting on two pools of one network.
    two_pools = _chain_variant(
        tmp_path / "two_pools",
        classes=classes.replace(
            "inner_glycosidic_like,oligomer_like,", "inner_glycosidic_like,oligomer_like;soluble_polymer_like,"
        ),
    )
    with pytest.raises(
        UserTablesAssemblyError, match=r"'oligomer_hydrolase_like' .* acts on 2 pools .*competes for its active site"
    ):
        _chain_draft(two_pools)

    # A colliding state name: the class on the oligomer pool is named like the entry pool, and in the kcat form its
    # enzyme state takes the entry's state name; each single-class case alone has no collision, so the plain dataset
    # loads.
    collision = _chain_variant(
        tmp_path / "collision", classes=classes.replace("oligomer_hydrolase_like,", "polymer_p1,", 1)
    )
    for name in ("enzymes.csv", "kinetics.csv"):
        path = collision / name
        path.write_text(
            path.read_text(encoding="utf-8").replace("oligomer_hydrolase_like", "polymer_p1"), encoding="utf-8"
        )
    load_user_dataset(collision, registry=REGISTRY_INDEX)
    with pytest.raises(UserTablesAssemblyError, match=r"would give the state 'polymer_p1_concentration' to both"):
        _chain_draft(collision)

    # A product that is a solid substrate: drafts cover dissolved pools only.
    with pytest.raises(
        UserTablesAssemblyError, match=r"is registry substrate 'xylan' with physical state 'solid_polymer'"
    ):
        _chain_draft(
            _without_network_block(tmp_path / "solid", CHAIN),
            substrates=[
                {
                    "substrate": "Dissolved test pool",
                    "substrate_id": "dissolved_t1",
                    "substrate_class": "soluble_polymer_like",
                    "physical_state": "dissolved",
                    "bond_classes": "inner_glycosidic_like",
                    "product": "xylan",
                }
            ],
        )

    # Response laws are no longer refused (ASSEMBLE-003, tests/test_assemble_network_responses.py): an empty responses
    # argument drafts what no argument drafts, and a dataset's responses.csv rows on a pool are kept against its
    # member. What is refused is a law on a class that is no member or on a pool its class does not act on.
    laws_plain = _without_network_block(tmp_path / "laws", CHAIN)
    assert _draft_digest(_chain_draft(laws_plain, responses=[])) == _draft_digest(_chain_draft(laws_plain))
    oxidase = assemble_user_tables(
        dataset_id="oxidase_network",
        fungus="strain_l1",
        substrates=["syringaldazine_like"],
        conditions=[{**C40_PH5, "temperature": 50}],
        user_data=OXIDASE,
        network=True,
    )
    assert [dict(row) for row in oxidase.responses] == _csv_rows(OXIDASE / "responses.csv")
    with pytest.raises(UserTablesAssemblyError, match=r"but that class does not act on that pool"):
        _chain_draft(
            laws_plain,
            responses=[
                {
                    "enzyme_class": "depolymerase_like",
                    "substrate": "oligomer_o1",
                    "law": "temperature_arrhenius_reference",
                    "parameter": "activation_energy",
                    "value": 50,
                    "units": "kJ/mol",
                    "evidence_type": "estimate",
                    "source": "Illustrative test note",
                }
            ],
        )

    # An entry no class of the fungus acts on.
    with pytest.raises(UserTablesAssemblyError, match=r"No enzyme class of .* acts on Cellobiose \(cellobiose\)"):
        assemble_user_tables(
            dataset_id="no_member",
            fungus="Strain Z",
            substrates=["cellobiose"],
            conditions=[C30_PH5],
            enzyme_classes=[{"enzyme_class": "endo_xylanase", "evidence": "test assertion", "source": "test"}],
            registry=REGISTRY_INDEX,
            network=True,
        )


def test_disagreeing_user_initial_concentrations_of_an_entry_are_refused(tmp_path: Path) -> None:
    plain = _without_network_block(tmp_path, PARALLEL)
    rows = [
        {column: value for column, value in row.items() if column != "inhibitor"}
        for row in _csv_rows(plain / "kinetics.csv")
        if row["quantity"] != "ki"
    ]
    for row in rows:
        if row["enzyme_class"] == "cleaver_b_like" and row["quantity"] == "substrate_initial_concentration":
            row["value"] = "900"
    _write_csv(plain / "kinetics.csv", rows, list(rows[0]))
    load_user_dataset(plain, registry=REGISTRY_INDEX)
    with pytest.raises(
        UserTablesAssemblyError, match=r"states different initial concentrations of 'ester_s2' at condition 'c25_ph7'"
    ):
        assemble_user_tables(
            dataset_id="parallel_plain",
            fungus="strain_q2",
            substrates=["ester_s2"],
            conditions=[C25_PH7],
            user_data=plain,
            registry=REGISTRY_INDEX,
            network=True,
        )


def test_the_command_line_reports_a_refusal_with_exit_code_2(tmp_path: Path) -> None:
    # The oxidase dataset's responses.csv is now carried into a network draft (ASSEMBLE-003); a refusal of the network
    # rules still exits 2 and writes nothing: here no class of the strain acts on the requested entry substrate.
    code, _out, err = _cli(
        "assemble",
        "--fungus",
        "strain_l1",
        "--user-data",
        OXIDASE,
        "--substrate",
        "cellobiose",
        "--temperature-c",
        "50",
        "--ph",
        "5",
        "--network",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "oxidase_network",
        "--output",
        tmp_path / "draft",
    )
    assert code == EXIT_USAGE
    assert "No enzyme class of Oxidase source strain L1 acts on Cellobiose (cellobiose)" in err
    assert not (tmp_path / "draft" / "user_dataset.yml").exists()


def test_assemble_help_documents_the_network_option() -> None:
    code, out, _err = _cli("assemble", "--help")
    assert code == EXIT_OK
    assert "--network" in out
    assert "several enzymes acting together (--network):" in out
