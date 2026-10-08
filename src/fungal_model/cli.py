"""Command-line virtual experiments: name fungi, substrates and conditions, and FungMod calculates.

``fungmod run`` resolves the names on the registry (with an optional user
dataset overlaid in memory), runs the modelability preflight, simulates when
every requested case is runnable in the requested mode (with
``--runnable-only``, the runnable cases of a request whose other cases are
blocked), and writes the standard output bundle: tables, manifest, Markdown
report and, with ``--report``, the HTML report; with ``--compare-timecourses``
it also compares the simulation with the user dataset's time courses.
``fungmod preflight`` stops after the preflight, ``fungmod check-data``
validates a user dataset directory, and ``fungmod list`` shows what can be
named.

The user-data workflow: ``fungmod assemble`` drafts one reviewable user
dataset for a fungus on substrates at conditions from the sources a user has
(``assemble_user_tables``), ``fungmod draft-kinetics`` drafts user tables from
a public kinetics export or frozen snapshot (the API's provider table,
``USER_TABLE_PROVIDERS``), and ``fungmod fit`` fits kinetic constants of one
case to the dataset's time courses (``fit_user_dataset``). The enzyme
repertoire of ``assemble`` can be a UniProt proteome (``--proteome UP...``, or
``--fetch-proteome`` for the reference proteome found under the fungus's name
by ``fungal_model.sources.uniprot``); its frozen snapshots are read from disk,
and the network is reached only with ``assemble --fetch``, the one network
opt-in of the command line. ``assemble --network`` drafts an enzyme network
(``enzyme_network``: every class of the repertoire acting on a pool the
requested substrates release acts together) instead of single-class cases.

The command line only parses arguments and prints what the API returns; every
scientific decision (name resolution, modelability, the simulation rule of each
mode, sampling, tables and reports, assembly, drafting and fitting) stays in
``fungal_model.api``, and the choice of a proteome for an organism name in
``fungal_model.sources.uniprot``. Every value comes from the command line, the
registry or the API: the mode, the sample count, the seed and the output
directory have no defaults, a condition grid needs both temperature and pH
values, and an option that is not given leaves the API's own default (stated
in the help) in place.

Exit codes: 0 success; 1 the simulation failed after a passing preflight;
2 usage or input error (including invalid user data, a refused draft and a
refused fit); 3 the preflight blocks a requested case in the requested mode and
nothing is simulated; 4 partial run: with ``--runnable-only`` the runnable
cases were simulated and the blocked ones are listed as not simulated.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shlex
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from fungal_model import __version__
from fungal_model.api.environment_grid import EnvironmentGrid, environment_grid
from fungal_model.api.result_tables import CASE_STATUS_NOT_SIMULATED, preflight_policy
from fungal_model.api.user_data import (
    FIT_ERROR_MODELS,
    REVIEW_MARKER,
    USER_DATASET_MATURITY_GAP,
    UserDataError,
    UserDataset,
    load_user_dataset,
)
from fungal_model.api.user_data_assembly import (
    NETWORK_BLOCKED,
    STATUS_CONFLICT,
    STATUS_GAP,
    AssembledTablesDraft,
    assemble_user_tables,
)
from fungal_model.api.user_data_fit import TimecourseComparison, UserDataFitError, UserDatasetFit, fit_user_dataset
from fungal_model.api.user_data_sources import (
    DESIGN_QUANTITIES,
    USER_TABLE_PROVIDERS,
    UserTablesDraft,
)
from fungal_model.api.virtual_experiment import (
    DegradationScreenResult,
    VirtualExperiment,
    VirtualExperimentError,
    VirtualExperimentMode,
    virtual_experiment,
)
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.resources import default_registry_path
from fungal_model.screening import ModelabilityReport, RegistryScreenSimulationError
from fungal_model.screening.modelability import missing_item_suggestion
from fungal_model.sources.uniprot import (
    DEFAULT_SNAPSHOT_DIR,
    MissingSnapshotError,
    ProteomeCandidate,
    ProteomeChoiceError,
    ProteomeNameResolution,
    SnapshotConflictError,
    UniprotFetchError,
    UniprotSnapshot,
    fetch_proteome_by_name,
    fetch_proteome_snapshot,
)

EXIT_OK = 0
EXIT_SIMULATION_FAILED = 1
EXIT_USAGE = 2
EXIT_NOT_RUNNABLE = 3
EXIT_PARTIAL = 4

RUNNABLE_ONLY_HELP = (
    "simulate the runnable cases when the preflight blocks others (VirtualExperiment.simulate(blocked=\"report\")): "
    "the blocked cases are not simulated, are listed with their measurement requests and appear in the tables as "
    f"not_simulated, and the exit code is {EXIT_PARTIAL} (partial run); when no case is runnable nothing is "
    f"simulated (exit {EXIT_NOT_RUNNABLE})"
)

MODE_CHOICES = ("exploratory", "scientific")
EXPLORATORY_MODE_HELP = (
    "exploratory: samples the explicit ranges and exploratory priors of the records (--samples, --seed); "
    "output quantiles propagate those inputs and are not calibrated confidence intervals."
)
SCIENTIFIC_MODE_HELP = (
    "scientific: exact, non-exploratory, non-toy values and implemented mechanisms only, one run per case; "
    "scientific means exact with current registry records and implemented mechanisms; "
    "it does not mean experimentally validated."
)
NO_FETCH_HELP = (
    "Nothing is fetched from the network unless you pass fungmod assemble --fetch, the one network opt-in of the "
    "command line: sources are local files, a user dataset, or frozen snapshots already on disk."
)
FETCH_HELP = (
    "the network opt-in: query UniProt for --proteome or --fetch-proteome and freeze each response (SHA-256, URL, "
    "query, retrieval time, release header) under --snapshot-dir; an existing snapshot whose bytes differ from the "
    "new response is kept and the command refused. Without --fetch only frozen snapshots are read, and a missing "
    "one is refused with the command that fetches it."
)
IN_SAMPLE_HELP = (
    "Agreement with, and values fitted to, your own time courses are in-sample: they are not validation, and "
    "fitted values run in exploratory mode only."
)

_DESCRIPTION = (
    "FungMod virtual experiments from the command line: name fungi or enzyme sources, substrates and "
    "conditions, and FungMod preflights, simulates and writes tables, manifest and report. The user-data "
    "workflow assembles a reviewable dataset for a fungus, substrates and conditions, checks it, runs it, "
    "compares it with your time courses and fits kinetic constants to them."
)
_EPILOG = f"""modes (--mode is required; it decides what may be simulated):
  {EXPLORATORY_MODE_HELP}
  {SCIENTIFIC_MODE_HELP}

exit codes:
  0  success
  1  the simulation failed after a passing preflight
  2  usage or input error (unknown names, invalid user data, a refused draft or fit, missing arguments)
  3  the preflight blocks a requested case in the requested mode; nothing is simulated
  4  partial run (run --runnable-only): the runnable cases were simulated, the blocked ones are listed

examples:
  fungmod list --aliases
  fungmod preflight --fungus NAME --substrate NAME --temperature-c 30 --ph 5 --mode scientific
  fungmod run --fungus NAME --substrate NAME --temperature-c 30 --ph 5 \\
      --mode exploratory --samples 32 --seed 1 --output runs/first --report
  fungmod check-data path/to/user_dataset

user-data workflow (see docs/cli.md):
  fungmod assemble --fungus NAME --substrate NAME --temperature-c 30 --ph 5 \\
      --annotation overview.txt --annotation-tool "dbCAN 4.1.4" --kinetics-source export.json \\
      --dataset-id my_draft --output my_draft
  (or, for the enzyme repertoire of the UniProt reference proteome found under the fungus's name:
   --fetch-proteome --fetch in place of --annotation and --annotation-tool)
  (fill the REVIEW: fields listed by assemble and in my_draft/review.md)
  fungmod check-data my_draft
  fungmod run --user-data my_draft --fungus NAME --substrate NAME --condition CONDITION_ID \\
      --mode exploratory --samples 32 --seed 1 --output runs/mine --compare-timecourses
  (add --runnable-only when the draft has gaps: the runnable cases run, the gaps are listed, exit code 4)
  fungmod fit my_draft --case STRAIN_ID ENZYME_CLASS SUBSTRATE_ID --fit km 10 5000 uM \\
      --fit kcat 1 300 1/min --output my_draft_fitted
"""
_ASSEMBLE_EPILOG = f"""what the draft holds:
  One fungus per call. Its enzyme classes come only from its annotation, the classes you assert, its own rows in
  --user-data or its registry record. Per case (class x substrate x condition) the kinetics status is user_data,
  literature_same_organism, transferred_estimate (another organism's enzyme, written as estimates: exploratory
  mode only), conflict (choose with --entry-id) or gap (no kinetic constant; check-data lists the measurement
  requests). Kinetics are never reused at another condition. Decisions left to you (the reviewer, the time grid,
  the enzyme concentration of the kcat form, an unsettled yield, a new substrate's categories, the annotation
  source) are REVIEW: fields unless an option gives them; check-data refuses the draft until each is filled.
  {NO_FETCH_HELP}

the enzyme repertoire from a UniProt proteome (instead of --annotation):
  --proteome UP... takes that proteome; --fetch-proteome searches UniProt's reference proteomes for the name of
  --scientific-name (or, without it, of --fungus) and takes the one candidate whose organism name equals it
  (case-insensitive), or the only candidate; none, or several without one exact match, is refused with every
  candidate listed (add --proteome UP... to choose among them). Its UniProtKB export becomes the draft's
  genomes.csv row (UniProt release, or the retrieval date when no release header was sent) and its EC numbers and
  CAZy cross-references give the classes; no kinetic value comes from a proteome. --fetch is the only route to
  the network; without it the frozen snapshots under --snapshot-dir are read.

several enzymes acting together (--network):
  The draft declares enzyme_network with the requested substrates as entry substrates: the pools each releases
  are followed through stated products only (the user dataset's substrates.csv, a registry record's single
  product, or the request) that equal a substrate_id or a registry substrate id, never a name, and every class of
  the repertoire acting on a pool is a member with its own kinetics status. A network runs at a condition only
  when every member has kinetics there (all or nothing); a member without kinetics is a gap, never left out.
  Response laws (--responses) are refused; --user-data may then be a network dataset.

examples:
  fungmod assemble --fungus "Strain G1" --substrate NAME --temperature-c 30 --temperature-c 40 --ph 5 \\
      --annotation overview.txt --annotation-tool "dbCAN 4.1.4" \\
      --kinetics-source export.json --entry-id 12345 \\
      --design substrate_initial_concentration=10 mM --time-grid 10 hour 61 \\
      --dataset-id strain_g1_draft --output strain_g1_draft
  fungmod assemble --fungus "Strain G2" --scientific-name "Genus species" --fetch-proteome --fetch \\
      --substrate NAME --temperature-c 30 --ph 5 --dataset-id strain_g2_draft --output strain_g2_draft
  fungmod assemble --fungus STRAIN --user-data my_dataset --substrate SUBSTRATE_ID --temperature-c 30 --ph 5 \\
      --network --dataset-id strain_network_draft --output strain_network_draft
"""
_DRAFT_EPILOG = f"""what the draft holds:
  One strain per organism and expression host, enzyme classes resolved by EC number, substrates resolved by name,
  one condition per temperature and pH, and Km, kcat, Vmax or the pH-ionization constants copied as literature
  values without unit conversion. Mutant enzymes, conflicts, unresolved EC numbers and unconvertible parameters
  are listed with the reason. The reviewer and the time grid are always REVIEW: fields.
  {NO_FETCH_HELP}

