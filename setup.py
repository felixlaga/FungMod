"""Setuptools hook that stages canonical data roots into built distributions."""

from __future__ import annotations

import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scripts.stage_packaged_resources import SOURCE_DIRECTORIES, stage_packaged_resources  # noqa: E402


class build_py(_build_py):
    """Build Python modules, then stage the canonical immutable resources."""

    def run(self) -> None:
        super().run()
        stage_packaged_resources(
            ROOT,
            Path(self.build_lib) / "fungal_model" / "_resources",
        )

    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        outputs = list(super().get_outputs(include_bytecode=include_bytecode))
        destination = Path(self.build_lib) / "fungal_model" / "_resources"
        outputs.extend(
            str(destination / directory_name / path.relative_to(ROOT / directory_name))
            for directory_name in SOURCE_DIRECTORIES
            for path in sorted((ROOT / directory_name).rglob("*"))
            if path.is_file()
        )
        return outputs


setup(cmdclass={"build_py": build_py})
