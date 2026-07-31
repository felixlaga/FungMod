"""Build deterministic, researcher-facing release notebooks."""

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


def fungal_beta_glucosidase_showcase_notebook() -> nbformat.NotebookNode:
    """Return the five-source purified-enzyme comparison notebook."""

    return _notebook(
        [
            _markdown(
                """
                # Five fungal β-glucosidases on cellobiose

                This notebook models purified β-glucosidases sourced from five fungi:
                *Aspergillus fumigatus*, *Chaetomium globosum*,
                *Emericella nidulans*, *Neurospora crassa*, and
                *Penicillium brasilianum*. Every case acts on the same dissolved
                cellobiose substrate at the same explicitly configured assay
                condition and standardized enzyme dose.

                **Scope:** these are source-organism labels for purified enzymes, not
                whole-fungus simulations. The model does not represent culturing,
                fungal growth, secretion, uptake, regulation, transport, biomass,
                pathogenicity, or ecosystem behavior. It is a researcher-facing
                exploratory example, not empirical validation. This is not
                whole-fungus physiology.

                **Safety:** this is computational enzyme-kinetics work only. It does
                not provide organism handling, culture, or experimental protocols.
                """
            ),
            _markdown(
                """
                ## Evidence and implemented mechanism

                The five `kcat`, cellobiose `Km`, and glucose `Ki` parameter sets come
                from the matched 50 °C, pH 5 rows attributed to Bohlin et al. (2010)
                in the open Table 5 literature transcription:

                - [Bohlin et al. primary study](https://doi.org/10.1002/bit.22885)
                - [Teugjas and Väljamäe open comparison table](https://pmc.ncbi.nlm.nih.gov/articles/PMC3726394/#__sec17title)

                FungMod supplies the implemented generic homogeneous
                Michaelis–Menten process, a provenance-bound competitive-inhibition
                modifier, and a stoichiometric map that releases two glucose
                concentration equivalents per cellobiose consumed. The source paper
                discusses transglycosylation; this reduced model does **not** implement
                it, so the omission remains a visible limitation.

                Parameter uncertainty was not transcribed and remains unknown. The
                10 nM enzyme concentration and 10 mM starting cellobiose are explicit
                matched comparison assumptions, not values attributed to the paper.
                """
            ),
            _markdown(
                """
                ## Install and load the packaged evidence

                In a fresh Python 3.11+ environment:

                ```bash
                python -m pip install "fungmod[notebooks]"
                ```

                The evidence-backed showcase input is shipped inside the wheel, so the
                notebook works from an installed package without a repository checkout.
                """
            ),
            _code(
                """
                import copy
                import csv
                import json
                import os
                from pathlib import Path

                import matplotlib.pyplot as plt
                import numpy as np
                import yaml

                import fungmod as fm

                OUTPUT_ROOT = Path(
                    os.environ.get("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", "outputs/notebooks")
                ).resolve()
                OUTPUT = OUTPUT_ROOT / "22_five_fungal_beta_glucosidases"
                CONFIG_DIR = OUTPUT / "generated_configs"
                FIGURE_DIR = OUTPUT / "figures"
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                FIGURE_DIR.mkdir(parents=True, exist_ok=True)

                evidence_path = fm.package_data_path(
                    "data/showcases/five_fungal_beta_glucosidases.yml"
                )
                evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
                cases = evidence["cases"]
                scenario = evidence["scenario"]

                {
                    "fungmod_version": fm.__version__,
                    "evidence_path": str(evidence_path),
                    "case_count": len(cases),
                    "source_organisms": [case["source_organism"] for case in cases],
                    "ranking_allowed": scenario["ranking_allowed"],
                }
                """
            ),
            _markdown(
                """
                ## 1. Inspect the model inputs before running

                All five rows share one paper, substrate, assay context, starting
                concentrations, enzyme dose, time grid, and reduced mechanism. Only the
                three reported kinetic parameters change between cases.
                """
            ),
            _code(
                """
                input_rows = [
                    {
                        "source_organism": case["source_organism"],
                        "kcat_per_s": case["kcat"]["value"],
                        "Km_cellobiose_mM": case["km_cellobiose"]["value"],
                        "Ki_glucose_mM": case["ki_glucose"]["value"],
                        "kcat_over_Km_per_mM_s": (
                            case["kcat"]["value"] / case["km_cellobiose"]["value"]
                        ),
                        "maturity": case["maturity"],
                    }
                    for case in cases
                ]

                {
                    "assay_temperature_C": scenario["temperature"]["display_value"],
                    "assay_pH": scenario["ph"]["value"],
                    "initial_cellobiose_mM": scenario["initial_cellobiose"]["value"],
                    "enzyme_dose_nM": scenario["beta_glucosidase_concentration"]["display_value"],
                    "parameters": input_rows,
                }
                """
            ),
            _markdown(
                """
                ## 2. Build inspectable configured models

                This function only assembles human-readable configuration data. It
                defines no kinetic equation or solver. Each generated YAML file is
                archived beside its result bundle, and FungMod's public configured
                workflow owns model construction, unit checking, maturity admission,
                integration, validation, and output writing.
                """
            ),
            _code(
                """
                def configured_case(case, *, with_glucose_inhibition):
                    source = evidence["provenance"]["primary_doi"]
                    condition = (
                        "Purified-enzyme cellobiose assay at 50 degrees C and pH 5; "
                        "other temperatures, pH values, substrates, or enzyme preparations "
                        "are outside this parameter set."
                    )
                    parameter_notes = (
                        "Literature value transcribed from the open Table 5 source. "
                        "No uncertainty value was transcribed."
                    )
                    config = {
                        "kind": "model_config",
                        "name": (
                            f"{case['source_organism']} purified beta-glucosidase "
                            "on cellobiose"
                        ),
                        "mode": "exploratory",
                        "maturity": "exploratory",
                        "provenance": {
                            "source": source,
                            "measurement_method": (
                                "Reduced mechanistic scenario using literature-reported "
                                "purified-enzyme parameters."
                            ),
                            "confidence_level": "literature_reported_with_scenario_assumptions",
                            "notes": (
                                "The kinetic constants are literature reported. The enzyme "
                                "dose, starting concentrations, and reduced mechanism are "
                                "explicit FungMod showcase assumptions."
                            ),
                            "validity_range": condition,
                            "units": "not_applicable",
                        },
                        "entities": {
                            "environment": {
                                "id": "bohlin_2010_50C_pH5",
                                "loader": "environment",
                                "data": {
                                    "kind": "environment",
                                    "name": "Bohlin 2010 matched beta-glucosidase assay context",
                                    "provenance": {
                                        "source": source,
                                        "measurement_method": "reported comparative assay condition",
                                        "confidence_level": "literature_reported",
                                        "notes": (
                                            "Applicability metadata for the parameter set; "
                                            "no temperature or pH response curve is inferred."
                                        ),
                                        "validity_range": condition,
                                        "units": "not_applicable",
                                    },
                                    "conditions": {
                                        "temperature": scenario["temperature"],
                                        "ph": scenario["ph"],
                                    },
                                    "parameters": [],
                                },
                            },
                            "substrates": [
                                {
                                    "id": "cellobiose",
                                    "loader": "generic_dissolved",
                                    "data": {
                                        "kind": "substrate",
                                        "name": "Cellobiose",
                                        "substrate_type": "generic_dissolved",
                                        "chemical_class": (
                                            "beta-1,4-linked glucose disaccharide"
                                        ),
                                        "physical_state": "dissolved",
                                        "bond_types": ["beta_1_4_glycosidic"],
                                        "accessible_bonds": ["beta_1_4_glycosidic"],
                                        "required_enzyme_classes": ["beta-glucosidase"],
                                        "degradation_products": [
                                            {
                                                "name": "beta-D-glucose",
                                                "formula": "C6H12O6",
                                                "assimilable": None,
                                                "notes": (
                                                    "Product identity only; uptake and "
                                                    "metabolism are not represented."
                                                ),
                                                "source": source,
                                            }
                                        ],
                                        "completeness": "partial",
                                        "default_degradation_model": "homogeneous_dissolved",
                                        "water_activity_dependence": "unknown",
                                        "provenance": {
                                            "source": source,
                                            "measurement_method": (
                                                "substrate identity in the comparative "
                                                "purified-enzyme assay"
                                            ),
                                            "confidence_level": "literature_reported",
                                            "notes": (
                                                "Dissolved cellobiose metadata for this "
                                                "scoped enzyme-kinetics case."
                                            ),
                                            "validity_range": condition,
                                            "units": "not_applicable",
                                        },
                                        "parameters": [],
                                    },
                                }
                            ],
                            "enzymes": [
                                {
                                    "id": case["id"] + "_beta_glucosidase",
                                    "loader": "enzyme",
                                    "data": {
                                        "kind": "enzyme",
                                        "name": case["enzyme_label"],
                                        "enzyme_class": "beta-glucosidase",
                                        "target_bond_types": ["beta_1_4_glycosidic"],
                                        "target_substrate_names": ["Cellobiose"],
                                        "target_substrate_classes": [
                                            "beta-1,4-linked glucose disaccharide"
                                        ],
                                        "validity_labels": [
                                            "purified_enzyme",
                                            "literature_reported",
                                            "50C_pH5_cellobiose",
                                        ],
                                        "provenance": {
                                            "source": case["source"],
                                            "measurement_method": (
                                                "purified-enzyme comparative kinetic assay"
                                            ),
                                            "confidence_level": "literature_reported",
                                            "notes": (
                                                "Source-organism label for a purified enzyme; "
                                                "not a whole-fungus capability model."
                                            ),
                                            "validity_range": condition,
                                            "units": "not_applicable",
                                        },
                                        "catalytic_parameters": [
                                            {
                                                "name": "cellobiose turnover number",
                                                "symbol": "kcat_cellobiose",
                                                "value": case["kcat"]["value"],
                                                "units": case["kcat"]["units"],
                                                "uncertainty": None,
                                                "source": case["source"],
                                                "confidence_level": "literature_reported",
                                                "notes": parameter_notes,
                                                "measurement_method": (
                                                    "comparative purified-enzyme kinetic fit"
                                                ),
                                                "validity_range": condition,
                                            },
                                            {
                                                "name": "cellobiose Michaelis constant",
                                                "symbol": "Km_cellobiose",
                                                "value": case["km_cellobiose"]["value"],
                                                "units": case["km_cellobiose"]["units"],
                                                "uncertainty": None,
                                                "source": case["source"],
                                                "confidence_level": "literature_reported",
                                                "notes": parameter_notes,
                                                "measurement_method": (
                                                    "comparative purified-enzyme kinetic fit"
                                                ),
                                                "validity_range": condition,
                                            },
                                            {
                                                "name": "apparent glucose inhibition constant",
                                                "symbol": "Ki_glucose",
                                                "value": case["ki_glucose"]["value"],
                                                "units": case["ki_glucose"]["units"],
                                                "uncertainty": None,
                                                "source": case["source"],
                                                "confidence_level": "literature_reported",
                                                "notes": parameter_notes,
                                                "measurement_method": (
                                                    "comparative purified-enzyme apparent "
                                                    "inhibition fit"
                                                ),
                                                "validity_range": condition,
                                            },
                                        ],
                                        "adsorption_parameters": [],
                                        "parameters": [],
                                    },
                                }
                            ],
                            "product_maps": [
                                {
                                    "id": "cellobiose_to_two_glucose",
                                    "loader": "stoichiometric",
                                    "data": {
                                        "kind": "product_map",
                                        "name": "cellobiose to two glucose equivalents",
                                        "product_map_type": "stoichiometric",
                                        "maturity": "literature_stoichiometry",
                                        "provenance": {
                                            "source": source,
                                            "measurement_method": (
                                                "reaction stoichiometry for cellobiose hydrolysis"
                                            ),
                                            "confidence_level": "literature_reported",
                                            "notes": (
                                                "Water is treated as the non-limiting solvent "
                                                "and is not an explicit state."
                                            ),
                                            "validity_range": (
                                                "cellobiose hydrolysis to glucose equivalents"
                                            ),
                                            "units": "dimensionless",
                                        },
                                        "reactants": {"cellobiose_concentration": 1.0},
                                        "products": {
                                            "beta_D_glucose_concentration": 2.0
                                        },
                                        "notes": (
                                            "Two glucose concentration equivalents are "
                                            "released per cellobiose consumed."
                                        ),
                                        "parameters": [],
                                    },
                                }
                            ],
                        },
                        "parameters": [],
                        "processes": [
                            {
                                "id": "cellobiose_hydrolysis",
                                "process_type": "homogeneous_michaelis_menten",
                                "states": {
                                    "substrate": "cellobiose_concentration",
                                    "product": "beta_D_glucose_concentration",
                                    "enzyme": "beta_glucosidase_concentration",
                                },
                                "parameters": {
                                    "km": "Km_cellobiose",
                                    "kcat": "kcat_cellobiose",
                                    "rate_units": "millimole / liter / second",
                                },
                                "product_map": "cellobiose_to_two_glucose",
                                "modifiers": [
                                    {
                                        "type": "competitive_inhibition",
                                        "substrate_state": "cellobiose_concentration",
                                        "inhibitor_state": (
                                            "beta_D_glucose_concentration"
                                        ),
                                        "michaelis_constant": "Km_cellobiose",
                                        "inhibition_constant": "Ki_glucose",
                                        "primary_source": source,
                                        "maturity": (
                                            "literature_backed_software_tested"
                                        ),
                                    }
                                ],
                                "assumptions": [
                                    (
                                        "Dissolved cellobiose hydrolysis is represented "
                                        "by a homogeneous Michaelis-Menten process."
                                    ),
                                    (
                                        "Glucose product feeds back through the explicit "
                                        "competitive-inhibition modifier."
                                    ),
                                    (
                                        "Transglycosylation, enzyme inactivation, and "
                                        "whole-fungus physiology are not represented."
                                    ),
                                ],
                            }
                        ],
                        "initial_state": {
                            "states": {
                                "cellobiose_concentration": scenario[
                                    "initial_cellobiose"
                                ],
                                "beta_D_glucose_concentration": scenario[
                                    "initial_glucose"
                                ],
                                "beta_glucosidase_concentration": scenario[
                                    "beta_glucosidase_concentration"
                                ],
                            }
                        },
                        "time": {
                            "start": {
                                "value": scenario["time"]["start"],
                                "units": scenario["time"]["units"],
                            },
                            "stop": {
                                "value": scenario["time"]["stop"],
                                "units": scenario["time"]["units"],
                            },
                            "points": scenario["time"]["points"],
                        },
                        "validators": [
                            {
                                "id": "non_negative_states",
                                "validator_type": "non_negative",
                                "species": [
                                    "cellobiose_concentration",
                                    "beta_D_glucose_concentration",
                                    "beta_glucosidase_concentration",
                                ],
                            },
                            {
                                "id": "glucose_equivalent_balance",
                                "validator_type": "mass_balance",
                                "conserved_weights": {
                                    "cellobiose_concentration": 2.0,
                                    "beta_D_glucose_concentration": 1.0,
                                },
                            },
                        ],
                        "outputs": {
                            "directory": (
                                "outputs/fungal_beta_glucosidase_showcase/"
                                + case["id"]
                            ),
                            "save": [
                                "record",
                                "validation_report",
                                "standard_tables",
                            ],
                            "plots": ["state_trajectories", "process_rates"],
                        },
                    }
                    if not with_glucose_inhibition:
                        config = copy.deepcopy(config)
                        config["name"] += " without glucose inhibition counterfactual"
                        config["processes"][0]["modifiers"] = []
                        config["provenance"]["notes"] += (
                            " This counterfactual removes only the configured glucose "
                            "inhibition modifier; it is not alternate biological evidence."
                        )
                    return config

                generated_preview = configured_case(
                    cases[0], with_glucose_inhibition=True
                )
                {
                    "config_name": generated_preview["name"],
                    "mode": generated_preview["mode"],
                    "maturity": generated_preview["maturity"],
                    "process": generated_preview["processes"][0],
                    "validators": generated_preview["validators"],
                }
                """
            ),
            _markdown(
                """
                ## 3. Run five inhibited cases and five matched counterfactuals

                Each inhibited run uses its literature-reported `Ki` and lets the
                simulated glucose product feed back on the rate. Its paired
                counterfactual removes only that modifier. This isolates the modeled
                impact of glucose inhibition under the stated assumptions; it does not
                prove an experimental causal effect.
                """
            ),
            _code(
                """
                runs = {}
                config_paths = {}
                for case in cases:
                    pair = {}
                    pair_paths = {}
                    for label, enabled in (
                        ("with_glucose_inhibition", True),
                        ("without_glucose_inhibition", False),
                    ):
                        config = configured_case(
                            case, with_glucose_inhibition=enabled
                        )
                        config_path = CONFIG_DIR / f"{case['id']}__{label}.yml"
                        config_path.write_text(
                            yaml.safe_dump(config, sort_keys=False),
                            encoding="utf-8",
                        )
                        run_output = OUTPUT / label / case["id"]
                        pair[label] = fm.run_configured_model(
                            config_path,
                            output_dir=run_output,
                        )
                        pair_paths[label] = {
                            "config": config_path,
                            "output": run_output,
                        }
                    runs[case["id"]] = pair
                    config_paths[case["id"]] = pair_paths

                {
                    case["source_organism"]: {
                        label: {
                            "solver_success": bool(result.solver_metadata["success"]),
                            "validations": result.validation_report(),
                        }
                        for label, result in runs[case["id"]].items()
                    }
                    for case in cases
                }
                """
            ),
            _markdown(
                """
                ## 4. Build a conditional scenario summary

                The 50% threshold is the first saved time-grid point at or below
                5 mM cellobiose. `None` would remain explicit if a case did not cross
                it. The table is a description of these ten configured trajectories,
                not a ranking of fungi or real-world enzyme preparations.
                """
            ),
            _code(
                """
                summary_rows = []
                initial_cellobiose = float(
                    scenario["initial_cellobiose"]["value"]
                )
                for case in cases:
                    inhibited = runs[case["id"]]["with_glucose_inhibition"]
                    counterfactual = runs[case["id"]][
                        "without_glucose_inhibition"
                    ]
                    time_seconds = np.asarray(
                        inhibited.time.to("second").magnitude,
                        dtype=float,
                    )
                    substrate_mM = np.asarray(
                        inhibited.state("cellobiose_concentration").to("mM").magnitude,
                        dtype=float,
                    )
                    glucose_mM = np.asarray(
                        inhibited.state("beta_D_glucose_concentration").to("mM").magnitude,
                        dtype=float,
                    )
                    inhibited_rate = np.asarray(
                        inhibited.rate("cellobiose_hydrolysis").to("mM / second").magnitude,
                        dtype=float,
                    )
                    counterfactual_substrate = np.asarray(
                        counterfactual.state("cellobiose_concentration").to("mM").magnitude,
                        dtype=float,
                    )
                    crossing = np.flatnonzero(
                        substrate_mM <= 0.5 * initial_cellobiose
                    )
                    t50_seconds = (
                        None if crossing.size == 0 else float(time_seconds[crossing[0]])
                    )
                    conversion = 100.0 * (
                        1.0 - substrate_mM[-1] / initial_cellobiose
                    )
                    counterfactual_conversion = 100.0 * (
                        1.0 - counterfactual_substrate[-1] / initial_cellobiose
                    )
                    summary_rows.append(
                        {
                            "source_organism": case["source_organism"],
                            "substrate": "cellobiose",
                            "kcat_per_s": case["kcat"]["value"],
                            "Km_cellobiose_mM": case["km_cellobiose"]["value"],
                            "Ki_glucose_mM": case["ki_glucose"]["value"],
                            "kcat_over_Km_per_mM_s": (
                                case["kcat"]["value"]
                                / case["km_cellobiose"]["value"]
                            ),
                            "t50_grid_seconds": t50_seconds,
                            "final_cellobiose_mM": float(substrate_mM[-1]),
                            "final_glucose_mM": float(glucose_mM[-1]),
                            "final_conversion_percent": conversion,
                            "counterfactual_conversion_percent": (
                                counterfactual_conversion
                            ),
                            "modeled_inhibition_penalty_percentage_points": (
                                counterfactual_conversion - conversion
                            ),
                            "initial_rate_mM_per_s": float(inhibited_rate[0]),
                            "final_rate_mM_per_s": float(inhibited_rate[-1]),
                            "comparison_allowed": True,
                            "ranking_allowed": False,
                            "ranking_blocking_reason": scenario[
                                "ranking_blocking_reason"
                            ].strip(),
                        }
                    )

                summary_path = OUTPUT / "scenario_summary.csv"
                with summary_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=list(summary_rows[0])
                    )
                    writer.writeheader()
                    writer.writerows(summary_rows)

                summary_rows
                """
            ),
            _markdown(
                """
                ## 5. Plot substrate loss, product release, rates, and inhibition impact

                Curves show model states and rates conditional on the same dose and
                initial concentrations. The paired bars compare each inhibited
                trajectory only with its own no-inhibition counterfactual.
                """
            ),
            _code(
                """
                colors = plt.cm.viridis(np.linspace(0.08, 0.92, len(cases)))
                fig, axes = plt.subplots(2, 2, figsize=(14, 10))

                for color, case in zip(colors, cases, strict=True):
                    result = runs[case["id"]]["with_glucose_inhibition"]
                    hours = np.asarray(result.time.to("hour").magnitude, dtype=float)
                    substrate = np.asarray(
                        result.state("cellobiose_concentration").to("mM").magnitude,
                        dtype=float,
                    )
                    glucose = np.asarray(
                        result.state("beta_D_glucose_concentration").to("mM").magnitude,
                        dtype=float,
                    )
                    rate = np.asarray(
                        result.rate("cellobiose_hydrolysis").to("mM / second").magnitude,
                        dtype=float,
                    )
                    label = case["source_organism"]
                    axes[0, 0].plot(hours, substrate, color=color, label=label)
                    axes[0, 1].plot(hours, glucose, color=color, label=label)
                    axes[1, 0].plot(hours, rate, color=color, label=label)

                axes[0, 0].set(
                    title="Cellobiose remaining with dynamic glucose inhibition",
                    xlabel="Time (h)",
                    ylabel="Cellobiose (mM)",
                )
                axes[0, 1].set(
                    title="Stoichiometric glucose release",
                    xlabel="Time (h)",
                    ylabel="Glucose equivalents (mM)",
                )
                axes[1, 0].set(
                    title="Cellobiose hydrolysis rate",
                    xlabel="Time (h)",
                    ylabel="Rate (mM s$^{-1}$)",
                )

                positions = np.arange(len(cases), dtype=float)
                width = 0.36
                inhibited_values = [
                    row["final_conversion_percent"] for row in summary_rows
                ]
                counterfactual_values = [
                    row["counterfactual_conversion_percent"] for row in summary_rows
                ]
                axes[1, 1].bar(
                    positions - width / 2,
                    inhibited_values,
                    width,
                    label="Dynamic glucose inhibition",
                    color=colors,
                )
                axes[1, 1].bar(
                    positions + width / 2,
                    counterfactual_values,
                    width,
                    label="No-inhibition counterfactual",
                    facecolor="none",
                    edgecolor=colors,
                    linewidth=1.8,
                )
                axes[1, 1].set(
                    title="Final conversion after 2 h (conditional scenario)",
                    ylabel="Cellobiose conversion (%)",
                    xticks=positions,
                    xticklabels=[
                        case["source_organism"].replace(" ", "\\n", 1)
                        for case in cases
                    ],
                )
                axes[1, 1].tick_params(axis="x", labelsize=8)

                for axis in axes.flat:
                    axis.grid(alpha=0.2)
                axes[0, 0].legend(fontsize=8)
                axes[1, 1].legend(fontsize=8)
                fig.suptitle(
                    "Five purified fungal beta-glucosidases on cellobiose\\n"
                    "exploratory matched-dose model; not whole-fungus validation",
                    fontsize=14,
                )
                fig.tight_layout()
                figure_path = FIGURE_DIR / "five_fungal_beta_glucosidases.png"
                fig.savefig(figure_path, dpi=180, bbox_inches="tight")
                plt.close(fig)

                str(figure_path)
                """
            ),
            _markdown(
                """
                ## 6. Audit provenance, assumptions, conservation, and solver metadata

                A persuasive curve is not enough. The standard bundle keeps the input
                config, merged parameters, entity snapshots, assumptions, validation
                report, conservation diagnostics, solver diagnostics, rates, states,
                and manifest together. The checks below verify those artifacts across
                all ten runs.
                """
            ),
            _code(
                """
                audit_rows = []
                required_artifacts = {
                    "assumptions.json",
                    "conservation_diagnostics.csv",
                    "entity_snapshots/index.json",
                    "input_model_config.json",
                    "merged_parameters.json",
                    "output_manifest.json",
                    "process_rates.csv",
                    "solver_diagnostics.csv",
                    "state_trajectories.csv",
                    "validation_report.json",
                }
                for case in cases:
                    for label in (
                        "with_glucose_inhibition",
                        "without_glucose_inhibition",
                    ):
                        run_output = config_paths[case["id"]][label]["output"]
                        manifest = json.loads(
                            (run_output / "output_manifest.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        missing = sorted(
                            required_artifacts - set(manifest["files"])
                        )
                        conservation = json.loads(
                            (run_output / "conservation_diagnostics.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        solver = json.loads(
                            (run_output / "solver_diagnostics.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        audit_rows.append(
                            {
                                "source_organism": case["source_organism"],
                                "scenario": label,
                                "missing_required_artifacts": missing,
                                "conservation_status": conservation["rows"][0][
                                    "status"
                                ],
                                "solver_status": solver["status"],
                                "validation_passed": all(
                                    row["passed"]
                                    for row in runs[case["id"]][label].validation_report()
                                ),
                            }
                        )

                assert all(
                    not row["missing_required_artifacts"] for row in audit_rows
                )
                assert all(row["validation_passed"] for row in audit_rows)
                audit_rows
                """
            ),
            _markdown(
                """
                ## 7. Close the comparison with a machine-readable manifest

                The showcase manifest records the source, case set, scenario
                assumptions, interpretation boundary, and every generated file. It
                supplements—not replaces—the standard manifest inside each run.
                """
            ),
            _code(
                """
                generated_files = sorted(
                    path.relative_to(OUTPUT).as_posix()
                    for path in OUTPUT.rglob("*")
                    if path.is_file()
                )
                showcase_manifest = {
                    "kind": "fungmod_five_fungal_beta_glucosidases_showcase",
                    "fungmod_version": fm.__version__,
                    "primary_source": evidence["provenance"]["primary_doi"],
                    "transcription_source": evidence["provenance"][
                        "transcription_pmc"
                    ],
                    "source_organisms": [
                        case["source_organism"] for case in cases
                    ],
                    "substrate": evidence["reaction"]["substrate"],
                    "scenario": scenario,
                    "scientific_scope": (
                        "Exploratory purified-enzyme trajectories under one matched "
                        "scenario; not whole-fungus modeling or empirical validation."
                    ),
                    "files": [
                        *generated_files,
                        "showcase_manifest.json",
                    ],
                }
                showcase_manifest_path = OUTPUT / "showcase_manifest.json"
                showcase_manifest_path.write_text(
                    json.dumps(showcase_manifest, indent=2, sort_keys=True) + "\\n",
                    encoding="utf-8",
                )

                {
                    "showcase_manifest": str(showcase_manifest_path),
                    "file_count": len(showcase_manifest["files"]),
                    "summary": str(summary_path),
                    "figure": str(figure_path),
                }
                """
            ),
            _markdown(
                """
                ## Interpretation

                The trajectories expose a real mechanistic tension in the supplied
                parameters: turnover, substrate affinity, and glucose inhibition all
                shape the conditional time course. The no-inhibition pairs show how
                dynamic product feedback changes each reduced model.

                Do **not** convert this notebook into a league table of fungi. The
                values describe purified enzymes under one reported assay context,
                while the time courses additionally depend on a standardized,
                non-literature enzyme dose and an intentionally reduced mechanism.
                No empirical time-course data, parameter uncertainties, preparation
                effects, model discrepancy, or whole-organism processes were compared.

                ## Capability boundary

                This notebook adds no organism-specific branch to the FungMod engine.
                All cases use the same generic configured process, modifier,
                stoichiometry, solver, validators, and output contracts. It does not
                claim calibration, prediction accuracy, optimality, transglycosylation,
                fungal physiology, cellulose surface degradation, or arbitrary
                fungus–substrate coverage.
                """
            ),
        ],
        prefix="fungal-bg",
    )


NOTEBOOKS = {
    "20_zero_to_complete_virtual_experiment.ipynb": zero_to_results_notebook,
    "21_advanced_capabilities.ipynb": advanced_capabilities_notebook,
    "22_five_fungal_beta_glucosidases.ipynb": fungal_beta_glucosidase_showcase_notebook,
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