example:
  fungmod draft-kinetics export.json --provider PROVIDER --entry-id 12345 \\
      --design substrate_initial_concentration=10 mM --design enzyme_concentration=0.001 mM \\
      --dataset-id my_tables --output my_tables
"""
_FIT_EPILOG = f"""what the fit does:
  One case, constants shared by the fitted conditions (same temperature and pH), bounded least squares on
  ln(value) with the assembled virtual-experiment model, and an identifiability verdict per quantity (profile
  likelihood with sd weighting, local information when unweighted). An unidentified quantity refuses the fit
  (exit 2) unless --allow-unidentified. The fitted dataset is a new directory whose fitted rows have evidence
  type fitted (maturity user_fitted).
  {IN_SAMPLE_HELP}

example:
  fungmod fit my_dataset --case strain_e1 my_class my_substrate \\
      --fit km 10 5000 uM --fit kcat 1 300 1/min --initial km 1000 --initial kcat 5 \\
      --output my_dataset_fitted
"""


class _UsageError(Exception):
    """A usage or input problem reported with exit code 2."""

    def __init__(self, message: str, details: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.details = tuple(details)



def shell_quote(argument: str) -> str:
    """Quote one argument of a printed next-step command for the shell of the platform.

    POSIX shells get ``shlex.quote``; on Windows, where single quotes do not quote and
    backslashes are path separators, the argument is quoted the way ``cmd`` and
    PowerShell read it (``subprocess.list2cmdline``).
    """

    if os.name == "nt":
        return subprocess.list2cmdline([argument])
    return shlex.quote(argument)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``fungmod`` command line and return its exit code."""

    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(arguments)
    except SystemExit as exc:
        return _system_exit_code(exc)
    # The command as given, for printed commands that repeat it with one option more.
    args.command_line = [str(argument) for argument in arguments]
    handlers = {
        "run": _run,
        "preflight": _preflight,
        "check-data": _check_data,
        "list": _list,
        "assemble": _assemble,
        "draft-kinetics": _draft_kinetics,
        "fit": _fit,
    }
    try:
        return handlers[args.command](args)
    except _UsageError as exc:
        print(f"fungmod {args.command}: error: {exc}", file=sys.stderr)
        for line in exc.details:
            print(f"  {line}", file=sys.stderr)
        return EXIT_USAGE


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser of the ``fungmod`` command."""

    parser = argparse.ArgumentParser(
        prog="fungmod",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"fungmod {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    selection = _selection_parser()

    run = commands.add_parser(
        "run",
        parents=[selection],
        help="preflight, simulate and write tables, manifest and report",
        description=(
            "Preflight every fungus x substrate x condition case, then simulate when every case is runnable "
            "in the requested mode (with --runnable-only: the runnable cases, listing the blocked ones) and write "
            "the standard output bundle."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run.add_argument(
        "--samples",
        type=_positive_int,
        metavar="N",
        help="samples per case; required in exploratory mode, refused in scientific mode (one exact run per case)",
    )
    run.add_argument(
        "--seed",
        type=_nonnegative_int,
        metavar="S",
        help="random seed of the exploratory samples; required with --samples so that the run is reproducible",
    )
    run.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DIR",
        help="new or empty directory for the output bundle",
    )
    run.add_argument(
        "--report",
        action="store_true",
        help="also write the HTML report and index.html (the Markdown report is always written)",
    )
    run.add_argument(
        "--no-plots",
        action="store_true",
        help="skip the quick-look PNG figures; tables, manifest and report are still written",
    )
    run.add_argument("--runnable-only", action="store_true", help=RUNNABLE_ONLY_HELP)
    run.add_argument(
        "--compare-timecourses",
        action="store_true",
        help=(
            "after simulating, compare the simulation with the time courses of --user-data "
            "(DegradationScreenResult.compare_with_timecourses): writes timecourse_comparison.csv and prints RMSE "
            f"and band coverage per series. {IN_SAMPLE_HELP}"
        ),
    )

    preflight = commands.add_parser(
        "preflight",
        parents=[selection],
        help="check every case without simulating",
        description=(
            "Run the modelability preflight only. Exit 0 when every case is runnable in the requested mode, "
            "otherwise 3 with the missing inputs and their measurement requests."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    preflight.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help="also write the preflight tables to this new or empty directory",
    )

    check = commands.add_parser(
        "check-data",
        help="validate a user dataset directory",
        description=(
            "Load a user dataset (user_dataset.yml and CSV tables) and report its id, digest, generated "
            "records and gaps, or every issue as file:row:column: message."
        ),
    )
    check.add_argument("directory", type=Path, metavar="DIR", help="user dataset directory")
    _add_registry_argument(check)

    listing = commands.add_parser(
        "list",
        help="list the fungi, substrates and environments that can be named",
        description="List the registry's fungi, substrates and environments with id, name and maturity.",
    )
    listing.add_argument(
        "--user-data",
        type=Path,
        metavar="DIR",
        help="overlay this user dataset in memory before listing",
    )
    _add_registry_argument(listing)
    listing.add_argument("--aliases", action="store_true", help="also list the aliases that can be used as names")
    _add_assemble_parser(commands)
    _add_draft_kinetics_parser(commands)
    _add_fit_parser(commands)
    return parser


def _add_assemble_parser(commands: Any) -> None:
    assemble = commands.add_parser(
        "assemble",
        help="draft one reviewable user dataset for a fungus on substrates at conditions",
        description=(
            "Assemble one reviewable user-dataset draft for one fungus on the named substrates at a grid of "
            "conditions from the sources you give (assemble_user_tables): its genome annotation, enzyme classes you "
            "assert, its registry record, an existing user dataset, and kinetic-law sources. Prints the per-case "
            "report (kinetics status, sources, reason), the REVIEW: fields to fill and the next commands. "
            f"{NO_FETCH_HELP}"
        ),
        epilog=_ASSEMBLE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    request = assemble.add_argument_group("the request")
    request.add_argument(
        "--fungus",
        action="append",
        required=True,
        metavar="NAME",
        help=(
            "the one fungus of this draft: a strain of --user-data, a registry fungus (name, alias or id), or a "
            "free-text name for a new strain"
        ),
    )
    request.add_argument(
        "--substrate",
        action="append",
        required=True,
        metavar="NAME",
        help=(
            "substrate (repeatable): a registry substrate, a substrate of --user-data, or a new name whose "
            "categories become REVIEW: fields of substrates.csv"
        ),
    )
    request.add_argument(
        "--temperature-c",
        dest="temperature_c",
        action="append",
        type=_finite_float,
        metavar="T",
        help="condition temperature in degrees Celsius (repeatable, needs --ph); every T x pH pair is one condition",
    )
    request.add_argument(
        "--ph",
        action="append",
        type=_finite_float,
        metavar="PH",
        help="condition pH (repeatable, needs --temperature-c)",
    )
    request.add_argument(
        "--scientific-name",
        metavar="NAME",
        help="species of a new strain; kinetic-law entries of that organism count as the fungus's own species",
    )
    repertoire = assemble.add_argument_group(
        "enzyme repertoire of the fungus (evidence; a name at most selects a UniProt proteome)"
    )
    repertoire.add_argument(
        "--annotation",
        type=Path,
        metavar="FILE",
        help=(
            "dbCAN overview.txt of the fungus, or a UniProtKB TSV export of its proteome when --annotation-tool "
            "names UniProt; copied into the draft and listed in genomes.csv"
        ),
    )
    repertoire.add_argument(
        "--annotation-tool",
        metavar="TOOL",
        help=(
            'the annotation tool and its version, for example "dbCAN 4.1.4", or "UniProt" with the release or '
            'download date, for example "UniProt 2026_03" (required with --annotation)'
        ),
    )
    repertoire.add_argument(
        "--annotation-source",
        metavar="TEXT",
        help="the genome or proteome that was annotated, ideally with its accession; without it a REVIEW: field",
    )
    repertoire.add_argument(
        "--proteome",
        metavar="PROTEOME_ID",
        help=(
            "a UniProt proteome identifier (UP followed by digits) whose UniProtKB export gives the fungus's classes "
            "(instead of --annotation); with --fetch-proteome it chooses among the name's candidates"
        ),
    )
    repertoire.add_argument(
        "--fetch-proteome",
        action="store_true",
        help=(
            "take the enzyme repertoire from the UniProt reference proteome found under --scientific-name (or, "
            "without it, --fungus); the one exact organism-name match or the only candidate is taken, anything else "
            "is refused with the candidates listed"
        ),
    )
    repertoire.add_argument("--fetch", action="store_true", help=FETCH_HELP)
    repertoire.add_argument(
        "--snapshot-dir",
        type=Path,
        metavar="DIR",
        help=(
            f"directory of the frozen UniProt snapshots (default: {DEFAULT_SNAPSHOT_DIR}, the API's "
            "DEFAULT_SNAPSHOT_DIR, relative to the current directory; --cache-dir holds the kinetics snapshots)"
        ),
    )
    repertoire.add_argument(
        "--enzyme-class",
        dest="enzyme_classes",
        action="append",
        metavar="CLASS",
        help="an enzyme class you assert for the fungus (name, alias, EC number or id); its evidence and source "
        "become REVIEW: fields of enzymes.csv (repeatable)",
    )
    repertoire.add_argument(
        "--enzyme-class-evidence",
        dest="enzyme_classes",
        action="append",
        nargs=3,
        metavar=("CLASS", "EVIDENCE", "SOURCE"),
        help="an enzyme class you assert, with its evidence and source (repeatable)",
    )
    kinetics = assemble.add_argument_group("kinetics sources")
    kinetics.add_argument(
        "--kinetics-source",
        dest="kinetics_sources",
        action="append",
        metavar="SOURCE",
        help=(
            "a kinetic-law export JSON file or a reaction id read from the frozen snapshots on disk, as "
            "assemble_user_tables accepts them (repeatable; see docs/user-data.md)"
        ),
    )
    kinetics.add_argument(
        "--entry-id",
        dest="entry_ids",
        action="append",
        metavar="ID",
        help="select this entry id across the kinetics sources (repeatable); without it every entry is considered",
    )
    kinetics.add_argument(
        "--same-species",
        action="append",
        metavar="ORGANISM",
        help="an organism name of the kinetics sources that you declare to be the fungus's own species (repeatable)",
    )
    kinetics.add_argument(
        "--cache-dir",
        type=Path,
        metavar="DIR",
        help="directory of frozen snapshots searched for a reaction id (default: the API's snapshot directory)",
    )
    kinetics.add_argument(
        "--user-data",
        type=Path,
        metavar="DIR",
        help="an existing user dataset that holds the fungus; its rows for the fungus and substrates are kept",
    )
    kinetics.add_argument(
        "--responses",
        type=Path,
        metavar="FILE",
        help=(
            "CSV of temperature or pH response-law rows for the fungus: the columns of responses.csv with "
            "substrate in place of strain_id and substrate_id"
        ),
    )
    assay = assemble.add_argument_group("the virtual assay")
    _add_design_argument(assay)
    assay.add_argument(
        "--time-grid",
        nargs=3,
        metavar=("DURATION", "UNITS", "POINTS"),
        help="simulation time grid, for example 10 hour 61; without it (and without --user-data) a REVIEW: field",
    )
    request.add_argument(
        "--network",
        action="store_true",
        help=(
            "draft an enzyme network (enzyme_network in user_dataset.yml) instead of single-class cases: every "
            "class of the repertoire acting on a requested substrate, or on a pool it releases through a stated "
            "product, acts together (assemble_user_tables(network=True))"
        ),
    )
    output = assemble.add_argument_group("output")
    output.add_argument("--dataset-id", required=True, metavar="ID", help="lowercase snake_case id of the draft")
    output.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DIR",
        help="new or empty directory for the draft (tables, user_dataset.yml, review.md, annotation copy)",
    )
    _add_registry_argument(output)


def _add_draft_kinetics_parser(commands: Any) -> None:
    draft = commands.add_parser(
        "draft-kinetics",
        help="draft user tables from a public kinetics export or frozen snapshot",
        description=(
            "Draft user-dataset tables from kinetic-law entries of a public kinetics database for review "
            "(the drafting function of --provider in the API's USER_TABLE_PROVIDERS). Prints the converted entries, "
            "the entries and parameters not converted with the reason, and the REVIEW: fields to fill. "
            f"{NO_FETCH_HELP} To fetch, use the Python API (source_proposal, whose explicit refresh option is the "
            "only route that queries the database) or download an export from the database's website."
        ),
        epilog=_DRAFT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    draft.add_argument(
        "source",
        metavar="SOURCE",
        help="a kinetic-law export JSON file, or a reaction id read from the frozen snapshots on disk",
    )
    draft.add_argument(
        "--provider",
        required=True,
        choices=tuple(USER_TABLE_PROVIDERS),
        help="the database the source comes from (required; the providers the API can draft from)",
    )
    draft.add_argument("--dataset-id", required=True, metavar="ID", help="lowercase snake_case id of the draft")
    draft.add_argument(
        "--output", type=Path, required=True, metavar="DIR", help="new or empty directory for the draft"
    )
    draft.add_argument(
        "--entry-id",
        dest="entry_ids",
        action="append",
        metavar="ID",
        help="convert only this entry id (repeatable); without it every entry of the source is considered",
    )
    draft.add_argument(
        "--strain-for",
        action="append",
        metavar="ORGANISM=STRAIN_ID",
        help="use STRAIN_ID as the strain id of entries of ORGANISM (repeatable)",
    )
    _add_design_argument(draft)
    draft.add_argument(
        "--propose-enzyme-classes",
        action="store_true",
        help="draft an enzyme_classes.csv row with REVIEW: bond and substrate classes for an unresolved EC number",
    )
    draft.add_argument(
        "--cache-dir",
        type=Path,
        metavar="DIR",
        help="directory of frozen snapshots searched for a reaction id (default: the API's snapshot directory)",
    )
    _add_registry_argument(draft)


def _add_fit_parser(commands: Any) -> None:
    fit = commands.add_parser(
        "fit",
        help="fit Km with kcat or Vmax of one case to the dataset's time courses",
        description=(
            "Fit kinetic constants of one case (strain, enzyme class, substrate) of a user dataset to that case's "
            "time courses (fit_user_dataset), print the fitted values with their intervals and identifiability "
            f"verdicts, and write the fitted dataset. {IN_SAMPLE_HELP}"
        ),
        epilog=_FIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fit.add_argument("directory", type=Path, metavar="DIR", help="user dataset directory with a timecourse.csv")
    fit.add_argument(
        "--case",
        nargs=3,
        required=True,
        metavar=("STRAIN_ID", "ENZYME_CLASS", "SUBSTRATE_ID"),
        help="the case whose constants are fitted, as the dataset's tables name it",
    )
    fit.add_argument(
        "--fit",
        dest="fit_bounds",
        action="append",
        nargs=4,
        required=True,
        metavar=("QUANTITY", "LOWER", "UPPER", "UNITS"),
        help=(
            "a fitted quantity (km, kcat or vmax) and its required bounds, 0 < LOWER < UPPER, in UNITS; the fitted "
            "value is reported in those units (repeatable; there are no default bounds)"
        ),
    )
    fit.add_argument(
        "--initial",
        action="append",
        nargs=2,
        metavar=("QUANTITY", "VALUE"),
        help="starting value in the units of its bounds; without it the dataset's exact value is the start",
    )
    fit.add_argument(
        "--condition",
        dest="conditions",
        action="append",
        metavar="CONDITION_ID",
        help="fit at this condition only (repeatable); without it every condition with time courses (the API's default)",
    )
    fit.add_argument(
        "--error-model",
        choices=FIT_ERROR_MODELS,
        help=(
            "sd_weighted (the API's default) divides each residual by the observation's sd and is refused when an "
            "observation has none; unweighted fits raw residuals and is used only when named"
        ),
    )
    fit.add_argument(
        "--allow-unidentified",
        action="store_true",
        help="write quantities the time courses do not identify, labelled NOT IDENTIFIED, instead of refusing the fit",
    )
    fit.add_argument(
        "--fitted-dataset-id",
        metavar="ID",
        help="dataset id of the fitted dataset (the API's default: <input id>_fitted)",
    )
    fit.add_argument(
        "--confidence-level",
        type=_finite_float,
        metavar="P",
        help="confidence level of the intervals and identifiability verdicts (the API's default: 0.95)",
    )
    fit.add_argument(
        "--profile-points",
        type=_positive_int,
        metavar="N",
        help="profile-likelihood grid points per quantity (the API's default: 21)",
    )
    fit.add_argument(
        "--diff-step",
        type=_finite_float,
        metavar="STEP",
        help="relative finite-difference step in log space (the API's default: FIT_DIFFERENCE_STEP, 1e-3)",
    )
    fit.add_argument(
        "--max-nfev",
        type=_positive_int,
        metavar="N",
        help="maximum optimizer function evaluations (the API's default: the optimizer's own limit)",
    )
    fit.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DIR",
        help="new or empty directory for the fitted dataset (a copy of the input with fitted rows and fit_report.json)",
    )
    _add_registry_argument(fit)


def _add_design_argument(container: Any) -> None:
    container.add_argument(
        "--design",
        action="append",
        nargs=2,
        metavar=("QUANTITY=VALUE", "UNITS"),
        help=(
            f"a virtual-assay amount ({', '.join(DESIGN_QUANTITIES)}) as QUANTITY=VALUE or QUANTITY=LOWER:UPPER, "
            "for example substrate_initial_concentration=10 mM (repeatable); kinetic constants come from the "
            "sources, never from the design"
        ),
    )


def _selection_parser() -> argparse.ArgumentParser:
    selection = argparse.ArgumentParser(add_help=False)
    what = selection.add_argument_group("what to simulate")
    what.add_argument(
        "--fungus",
        action="append",
        required=True,
        metavar="NAME",
        help="fungus or enzyme source: registry id, name or alias, or a strain of --user-data (repeatable)",
    )
    what.add_argument(
        "--substrate",
        action="append",
        required=True,
        metavar="NAME",
        help="substrate: registry id, name or alias, or a substrate of --user-data (repeatable)",
    )
    conditions = selection.add_argument_group(
        "conditions (registry environments or user-data conditions, or a temperature and pH grid)"
    )
    conditions.add_argument(
        "--environment",
        "--condition",
        dest="environment",
        action="append",
        metavar="NAME",
        help="registry environment id, name or alias, or a condition_id of --user-data (repeatable)",
    )
    conditions.add_argument(
        "--temperature-c",
        dest="temperature_c",
        action="append",
        type=_finite_float,
        metavar="T",
        help=(
            "grid temperature in degrees Celsius (repeatable, needs --ph); it changes rates only where the "
            "case template binds a response law, otherwise it is recorded as metadata"
        ),
    )
    conditions.add_argument(
        "--ph",
        action="append",
        type=_finite_float,
        metavar="PH",
        help="grid pH (repeatable, needs --temperature-c); same response-law rule as the temperature",
    )
    conditions.add_argument(
        "--oxygen",
        action="append",
        metavar="LABEL",
        help="grid oxygen label, metadata only (repeatable); without it the grid records oxygen as not_specified",
    )
    sources = selection.add_argument_group("data sources")
    sources.add_argument(
        "--user-data",
        type=Path,
        metavar="DIR",
        help="user dataset directory overlaid in memory on the registry (see fungmod check-data)",
    )
    _add_registry_argument(sources)
    selection.add_argument(
        "--mode",
        required=True,
        choices=MODE_CHOICES,
        help=f"required, no default. {EXPLORATORY_MODE_HELP} {SCIENTIFIC_MODE_HELP}",
    )
    return selection


def _add_registry_argument(container: Any) -> None:
    container.add_argument(
        "--registry",
        type=Path,
        metavar="PATH",
        help="registry index YAML (default: the registry packaged with FungMod)",
    )


# ---------------------------------------------------------------------------
# Subcommands


def _run(args: argparse.Namespace) -> int:
    mode = cast(VirtualExperimentMode, args.mode)
    if mode == "exploratory":
        if args.samples is None:
            raise _UsageError("--samples N is required in exploratory mode; FungMod does not choose a sample count.")
        if args.seed is None:
            raise _UsageError(
                "--seed S is required in exploratory mode so that the sampled run is reproducible; "
                "FungMod does not choose a seed."
            )
    else:
        given = [flag for flag, value in (("--samples", args.samples), ("--seed", args.seed)) if value is not None]
        if given:
            verb = "apply" if len(given) > 1 else "applies"
            raise _UsageError(
                f"{' and '.join(given)} {verb} only to exploratory mode; scientific mode runs each case once "
                "with exact values."
            )
    if args.compare_timecourses and args.user_data is None:
        raise _UsageError(
            "--compare-timecourses compares with the time courses of a user dataset; give --user-data DIR."
        )
    output = cast(Path, args.output)
    _require_new_output(output)
    study = _build_experiment(args)
    if args.compare_timecourses:
        dataset = cast(UserDataset, study.user_dataset)
        if not dataset.timecourses:
            raise _UsageError(
                f"--compare-timecourses: user dataset {dataset.dataset_id!r} has no timecourse.csv, so there is "
                "nothing to compare with; nothing was simulated."
            )
    _print_experiment(study)
    reports = study.preflight(mode=mode)
    blocked = _print_preflight(reports, mode=mode)
    partial = bool(blocked) and args.runnable_only and len(blocked) < len(reports)
    if blocked:
        _print_blocked(blocked, total=len(reports), mode=mode, command="run", runnable_only=args.runnable_only)
        if not partial:
            return EXIT_NOT_RUNNABLE
    try:
        result = study.simulate(
            mode=mode,
            n_samples=args.samples if mode == "exploratory" else 1,
            seed=args.seed,
            output_dir=output,
            quicklook=not args.no_plots,
            blocked="report" if args.runnable_only else "refuse",
        )
        report_path = result.write_report(include_html=args.report, include_index=args.report)
    except (RegistryScreenSimulationError, VirtualExperimentError) as exc:
        print(f"fungmod run: simulation failed: {exc}", file=sys.stderr)
        return EXIT_SIMULATION_FAILED
    _print_run_summary(result, report_path=report_path, html=args.report)
    if args.compare_timecourses:
        try:
            comparison = result.compare_with_timecourses()
        except UserDataError as exc:
            print()
            print(
                f"The simulation bundle in {result.output_directory} is complete; the time-course comparison was "
                "refused."
            )
            raise _user_data_error(exc) from exc
        _print_comparison(comparison)
    if result.partial_run:
        blocked_ids = ", ".join(case["case_id"] for case in result.blocked_cases())
        print()
        print(
            f"Partial run: {len(result.blocked_reports)} of {len(result.preflight_reports)} requested case(s) were "
            f"blocked by the preflight and not simulated ({blocked_ids}); exit code {EXIT_PARTIAL}."
        )
        return EXIT_PARTIAL
    return EXIT_OK


def _preflight(args: argparse.Namespace) -> int:
    mode = cast(VirtualExperimentMode, args.mode)
    output = cast("Path | None", args.output)
    if output is not None:
        _require_new_output(output)
    study = _build_experiment(args)
    _print_experiment(study)
    reports = study.preflight(mode=mode)
    blocked = _print_preflight(reports, mode=mode)
    if output is not None:
        written = study.write_preflight_report(mode=mode, output_dir=output)
        print()
        print("Preflight tables:")
        for name, path in written.paths.items():
            print(f"  {name}: {path}")
    if blocked:
        _print_blocked(blocked, total=len(reports), mode=mode, command="preflight")
        return EXIT_NOT_RUNNABLE
    print()
    print(f"All {len(reports)} case(s) are runnable in {mode} mode.")
    return EXIT_OK


def _check_data(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    registry = _load_registry(registry_path)
    try:
        dataset = load_user_dataset(args.directory, registry=registry)
    except UserDataError as exc:
        error = _user_data_error(exc)
        if REVIEW_MARKER in error.args[0]:
            error = _UsageError(
                error.args[0],
                [
                    *error.details,
                    f"Fill each {REVIEW_MARKER} field (a drafted directory's review.md says what to decide for "
                    "each), then run fungmod check-data again.",
                ],
            )
        raise error from exc
    simulation = dataset.manifest["simulation"]
    parameter_records = dataset.records["parameter_records"]
    gaps = [mapping for mapping in parameter_records if mapping["maturity"] == USER_DATASET_MATURITY_GAP]
    print(f"User dataset: {dataset.dataset_id}")
    print(f"Digest: {dataset.digest}")
    print(f"Directory: {dataset.source_directory}")
    print(f"Base registry: {registry_path} (registry {registry.registry_id})")
    print(f"Simulation time grid: {simulation['duration']} {simulation['units']}, {simulation['points']} points")
    print("Generated records:")
    rows = [(record_type, str(len(mappings))) for record_type, mappings in dataset.records.items()]
    for line in _table(("record type", "count"), rows):
        print(f"  {line}")
    print(f"Kinetic values: {len(parameter_records) - len(gaps)}; gaps: {len(gaps)}")
    if gaps:
        print("Gaps (explicit unknowns; preflight reports their cases as underparameterized):")
        for gap in gaps:
            print(f"  - {gap['record_id']}")
            print(f"    measurement request: {gap['provenance']['measurement_request']}")
    _print_genome_resolution(dataset)
    _print_cultures(dataset)
    _print_enzyme_networks(dataset)
    _print_timecourses(dataset)
    _print_fit_block(dataset)
    return EXIT_OK


def _list(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    registry = _load_registry(registry_path)
    print(
        f"Registry: {registry_path} (registry {registry.registry_id}, version {registry.version}, "
        f"maturity {registry.maturity})"
    )
    if args.user_data is not None:
        try:
            dataset = load_user_dataset(args.user_data, registry=registry)
            registry = dataset.overlay(registry)
        except UserDataError as exc:
            raise _user_data_error(exc) from exc
        print(f"User dataset: {dataset.dataset_id} (digest {dataset.digest}), overlaid in memory")
    sections = (
        ("Fungi and enzyme sources (--fungus)", registry.fungi),
        ("Substrates (--substrate)", registry.substrates),
        ("Environments (--environment)", registry.environments),
    )
    for title, records in sections:
        headers = ("id", "name", "maturity", *(("aliases",) if args.aliases else ()))
        rows = [
            (
                record.record_id,
                record.name,
                record.maturity,
                *(("; ".join(record.aliases),) if args.aliases else ()),
            )
            for record in records.values()
        ]
        print()
        print(f"{title}: {len(rows)}")
        for line in _table(headers, rows):
            print(f"  {line}")
    return EXIT_OK


def _assemble(args: argparse.Namespace) -> int:
    fungi = cast("list[str]", args.fungus)
    if len(fungi) > 1:
        raise _UsageError(
            f"assemble drafts one fungus per call and got {len(fungi)} --fungus values; run it once per fungus."
        )
    conditions = _assembly_conditions(args)
    output = cast(Path, args.output)
    _require_new_output(output, _DATASET_OUTPUT_REASON)
    registry_path = _registry_path(args)
    proteome, selection = _assembly_proteome(args, fungi[0])
    optional = {
        "scientific_name": args.scientific_name,
        "same_species": args.same_species,
        "annotation": args.annotation,
        "annotation_tool": args.annotation_tool,
        "annotation_source": args.annotation_source,
        "proteome": proteome,
        "proteome_selection": selection,
        "enzyme_classes": _asserted_classes(args.enzyme_classes),
        "kinetics_sources": args.kinetics_sources,
        "user_data": args.user_data,
        "responses": _response_rows(args.responses),
        "design": _design(args.design),
        "time_grid": _time_grid(args.time_grid),
        "entry_ids": args.entry_ids,
        "cache_dir": args.cache_dir,
        "network": True if args.network else None,
    }
    try:
        draft = assemble_user_tables(
            dataset_id=args.dataset_id,
            fungus=fungi[0],
            substrates=args.substrate,
            conditions=conditions,
            registry=registry_path,
            **{name: value for name, value in optional.items() if value is not None},
        )
        written = draft.write(output)
    except UserDataError as exc:
        raise _user_data_error(exc) from exc
    except (ValueError, KeyError, OSError) as exc:
        raise _UsageError(_exception_text(exc)) from exc
    _print_assembly(draft)
    _print_written(written, output)
    _print_review_fields(draft.review_fields)
    _print_assembly_next_steps(draft, output)
    return EXIT_OK


def _assembly_proteome(args: argparse.Namespace, fungus: str) -> tuple[UniprotSnapshot | None, str | None]:
    """The UniProt proteome snapshot of ``--proteome`` or ``--fetch-proteome`` and how it was chosen.

    The network is reached only with ``--fetch`` (``refresh`` of the sources
    module); otherwise the frozen snapshots are read and a missing one is
    refused with the command that fetches it.
    """

    proteome_id = cast("str | None", args.proteome)
    by_name = bool(args.fetch_proteome)
    if proteome_id is None and not by_name:
        given = [flag for flag, value in (("--fetch", args.fetch), ("--snapshot-dir", args.snapshot_dir)) if value]
        if given:
            raise _UsageError(
                f"{' and '.join(given)} {'apply' if len(given) > 1 else 'applies'} to the UniProt proteome of "
                "--proteome or --fetch-proteome; nothing else is fetched."
            )
        return None, None
    route = "--fetch-proteome" if by_name else "--proteome"
    annotated = [
        flag
        for flag, value in (
            ("--annotation", args.annotation),
            ("--annotation-tool", args.annotation_tool),
            ("--annotation-source", args.annotation_source),
        )
        if value is not None
    ]
    if annotated:
        raise _UsageError(
            f"{', '.join(annotated)} and {route} both give the fungus's annotation, and genomes.csv holds one "
            "annotation per strain: give --annotation FILE --annotation-tool TOOL, or the UniProt proteome, not both."
        )
    snapshot_dir = cast("Path | None", args.snapshot_dir) or Path(DEFAULT_SNAPSHOT_DIR)
    refresh = bool(args.fetch)
    resolution: ProteomeNameResolution | None = None
    name_from = "--scientific-name" if args.scientific_name is not None else "--fungus"
    try:
        if by_name:
            name = args.scientific_name if args.scientific_name is not None else fungus
            resolution, snapshot = fetch_proteome_by_name(
                name, proteome_id=proteome_id, snapshot_dir=snapshot_dir, refresh=refresh
            )
        else:
            assert proteome_id is not None
            snapshot = fetch_proteome_snapshot(proteome_id=proteome_id, snapshot_dir=snapshot_dir, refresh=refresh)
    except ProteomeChoiceError as exc:
        raise _proteome_choice_error(exc, args, name_from) from exc
    except MissingSnapshotError as exc:
        raise _UsageError(
            f"no frozen snapshot of {exc.description} in {exc.directory}; the command line reaches UniProt only "
            "with --fetch.",
            [
                f"To query UniProt and freeze the response(s) under {snapshot_dir}, run the same command with --fetch:",
                f"  {_command_with(args, '--fetch')}",
            ],
        ) from exc
    except SnapshotConflictError as exc:
        raise _UsageError(
            str(exc),
            [
                f"The frozen snapshot is kept. To store UniProt's new response instead, remove {exc.directory} (or "
                "choose another --snapshot-dir) and run the command again with --fetch.",
            ],
        ) from exc
    except UniprotFetchError as exc:
        raise _UsageError(str(exc)) from exc
    _print_proteome(snapshot, resolution, snapshot_dir=snapshot_dir, fetched=refresh, name_from=name_from)
    return snapshot, None if resolution is None else resolution.statement


def _proteome_choice_error(exc: ProteomeChoiceError, args: argparse.Namespace, name_from: str) -> _UsageError:
    details = [f"name searched: {exc.name!r} (from {name_from}); search snapshot {exc.search.text()}"]
    if exc.candidates:
        details.append(f"candidates ({len(exc.candidates)}):")
        details.extend(f"  {line}" for line in _candidate_table(exc.candidates))
        if len(exc.candidates) > _CANDIDATE_ROWS:
            details.append(f"  ... and {len(exc.candidates) - _CANDIDATE_ROWS} more in {exc.search.tsv_path}")
        details.append(
            "Choose one and run the same command with --proteome PROTEOME_ID; with --fetch-proteome kept, it must "
            "be one of these candidates:"
        )
        details.append(f"  {_command_with(args, '--proteome', 'PROTEOME_ID')}")
    else:
        details.append(
            "To use a proteome UniProt lists under another name, or one that is not a reference proteome, find its "
            "identifier on uniprot.org (Proteomes) and run the command without --fetch-proteome, with --proteome "
            "PROTEOME_ID."
        )
    return _UsageError(exc.reason, details)


def _command_with(args: argparse.Namespace, *extra: str) -> str:
    """The command as given, quoted for the platform's shell, with ``extra`` arguments appended."""

    return " ".join(("fungmod", *(shell_quote(argument) for argument in args.command_line), *extra))


