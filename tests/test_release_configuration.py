from __future__ import annotations

from pathlib import Path

import tomllib
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_public_distribution_metadata_and_install_contract() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert project["name"] == "fungmod"
    assert project["version"] == "0.1.1"
    assert project["requires-python"] == ">=3.11"
    assert project["license"] == "MIT"
    assert project["urls"]["Documentation"] == "https://fungmod.readthedocs.io/"
    assert pyproject["tool"]["setuptools"]["include-package-data"] is False
    setup_py = (ROOT / "setup.py").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "stage_packaged_resources" in setup_py
    assert "graft data" in manifest
    assert "graft data_registry" in manifest
    assert not any(
        path.is_file() for path in (ROOT / "src" / "fungal_model" / "_resources").rglob("*")
    )
    assert (ROOT / "LICENSE").is_file()
    assert "python3 -m pip install fungmod" in readme
    assert "pip`, not npm" in readme


def test_documentation_configuration_is_strict_and_read_the_docs_ready() -> None:
    mkdocs = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    read_the_docs = yaml.safe_load((ROOT / ".readthedocs.yaml").read_text(encoding="utf-8"))

    assert mkdocs["site_url"] == "https://fungmod.readthedocs.io/"
    assert mkdocs["strict"] is True
    assert mkdocs["theme"]["name"] == "material"
    assert "api.md" in str(mkdocs["nav"])
    assert "scientific-integrity.md" in str(mkdocs["nav"])
    assert read_the_docs["version"] == 2
    assert read_the_docs["mkdocs"]["configuration"] == "mkdocs.yml"
    assert read_the_docs["mkdocs"]["fail_on_warning"] is True
    assert read_the_docs["python"]["install"][0]["extra_requirements"] == ["docs"]


def test_documentation_covers_install_examples_capabilities_and_scope() -> None:
    required_pages = (
        "index.md",
        "install.md",
        "quickstart.md",
        "notebooks.md",
        "configured-models.md",
        "capabilities.md",
        "scientific-integrity.md",
        "api.md",
        "release-notes.md",
        "concepts/virtual-experiments.md",
        "concepts/outputs.md",
    )
    combined = ""
    for relative_path in required_pages:
        path = ROOT / "docs" / relative_path
        assert path.is_file(), relative_path
        combined += path.read_text(encoding="utf-8") + "\n"

    assert "python -m pip install fungmod" in combined
    assert "20_zero_to_complete_virtual_experiment.ipynb" in combined
    assert "21_advanced_capabilities.ipynb" in combined
    assert "22_five_fungal_beta_glucosidases.ipynb" in combined
    assert "not empirical validation" in combined.lower()
    assert "whole-fungus" in combined.lower()
    assert "coupled-network" in combined.lower()


def test_release_workflow_uses_pypi_trusted_publishing() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    publish = workflow["jobs"]["publish"]
    build_steps = "\n".join(str(step) for step in workflow["jobs"]["build"]["steps"])
    steps = "\n".join(str(step) for step in publish["steps"])

    assert "scripts/check_built_distribution_resources.py dist/fungmod-*.whl" in build_steps
    assert publish["environment"]["name"] == "pypi"
    assert publish["environment"]["url"] == "https://pypi.org/p/fungmod"
    assert publish["permissions"]["id-token"] == "write"
    assert "pypa/gh-action-pypi-publish@release/v1" in steps
    assert "actions/download-artifact@v6" in steps


def test_ci_builds_docs_notebooks_and_distribution() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert {"tests", "documentation", "release-notebooks", "package"} <= set(workflow["jobs"])
    commands = "\n".join(
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job["steps"]
    )

    assert "python -m mkdocs build --strict" in commands
    assert "scripts/build_release_notebooks.py --check" in commands
    assert "20_zero_to_complete_virtual_experiment.ipynb" in commands
    assert "21_advanced_capabilities.ipynb" in commands
    assert "22_five_fungal_beta_glucosidases.ipynb" in commands
    assert "python -m build" in commands
    assert "scripts/check_built_distribution_resources.py dist/fungmod-*.whl" in commands
    assert "python -m twine check dist/*" in commands
    assert "fungmod-wheel-smoke" in commands
