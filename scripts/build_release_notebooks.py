"""Build the two deterministic, researcher-facing release notebooks."""

from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

import nbformat


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks" / "examples"


def _markdown(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(dedent(source).strip() + "\n")


def _code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(dedent(source).strip() + "\n")


def _notebook(cells: list[nbformat.NotebookNode], *, prefix: str) -> nbformat.NotebookNode:
    for index, cell in enumerate(cells):
        cell["id"] = f"{prefix}-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.11",
            },
        },
    )


def zero_to_results_notebook() -> nbformat.NotebookNode:
    """Return the install-to-report notebook."""

    return _notebook(
        [
            _markdown(
                """
                # FungMod from zero to a complete virtual-experiment report

                This notebook starts at the installed public API and ends with a
                self-describing output bundle: preflight decisions, trajectories,
                final metrics, threshold times, uncertainty summaries, provenance,
                limitations, suggested experiments, quick-look figures, and a
                Markdown/HTML report.

                **Scope:** the bundled cellulose-equivalent enzyme-chain case is an
                exploratory software-verified example. It is not whole-fungus
                physiology, organism-specific evidence, calibration, or empirical
                validation. Runtime environment-grid values remain metadata unless an
                explicit response law or condition-specific record is active.

                **Validation:** Software execution is not empirical validation.
                """
            ),
            _markdown(
                """
                ## Install

                In a fresh Python 3.11+ environment:

                ```bash
                python -m pip install fungmod
                ```

                The distribution provides both `import fungmod` and the original
                `import fungal_model` namespace.
                """
            ),
            _code(
                """
                import json
                import os
                from pathlib import Path

                import fungmod as fm

                OUTPUT_ROOT = Path(
                    os.environ.get("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", "outputs/notebooks")
                ).resolve()
                OUTPUT = OUTPUT_ROOT / "20_zero_to_complete_virtual_experiment"
                SAMPLE_COUNT = int(os.environ.get("FUNGMOD_NOTEBOOK_SAMPLES", "8"))
                OUTPUT.mkdir(parents=True, exist_ok=True)

                {"fungmod_version": fm.__version__, "output_directory": str(OUTPUT)}
                """
            ),
            _markdown(
                """
                ## 1. Define a screen from researcher-facing names

                The grid creates four explicit environment cases. The public resolver
                maps the fungus/source and substrate aliases to registry IDs. Creating
                the study does not run a model.
                """
            ),
            _code(
                """
                grid = fm.environment_grid(
                    temperature_C=[25.0, 30.0],
                    ph=[4.5, 5.5],
                    oxygen="aerobic",
                )
                study = fm.virtual_experiment(
                    fungi="generic cellulase source",
                    substrates="cellulose film",
                    environments=grid,
                )

                study.to_dict()
                """
            ),
            _markdown(
                """
                ## 2. Run modelability preflight before simulation

                Preflight is a guardrail, not the scientific result. It makes missing,
                exploratory, incompatible, and unsupported inputs visible before the
                solver runs.
                """
            ),
            _code(
                """
                preflight = study.preflight(mode="exploratory")
                preflight_rows = [report.to_dict() for report in preflight]
                {
                    "case_count": study.case_count,
                    "statuses": [row["status"] for row in preflight_rows],
                    "summaries": [report.summary() for report in preflight],
                }
                """
            ),
            _markdown(
                """
                ## 3. Simulate the allowed exploratory cases

                A fixed seed makes sampled exploratory ranges reproducible. Quick-look
                plots are presentation aids generated from exported tables; they are
                not validation plots.
                """
            ),
            _code(
                """
                result = study.simulate(
                    mode="exploratory",
                    n_samples=SAMPLE_COUNT,
                    seed=20260730,
                    output_dir=OUTPUT,
                    quicklook=True,
                )

                {
                    "mode": result.mode,
                    "samples_per_case": result.n_samples,
                    "case_results": len(result.screen_result.case_results),
                    "quicklook_files": [Path(path).name for path in result.quicklook_paths],
                }
                """
            ),
            _markdown(
                """
                ## 4. Inspect mechanism, assumptions, and numerical results together

                Read mechanism and assumption rows before interpreting curves. The
                first few rows below are deliberately kept as dictionaries so units,
                status labels, and allowed-use fields remain visible.
                """
            ),
            _code(
                """
                mechanisms = result.mechanism_summary()
                assumptions = result.assumption_summary()
                final_metrics = result.final_metrics()
                threshold_times = result.threshold_times()

                {
                    "mechanisms": mechanisms[:4],
                    "assumptions": assumptions[:4],
                    "final_metrics": final_metrics[:6],
                    "threshold_times": threshold_times[:6],
                }
                """
            ),
            _markdown(
                """
                ## 5. Inspect uncertainty and comparison guardrails

                Quantile bands summarize explicit sampled inputs and resulting
                trajectories. They are not posterior intervals or empirical confidence
                intervals. Comparison rows carry their own `comparison_allowed`,
                `ranking_allowed`, and blocking-reason fields.
                """
            ),
            _code(
                """
                uncertainty_rows = result.uncertainty_summary()
                trajectory_rows = result.trajectory_quantiles()
                comparison_rows = result.comparison_summary()

                {
                    "uncertainty_examples": uncertainty_rows[:5],
                    "trajectory_quantile_examples": trajectory_rows[:5],
                    "comparison_guardrails": [
                        {
                            key: row.get(key, "")
                            for key in (
                                "source_metric",
                                "comparison_allowed",
                                "ranking_allowed",
                                "ranking_blocking_reason",
                            )
                        }
                        for row in comparison_rows[:6]
                    ],
                }
                """
            ),
            _markdown(
                """
                ## 6. Let the result identify limitations and next measurements

                FungMod keeps unsupported biology and missing evidence in standard
                tables rather than hiding them behind a successful solver run.
                """
            ),
            _code(
                """
                limitations = result.limitations()
                suggestions = result.suggested_experiments()
                provenance = result.provenance()

                {
                    "limitations": limitations[:8],
                    "suggested_experiments": suggestions[:8],
                    "provenance": provenance[:6],
                }
                """
            ),
            _markdown(
                """
                ## 7. Write a navigable report and verify the manifest

                The report is rendered only from existing standard tables. The manifest
                is the machine-readable inventory for downstream analysis and archiving.
                """
            ),
            _code(
                """
                report_path = result.write_report(
                    OUTPUT / "report",
                    include_html=True,
                    include_index=True,
                )
                manifest = json.loads((OUTPUT / "output_manifest.json").read_text(encoding="utf-8"))
                required = {
                    "time_series_long.csv",
                    "final_metrics.csv",
                    "threshold_times.csv",
                    "uncertainty_summary.csv",
                    "trajectory_quantiles.csv",
                    "provenance_table.csv",
                    "limitations_table.csv",
                    "suggested_experiments.csv",
                    "report/virtual_experiment_report.md",
                    "report/virtual_experiment_report.html",
                    "report/index.html",
                }
                missing = sorted(required - set(manifest["files"]))
                assert not missing, missing

                {
                    "report": str(report_path),
                    "manifest_schema": manifest["output_schema_version"],
                    "artifact_count": len(manifest["files"]),
                    "missing_required_artifacts": missing,
                }
                """
            ),
            _markdown(
                """
                ## What the notebook established

                - The installed package can resolve its bundled registry without a
                  repository checkout.
                - Modelability, mechanisms, assumptions, numerical outputs,
                  uncertainty, provenance, and limitations stay connected.
                - Every displayed result is recoverable from exported tables.

                It did **not** establish organism-specific performance, experimental
                agreement, publication-grade calibration, or whole-fungus behavior.
                """
            ),
        ],
        prefix="zero",
    )