def _draft_kinetics(args: argparse.Namespace) -> int:
    output = cast(Path, args.output)
    _require_new_output(output, _DATASET_OUTPUT_REASON)
    optional = {
        "strain_id_for_organism": _strain_map(args.strain_for),
        "entry_ids": args.entry_ids,
        "design": _design(args.design),
        "cache_dir": args.cache_dir,
    }
    registry_path = _registry_path(args)
    drafter = USER_TABLE_PROVIDERS[args.provider]
    try:
        draft = drafter(
            args.source,
            dataset_id=args.dataset_id,
            propose_enzyme_classes=args.propose_enzyme_classes,
            registry=registry_path,
            **{name: value for name, value in optional.items() if value is not None},
        )
        written = draft.write(output)
    except (ValueError, KeyError, OSError) as exc:
        raise _UsageError(_exception_text(exc)) from exc
    _print_draft(draft, provider=args.provider, source=args.source)
    _print_written(written, output)
    _print_review_fields(draft.review_fields)
    _print_draft_next_steps(draft, output)
    return EXIT_OK


def _fit(args: argparse.Namespace) -> int:
    output = cast(Path, args.output)
    _require_new_output(output, _DATASET_OUTPUT_REASON)
    strain_id, enzyme_class, substrate_id = cast("list[str]", args.case)
    bounds: dict[str, tuple[float, float, str]] = {}
    for quantity, lower, upper, units in cast("list[list[str]]", args.fit_bounds):
        if quantity in bounds:
            raise _UsageError(f"--fit {quantity} is given twice; give each fitted quantity once.")
        bounds[quantity] = (
            _number_argument(lower, f"--fit {quantity} LOWER"),
            _number_argument(upper, f"--fit {quantity} UPPER"),
            units,
        )
    initial: dict[str, float] | None = None
    if args.initial is not None:
        initial = {}
        for quantity, value in cast("list[list[str]]", args.initial):
            if quantity in initial:
                raise _UsageError(f"--initial {quantity} is given twice; give each starting value once.")
            initial[quantity] = _number_argument(value, f"--initial {quantity} VALUE")
    optional = {
        "initial": initial,
        "conditions": args.conditions,
        "error_model": args.error_model,
        "fitted_dataset_id": args.fitted_dataset_id,
        "confidence_level": args.confidence_level,
        "profile_points": args.profile_points,
        "diff_step": args.diff_step,
        "max_nfev": args.max_nfev,
    }
    registry_path = _registry_path(args)
    print(f"Fitting {', '.join(bounds)} of {strain_id} / {enzyme_class} / {substrate_id} in {args.directory}")
    try:
        fit = fit_user_dataset(
            args.directory,
            parameters=[(strain_id, enzyme_class, substrate_id, quantity) for quantity in bounds],
            bounds=bounds,
            base_registry=registry_path,
            allow_unidentified=args.allow_unidentified,
            **{name: value for name, value in optional.items() if value is not None},
        )
    except UserDataError as exc:
        error = _user_data_error(exc)
        if isinstance(exc, UserDataFitError) and exc.report is not None and exc.report.get("quantities"):
            print()
            print("The fit was refused; nothing was written. What the fit found:")
            _print_fit_quantities(exc.report)
            if exc.report.get("identified") is False:
                error = _UsageError(
                    error.args[0],
                    [*error.details, "On the command line, --allow-unidentified writes it labelled as not identified."],
                )
        raise error from exc
    _print_fit(fit)
    try:
        fitted = fit.write(output, registry=registry_path)
    except UserDataError as exc:
        raise _user_data_error(exc) from exc
    _print_fitted_dataset(fitted, fit, output)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Inputs


