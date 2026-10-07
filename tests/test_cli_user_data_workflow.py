"""The user-data workflow from the command line (CLI-002): assemble, draft-kinetics, check-data, run, compare, fit.

The printed run command of a draft with gaps carries --runnable-only (RUN-001): its runnable cases run and its gaps
are listed with their measurement requests (exit code 4).

Inputs are the repository's own fixtures only: the frozen SABIO-RK Reaction 618
export (real entries), the hand-written dbCAN format fixture of
``tests/fixtures/user_data/genome_case`` (synthetic gene identifiers, not a real
genome), the illustrative ``oxidase_case`` and ``uniprot_case`` datasets, and
the synthetic esterase time courses that ``tests/test_user_data_timecourse.py``
builds from a FungMod simulation with known constants (labelled synthetic in
their source column). Review fields are filled with the test reviewer's answers
of ``tests/test_user_data_assembly.py``. Every test runs with the network
refused, so no subcommand may fetch.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shlex
import shutil
import socket
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from fungal_model import (
    AVAILABLE_SOURCE_PROVIDERS,
    assemble_user_tables,
    load_user_dataset,
    user_tables_from_sabiork,
)
from fungal_model.api.user_data import FIT_IDENTIFIED, FIT_NOT_IDENTIFIED, REVIEW_MARKER
from fungal_model.api.user_data_fit import FIT_CLAIM_BOUNDARY, TIMECOURSE_COMPARISON_NOTE
from fungal_model.api.user_data_sources import USER_TABLE_PROVIDERS
from fungal_model.calibration.bayesian import BOUNDED_ABOVE_ONLY, BOUNDED_BELOW_ONLY
from fungal_model.cli import (
    EXIT_NOT_RUNNABLE,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_USAGE,
    IN_SAMPLE_HELP,
    NO_FETCH_HELP,
    main,
    shell_quote,
)
from fungal_model.registry import load_registry
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from tests.test_user_data_assembly import (
    ANNOTATION,
    ANNOTATION_SOURCE,
    CACHE,
    EXPORT,
    G1,
    OXIDASE,
    REGISTRY_INDEX,
    TIME_GRID,
    TOOL,
    _fill,
)
from tests.test_user_data_timecourse import (
    ESTERASE_CASE,
    STARTING_CONDITIONS,
    TIMECOURSE_TABLE,
    _esterase_dataset,
    _simulated_medians,
    _timecourse_from,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
ESTERASE = FIXTURES / "esterase_case"
UNIPROT = FIXTURES / "uniprot_case"
ESTERASE_STRAIN = "Esterase source strain E1"
ESTERASE_SUBSTRATE = "p-nitrophenyl butyrate"
NOT_IDENTIFIED_VERDICTS = {FIT_NOT_IDENTIFIED, BOUNDED_ABOVE_ONLY, BOUNDED_BELOW_ONLY}

G1_ASSEMBLE = (
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
    str(ANNOTATION),
    "--annotation-tool",
    TOOL,
    "--kinetics-source",
    str(EXPORT),
    "--entry-id",
    "35622",
    "--registry",
    str(REGISTRY_INDEX),
    "--dataset-id",
    "g1_cli",
)
G1_API = {
    "dataset_id": "g1_cli",
    "fungus": G1,
    "substrates": ["cellobiose"],
    "conditions": [
        {"temperature": 30.0, "temperature_units": "degC", "ph": 5.0},
        {"temperature": 40.0, "temperature_units": "degC", "ph": 5.0},
    ],
    "annotation": ANNOTATION,
    "annotation_tool": TOOL,
    "kinetics_sources": [str(EXPORT)],
    "entry_ids": ["35622"],
    "registry": REGISTRY_INDEX,
}
FIT_ARGUMENTS = (
    "--case",
    *ESTERASE_CASE,
    "--fit",
    "km",
    "10",
    "5000",
    "µM",
    "--fit",
    "kcat",
    "1",
    "300",
    "1/min",
    "--initial",
    "km",
    "1000",
    "--initial",
    "kcat",
    "5",
    "--profile-points",
    "11",
)


def _refuse_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("The fungmod command line must not touch the network.")


@pytest.fixture(autouse=True, scope="module")
def no_network() -> Iterator[None]:
    # Module scope, so that the module-scoped datasets and fits below also run without a network.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(urllib.request, "urlopen", _refuse_network)
        patch.setattr(sabiork_fetch, "urlopen", _refuse_network)
        patch.setattr(socket.socket, "connect", _refuse_network)
        yield


def _cli(*args: str | Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()
    }


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _review_line(field: dict[str, object]) -> str:
    row = "-" if field["row"] is None else str(field["row"])
    return f"{field['file']}:{row}:{field['column'] or '-'}: {field['note']}"


def _split_printed_command(text: str) -> list[str]:
    """Split a printed command the way the platform's shell would (see ``fungal_model.cli.shell_quote``)."""

    if os.name == "nt":
        return [part[1:-1] if len(part) > 1 and part[0] == part[-1] == '"' else part for part in shlex.split(text, posix=False)]
    return shlex.split(text)


