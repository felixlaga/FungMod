"""The paper's tables are generated from the recorded results and the committed copies match them."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from fungal_model.research import paper_tables
from fungal_model.research.gelain_culture import CultureBenchmarkError

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / paper_tables.PAPER_TABLES_DIR


def test_committed_tables_and_manifest_match_the_recorded_results() -> None:
    assert paper_tables.check_tables(ROOT) == []


def test_regenerating_the_tables_elsewhere_is_byte_identical(tmp_path: Path) -> None:
    manifest = paper_tables.write_tables(ROOT, tmp_path)
    for name, entry in manifest["tables"].items():
        assert (tmp_path / entry["file"]).read_bytes() == (TABLES / entry["file"]).read_bytes(), name
        assert (tmp_path / entry["latex_file"]).read_bytes() == (TABLES / entry["latex_file"]).read_bytes(), name
    assert json.loads((tmp_path / paper_tables.MANIFEST_NAME).read_text(encoding="utf-8")) == json.loads(
        (TABLES / paper_tables.MANIFEST_NAME).read_text(encoding="utf-8")
    )


def test_manifest_digests_name_the_files_on_disk() -> None:
    manifest = json.loads((TABLES / paper_tables.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert set(manifest["tables"]) == {builder(ROOT).name for builder in paper_tables.TABLE_BUILDERS}
    for entry in manifest["tables"].values():
        assert entry["sources"], entry["file"]
        for source, digest in entry["sources"].items():
            assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == digest, source


def test_every_table_is_included_and_referenced_by_the_manuscript() -> None:
    text = (ROOT / "paper" / "paper.tex").read_text(encoding="utf-8")
    manifest = json.loads((TABLES / paper_tables.MANIFEST_NAME).read_text(encoding="utf-8"))
    for name, entry in manifest["tables"].items():
        assert entry["latex_file"] == f"{name}.tex"
        assert f"\\input{{tables/{name}}}" in text, name
        assert f"\\ref{{tab:{name}}}" in text, name
    assert "paper.md" not in text


def test_latex_inline_escapes_specials_and_sets_code_spans_in_typewriter() -> None:
    assert paper_tables.latex_inline("a_b & 5% `K_ind` <x> #1 {y} $z ~ ^") == (
        "a\\_\\allowbreak{}b \\& 5\\% \\texttt{K\\_\\allowbreak{}ind} \\textless{}x\\textgreater{} \\#1 \\{y\\} \\$z"
        " \\textasciitilde{} \\textasciicircum{}"
    )
    assert paper_tables.latex_escape("back\\slash") == "back\\textbackslash{}slash"


def test_latex_tables_are_captioned_full_width_floats_with_one_tabularx_per_pipe_table() -> None:
    for table in paper_tables.build_tables(ROOT):
        latex = table.rendered_latex()
        assert latex.startswith(paper_tables.LATEX_MARKER + "\n\\begin{table}[tbp]\n")
        assert f"\\label{{tab:{table.name}}}" in latex and "\\caption{" in latex
        pipe_tables = sum(1 for line in table.markdown.splitlines() if line.startswith("| ---"))
        assert latex.count("\\begin{tabularx}{\\textwidth}{") == pipe_tables >= 1
        assert latex.count("\\toprule") == latex.count("\\bottomrule") == pipe_tables
        assert "\\hsize\\raggedright\\arraybackslash}X" in latex
        for spec in re.findall(r"\\begin\{tabularx\}\{\\textwidth\}\{(.*)\}", latex):
            factors = [float(value) for value in re.findall(r"\\hsize=([0-9.]+)\\hsize", spec)]
            assert len(factors) == spec.count("X") >= 1 and abs(sum(factors) - len(factors)) < 1e-9
        assert "`" not in latex and "<!--" not in latex
    cross = paper_tables.cross_solver_table(ROOT).rendered_latex()
    assert "Outcome & \\texttt{reproduced} \\\\" in cross and "\\texttt{K\\_\\allowbreak{}ind}" in cross
    assert "\\par\\medskip" in cross  # two tabulars in one float
    holdouts = paper_tables.joint_benchmark_table(ROOT).rendered_latex()
    assert "hydrolysis\\_\\allowbreak{}retained" in holdouts and "33 of 33" in holdouts


def test_key_numbers_agree_with_the_tables_they_summarise() -> None:
    manifest = json.loads((TABLES / paper_tables.MANIFEST_NAME).read_text(encoding="utf-8"))
    stage_a = manifest["tables"]["table_3_criticism_stage_a"]["key_numbers"]
    assert stage_a["models"]["M2_soluble_product_pool"]["primary"]["screen_passed"] is True
    assert stage_a["models"]["M1_induction_state"]["primary"]["screen_passed"] is False
    cross = manifest["tables"]["table_5_cross_solver"]["key_numbers"]
    assert cross["outcome"] == "reproduced" and cross["optimum_relative_difference"] <= 1e-3
    bayes = manifest["tables"]["table_2_identifiability"]["key_numbers"]
    assert bayes["converged"] is True and bayes["identified_count"] == 5
    stage_b = manifest["tables"]["table_4_criticism_stage_b"]["key_numbers"]
    assert stage_b["M2_soluble_product_pool"]["outcome"] == "improves fit but unidentified (R1, not R3)"
    joint = manifest["tables"]["table_1_joint_holdouts"]["key_numbers"]
    assert joint["validated"] is False and joint["folds_numerically_checked"] == joint["folds"]
    text = (TABLES / "table_5_cross_solver.md").read_text(encoding="utf-8")
    assert "| Outcome | `reproduced` |" in text


def test_table_builders_refuse_missing_results(tmp_path: Path) -> None:
    with pytest.raises(CultureBenchmarkError, match="missing"):
        paper_tables.joint_benchmark_table(tmp_path)
    with pytest.raises(CultureBenchmarkError):
        paper_tables.criticism_stage_b_table(tmp_path)


def test_check_tables_reports_a_tampered_table(tmp_path: Path) -> None:
    paper_tables.write_tables(ROOT, tmp_path)
    assert paper_tables.check_tables(ROOT, tmp_path) == []
    target = tmp_path / "table_5_cross_solver.md"
    target.write_text(target.read_text(encoding="utf-8").replace("reproduced", "edited"), encoding="utf-8")
    problems = paper_tables.check_tables(ROOT, tmp_path)
    assert len(problems) == 1 and "table_5_cross_solver.md" in problems[0]
    latex = tmp_path / "table_2_identifiability.tex"
    latex.write_text(latex.read_text(encoding="utf-8").replace("identified", "edited", 1), encoding="utf-8")
    problems = paper_tables.check_tables(ROOT, tmp_path)
    assert len(problems) == 2 and any("table_2_identifiability.tex differs from the LaTeX table" in problem for problem in problems)
    latex.unlink()
    assert any("table_2_identifiability.tex is missing" in problem for problem in paper_tables.check_tables(ROOT, tmp_path))
    (tmp_path / paper_tables.MANIFEST_NAME).unlink()
    assert any("manifest.json is missing" in problem for problem in paper_tables.check_tables(ROOT, tmp_path))


def test_generated_tables_carry_the_generator_marker() -> None:
    markdown = sorted(TABLES.glob("*.md"))
    latex = sorted(TABLES.glob("*.tex"))
    assert len(markdown) == len(latex) == len(paper_tables.TABLE_BUILDERS)
    for path in markdown:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert re.match(r"<!-- generated by scripts/reproduce_paper.py tables; do not edit -->", first), path
    for path in latex:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first == paper_tables.LATEX_MARKER, path