def _registry_path(args: argparse.Namespace) -> Path:
    if args.registry is None:
        return default_registry_path()
    path = cast(Path, args.registry)
    if not path.is_file():
        raise _UsageError(f"--registry {path} is not a file; pass a registry index YAML.")
    return path.resolve()


def _load_registry(path: Path) -> FungModRegistry:
    try:
        return load_registry(path)
    except (OSError, ValueError) as exc:
        raise _UsageError(f"cannot load registry {path}: {exc}") from exc


def _environments(args: argparse.Namespace) -> list[str] | EnvironmentGrid:
    names = cast("list[str] | None", args.environment)
    temperatures = cast("list[float] | None", args.temperature_c)
    ph_values = cast("list[float] | None", args.ph)
    oxygen = cast("list[str] | None", args.oxygen)
    grid_given = temperatures is not None or ph_values is not None or oxygen is not None
    if names is not None and grid_given:
        raise _UsageError(
            "give either --environment/--condition or a grid (--temperature-c, --ph, --oxygen), not both."
        )
    if names is not None:
        return names
    if not grid_given:
        raise _UsageError(
            "name the conditions: --environment/--condition NAME, or a grid with --temperature-c and --ph."
        )
    temperatures, ph_values = _grid_values(temperatures, ph_values)
    return environment_grid(temperature_C=temperatures, ph=ph_values, oxygen=() if oxygen is None else oxygen)