def _printed_run_commands(stdout: str) -> list[list[str]]:
    """The `fungmod run` commands a draft prints as its next step, without the placeholder mode line."""

    commands = []
    for line in stdout.splitlines():
        text = line.strip()
        if text.startswith("fungmod run "):
            commands.append(_split_printed_command(text.removesuffix("\\").strip())[1:])
    return commands


def _trajectories(run_directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(run_directory).as_posix(): path.read_bytes()
        for path in sorted(run_directory.glob("*/trajectories/*.csv"))
    }


def _set_contributor(directory: Path) -> None:
    path = directory / "user_dataset.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# assemble -> fill review fields -> check-data -> run


def test_assemble_fill_check_data_and_run_end_to_end(tmp_path: Path) -> None:
    draft_dir = tmp_path / "g1_draft"
    code, out, err = _cli(*G1_ASSEMBLE, "--output", draft_dir)

    assert code == EXIT_OK, err
    draft = assemble_user_tables(**G1_API)
    # The command line passes the arguments through: the same draft, byte for byte.
    api_dir = tmp_path / "api_draft"
    draft.write(api_dir)
    assert _files(draft_dir) == _files(api_dir)

    assert "Assembled draft: g1_cli" in out
    assert f"fungus {G1!r} -> {G1} (strain genome_annotated_strain_g1, new_strain)" in out
    cases = {case["condition"]: case for case in draft.assembly["cases"]}
    assert cases["c30_ph5"]["kinetics_status"] == "transferred_estimate"
    assert cases["c40_ph5"]["kinetics_status"] == "gap"
    table = [line.split() for line in out.splitlines() if line.strip().startswith(("1 ", "2 "))]
    assert ["c30_ph5", "transferred_estimate", "same_condition", "SABIO-RK", "EntryID", "35622"] == table[0][-6:]
    assert ["c40_ph5", "gap", "none"] == table[1][-6:-3]
    for index, case in enumerate(draft.assembly["cases"], start=1):
        assert f"  case {index}: {case['reason']}" in out
    assert "Transferred from another organism (estimates, exploratory mode only): entries 35622" in out
    assert "cellulase_generic: substrate class 'cellobiose' is not among" in out
    for item in draft.assembly["unmodellable_enzyme_classes"]:
        assert f"  - {item['enzyme_class']} (families {', '.join(item['families'])}): {item['reason']}" in out
    # Every REVIEW field the API reports is listed as file:row:column: note.
    assert f"Fields to fill ({len(draft.review_fields)})" in out
    assert len(draft.review_fields) == 8
    for field in draft.review_fields:
        assert _review_line(dict(field)) in out
    assert f"fungmod check-data {shell_quote(str(draft_dir))}" in out

    # The draft does not load until every REVIEW field is filled.
    code, out_check, err_check = _cli("check-data", draft_dir)
    assert code == EXIT_USAGE
    assert "still has unfilled review fields" in err_check
    assert "user_dataset.yml:-:contributor: Unfilled review field contributor" in err_check
    assert "kinetics.csv:5:value: Unfilled review field value" in err_check
    assert f"Fill each {REVIEW_MARKER} field" in err_check

    _fill(draft_dir)
    code, out_check, err_check = _cli("check-data", draft_dir, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err_check
    dataset = load_user_dataset(draft_dir, registry=REGISTRY_INDEX)
    assert f"Digest: {dataset.digest}" in out_check
    assert "Kinetic values: 4; gaps: 4" in out_check
    assert "Genome and proteome annotations (genomes.csv): 1" in out_check
    # beta-glucosidase, cellobiohydrolase (registry class since USERDATA-008), the generic cellulase class, and
    # endo-xylanase and glucoamylase (registry classes since REGISTRY-002).
    assert len(dataset.genome_resolved_classes) == 5
    assert f"Enzyme classes resolved from them: {len(dataset.genome_resolved_classes)}" in out_check
    for item in dataset.genome_resolved_classes:
        assert item["evidence"] in out_check
    assert f"Resolved classes without a registry record: {len(dataset.unmodellable_enzyme_classes)}" in out_check
    assert "Families without an enzyme class: 2" in out_check
    assert "Time courses" not in out_check

    # The printed run command works as printed: the 40 degC gap is blocked and listed, the 30 degC case runs.
    (selection,) = _printed_run_commands(out)
    assert selection[:6] == ["run", "--user-data", str(draft_dir), "--fungus", G1, "--substrate"]
    assert selection[-5:] == ["--condition", "c30_ph5", "--condition", "c40_ph5", "--runnable-only"]
    assert (
        "--runnable-only because 1 case(s) of this command have no kinetics in the draft (beta_glucosidase on "
        "cellobiose at c40_ph5 (gap)): the preflight blocks them, so without the flag nothing is simulated (exit code "
        "3); with it the runnable cases are simulated and the blocked ones are listed with their measurement requests "
        "(exit code 4)."
    ) in out
    run = ("--mode", "exploratory", "--samples", "2", "--seed", "5", "--no-plots")
    partial = tmp_path / "partial"
    code, out_run, err_run = _cli(*selection, *run, "--output", partial)
    assert code == EXIT_PARTIAL, err_run
    assert "Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode." in out_run
    assert "Measure km of beta-glucosidase from Genome-annotated strain G1 on Cellobiose at 40 degC, pH 5" in out_run
    assert "Simulated 1 case(s) in exploratory mode: 2 sample(s) per case, seed 5." in out_run
    assert "(case_0001); exit code 4." in out_run
    cases = _csv_rows(partial / "case_summary.csv")
    assert [(row["case_id"], row["environment_id"], row["case_status"]) for row in cases] == [
        ("case_0000", "g1_cli__c30_ph5", "simulated"),
        ("case_0001", "g1_cli__c40_ph5", "not_simulated"),
    ]
    manifest = json.loads((partial / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["user_dataset_id"] == "g1_cli"
    assert manifest["user_dataset_digest"] == dataset.digest
    assert manifest["partial_run"] is True
    (blocked_case,) = manifest["blocked_cases"]
    assert blocked_case["environment_id"] == "g1_cli__c40_ph5"
    assert any(
        request.startswith("Measure km of beta-glucosidase from Genome-annotated strain G1 on Cellobiose at 40 degC")
        for request in blocked_case["suggested_experiments"]
    )

    # Without --runnable-only the same command is refused as before: exit 3, nothing written.
    blocked = tmp_path / "blocked"
    code, out_run, err_run = _cli(*selection[:-1], *run, "--output", blocked)
    assert code == EXIT_NOT_RUNNABLE, err_run
    assert "Measure km of beta-glucosidase from Genome-annotated strain G1 on Cellobiose at 40 degC, pH 5" in out_run
    assert not blocked.exists()

    # The 30 degC case alone gives the partial run's trajectories byte for byte (same seed, first grid position).
    output = tmp_path / "run_c30"
    code, out_run, err_run = _cli(*selection[:-3], *run, "--output", output)
    assert code == EXIT_OK, err_run
    assert "Simulated 1 case(s) in exploratory mode: 2 sample(s) per case, seed 5." in out_run
    assert _trajectories(output) == _trajectories(partial) != {}

    # In scientific mode no case is runnable (the transfer is an estimate, c40 is a gap): exit 3, even with the flag.
    code, out_run, err_run = _cli(*selection, "--mode", "scientific", "--output", tmp_path / "scientific")
    assert code == EXIT_NOT_RUNNABLE, err_run
    assert "--runnable-only has nothing to simulate: no requested case is runnable." in out_run
    assert not (tmp_path / "scientific").exists()


def test_assemble_options_reach_the_api_unchanged(tmp_path: Path) -> None:
    design = {
        "substrate_initial_concentration": {"value": 10.0, "units": "mM"},
        "enzyme_concentration": {"lower": 0.0005, "upper": 0.002, "units": "mM"},
    }
    arguments = (
        *G1_ASSEMBLE[:7],  # one condition: 30 degC
        *G1_ASSEMBLE[9:],
        "--annotation-source",
        ANNOTATION_SOURCE,
        "--same-species",
        "Oryza sativa",
        "--design",
        "substrate_initial_concentration=10",
        "mM",
        "--design",
        "enzyme_concentration=0.0005:0.002",
        "mM",
        "--time-grid",
        "10",
        "hour",
        "61",
        "--cache-dir",
        str(CACHE),
    )
    code, out, err = _cli(*arguments, "--output", tmp_path / "cli")

    assert code == EXIT_OK, err
    draft = assemble_user_tables(
        **{**G1_API, "conditions": G1_API["conditions"][:1]},
        annotation_source=ANNOTATION_SOURCE,
        same_species=["Oryza sativa"],
        design=design,
        time_grid=TIME_GRID,
        cache_dir=CACHE,
    )
    draft.write(tmp_path / "api")
    assert _files(tmp_path / "cli") == _files(tmp_path / "api")
    (case,) = draft.assembly["cases"]
    # The declared species makes the rice entry the fungus's own literature, not a transfer.
    assert case["kinetics_status"] == "literature_same_organism"
    assert "literature_same_organism" in out
    # With the design, time grid and annotation source given, only the reviewer is left to fill.
    assert [field["column"] for field in draft.review_fields] == ["contributor"]
    assert "Fields to fill (1)" in out
    assert "user_dataset.yml:-:contributor: REVIEW: name of the person who reviewed these tables" in out

    asserted = (
        "assemble",
        "--fungus",
        "Asserted strain A1",
        "--substrate",
        "cellobiose",
        "--temperature-c",
        "30",
        "--ph",
        "5",
        "--enzyme-class-evidence",
        "beta-glucosidase",
        "test-only assertion, not a measurement",
        "tests/test_cli_user_data_workflow.py",
        "--enzyme-class",
        "cellulase_generic",
        "--kinetics-source",
        str(EXPORT),
        "--entry-id",
        "35622",
        "--dataset-id",
        "asserted_cli",
    )
    code, out, err = _cli(*asserted, "--output", tmp_path / "asserted_cli")
    assert code == EXIT_OK, err
    api = assemble_user_tables(
        dataset_id="asserted_cli",
        fungus="Asserted strain A1",
        substrates=["cellobiose"],
        conditions=[{"temperature": 30.0, "temperature_units": "degC", "ph": 5.0}],
        enzyme_classes=[
            {
                "enzyme_class": "beta-glucosidase",
                "evidence": "test-only assertion, not a measurement",
                "source": "tests/test_cli_user_data_workflow.py",
            },
            "cellulase_generic",
        ],
        kinetics_sources=[str(EXPORT)],
        entry_ids=["35622"],
    )
    api.write(tmp_path / "asserted_api")
    assert _files(tmp_path / "asserted_cli") == _files(tmp_path / "asserted_api")
    # The class asserted by name alone leaves its evidence and source to the reviewer.
    assert {(field["file"], field["column"]) for field in api.review_fields} >= {
        ("enzymes.csv", "evidence"),
        ("enzymes.csv", "source"),
    }
    for field in api.review_fields:
        assert _review_line(dict(field)) in out


def test_assemble_with_a_response_law_prints_the_grid_command(tmp_path: Path) -> None:
    without_law = tmp_path / "oxidase_without_law"
    shutil.copytree(OXIDASE, without_law)
    (without_law / "responses.csv").unlink()
    law_rows = []
    for row in _csv_rows(OXIDASE / "responses.csv"):
        row["substrate"] = row.pop("substrate_id")
        row.pop("strain_id")
        law_rows.append(row)
    responses = tmp_path / "law.csv"
    with responses.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(law_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(law_rows)

    draft_dir = tmp_path / "draft"
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_l1",
        "--substrate",
        "syringaldazine_like",
        "--temperature-c",
        "50",
        "--temperature-c",
        "40",
        "--ph",
        "5",
        "--user-data",
        without_law,
        "--responses",
        responses,
        "--dataset-id",
        "oxidase_assembly",
        "--output",
        draft_dir,
    )

    assert code == EXIT_OK, err
    api = assemble_user_tables(
        dataset_id="oxidase_assembly",
        fungus="strain_l1",
        substrates=["syringaldazine_like"],
        conditions=[
            {"temperature": 50.0, "temperature_units": "degC", "ph": 5.0},
            {"temperature": 40.0, "temperature_units": "degC", "ph": 5.0},
        ],
        user_data=without_law,
        responses=law_rows,
    )
    api.write(tmp_path / "api")
    assert _files(draft_dir) == _files(tmp_path / "api")
    carried = {case["condition"]: case for case in api.assembly["cases"]}["c40_ph5"]
    assert carried["condition_route"] == "response_law"
    assert "condition c40_ph5: 40 degC, pH 5 (an EnvironmentGrid condition, not a conditions.csv row)" in out

    listed, grid = _printed_run_commands(out)
    assert listed[-2:] == ["--condition", "c50_ph5"]
    assert grid[-4:] == ["--temperature-c", "40", "--ph", "5"]
    _set_contributor(draft_dir)
    for index, selection in enumerate((listed, grid)):
        output = tmp_path / f"run_{index}"
        code, out_run, err_run = _cli(
            *selection, "--mode", "exploratory", "--samples", "2", "--seed", "1", "--output", output, "--no-plots"
        )
        assert code == EXIT_OK, err_run
    assert "environment effect: active_response_model" in out_run


# ---------------------------------------------------------------------------
# draft-kinetics


def test_draft_kinetics_lists_entries_as_the_api_reports_them(tmp_path: Path) -> None:
    assert dict(USER_TABLE_PROVIDERS) == {"sabiork": user_tables_from_sabiork}
    assert tuple(USER_TABLE_PROVIDERS) == AVAILABLE_SOURCE_PROVIDERS

    output = tmp_path / "r618"
    code, out, err = _cli(
        "draft-kinetics", EXPORT, "--provider", "sabiork", "--dataset-id", "r618", "--output", output
    )

    assert code == EXIT_OK, err
    draft = user_tables_from_sabiork(str(EXPORT), dataset_id="r618")
    draft.write(tmp_path / "api")
    assert _files(output) == _files(tmp_path / "api")
    assert draft.converted_entry_ids == ("38521", "39245", "44879", "44888", "60725")
    assert "Entries converted: 5 (38521, 39245, 44879, 44888, 60725)" in out
    assert f"Entries listed, not converted: {len(draft.not_converted)}" in out
    assert len(draft.not_converted) == 24
    for item in draft.not_converted:
        assert f"  {item['entry_id']}: {item['reason']}" in out
    assert f"Parameters listed, not converted: {len(draft.not_converted_parameters)}" in out
    for item in draft.not_converted_parameters:
        assert f"  entry {item['entry_id']} {item['parameter']} ({item['parameter_type']})" in out
    for field in draft.review_fields:
        assert _review_line(dict(field)) in out
    for row in draft.strains:
        assert row["strain_id"] in out
    assert f"fungmod check-data {shell_quote(str(output))}" in out

    # One selected entry, with the design, a strain id and the reaction-id form read from the frozen snapshots.
    selected = tmp_path / "os3bglu6"
    code, out, err = _cli(
        "draft-kinetics",
        "618",
        "--provider",
        "sabiork",
        "--cache-dir",
        CACHE,
        "--entry-id",
        "35622",
        "--strain-for",
        "Oryza sativa=os3bglu6_source",
        "--design",
        "substrate_initial_concentration=10",
        "mM",
        "--design",
        "enzyme_concentration=0.001",
        "mM",
        "--dataset-id",
        "os3bglu6_sabiork",
        "--output",
        selected,
    )
    assert code == EXIT_OK, err
    api = user_tables_from_sabiork(
        "618",
        dataset_id="os3bglu6_sabiork",
        entry_ids=["35622"],
        strain_id_for_organism={"Oryza sativa": "os3bglu6_source"},
        design={
            "substrate_initial_concentration": {"value": 10.0, "units": "mM"},
            "enzyme_concentration": {"value": 0.001, "units": "mM"},
        },
        cache_dir=CACHE,
    )
    api.write(tmp_path / "os3bglu6_api")
    assert _files(selected) == _files(tmp_path / "os3bglu6_api")
    assert "Entries converted: 1 (35622)" in out
    assert "os3bglu6_source" in out


def test_draft_kinetics_proposes_enzyme_classes_only_on_request(tmp_path: Path) -> None:
    code, out, err = _cli(
        "draft-kinetics",
        EXPORT,
        "--provider",
        "sabiork",
        "--entry-id",
        "39470",
        "--propose-enzyme-classes",
        "--dataset-id",
        "proposed",
        "--output",
        tmp_path / "proposed",
    )

    assert code == EXIT_OK, err
    api = user_tables_from_sabiork(str(EXPORT), dataset_id="proposed", entry_ids=["39470"], propose_enzyme_classes=True)
    assert api.enzyme_classes
    assert "enzyme_classes.csv: 1 row(s)" in out
    for field in api.review_fields:
        assert _review_line(dict(field)) in out


# ---------------------------------------------------------------------------
# check-data on a proteome-annotated dataset


def test_check_data_prints_the_proteome_resolution() -> None:
    dataset = load_user_dataset(UNIPROT, registry=REGISTRY_INDEX)

    code, out, err = _cli("check-data", UNIPROT)

    assert code == EXIT_OK, err
    (annotation,) = dataset.genome_annotations
    assert "Genome and proteome annotations (genomes.csv): 1" in out
    assert (
        f"  {annotation['annotation_file']}: proteome {annotation['proteome_id']}; "
        f"{len(annotation['unresolved_ec_numbers'])} unresolved EC number(s); "
        f"{len(annotation['ec_cazy_disagreements'])} EC/CAZy disagreement(s)"
    ) in out
    assert f"  note: {annotation['claim_boundary']}" in out
    for item in dataset.genome_resolved_classes:
        assert item["evidence"] in out
    for item in dataset.unmapped_families:
        assert f"  - {item['strain_id']} {item['family']}: {item['reason']}" in out


# ---------------------------------------------------------------------------
# Time courses: run --compare-timecourses and fit


@pytest.fixture(scope="module")
def esterase_with_timecourses(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The synthetic esterase dataset of the fit tests: three starting concentrations at 37 degC, pH 7.5."""

    root = tmp_path_factory.mktemp("cli_esterase")
    registry = load_registry(REGISTRY_INDEX)
    directory = _esterase_dataset(root / "dataset", conditions=STARTING_CONDITIONS)
    medians = _simulated_medians(directory, registry, root / "truth", strain=ESTERASE_STRAIN, substrate=ESTERASE_SUBSTRATE)
    sd = {condition: max(0.01 * initial, 0.5) for condition, initial in STARTING_CONDITIONS.items()}
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=ESTERASE_CASE, sd=sd, noise_seed=20261006), encoding="utf-8"
    )
    return directory


@pytest.fixture(scope="module")
def cli_fit(tmp_path_factory: pytest.TempPathFactory, esterase_with_timecourses: Path) -> tuple[int, str, str, Path]:
    output = tmp_path_factory.mktemp("cli_fit") / "fitted"
    code, out, err = _cli("fit", esterase_with_timecourses, *FIT_ARGUMENTS, "--output", output)
    return code, out, err, output


def _esterase_run(dataset: Path, output: Path, *extra: str) -> tuple[int, str, str]:
    return _cli(
        "run",
        "--user-data",
        dataset,
        "--fungus",
        ESTERASE_STRAIN,
        "--substrate",
        ESTERASE_SUBSTRATE,
        *(part for condition in STARTING_CONDITIONS for part in ("--condition", condition)),
        "--mode",
        "exploratory",
        "--samples",
        "1",
        "--seed",
        "1",
        "--output",
        output,
        "--no-plots",
        *extra,
    )


def _comparison_lines(stdout: str) -> dict[tuple[str, str], list[str]]:
    section = stdout.split("Time-course comparison with user dataset", 1)[1]
    return {
        (parts[0], parts[1]): parts
        for parts in (line.split() for line in section.splitlines()[2:])
        if parts and parts[0].startswith("case_") and parts[1] in {"substrate", "product"}
    }


def test_run_compares_with_the_time_courses_and_prints_rmse(tmp_path: Path, esterase_with_timecourses: Path) -> None:
    code, out, err = _cli("check-data", esterase_with_timecourses)
    assert code == EXIT_OK, err
    assert "Time courses (timecourse.csv; observations, not records): 6 series in 3 case(s)" in out
    assert "Fitted values" not in out

    output = tmp_path / "run"
    code, out, err = _esterase_run(esterase_with_timecourses, output, "--compare-timecourses")

    assert code == EXIT_OK, err
    rows = _csv_rows(output / "timecourse_comparison.csv")
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert "timecourse_comparison.csv" in manifest["files"]
    printed = _comparison_lines(out)
    series = {(row["case_id"], row["observable"]): row for row in rows}
    assert set(printed) == set(series) and len(printed) == 6
    for key, row in series.items():
        parts = printed[key]
        assert parts[2] == row["series_n_observations"] == "8"
        assert parts[4] == f"{float(row['series_rmse']):.4g}"
        assert parts[5] == row["units"]
        assert parts[-1] == "0"  # no observation was used in a fit
    assert TIMECOURSE_COMPARISON_NOTE in out
    assert f"Comparison table: {output / 'timecourse_comparison.csv'}" in out


def test_fit_prints_values_intervals_verdicts_and_writes_the_fitted_dataset(
    tmp_path: Path, cli_fit: tuple[int, str, str, Path]
) -> None:
    code, out, err, output = cli_fit

    assert code == EXIT_OK, err
    report = json.loads((output / "fit_report.json").read_text(encoding="utf-8"))
    assert report["settings"]["profile_points"] == 11
    assert report["error_model"] == "sd_weighted"
    fitted = load_user_dataset(output, registry=REGISTRY_INDEX)
    assert fitted.dataset_id == "esterase_demo_fitted"
    assert f"Fitted dataset: esterase_demo_fitted (digest {fitted.digest})" in out
    for item in report["quantities"]:
        assert item["identifiability"] == FIT_IDENTIFIED
        line = next(text.split() for text in out.splitlines() if text.strip().startswith(f"{item['quantity']} "))
        assert line[1] == f"{item['value']:.4g}"
        assert line[2] == item["units"]
        assert " ".join(line[3:5]) == f"[{item['interval'][0]:.4g}, {item['interval'][1]:.4g}]"
        assert line[5] == FIT_IDENTIFIED
    assert "observations: 48 (timecourse.csv rows 2-49); fitted quantities: 2; residual degrees of freedom: 46" in out
    assert f"In-sample: {FIT_CLAIM_BOUNDARY}" in out
    assert "scientific mode refuses them" in out

    code, out_check, err_check = _cli("check-data", output)
    assert code == EXIT_OK, err_check
    assert "Fitted values (fitted to the time courses of esterase_demo" in out_check
    assert FIT_CLAIM_BOUNDARY in out_check

    # The printed next run works, and the comparison marks every observation as used in the fit.
    (selection,) = _printed_run_commands(out)
    run_output = tmp_path / "fitted_run"
    code, out_run, err_run = _cli(
        *selection, "--mode", "exploratory", "--samples", "1", "--seed", "1", "--output", run_output, "--no-plots",
        "--compare-timecourses",
    )
    assert code == EXIT_OK, err_run
    assert all(parts[-1] == "8" for parts in _comparison_lines(out_run).values())
    code, out_run, err_run = _cli(*selection, "--mode", "scientific", "--output", tmp_path / "scientific")
    assert code == EXIT_NOT_RUNNABLE, err_run


@pytest.fixture(scope="module")
def saturating_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Initial substrate far above Km, product only: the time courses do not identify Km."""

    root = tmp_path_factory.mktemp("cli_saturating")
    registry = load_registry(REGISTRY_INDEX)
    conditions = {"s20000": 20000.0}
    directory = _esterase_dataset(root / "dataset", conditions=conditions)
    medians = _simulated_medians(directory, registry, root / "truth", strain=ESTERASE_STRAIN, substrate=ESTERASE_SUBSTRATE)
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=ESTERASE_CASE, sd={"s20000": 0.5}, observables=("product",), noise_seed=11),
        encoding="utf-8",
    )
    return directory


def test_an_unidentified_fit_exits_2_unless_allowed(tmp_path: Path, saturating_dataset: Path) -> None:
    arguments = (
        "fit",
        saturating_dataset,
        "--case",
        *ESTERASE_CASE,
        "--fit",
        "km",
        "10",
        "2000",
        "µM",
        "--fit",
        "kcat",
        "1",
        "100",
        "1/min",
        "--initial",
        "km",
        "500",
        "--initial",
        "kcat",
        "10",
        "--profile-points",
        "7",
    )
    refused = tmp_path / "refused"
    code, out, err = _cli(*arguments, "--output", refused)

    assert code == EXIT_USAGE
    assert not refused.exists()
    assert "A fitted quantity is not identified by the time courses; no fitted values are written." in err
    assert "timecourse.csv:-:-: km is" in err and "allow_unidentified=True" in err
    assert "On the command line, --allow-unidentified writes it labelled as not identified." in err
    assert "The fit was refused; nothing was written." in out
    lines = {text.split()[0]: text.split() for text in out.splitlines() if text.strip().startswith(("km ", "kcat "))}
    assert FIT_IDENTIFIED not in lines["km"] and set(lines["km"]) & NOT_IDENTIFIED_VERDICTS
    assert FIT_IDENTIFIED in lines["kcat"]

    allowed = tmp_path / "allowed"
    code, out, err = _cli(*arguments, "--allow-unidentified", "--fitted-dataset-id", "saturating_fit", "--output", allowed)
    assert code == EXIT_OK, err
    fitted = load_user_dataset(allowed, registry=REGISTRY_INDEX)
    assert fitted.dataset_id == "saturating_fit"
    assert fitted.manifest["fit"]["allow_unidentified"] is True
    verdicts = {entry["quantity"]: entry["identifiability"] for entry in fitted.manifest["fit"]["quantities"]}
    assert verdicts["km"] != FIT_IDENTIFIED
    assert verdicts["km"] in out


def test_comparison_refusals(tmp_path: Path, esterase_with_timecourses: Path) -> None:
    code, out, err = _cli(
        "run",
        "--fungus",
        "P. chrysosporium",
        "--substrate",
        "cellobiose",
        "--temperature-c",
        "30",
        "--ph",
        "5",
        "--mode",
        "scientific",
        "--output",
        tmp_path / "no_user_data",
        "--compare-timecourses",
    )
    assert code == EXIT_USAGE
    assert "give --user-data DIR" in err
    assert not (tmp_path / "no_user_data").exists()

    code, out, err = _cli(
        "run",
        "--user-data",
        ESTERASE,
        "--fungus",
        ESTERASE_STRAIN,
        "--substrate",
        ESTERASE_SUBSTRATE,
        "--condition",
        "c37_ph7_5",
        "--mode",
        "exploratory",
        "--samples",
        "1",
        "--seed",
        "1",
        "--output",
        tmp_path / "no_timecourses",
        "--compare-timecourses",
    )
    assert code == EXIT_USAGE
    assert "has no timecourse.csv" in err and "nothing was simulated" in err
    assert not (tmp_path / "no_timecourses").exists()

    # Observations beyond the simulated duration: the bundle is written, the comparison is refused.
    short = tmp_path / "short"
    shutil.copytree(esterase_with_timecourses, short)
    manifest = yaml.safe_load((short / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["simulation"] = {"duration": 30, "units": "minute", "points": 31}
    (short / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    output = tmp_path / "short_run"
    code, out, err = _esterase_run(short, output, "--compare-timecourses")
    assert code == EXIT_USAGE
    assert (output / "output_manifest.json").is_file()
    assert "the time-course comparison was refused" in out
    assert "lie outside the simulated time range" in err
    assert ":time: time 40 minute of" in err
    assert not (output / "timecourse_comparison.csv").exists()


# ---------------------------------------------------------------------------
# Usage and input errors


ASSEMBLE_BASE = ("assemble", "--fungus", G1, "--substrate", "cellobiose", "--dataset-id", "g1_cli")
GRID = ("--temperature-c", "30", "--ph", "5")
ANNOTATED = ("--annotation", str(ANNOTATION), "--annotation-tool", TOOL)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("assemble", "--fungus", G1, "--substrate", "cellobiose", *GRID), "required: --dataset-id"),
        (("assemble", "--substrate", "cellobiose", "--dataset-id", "x", *GRID), "required: --fungus"),
        ((*ASSEMBLE_BASE, "--fungus", "second", *GRID, *ANNOTATED), "one fungus per call"),
        ((*ASSEMBLE_BASE, "--temperature-c", "30", *ANNOTATED), "needs at least one --temperature-c and at least one"),
        ((*ASSEMBLE_BASE, *ANNOTATED), "name the conditions with --temperature-c T and --ph PH"),
        ((*ASSEMBLE_BASE, *GRID, "--temperature-c", "30", *ANNOTATED), "repeats the condition"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--design", "substrate_initial_concentration", "mM"), "QUANTITY=VALUE"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--design", "km=5", "mM"), "kinetic constants come from the source"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--design", "enzyme_loading=x", "mg/L"), "is not a number"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--time-grid", "10", "hour", "many"), "POINTS 'many' must be a whole"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--time-grid", "10", "parsec", "61"), "must be a time unit"),
        (("assemble", "--fungus", G1, "--substrate", "cellobiose", "--dataset-id", "Bad-Id", *GRID, *ANNOTATED),
         "dataset_id must be lowercase snake_case"),
        ((*ASSEMBLE_BASE, *GRID, "--annotation", "missing_overview.txt", "--annotation-tool", TOOL), "is not a file"),
        ((*ASSEMBLE_BASE, *GRID), "No enzyme class has evidence"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--responses", "missing.csv"), "--responses missing.csv is not a file"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--kinetics-source", "missing_export.json"), "is not a file"),
        ((*ASSEMBLE_BASE, *GRID, *ANNOTATED, "--user-data", "no_such_dataset"), "is not a directory"),
        (("draft-kinetics", str(EXPORT), "--dataset-id", "x"), "required: --provider"),
        (("draft-kinetics", str(EXPORT), "--provider", "other", "--dataset-id", "x"), "invalid choice: 'other'"),
        (("draft-kinetics", str(EXPORT), "--provider", "sabiork", "--dataset-id", "x", "--strain-for", "Oryza"),
         "must be ORGANISM=STRAIN_ID"),
        (("draft-kinetics", "missing_export.json", "--provider", "sabiork", "--dataset-id", "x"), "is not a file"),
        (("draft-kinetics", str(EXPORT), "--provider", "sabiork", "--dataset-id", "x", "--entry-id", "1"),
         "EntryID(s) 1 are not in the source"),
        (("fit", str(ESTERASE), "--case", *ESTERASE_CASE), "required: --fit"),
        (("fit", str(ESTERASE), "--fit", "km", "1", "2", "mM"), "required: --case"),
        (("fit", str(ESTERASE), "--case", *ESTERASE_CASE, "--fit", "km", "x", "2", "mM"), "LOWER: 'x' is not a number"),
        (("fit", str(ESTERASE), "--case", *ESTERASE_CASE, "--fit", "km", "1", "2", "mM", "--fit", "km", "1", "3", "mM"),
         "--fit km is given twice"),
        (("fit", str(ESTERASE), "--case", *ESTERASE_CASE, "--fit", "km", "1", "2", "mM", "--error-model", "robust"),
         "invalid choice: 'robust'"),
        (("fit", str(ESTERASE), "--case", *ESTERASE_CASE, "--fit", "km", "0", "2", "mM"), "No time course"),
        (("fit", "no_such_dataset", "--case", *ESTERASE_CASE, "--fit", "km", "1", "2", "mM"), "is not a directory"),
    ],
)
def test_usage_and_input_errors_exit_2_and_write_nothing(
    tmp_path: Path, arguments: tuple[str, ...], message: str
) -> None:
    output = tmp_path / "out"

    code, out, err = _cli(*arguments, "--output", output)

    assert code == EXIT_USAGE
    assert message in err
    assert not output.exists()