def advanced_capabilities_notebook() -> nbformat.NotebookNode:
    """Return the provenance-to-thermodynamics notebook."""

    return _notebook(
        [
            _markdown(
                """
                # FungMod advanced capabilities: provenance to solver-time thermodynamics

                This notebook connects the deepest currently implemented public
                surfaces in one reproducible workflow:

                1. offline-first SABIO-RK source provenance and review-only proposals;
                2. registry-backed uncertainty-aware Reaction 618 simulation;
                3. provenance-bound competitive and substrate-inhibition laws;
                4. explicit dynamic reaction quotients, Gibbs energy, electron-balance
                   binding, and solver-time forward-rate enforcement;
                5. conservation, entropy-rate, solver, report, and manifest artifacts.

                **Scientific boundary:** source proposals require curator review, and
                every configured mechanism example is either exploratory or an
                artificial framework benchmark.

                **Validation:** Software execution is not empirical validation.
                """
            ),
            _code(
                """
                import csv
                import json
                import os
                from pathlib import Path

                import fungmod as fm

                OUTPUT_ROOT = Path(
                    os.environ.get("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", "outputs/notebooks")
                ).resolve()
                OUTPUT = OUTPUT_ROOT / "21_advanced_capabilities"
                SAMPLE_COUNT = int(os.environ.get("FUNGMOD_NOTEBOOK_SAMPLES", "12"))
                OUTPUT.mkdir(parents=True, exist_ok=True)

                {"fungmod_version": fm.__version__, "output_directory": str(OUTPUT)}
                """
            ),
            _markdown(
                """
                ## 1. Start with frozen source evidence, not an invented parameter

                The default SABIO-RK path is offline-first. It reads the frozen,
                checksummed Reaction 618 snapshot shipped with FungMod. The proposal is
                written outside `data_registry/` and remains review-only.
                """
            ),
            _code(
                """
                proposal = fm.source_proposal(provider="sabiork", reaction_id="618")
                proposal_output = proposal.write(OUTPUT / "source_proposal")
                proposed_records = proposal.proposed_records()

                {
                    "query": proposal.source_query,
                    "snapshot": proposal.source_snapshot_path,
                    "status": proposal.proposal_status,
                    "reaction_record_count": len(proposal.reaction_records),
                    "parameter_record_count": len(proposed_records["parameter_records"]),
                    "written_files": sorted(path.name for path in proposal_output.paths.values()),
                }
                """
            ),
            _markdown(
                """
                ## 2. Run the registry-backed Reaction 618 uncertainty screen

                The selected kinetic records are provenance-backed, while enzyme
                concentration remains an explicit user-supplied exploratory prior.
                Therefore the run is exploratory and its quantiles are not calibrated
                confidence intervals.
                """
            ),
            _code(
                """
                reaction_study = fm.virtual_experiment(
                    fungi="beta-glucosidase source",
                    substrates="cellobiose",
                    environments="SABIO-RK Reaction 618 selected assay conditions",
                )
                reaction_result = reaction_study.simulate(
                    mode="exploratory",
                    n_samples=SAMPLE_COUNT,
                    seed=618,
                    output_dir=OUTPUT / "reaction_618",
                    quicklook=True,
                )
                reaction_result.write_report(
                    OUTPUT / "reaction_618" / "report",
                    include_html=True,
                    include_index=True,
                )

                {
                    "preflight": [row.to_dict() for row in reaction_result.preflight_reports],
                    "final_metrics": reaction_result.final_metrics()[:8],
                    "threshold_times": reaction_result.threshold_times()[:6],
                }
                """
            ),
            _code(
                """
                sampled = reaction_result.sampled_parameters()
                uncertainty = reaction_result.uncertainty_summary()
                provenance = reaction_result.provenance()
                suggestions = reaction_result.suggested_experiments()

                {
                    "exploratory_enzyme_prior": [
                        row for row in sampled
                        if row.get("symbol") == "enzyme_concentration_beta_glucosidase"
                    ][:4],
                    "uncertainty_rows": uncertainty[:6],
                    "provenance_rows": provenance[:6],
                    "suggested_experiments": suggestions[:6],
                }
                """
            ),
            _markdown(
                """
                ## 3. Exercise two provenance-bound inhibition laws

                These homogeneous configurations are artificial software benchmarks.
                They demonstrate that inhibition state ownership, positive
                unit-compatible constants, primary-source metadata, maturity labels,
                assumptions, and limitations all survive assembly and output writing.
                They do not provide organism-specific inhibition evidence.
                """
            ),
            _code(
                """
                inhibition_configs = {
                    "competitive": "toy_homogeneous_competitive_inhibition.yml",
                    "substrate": "toy_homogeneous_substrate_inhibition.yml",
                }
                inhibition_results = {}
                for label, filename in inhibition_configs.items():
                    inhibition_results[label] = fm.run_configured_model(
                        fm.example_data_path(Path("model_configs") / filename),
                        output_dir=OUTPUT / f"{label}_inhibition",
                    )

                inhibition_summary = {
                    label: {
                        "processes": sorted(run.process_rates),
                        "validation": run.validation_report(),
                        "solver_success": run.solver_metadata["success"],
                    }
                    for label, run in inhibition_results.items()
                }
                inhibition_summary
                """
            ),
            _markdown(
                """
                ## 4. Run explicit solver-time thermodynamic enforcement

                The packaged configuration is a generic A-to-B framework benchmark. It
                supplies every activity, concentration, temperature, standard-energy,
                gas-constant, electron-balance, tolerance, and provenance input
                explicitly. The solver blocks an unfavorable nonnegative forward rate;
                it does not infer missing chemistry.
                """
            ),
            _code(
                """
                thermo_output = OUTPUT / "dynamic_thermodynamics"
                thermo_result = fm.run_configured_model(
                    fm.example_data_path(
                        "model_configs/showcase_dynamic_thermodynamics.yml"
                    ),
                    output_dir=thermo_output,
                )

                prefix = "dynamic_thermodynamics.a_to_b_dynamic"
                reaction_quotient = thermo_result.derived_quantities[
                    f"{prefix}.reaction_quotient"
                ].magnitude
                delta_gibbs = thermo_result.derived_quantities[
                    f"{prefix}.delta_gibbs"
                ].to("joule / mole").magnitude
                rate_blocked = thermo_result.derived_quantities[
                    f"{prefix}.rate_blocked"
                ].magnitude

                {
                    "initial_reaction_quotient": float(reaction_quotient[0]),
                    "final_reaction_quotient": float(reaction_quotient[-1]),
                    "initial_delta_gibbs_J_per_mol": float(delta_gibbs[0]),
                    "final_delta_gibbs_J_per_mol": float(delta_gibbs[-1]),
                    "blocked_time_points": int(rate_blocked.sum()),
                    "solver_dynamic_thermodynamics": thermo_result.solver_metadata[
                        "dynamic_thermodynamics"
                    ],
                }
                """
            ),
            _markdown(
                """
                ## 5. Inspect package-generated advanced diagnostics

                The entropy-rate output uses a separately supplied static,
                condition-specific delta G and explicit control-volume conversion. It
                must not be confused with the dynamic delta-G trajectory used by the
                solver constraint.
                """
            ),
            _code(
                """
                thermodynamic_summary = json.loads(
                    (thermo_output / "thermodynamic_summary.json").read_text(encoding="utf-8")
                )
                conservation_summary = json.loads(
                    (thermo_output / "conservation_diagnostics.json").read_text(encoding="utf-8")
                )
                solver_summary = json.loads(
                    (thermo_output / "solver_diagnostics.json").read_text(encoding="utf-8")
                )
                entropy_summary = json.loads(
                    (thermo_output / "entropy_production_rate_timeseries.json").read_text(
                        encoding="utf-8"
                    )
                )
                with (thermo_output / "entropy_production_rate_timeseries.csv").open(
                    newline="", encoding="utf-8"
                ) as handle:
                    entropy_rows = list(csv.DictReader(handle))

                {
                    "thermodynamic_summary": thermodynamic_summary,
                    "conservation_status_counts": conservation_summary["status_counts"],
                    "solver_status": solver_summary["status"],
                    "entropy_guardrail": entropy_rows[0]["guardrails"],
                    "entropy_row_count": entropy_summary["row_count"],
                }
                """
            ),
            _markdown(
                """
                ## 6. Verify the advanced output bundle

                The manifest closes the loop from configuration to artifacts. A
                downstream analysis can discover the complete bundle without scraping
                notebook output.
                """
            ),
            _code(
                """
                manifest = json.loads(
                    (thermo_output / "output_manifest.json").read_text(encoding="utf-8")
                )
                required = {
                    "configured_metadata.json",
                    "conservation_diagnostics.csv",
                    "derived_quantities.csv",
                    "entropy_production_rate_timeseries.csv",
                    "process_rates.csv",
                    "solver_diagnostics.csv",
                    "thermodynamic_summary.csv",
                    "validation_report.json",
                }
                missing = sorted(required - set(manifest["files"]))
                assert not missing, missing
                assert thermodynamic_summary["has_solver_time_enforcement"] is True
                assert entropy_summary["has_dynamic_delta_gibbs"] is False

                {
                    "artifact_count": len(manifest["files"]),
                    "missing_required_artifacts": missing,
                    "validation": thermo_result.validation_report(),
                }
                """
            ),
            _markdown(
                """
                ## Capability boundary

                This notebook exercised deep implemented contracts, but it intentionally
                did not:

                - promote a source proposal without an explicit curator decision;
                - present artificial inhibition or thermodynamic inputs as biology;
                - claim empirical validation, calibration, or prediction accuracy;
                - infer nonideal activities, reverse rates, coupled-network fluxes,
                  intracellular metabolism, or whole-fungus physiology.

                Those omissions are scientific controls, not missing notebook polish.
                """
            ),
        ],
        prefix="advanced",
    )


NOTEBOOKS = {
    "20_zero_to_complete_virtual_experiment.ipynb": zero_to_results_notebook,
    "21_advanced_capabilities.ipynb": advanced_capabilities_notebook,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if generated notebooks differ.")
    args = parser.parse_args()
    failures: list[str] = []
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    for filename, factory in NOTEBOOKS.items():
        path = NOTEBOOK_DIR / filename
        rendered = nbformat.writes(factory())
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != rendered:
                failures.append(filename)
        else:
            path.write_text(rendered, encoding="utf-8")
    if failures:
        print("Generated release notebooks are stale: " + ", ".join(failures))
        return 1
    if args.check:
        print("Generated release notebooks are current.")
    else:
        print("Wrote " + ", ".join(NOTEBOOKS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
