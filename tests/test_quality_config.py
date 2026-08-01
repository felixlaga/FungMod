from __future__ import annotations

from pathlib import Path

import tomllib
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_dev_quality_tools_are_declared() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]

    assert any(dependency.startswith("ruff") for dependency in dev_dependencies)
    assert any(dependency.startswith("pyright") for dependency in dev_dependencies)
    assert any(dependency.startswith("pytest-cov") for dependency in dev_dependencies)


def test_quality_tool_configs_exist() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pyright = yaml.safe_load((ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))

    assert pyproject["tool"]["ruff"]["src"] == ["src", "tests"]
    assert "F" in pyproject["tool"]["ruff"]["lint"]["select"]
    assert pyproject["tool"]["coverage"]["run"]["source"] == ["fungal_model"]
    assert pyproject["tool"]["coverage"]["report"]["fail_under"] >= 80
    assert pyright["include"] == ["src/fungal_model", "src/fungmod"]
    assert pyright["typeCheckingMode"] == "basic"
    assert pyright["reportArgumentType"] is True
    assert pyright["reportAssignmentType"] is True
    assert pyright["reportAttributeAccessIssue"] is True
    assert pyright["reportCallIssue"] is True
    assert pyright["reportGeneralTypeIssues"] is True
    assert pyright["reportInvalidTypeForm"] is True
    assert pyright["reportOperatorIssue"] is True
    assert pyright["reportOptionalOperand"] is True
    assert pyright["reportReturnType"] is True
    assert pyright["reportOptionalMemberAccess"] is True

    debt_register = (ROOT / "ARCHITECTURE_DEBT.md").read_text(encoding="utf-8")
    assert "FD-005 Pyright optional-value baseline" in debt_register
    assert "Status: resolved in PR-41" in debt_register
    assert "FD-007 Wheel-packaged resource mirror" in debt_register
    assert "Status: resolved on 2026-08-01" in debt_register


def test_ci_runs_lint_typecheck_and_coverage() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    commands = "\n".join(
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job["steps"]
    )

    assert "python -m ruff check src tests" in commands
    assert "python -m pyright" in commands
    assert "python -m pytest --cov=fungal_model" in commands
    assert "--cov-report=xml" in commands


def test_branch_protection_policy_documents_quality_gates() -> None:
    policy = (ROOT / ".github" / "BRANCH_PROTECTION.md").read_text(encoding="utf-8")

    assert "require pull requests before merging" in policy
    assert "`CI / tests`" in policy
    assert "python -m ruff check src tests" in policy
    assert "python -m pyright" in policy
    assert "python -m pytest --cov=fungal_model" in policy
    assert "require branches to be up to date before merging" in policy
    assert "block force pushes" in policy
    assert "block direct bypass" in policy


def test_readme_states_ci_is_required_before_merging() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "CI is required before merging" in readme
    assert "passing CI" in readme
    assert "up-to-date branches" in readme
    assert "no force pushes" in readme
    assert "no unaudited direct bypass" in readme