def _grid_values(
    temperatures: list[float] | None, ph_values: list[float] | None
) -> tuple[list[float], list[float]]:
    if temperatures is None or ph_values is None:
        raise _UsageError(
            "a condition grid needs at least one --temperature-c and at least one --ph value; "
            "FungMod does not assume a missing condition."
        )
    return temperatures, ph_values


def _assembly_conditions(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Every --temperature-c x --ph pair as one condition mapping of ``assemble_user_tables``, in grid order."""

    temperatures = cast("list[float] | None", args.temperature_c)
    ph_values = cast("list[float] | None", args.ph)
    if temperatures is None and ph_values is None:
        raise _UsageError(
            "name the conditions with --temperature-c T and --ph PH (every pair is one condition); FungMod does not "
            "invent conditions."
        )
    temperatures, ph_values = _grid_values(temperatures, ph_values)
    return [
        {"temperature": temperature, "temperature_units": "degC", "ph": ph}
        for temperature in temperatures
        for ph in ph_values
    ]


def _asserted_classes(values: list[str | list[str]] | None) -> list[str | dict[str, str]] | None:
    if values is None:
        return None
    classes: list[str | dict[str, str]] = []
    for value in values:
        if isinstance(value, str):
            classes.append(value)
        else:
            enzyme_class, evidence, source = value
            classes.append({"enzyme_class": enzyme_class, "evidence": evidence, "source": source})
    return classes


def _design(values: list[list[str]] | None) -> dict[str, dict[str, Any]] | None:
    """``--design QUANTITY=VALUE UNITS`` or ``QUANTITY=LOWER:UPPER UNITS`` as the API's design mapping."""

    if values is None:
        return None
    design: dict[str, dict[str, Any]] = {}
    for spec, units in values:
        quantity, separator, amount = spec.partition("=")
        if not separator or not quantity or not amount:
            raise _UsageError(
                f"--design {spec!r} must be QUANTITY=VALUE or QUANTITY=LOWER:UPPER, followed by UNITS."
            )
        if quantity in design:
            raise _UsageError(f"--design {quantity} is given twice; give each design quantity once.")
        lower, colon, upper = amount.partition(":")
        if colon:
            design[quantity] = {
                "lower": _number_argument(lower, f"--design {quantity} LOWER"),
                "upper": _number_argument(upper, f"--design {quantity} UPPER"),
                "units": units,
            }
        else:
            design[quantity] = {"value": _number_argument(amount, f"--design {quantity} VALUE"), "units": units}
    return design


def _time_grid(values: list[str] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    duration, units, points = values
    try:
        point_count = int(points)
    except ValueError:
        raise _UsageError(f"--time-grid POINTS {points!r} must be a whole number.") from None
    return {"duration": _integer_or_number(duration, "--time-grid DURATION"), "units": units, "points": point_count}


def _response_rows(path: Path | None) -> list[dict[str, str]] | None:
    """Read a responses CSV (responses.csv columns, ``substrate`` for ``strain_id`` and ``substrate_id``)."""

    if path is None:
        return None
    if not path.is_file():
        raise _UsageError(f"--responses {path} is not a file; give a CSV of response-law rows.")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise _UsageError(f"--responses {path}:{line}: the row has more cells than the header.")
            rows.append({str(key): "" if value is None else value for key, value in row.items()})
    if not rows:
        raise _UsageError(f"--responses {path} holds no rows below its header.")
    return rows


def _strain_map(values: list[str] | None) -> dict[str, str] | None:
    if values is None:
        return None
    mapping: dict[str, str] = {}
    for value in values:
        organism, separator, strain_id = value.rpartition("=")
        if not separator or not organism.strip() or not strain_id:
            raise _UsageError(f"--strain-for {value!r} must be ORGANISM=STRAIN_ID.")
        if organism in mapping:
            raise _UsageError(f"--strain-for names organism {organism!r} twice.")
        mapping[organism] = strain_id
    return mapping


def _build_experiment(args: argparse.Namespace) -> VirtualExperiment:
    environments = _environments(args)
    registry_path = _registry_path(args)
    try:
        return virtual_experiment(
            fungi=args.fungus,
            substrates=args.substrate,
            environments=environments,
            registry=registry_path,
            user_data=args.user_data,
        )
    except UserDataError as exc:
        raise _user_data_error(exc) from exc
    except (ValueError, KeyError, OSError) as exc:
        raise _UsageError(_exception_text(exc)) from exc


_RUN_OUTPUT_REASON = "so that the manifest lists only the files of this run"
# Proteome-search candidates printed; the rest are counted and stay in the frozen search snapshot.
_CANDIDATE_ROWS = 25
_DATASET_OUTPUT_REASON = "so that the directory holds only this dataset's files; nothing is overwritten"


def _require_new_output(path: Path, reason: str = _RUN_OUTPUT_REASON) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        raise _UsageError(f"--output {path} exists and is not a directory.")
    if any(path.iterdir()):
        raise _UsageError(f"--output {path} is not empty; choose a new or empty directory {reason}.")


def _user_data_error(exc: UserDataError) -> _UsageError:
    heading = str(exc).splitlines()[0]
    return _UsageError(heading, [_issue_line(issue) for issue in exc.issues])


def _issue_line(issue: Mapping[str, Any]) -> str:
    row = "-" if issue["row"] is None else str(issue["row"])
    column = issue["column"] if issue["column"] else "-"
    return f"{issue['file']}:{row}:{column}: {issue['message']}"


def _exception_text(exc: BaseException) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def _positive_int(text: str) -> int:
    value = _integer(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} must be a whole number of at least 1")
    return value


def _nonnegative_int(text: str) -> int:
    value = _integer(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"{text!r} must be a whole number of at least 0")
    return value


def _integer(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None


def _finite_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"{text!r} is not a finite number")
    return value


def _number_argument(text: str, label: str) -> float:
    try:
        return _finite_float(text)
    except argparse.ArgumentTypeError as exc:
        raise _UsageError(f"{label}: {exc}.") from None


def _integer_or_number(text: str, label: str) -> int | float:
    """A whole number stays an integer (as written in user_dataset.yml); anything else is a finite number."""

    try:
        return int(text)
    except ValueError:
        return _number_argument(text, label)


def _system_exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return EXIT_OK
    if isinstance(exc.code, int):
        return exc.code
    print(exc.code, file=sys.stderr)
    return EXIT_USAGE


# ---------------------------------------------------------------------------
# Output


def _print_experiment(study: VirtualExperiment) -> None:
    registry = study.registry
    print(
        f"Registry: {study.registry_source} (registry {registry.registry_id}, version {registry.version}, "
        f"maturity {registry.maturity})"
    )
    if study.user_dataset_id is not None:
        print(f"User dataset: {study.user_dataset_id} (digest {study.user_dataset_digest}), overlaid in memory")
    for resolved in study.resolved_records:
        print(f"  {resolved.record_type} {resolved.query!r} -> {resolved.record_id} ({resolved.record.name})")
    for case in study.environment_cases:
        print(
            f"  environment grid case {case.environment_id}: temperature {case.temperature} "
            f"{case.temperature_units}, pH {case.ph}, oxygen {case.oxygen}"
        )
    print(
        f"Cases: {len(study.fungus_ids)} fungus x {len(study.substrate_ids)} substrate x "
        f"{len(study.environment_ids)} environment = {study.case_count}"
    )


def _print_preflight(reports: Sequence[ModelabilityReport], *, mode: str) -> list[ModelabilityReport]:
    """Print the preflight table and return the reports that block simulation in ``mode``."""

    policies = [preflight_policy(report) for report in reports]
    rows = [
        (
            str(index),
            report.fungus_id,
            report.substrate_id,
            report.environment_id,
            report.status,
            "yes" if policy["simulation_allowed_for_mode"] else "no",
        )
        for index, (report, policy) in enumerate(zip(reports, policies, strict=True), start=1)
    ]
    print()
    print(f"Preflight in {mode} mode:")
    for line in _table(("#", "fungus", "substrate", "environment", "status", "runnable"), rows):
        print(f"  {line}")
    for index, (report, policy) in enumerate(zip(reports, policies, strict=True), start=1):
        lines = _report_item_lines(report, policy)
        if lines:
            print(f"  case {index}:")
            for line in lines:
                print(f"    {line}")
    return [report for report, policy in zip(reports, policies, strict=True) if not policy["simulation_allowed_for_mode"]]


def _report_item_lines(report: ModelabilityReport, policy: Mapping[str, Any]) -> list[str]:
    lines = [f"uncertain {item.item_type} {item.item_id}: {item.message}" for item in report.uncertain]
    for item in report.missing:
        if item.item_type == "parameter":
            lines.append(f"missing parameter {item.item_id}; suggested experiment: {missing_item_suggestion(item)}")
        else:
            lines.append(f"missing {item.item_type} {item.item_id}: {item.message}")
    lines.extend(f"incompatible {item.item_type} {item.item_id}: {item.message}" for item in report.incompatible)
    if not policy["simulation_allowed_for_mode"]:
        lines.append(
            f"blocked: {policy['blocking_reason']}; next action: {policy['recommended_next_action']}"
        )
    return lines


def _print_blocked(
    blocked: Sequence[ModelabilityReport], *, total: int, mode: str, command: str, runnable_only: bool = False
) -> None:
    print()
    print(f"Not runnable: {len(blocked)} of {total} case(s) cannot be simulated in {mode} mode.")
    some_runnable = len(blocked) < total
    if command == "run" and runnable_only and some_runnable:
        print(
            f"--runnable-only: simulating the {total - len(blocked)} runnable case(s); the blocked case(s) are not "
            "simulated and are listed in case_summary.csv as not_simulated, with their missing inputs in "
            "missing_parameters.csv and their measurement requests in suggested_experiments.csv."
        )
    elif command == "run":
        print(
            "Nothing was simulated: FungMod simulates only when every requested case passes the preflight. "
            "Supply the missing inputs, choose other cases, or check the mode."
        )
        if runnable_only:
            print("--runnable-only has nothing to simulate: no requested case is runnable.")
        elif some_runnable:
            print(
                f"Add --runnable-only to simulate the {total - len(blocked)} runnable case(s) and list the blocked "
                f"one(s) as not simulated (exit code {EXIT_PARTIAL})."
            )
    if mode == "scientific":
        print(
            "Scientific simulation requires exact, non-exploratory, non-toy modelable cases. Scientific means "
            "exact with current registry records and implemented mechanisms; it does not mean experimentally "
            "validated."
        )
    requests = list(dict.fromkeys(request for report in blocked for request in report.suggested_experiments))
    if requests:
        print("Measurement requests:")
        for request in requests:
            print(f"  - {request}")
    else:
        print("No measurement request applies: the blocking reasons above are not missing parameter values.")
    if command == "run" and not (runnable_only and some_runnable):
        print("Run `fungmod preflight` with the same arguments and --output DIR to write the preflight tables.")


def _print_run_summary(result: DegradationScreenResult, *, report_path: Path, html: bool) -> None:
    root = Path(result.output_directory)
    manifest_path = root / "output_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tables: Mapping[str, str] = manifest["tables"]
    all_cases = result.case_summary()
    cases = [case for case in all_cases if case["case_status"] != CASE_STATUS_NOT_SIMULATED]
    print()
    if result.mode == "exploratory":
        print(
            f"Simulated {len(cases)} case(s) in exploratory mode: {result.n_samples} sample(s) per case, "
            f"seed {result.seed}."
        )
    else:
        print(f"Simulated {len(cases)} case(s) in scientific mode: one exact run per case.")
    if manifest["partial_run"]:
        print(
            f"Partial run: {manifest['simulated_case_count']} of {manifest['requested_case_count']} requested case(s) "
            "simulated; the others were blocked by the preflight."
        )
    print(f"Run label: {manifest['run_label']}")
    if manifest["scientific_mode_note"]:
        print(manifest["scientific_mode_note"])
    final_metrics = result.final_metrics()
    threshold_times = result.threshold_times()
    summary_metrics = result.summary_metrics()
    for case in all_cases:
        case_id = case["case_id"]
        print()
        print(f"Case {case_id}: {case['fungus_id']} + {case['substrate_id']} + {case['environment_id']}")
        if case["case_status"] == CASE_STATUS_NOT_SIMULATED:
            print(f"  not simulated: {case['not_simulated_reason']}")
            continue
        print(f"  samples: {case['sample_count']} simulated, {case['sample_failure_count']} failed")
        response = case["environment_response_model"]
        effect = case["environment_effect_status"]
        shown_response = response and response not in {"none", effect}
        print(f"  environment effect: {effect}" + (f" ({response})" if shown_response else ""))
        print(f"  environment guardrail: {case['environment_guardrail']}")
        summaries = [row for row in summary_metrics if row["case_id"] == case_id]
        heading = "median [5th, 95th percentile] over samples" if result.n_samples > 1 else "one run"
        for title, rows in (("Final metrics", final_metrics), ("Threshold times", threshold_times)):
            lines = _metric_lines([row for row in rows if row["case_id"] == case_id], summaries)
            if lines:
                print(f"  {title} ({heading}):")
                for line in lines:
                    print(f"    {line}")
    limitations = result.limitations()
    severities = Counter(row["severity"] for row in limitations)
    severity_text = ", ".join(f"{count} {severity}" for severity, count in sorted(severities.items()))
    print()
    print(f"Output directory: {root}")
    print(f"Manifest: {manifest_path}")
    print(f"Report: {report_path}")
    if html:
        print(f"HTML report: {report_path.parent / 'virtual_experiment_report.html'}")
        print(f"Report index: {report_path.parent / 'index.html'}")
    print(f"Limitations: {len(limitations)} ({severity_text}) in {tables['limitations_table']}")
    print(f"Provenance: {len(result.provenance())} row(s) in {tables['provenance_table']}")
    print(f"Suggested experiments: {len(result.suggested_experiments())} in {tables['suggested_experiments']}")


def _metric_lines(rows: Sequence[Mapping[str, str]], summaries: Sequence[Mapping[str, str]]) -> list[str]:
    by_metric: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        by_metric.setdefault(row["metric"], []).append(row)
    if not by_metric:
        return []
    width = max(len(metric) for metric in by_metric)
    lines: list[str] = []
    for metric, metric_rows in by_metric.items():
        parts = [_summary_text(summary) for summary in summaries if summary["metric"] == metric]
        statuses = Counter(row["status"] for row in metric_rows if row["status"] != "computed")
        for status, count in statuses.items():
            notes = sorted({row["notes"] for row in metric_rows if row["status"] == status and row["notes"]})
            text = status if count == len(metric_rows) == 1 else f"{status} in {count} of {len(metric_rows)} samples"
            parts.append(f"{text} ({'; '.join(notes)})" if notes else text)
        lines.append(f"{metric.ljust(width)}  {'; '.join(parts)}")
    return lines


def _summary_text(summary: Mapping[str, str]) -> str:
    units = summary["units"]
    if int(summary["count"]) == 1:
        return f"{_number(summary['p50'])} {units}"
    return (
        f"{_number(summary['p50'])} [{_number(summary['p05'])}, {_number(summary['p95'])}] {units} "
        f"(n={summary['count']})"
    )


def _print_comparison(comparison: TimecourseComparison) -> None:
    used = Counter(
        (row["case_id"], row["observable"]) for row in comparison.rows if row["used_in_fit"]
    )
    rows = [
        (
            str(series["case_id"]),
            str(series["observable"]),
            str(series["n_observations"]),
            str(series["n_with_sd"]),
            f"{series['rmse']:.4g} {series['units']}",
            f"{series['mean_residual']:.4g}",
            f"{series['fraction_inside_band']:.4g}",
            str(used[(series["case_id"], series["observable"])]),
        )
        for series in comparison.series
    ]
    print()
    print(f"Time-course comparison with user dataset {comparison.dataset_id} (in-sample agreement, not validation):")
    headers = ("case", "observable", "n", "with sd", "RMSE", "mean residual", "inside 5-95% band", "used in fit")
    for line in _table(headers, rows):
        print(f"  {line}")
    cases = dict.fromkeys((series["case_id"], series["timecourse_case_id"]) for series in comparison.series)
    for case_id, timecourse_case_id in cases:
        print(f"  {case_id}: time courses of {timecourse_case_id}")
    for item in comparison.not_compared:
        print(f"  not compared: {item['series_id']}: {item['reason']}")
    print(f"  {comparison.note}")
    print(f"  Interpolation: {comparison.interpolation}.")
    print(f"Comparison table: {comparison.path}")


def _print_proteome(
    snapshot: UniprotSnapshot,
    resolution: ProteomeNameResolution | None,
    *,
    snapshot_dir: Path,
    fetched: bool,
    name_from: str,
) -> None:
    print("Proteome of the fungus (UniProt):")
    if fetched:
        print(f"  network: --fetch given; UniProt was queried and the responses are frozen under {snapshot_dir}")
    else:
        print(f"  network: not used; frozen snapshots under {snapshot_dir} (--fetch queries UniProt)")
    if resolution is not None:
        search = resolution.search
        print(f"  name searched: {resolution.name!r} (from {name_from})")
        print(f"  search: {search.query} -> {len(resolution.candidates)} candidate(s); snapshot {search.text()}")
        for line in _candidate_table(resolution.candidates, chosen=resolution.proteome_id):
            print(f"    {line}")
        if len(resolution.candidates) > _CANDIDATE_ROWS:
            print(f"    ... and {len(resolution.candidates) - _CANDIDATE_ROWS} more in {search.tsv_path}")
        print(f"  chosen: {resolution.proteome_id} ({resolution.chosen.organism}) because {resolution.match_rule}")
    release = f"UniProt release {snapshot.uniprot_release}" if snapshot.uniprot_release else "no UniProt release header"
    print(
        f"  export: {snapshot.query}, {snapshot.metadata.get('entry_rows')} UniProtKB entries of "
        f"{snapshot.metadata.get('organism') or 'an unnamed organism'}; snapshot {snapshot.directory} (SHA-256 "
        f"{snapshot.sha256}; retrieved {snapshot.retrieved_at}; {release})"
    )
    print()


def _candidate_table(candidates: Sequence[ProteomeCandidate], *, chosen: str | None = None) -> list[str]:
    rows = [
        (
            str(index),
            item.proteome_id,
            item.organism,
            item.organism_id or "-",
            item.proteome_type,
            "-" if item.protein_count is None else str(item.protein_count),
            "chosen" if item.proteome_id == chosen else "",
        )
        for index, item in enumerate(candidates[:_CANDIDATE_ROWS], start=1)
    ]
    return _table(("#", "proteome", "organism", "taxonomy", "type", "proteins", ""), rows)


def _print_assembly(draft: AssembledTablesDraft) -> None:
    report = draft.assembly
    fungus = report["fungus"]
    registry_fungus = f", registry fungus {fungus['registry_fungus_id']}" if fungus["registry_fungus_id"] else ""
    print(f"Assembled draft: {draft.dataset_id}")
    print(
        f"  fungus {fungus['input']!r} -> {fungus['name']} (strain {fungus['strain_id']}, "
        f"{fungus['resolved_as']}{registry_fungus})"
    )
    for item in report["substrates"]:
        if item.get("network_role") == "intermediate":
            print(
                f"  pool {item['substrate_id']} -> {item['name']} ({item['resolved_as']}; released by "
                f"{item['released_by']}, an intermediate of the enzyme network)"
            )
            continue
        print(f"  substrate {item['input']!r} -> {item['name']} ({item['substrate_id']}, {item['resolved_as']})")
    for item in report["requested_conditions"]:
        where = "conditions.csv" if item["in_conditions_csv"] else "an EnvironmentGrid condition, not a conditions.csv row"
        print(
            f"  condition {item['condition_id']}: {_value_text(item['temperature'])} {item['temperature_units']}, "
            f"pH {_value_text(item['ph'])} ({where})"
        )
    for item in report["measured_conditions"]:
        print(f"  condition {item['condition_id']}: {item['condition']} ({item['reason']})")

    classes = report["enzyme_classes"]
    print()
    print(f"Enzyme classes of the fungus: {len(classes)}")
    rows = [
        (item["enzyme_class"], item["declared_in"], "; ".join(evidence["evidence"] for evidence in item["evidence"]))
        for item in classes
    ]
    for line in _table(("class", "declared in", "evidence"), rows):
        print(f"  {line}")
    if report["unmodellable_enzyme_classes"]:
        print("Annotated classes without a registry record (no case is assembled for them):")
        for item in report["unmodellable_enzyme_classes"]:
            print(f"  - {item['enzyme_class']} (families {', '.join(item['families'])}): {item['reason']}")
    if report["unmapped_families"]:
        print("Annotated families without an enzyme class:")
        for item in report["unmapped_families"]:
            print(f"  - {item['family']}: {item['reason']}")
    annotation = report.get("annotation") or {}
    if annotation.get("unresolved_ec_numbers"):
        print("EC numbers of the proteome without a registry class (listed, not resolved):")
        for item in annotation["unresolved_ec_numbers"]:
            print(f"  - {item['ec_number']} ({item['accession_count']} protein(s)): {item['reason']}")
    if annotation.get("ec_cazy_disagreements"):
        print("Proteins whose CAZy and EC annotations name different classes (they support no class):")
        for item in annotation["ec_cazy_disagreements"]:
            print(
                f"  - {item['accession']}: CAZy {', '.join(item['cazy_families'])} -> "
                f"{', '.join(item['cazy_classes']) or 'no class'}; EC {', '.join(item['ec_numbers'])} -> "
                f"{', '.join(item['ec_classes']) or 'no class'}"
            )
    for item in report["substrate_compatibility"]:
        acting = ", ".join(entry["enzyme_class"] for entry in item["acting"]) or "none"
        print(f"On {item['substrate']} ({item['substrate_id']}): acting classes {acting}")
        for entry in item["not_acting"]:
            print(f"  not acting: {entry['enzyme_class']}: {entry['reason']}")
        for entry in item["acting_without_evidence"]:
            print(f"  acting without evidence in the fungus, not added: {entry['enzyme_class']}: {entry['reason']}")
        if item["undetermined"]:
            print(f"  undetermined: {item['undetermined']}")
    if "network" in report:
        _print_assembly_network(report["network"])

    cases = report["cases"]
    print()
    print(f"Cases: {len(cases)} (enzyme class x substrate x condition)")
    rows = [
        (
            str(index),
            case["fungus"],
            case["enzyme_class"],
            case["substrate_id"],
            case["condition"],
            case["kinetics_status"],
            case["condition_route"],
            "; ".join(case["source_ids"]) or "-",
        )
        for index, case in enumerate(cases, start=1)
    ]
    headers = ("#", "fungus", "class", "substrate", "condition", "kinetics status", "route", "source ids")
    for line in _table(headers, rows):
        print(f"  {line}")
    for index, case in enumerate(cases, start=1):
        print(f"  case {index}: {case['reason']}")
    if report["transferred_entry_ids"]:
        print(
            f"Transferred from another organism (estimates, exploratory mode only): entries "
            f"{', '.join(report['transferred_entry_ids'])}"
        )
    if report["entries"]:
        print()
        print(f"Kinetic-law entries considered: {len(report['entries'])}")
        rows = [
            (str(entry["entry_id"]), entry["organism"] or "-", entry["use"], entry["reason"] or "-")
            for entry in report["entries"]
        ]
        for line in _table(("entry", "organism", "use", "reason"), rows):
            print(f"  {line}")
    for item in report["unused_user_rows"]:
        print(f"Unused user-data row: {item}")
    for item in report["stored_registry_cases"]:
        print(f"Stored registry case {item['process_compatibility']}: {item['note']}")
    print()
    print("Limitations of this draft:")
    for text in report["limitations"]:
        print(f"  - {text}")


def _print_assembly_network(network: Mapping[str, Any]) -> None:
    print()
    print(
        f"Enzyme network (--network; user_dataset.yml {network['manifest_field']}, entry substrates "
        f"{', '.join(network['entry_substrates'])}): the member classes act together, all or nothing per condition"
    )
    for item in network["networks"]:
        links = []
        for link in item["links"]:
            product = link["product"] or "a product under review"
            amount = (
                f"{link['product_yield']} {link['yield_basis']}" if link["product_yield"] else "yield under review"
            )
            final = "" if link["releases_pool"] else ", final product"
            links.append(f"{link['substrate_id']} -> {product} ({amount}{final})")
        print(f"  from {item['entry_substrate']}: {', '.join(links)}")
        conditions = [str(entry["condition"]) for entry in item["conditions"]]
        rows = [
            (
                member["enzyme_class"],
                f"{member['pool']} ({member['pool_role']})",
                *(member["kinetics_status"].get(condition, "-") for condition in conditions),
            )
            for member in item["members"]
        ]
        for line in _table(("member class", "pool", *conditions), rows):
            print(f"  {line}")
        if item["undetermined_pools"]:
            print(
                f"  members on {', '.join(item['undetermined_pools'])} are decided when the reviewed tables are loaded "
                "(substrate class or bond classes under review)"
            )
        for entry in item["conditions"]:
            blocked = f": {'; '.join(entry['blocked_by'])}" if entry["blocked_by"] else ""
            print(
                f"  {entry['condition']}: {entry['status']} (initial concentration of {item['entry_substrate']}: "
                f"{entry['initial_concentration']}){blocked}"
            )
        for member in item["not_members"]:
            reasons = "; ".join(member["reasons"]) or "the pools are under review"
            print(f"  not a member (acts on no pool of this network): {member['enzyme_class']}: {reasons}")


def _print_draft(draft: UserTablesDraft, *, provider: str, source: str) -> None:
    print(f"Drafted user tables: {draft.dataset_id} (provider {provider}, source {source})")
    converted = f" ({', '.join(draft.converted_entry_ids)})" if draft.converted_entry_ids else ""
    print(f"Entries converted: {len(draft.converted_entry_ids)}{converted}")
    if draft.not_converted:
        print(f"Entries listed, not converted: {len(draft.not_converted)}")
        for item in draft.not_converted:
            print(f"  {item['entry_id']}: {item['reason']}")
    if draft.not_converted_parameters:
        print(f"Parameters listed, not converted: {len(draft.not_converted_parameters)}")
        for item in draft.not_converted_parameters:
            value = f" {item['value']} {item['units']}" if item.get("value") else ""
            print(f"  entry {item['entry_id']} {item['parameter']} ({item['parameter_type']}){value}: {item['reason']}")
    print()
    print("Tables:")
    for name, rows in draft.tables().items():
        print(f"  {name}: {len(rows)} row(s)")
    print("Strains (--fungus):")
    for line in _table(("strain_id", "name"), [(row["strain_id"], row["name"]) for row in draft.strains]):
        print(f"  {line}")
    print("Substrates (--substrate):")
    rows = [(row["substrate_id"], row["registry_substrate"] or "-", row["name"] or "-") for row in draft.substrates]
    for line in _table(("substrate_id", "registry substrate", "name"), rows):
        print(f"  {line}")
    print("Conditions (--condition):")
    rows = [
        (row["condition_id"], f"{row['temperature']} {row['temperature_units']}", row["ph"], row["notes"] or "-")
        for row in draft.conditions
    ]
    for line in _table(("condition_id", "temperature", "pH", "notes"), rows):
        print(f"  {line}")


def _print_written(written: Mapping[str, Path], output: Path) -> None:
    print()
    print(f"Draft written to {output}:")
    for name in sorted(written):
        print(f"  {name}")


def _print_review_fields(fields: Sequence[Mapping[str, Any]]) -> None:
    print()
    if not fields:
        print(f"No {REVIEW_MARKER} fields: review the tables and review.md before loading them.")
        return
    print(f"Fields to fill ({len(fields)}); check-data refuses the directory until each {REVIEW_MARKER} field is filled:")
    for field in fields:
        row = "-" if field["row"] is None else str(field["row"])
        print(f"  {field['file']}:{row}:{field['column'] or '-'}: {field['note']}")


def _print_assembly_next_steps(draft: AssembledTablesDraft, output: Path) -> None:
    report = draft.assembly
    directory = shell_quote(str(output))
    selection = [
        "--user-data",
        directory,
        "--fungus",
        shell_quote(report["fungus"]["name"]),
        *(
            part
            for item in report["substrates"]
            if item.get("network_role") != "intermediate"
            for part in ("--substrate", shell_quote(item["registry_substrate"] or item["name"]))
        ),
    ]
    listed = [item for item in report["requested_conditions"] if item["in_conditions_csv"]]
    grid = [item for item in report["requested_conditions"] if not item["in_conditions_csv"]]
    commands = []
    notes = []
    if listed:
        conditions = [part for item in listed for part in ("--condition", shell_quote(item["condition_id"]))]
        command, note = _assembly_run_command(report, selection, conditions, [item["condition_id"] for item in listed])
        commands.append(command)
        notes.extend(note)
    for item in grid:
        values = item["environment_grid"]
        grid_parts = [
            *(part for value in values["temperature_C"] for part in ("--temperature-c", _value_text(value))),
            *(part for value in values["ph"] for part in ("--ph", _value_text(value))),
        ]
        command, note = _assembly_run_command(report, selection, grid_parts, [item["condition_id"]])
        commands.append(command)
        notes.extend(note)
    _print_next_steps(draft, output, commands, notes)


def _assembly_run_command(
    report: Mapping[str, Any], selection: Sequence[str], conditions: Sequence[str], condition_ids: Sequence[str]
) -> tuple[str, list[str]]:
    """The ``fungmod run`` command for some conditions of a draft, with ``--runnable-only`` when a case is a gap.

    A gap or conflict case has no kinetics in the draft, so once loaded its roles are explicit gaps and the
    preflight blocks it; without ``--runnable-only`` the whole command would then simulate nothing (exit 3).
    """

    if "network" in report:
        return _network_run_command(report["network"], selection, conditions, condition_ids)
    gaps = [
        case
        for case in report["cases"]
        if case["condition"] in condition_ids and case["kinetics_status"] in {STATUS_GAP, STATUS_CONFLICT}
    ]
    if not gaps:
        return " ".join(("fungmod run", *selection, *conditions)), []
    listed = "; ".join(
        f"{case['enzyme_class']} on {case['substrate_id']} at {case['condition']} ({case['kinetics_status']})"
        for case in gaps
    )
    note = (
        f"--runnable-only because {len(gaps)} case(s) of this command have no kinetics in the draft ({listed}): "
        "the preflight blocks them, so without the flag nothing is simulated (exit code 3); with it the runnable "
        f"cases are simulated and the blocked ones are listed with their measurement requests (exit code "
        f"{EXIT_PARTIAL})."
    )
    return " ".join(("fungmod run", *selection, *conditions, "--runnable-only")), [note]


def _network_run_command(
    network: Mapping[str, Any], selection: Sequence[str], conditions: Sequence[str], condition_ids: Sequence[str]
) -> tuple[str, list[str]]:
    """The ``fungmod run`` command of a network draft, with ``--runnable-only`` when a network case is blocked."""

    blocked = [
        f"the network from {item['entry_substrate']} at {entry['condition']} ({'; '.join(entry['blocked_by'])})"
        for item in network["networks"]
        for entry in item["conditions"]
        if entry["condition"] in condition_ids and entry["status"] == NETWORK_BLOCKED
    ]
    if not blocked:
        return " ".join(("fungmod run", *selection, *conditions)), []
    note = (
        f"--runnable-only because {len(blocked)} enzyme-network case(s) of this command are blocked "
        f"({'; '.join(blocked)}): a network runs at a condition only when every member class has kinetics and its "
        "entry an initial concentration, so the preflight blocks these, and without the flag nothing is simulated "
        f"(exit code {EXIT_NOT_RUNNABLE}); with it the runnable network cases are simulated and the blocked ones are "
        f"listed with their measurement requests (exit code {EXIT_PARTIAL}; {EXIT_NOT_RUNNABLE} when none is runnable)."
    )
    return " ".join(("fungmod run", *selection, *conditions, "--runnable-only")), [note]


def _print_draft_next_steps(draft: UserTablesDraft, output: Path) -> None:
    directory = shell_quote(str(output))
    command = f"fungmod run --user-data {directory} --fungus STRAIN --substrate SUBSTRATE --condition CONDITION_ID"
    _print_next_steps(draft, output, [command])


def _print_next_steps(
    draft: UserTablesDraft, output: Path, commands: Sequence[str], notes: Sequence[str] = ()
) -> None:
    directory = shell_quote(str(output))
    step = 1
    print()
    print("Next:")
    if draft.review_fields:
        print(f"  {step}. Fill the {len(draft.review_fields)} {REVIEW_MARKER} field(s) above; {output / 'review.md'} "
              "explains every decision.")
        step += 1
    print(f"  {step}. fungmod check-data {directory}")
    step += 1
    print(f"  {step}. Run it (exploratory mode samples ranges and estimates; scientific mode takes exact measured, "
          "literature or design values only):")
    for command in commands:
        print(f"     {command} \\")
        print("       --mode exploratory --samples N --seed S --output RUN_DIR")
    for note in notes:
        print(f"     {note}")


def _print_fit(fit: UserDatasetFit) -> None:
    report = fit.report
    case = report["case"]
    convergence = report["convergence"]
    print()
    print(f"Fit of user dataset {fit.input_dataset_id} (digest {fit.input_dataset_digest}):")
    print(f"  case: {case['strain_id']} / {case['enzyme_class']} / {case['substrate_id']}")
    print(f"  conditions: {', '.join(report['conditions'])}")
    print(
        f"  observations: {report['n_observations']} ({report['timecourse_file']} rows "
        f"{_rows_text(report['timecourse_rows'])}); fitted quantities: {report['n_parameters']}; "
        f"residual degrees of freedom: {report['residual_degrees_of_freedom']}"
    )
    print(f"  error model: {report['error_model']}")
    print(f"  objective: {report['objective']}")
    state = "converged" if convergence["success"] else "did not converge"
    print(f"  optimizer: {state} ({convergence['message']})")
    _print_fit_quantities(report)
    for warning in report.get("warnings", []):
        print(f"  warning: {warning}")
    print()
    print(f"In-sample: {report['claim_boundary']}")


def _print_fit_quantities(report: Mapping[str, Any]) -> None:
    level = report["settings"]["confidence_level"]
    rows = []
    for item in report["quantities"]:
        interval = item["interval"]
        rows.append(
            (
                item["quantity"],
                f"{item['value']:.4g}",
                item["units"],
                "-" if interval is None else f"[{interval[0]:.4g}, {interval[1]:.4g}]",
                item["identifiability"],
                f"[{item['bounds'][0]:.4g}, {item['bounds'][1]:.4g}]",
                f"{item['initial']:.4g} ({item['initial_source']})",
            )
        )
    headers = ("quantity", "value", "units", f"interval ({level:.0%})", "identifiability", "bounds", "start")
    for line in _table(headers, rows):
        print(f"  {line}")
    for item in report["quantities"]:
        print(f"  {item['quantity']}: {item['identifiability_method']}; {item['reason']}")


def _print_fitted_dataset(fitted: UserDataset, fit: UserDatasetFit, output: Path) -> None:
    case = fit.report["case"]
    directory = shell_quote(str(output))
    conditions = " ".join(f"--condition {shell_quote(condition)}" for condition in fit.report["conditions"])
    print()
    print(f"Fitted dataset: {fitted.dataset_id} (digest {fitted.digest})")
    print(f"Directory: {fitted.source_directory}")
    print(f"Fit report: {output / 'fit_report.json'}")
    print()
    print("Next (fitted values run in exploratory mode only; scientific mode refuses them):")
    print(f"  fungmod check-data {directory}")
    print(
        f"  fungmod run --user-data {directory} --fungus {shell_quote(case['strain_id'])} "
        f"--substrate {shell_quote(case['substrate_id'])} {conditions} \\"
    )
    print("    --mode exploratory --samples N --seed S --output RUN_DIR --compare-timecourses")


def _print_genome_resolution(dataset: UserDataset) -> None:
    if not dataset.genome_annotations:
        return
    print(f"Genome and proteome annotations (genomes.csv): {len(dataset.genome_annotations)}")
    rows = [
        (
            item["strain_id"],
            item["annotation_file"],
            f"{item['annotation_tool']} {item['annotation_tool_version']}".strip(),
            item["source"],
        )
        for item in dataset.genome_annotations
    ]
    for line in _table(("strain", "file", "tool", "source"), rows):
        print(f"  {line}")
    for item in dataset.genome_annotations:
        details = []
        if item.get("proteome_id"):
            details.append(f"proteome {item['proteome_id']}")
        if "unresolved_ec_numbers" in item:
            details.append(f"{len(item['unresolved_ec_numbers'])} unresolved EC number(s)")
        if "ec_cazy_disagreements" in item:
            details.append(f"{len(item['ec_cazy_disagreements'])} EC/CAZy disagreement(s)")
        if details:
            print(f"  {item['annotation_file']}: {'; '.join(details)}")
        print(f"  note: {item['claim_boundary']}")
    resolved = dataset.genome_resolved_classes
    print(f"Enzyme classes resolved from them: {len(resolved)}")
    rows = [(item["strain_id"], item["enzyme_class"], item["declared_by"], item["evidence"]) for item in resolved]
    for line in _table(("strain", "class", "declared by", "evidence"), rows):
        print(f"  {line}")
    if dataset.unmodellable_enzyme_classes:
        print(f"Resolved classes without a registry record: {len(dataset.unmodellable_enzyme_classes)}")
        for item in dataset.unmodellable_enzyme_classes:
            print(
                f"  - {item['strain_id']} {item['enzyme_class']} (families {', '.join(item['families'])}): "
                f"{item['reason']}"
            )
    if dataset.unmapped_families:
        print(f"Families without an enzyme class: {len(dataset.unmapped_families)}")
        for item in dataset.unmapped_families:
            print(f"  - {item['strain_id']} {item['family']}: {item['reason']}")


def _print_cultures(dataset: UserDataset) -> None:
    if not dataset.cultures:
        return
    print(
        f"Cultures (culture.csv; the strain grows on the substrate and secretes its enzyme pools, "
        f"culture_physiology): {len(dataset.cultures)}"
    )
    rows = [
        (
            str(item["strain_id"]),
            str(item["substrate_id"]),
            str(item["enzyme_class"]),
            ", ".join(str(pool) for pool in item["enzyme_pools"]),
            _rows_text(item["rows"]) if item["rows"] else "none (every role a gap)",
        )
        for item in dataset.cultures
    ]
    headers = ("strain", "substrate", "consuming pool", "enzyme pools", "culture.csv rows")
    for line in _table(headers, rows):
        print(f"  {line}")


def _print_enzyme_networks(dataset: UserDataset) -> None:
    if not dataset.enzyme_networks:
        return
    print(
        f"Enzyme networks (user_dataset.yml enzyme_network; the classes act together on shared pools, "
        f"enzyme_network): {len(dataset.enzyme_networks)}"
    )
    rows = [
        (
            str(process["enzyme_class"]),
            str(process["pool"]),
            str(process["rate_form"]),
            str(process["inhibitor"] or "none"),
        )
        for item in dataset.enzyme_networks
        for process in item["processes"]
    ]
    for item in dataset.enzyme_networks:
        links = ", ".join(
            f"{link['substrate_id']} -> {link['releases']} ({link['yield']:g} {link['yield_basis']})" for link in item["links"]
        )
        print(f"  from {item['entry_substrate']}: {links}; strains {', '.join(item['strains'])}")
    headers = ("enzyme class", "pool", "rate form", "competitive inhibitor")
    for line in _table(headers, rows):
        print(f"  {line}")


def _print_timecourses(dataset: UserDataset) -> None:
    series = [item for items in dataset.timecourses.values() for item in items]
    if not series:
        return
    print(
        f"Time courses (timecourse.csv; observations, not records): {len(series)} series in "
        f"{len(dataset.timecourses)} case(s)"
    )
    rows = [
        (
            item.strain_id,
            item.class_key,
            item.substrate_id,
            item.condition_id,
            item.observable,
            str(len(item.points)),
            f"{_value_text(item.points[0].time)} to {_value_text(item.points[-1].time)} {item.time_units}",
            item.units,
            str(sum(1 for point in item.points if point.sd is not None)),
        )
        for item in series
    ]
    headers = ("strain", "class", "substrate", "condition", "observable", "points", "time", "units", "with sd")
    for line in _table(headers, rows):
        print(f"  {line}")


def _print_fit_block(dataset: UserDataset) -> None:
    block = dataset.manifest.get("fit")
    if not isinstance(block, Mapping):
        return
    case = block["case"]
    print(
        f"Fitted values (fitted to the time courses of {block['input_dataset_id']}, digest "
        f"{block['input_dataset_digest']}; {block['error_model']}; exploratory mode only):"
    )
    print(f"  case: {case['strain_id']} / {case['enzyme_class']} / {case['substrate_id']} at {', '.join(block['conditions'])}")
    for item in block["quantities"]:
        interval = item["interval"]
        interval_text = "no interval" if interval is None else f"interval [{interval[0]:.4g}, {interval[1]:.4g}]"
        print(
            f"  {item['quantity']} = {item['value']:.4g} {item['units']}: {item['identifiability']}, {interval_text}"
        )
    print(f"  {block['claim_boundary']}")


def _value_text(value: float) -> str:
    return f"{float(value):g}"


def _rows_text(rows: Sequence[int]) -> str:
    """Spreadsheet line numbers as compact ranges such as ``2-9, 12``."""

    ordered = sorted(set(rows))
    parts: list[str] = []
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        parts.append(str(ordered[index]) if end == index else f"{ordered[index]}-{ordered[end]}")
        index = end + 1
    return ", ".join(parts)


def _number(text: str) -> str:
    return f"{float(text):.4g}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [max([len(header), *(len(row[index]) for row in rows)]) for index, header in enumerate(headers)]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in (tuple(headers), *(tuple(row) for row in rows))
    ]


__all__ = [
    "EXIT_NOT_RUNNABLE",
    "EXIT_OK",
    "EXIT_SIMULATION_FAILED",
    "EXIT_USAGE",
    "build_parser",
    "main",
]