def test_fit_bounds_are_checked_by_the_api(tmp_path: Path, esterase_with_timecourses: Path) -> None:
    output = tmp_path / "out"
    code, out, err = _cli(
        "fit", esterase_with_timecourses, "--case", *ESTERASE_CASE, "--fit", "km", "0", "5000", "µM", "--output", output
    )

    assert code == EXIT_USAGE
    assert "Invalid fit bounds or starting values." in err
    assert "0 < lower < upper" in err
    assert not output.exists()


@pytest.mark.parametrize(
    "arguments",
    [
        (*G1_ASSEMBLE[:7], *G1_ASSEMBLE[9:]),
        ("draft-kinetics", str(EXPORT), "--provider", "sabiork", "--dataset-id", "x"),
        ("fit", str(ESTERASE), "--case", *ESTERASE_CASE, "--fit", "km", "1", "2", "mM"),
    ],
)
def test_new_subcommands_refuse_a_non_empty_output_directory(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    output = tmp_path / "used"
    output.mkdir()
    (output / "earlier.csv").write_text("x\n", encoding="utf-8")

    code, out, err = _cli(*arguments, "--output", output)

    assert code == EXIT_USAGE
    assert "is not empty" in err and "nothing is overwritten" in err
    assert sorted(path.name for path in output.iterdir()) == ["earlier.csv"]


def test_help_names_the_workflow_and_its_boundaries() -> None:
    code, top, _ = _cli("--help")
    assert code == EXIT_OK
    for command in ("assemble", "draft-kinetics", "fit", "check-data", "run"):
        assert command in top
    assert "user-data workflow" in top

    code, assemble_help, _ = _cli("assemble", "--help")
    assert code == EXIT_OK
    code, draft_help, _ = _cli("draft-kinetics", "--help")
    assert code == EXIT_OK
    code, fit_help, _ = _cli("fit", "--help")
    assert code == EXIT_OK
    code, run_help, _ = _cli("run", "--help")
    assert code == EXIT_OK
    flat = {name: " ".join(text.split()) for name, text in (("assemble", assemble_help), ("draft", draft_help))}
    for text in flat.values():
        assert NO_FETCH_HELP in text
    assert "{sabiork}" in draft_help  # the providers come from the API's table, not from cli.py
    assert IN_SAMPLE_HELP in " ".join(fit_help.split())
    assert "--compare-timecourses" in run_help
    assert IN_SAMPLE_HELP in " ".join(run_help.split())
    for option in ("--annotation-tool", "--kinetics-source", "--entry-id", "--design", "--time-grid", "--responses"):
        assert option in assemble_help
    for option in ("--case", "--fit", "--initial", "--error-model", "--allow-unidentified", "--profile-points"):
        assert option in fit_help


def test_the_command_line_names_no_source_database_and_opens_no_connection() -> None:
    source = (ROOT / "src" / "fungal_model" / "cli.py").read_text(encoding="utf-8")

    assert "sabio" not in source.lower()
    for forbidden in ("urllib", "urlopen", "socket", "refresh=True", "http://", "https://"):
        assert forbidden not in source, forbidden



def test_printed_commands_quote_arguments_for_the_platform_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """POSIX shells get shlex quoting; Windows gets the double quotes cmd and PowerShell read, never single quotes."""

    import fungal_model.cli as cli

    windows_path = r"C:\Users\runner\AppData\Local\Temp\pytest-0\g1 draft"
    monkeypatch.setattr(cli.os, "name", "nt")
    assert cli.shell_quote(windows_path) == f'"{windows_path}"'
    assert cli.shell_quote(r"C:\Temp\g1_draft") == r"C:\Temp\g1_draft"
    assert cli.shell_quote("Genome-annotated strain G1") == '"Genome-annotated strain G1"'
    monkeypatch.setattr(cli.os, "name", "posix")
    assert cli.shell_quote("/tmp/g1 draft") == "'/tmp/g1 draft'"
    assert cli.shell_quote("/tmp/g1_draft") == "/tmp/g1_draft"
