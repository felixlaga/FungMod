"""Command-line virtual experiments: name fungi, substrates and conditions, and FungMod calculates.

``fungmod run`` resolves the names on the registry (with an optional user
dataset overlaid in memory), runs the modelability preflight, simulates when
every requested case is runnable in the requested mode, and writes the
standard output bundle: tables, manifest, Markdown report and, with
``--report``, the HTML report. ``fungmod preflight`` stops after the
preflight, ``fungmod check-data`` validates a user dataset directory, and
``fungmod list`` shows what can be named.

The command line only parses arguments and prints what the API returns; every
scientific decision (name resolution, modelability, the simulation rule of each
mode, sampling, tables and reports) stays in ``fungal_model.api``. Every value
comes from the command line or the registry: the mode, the sample count, the
seed and the output directory have no defaults, and a condition grid needs
both temperature and pH values.

Exit codes: 0 success; 1 the simulation failed after a passing preflight;
2 usage or input error; 3 the preflight blocks a requested case in the
requested mode.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from fungal_model import __version__
from fungal_model.api.environment_grid import EnvironmentGrid, environment_grid
from fungal_model.api.result_tables import preflight_policy
from fungal_model.api.user_data import USER_DATASET_MATURITY_GAP, UserDataError, load_user_dataset
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

EXIT_OK = 0
EXIT_SIMULATION_FAILED = 1
EXIT_USAGE = 2
EXIT_NOT_RUNNABLE = 3

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

_DESCRIPTION = (
    "FungMod virtual experiments from the command line: name fungi or enzyme sources, substrates and "
    "conditions, and FungMod preflights, simulates and writes tables, manifest and report."
)
_EPILOG = f"""modes (--mode is required; it decides what may be simulated):
  {EXPLORATORY_MODE_HELP}
  {SCIENTIFIC_MODE_HELP}

exit codes:
  0  success
  1  the simulation failed after a passing preflight
  2  usage or input error (unknown names, invalid user data, missing arguments)
  3  the preflight blocks a requested case in the requested mode

examples:
  fungmod list --aliases
  fungmod preflight --fungus NAME --substrate NAME --temperature-c 30 --ph 5 --mode scientific
  fungmod run --fungus NAME --substrate NAME --temperature-c 30 --ph 5 \\
      --mode exploratory --samples 32 --seed 1 --output runs/first --report
  fungmod check-data path/to/user_dataset
"""


class _UsageError(Exception):
    """A usage or input problem reported with exit code 2."""

    def __init__(self, message: str, details: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.details = tuple(details)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``fungmod`` command line and return its exit code."""

    parser = build_parser()
    try:
        args = parser.parse_args(None if argv is None else list(argv))
    except SystemExit as exc:
        return _system_exit_code(exc)
    handlers = {
        "run": _run,
        "preflight": _preflight,
        "check-data": _check_data,
        "list": _list,
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
            "in the requested mode and write the standard output bundle."
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
    return parser


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
    output = cast(Path, args.output)
    _require_new_output(output)
    study = _build_experiment(args)
    _print_experiment(study)
    reports = study.preflight(mode=mode)
    blocked = _print_preflight(reports, mode=mode)
    if blocked:
        _print_blocked(blocked, total=len(reports), mode=mode, command="run")
        return EXIT_NOT_RUNNABLE
    try:
        result = study.simulate(
            mode=mode,
            n_samples=args.samples if mode == "exploratory" else 1,
            seed=args.seed,
            output_dir=output,
            quicklook=not args.no_plots,
        )
        report_path = result.write_report(include_html=args.report, include_index=args.report)
    except (RegistryScreenSimulationError, VirtualExperimentError) as exc:
        print(f"fungmod run: simulation failed: {exc}", file=sys.stderr)
        return EXIT_SIMULATION_FAILED
    _print_run_summary(result, report_path=report_path, html=args.report)
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
        raise _user_data_error(exc) from exc
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
    if temperatures is None or ph_values is None:
        raise _UsageError(
            "a condition grid needs at least one --temperature-c and at least one --ph value; "
            "FungMod does not assume a missing condition."
        )
    return environment_grid(temperature_C=temperatures, ph=ph_values, oxygen=() if oxygen is None else oxygen)


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


def _require_new_output(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        raise _UsageError(f"--output {path} exists and is not a directory.")
    if any(path.iterdir()):
        raise _UsageError(
            f"--output {path} is not empty; choose a new or empty directory so that the manifest lists only "
            "the files of this run."
        )


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


def _print_blocked(blocked: Sequence[ModelabilityReport], *, total: int, mode: str, command: str) -> None:
    print()
    print(f"Not runnable: {len(blocked)} of {total} case(s) cannot be simulated in {mode} mode.")
    if command == "run":
        print(
            "Nothing was simulated: FungMod simulates only when every requested case passes the preflight. "
            "Supply the missing inputs, choose other cases, or check the mode."
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
    if command == "run":
        print("Run `fungmod preflight` with the same arguments and --output DIR to write the preflight tables.")


def _print_run_summary(result: DegradationScreenResult, *, report_path: Path, html: bool) -> None:
    root = Path(result.output_directory)
    manifest_path = root / "output_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tables: Mapping[str, str] = manifest["tables"]
    cases = result.case_summary()
    print()
    if result.mode == "exploratory":
        print(
            f"Simulated {len(cases)} case(s) in exploratory mode: {result.n_samples} sample(s) per case, "
            f"seed {result.seed}."
        )
    else:
        print(f"Simulated {len(cases)} case(s) in scientific mode: one exact run per case.")
    print(f"Run label: {manifest['run_label']}")
    if manifest["scientific_mode_note"]:
        print(manifest["scientific_mode_note"])
    final_metrics = result.final_metrics()
    threshold_times = result.threshold_times()
    summary_metrics = result.summary_metrics()
    for case in cases:
        case_id = case["case_id"]
        print()
        print(f"Case {case_id}: {case['fungus_id']} + {case['substrate_id']} + {case['environment_id']}")
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
