"""Git transport must preserve checksum-pinned research data exactly."""
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("autocrlf", ["true", "false", "input"])
def test_git_round_trip_preserves_pinned_data_bytes(tmp_path, autocrlf):
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*arguments):
        return subprocess.run(
            ["git", *arguments], cwd=repository, check=True, capture_output=True
        ).stdout

    git("init", "--quiet")
    git("config", "core.autocrlf", autocrlf)
    git("config", "core.safecrlf", "false")
    (repository / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    # Byte fixtures exercise transport only; they are not scientific observations.
    examples = {
        "data/experiments/source_intake/example/recorded_values.csv": b"x,y\r\n1,2\r\n",
        "data/experiments/literature/example/observations.csv": b"x,y\n1,2\n",
        "data/benchmarks/example/results/residuals.csv": b"x,y\r\n1,2\r\n",
        "data/benchmarks/example/results/artifacts.json": b'{"status":"fixture"}\n',
        "data/mechanism_examples/example/kinetics.csv": b"x,y\r\n1,2\r\n",
        "data/user_mechanisms/example/states.csv": b"x,y\r\n1,2\r\n",
        "data/mechanism_sources/example/source.yml": b"source: synthetic transport fixture\r\n",
    }
    for name, contents in examples.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    git("add", "--", ".gitattributes", *examples)
    for name, contents in examples.items():
        assert git("show", ":" + name) == contents
        (repository / name).unlink()
    git("checkout-index", "--all", "--force")
    for name, contents in examples.items():
        assert (repository / name).read_bytes() == contents
