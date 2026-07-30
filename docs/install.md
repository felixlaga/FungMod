# Install

## Requirements

- Python 3.11, 3.12, or 3.13
- pip or another standards-compatible Python package installer

FungMod is a Python package, so installation uses `pip`, not npm.

## Install the release

Create and activate an isolated environment:

=== "macOS and Linux"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install fungmod
    ```

=== "Windows PowerShell"

    ```powershell
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install fungmod
    ```

Verify the installation from a directory that is not a repository checkout:

```bash
python -c "import fungmod; print(fungmod.__version__)"
```

Both import namespaces are supported:

```python
import fungmod                 # concise distribution namespace
import fungal_model           # original implementation namespace

assert fungmod.__version__ == fungal_model.__version__
```

## Notebook support

Install Jupyter and notebook execution tools with:

```bash
python -m pip install "fungmod[notebooks]"
```

## Development installation

From a clone:

```bash
git clone https://github.com/felixlaga/FungMod.git
cd FungMod
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,docs,notebooks]"
```

Run the gates:

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
MPLCONFIGDIR=/tmp/fungmod-mpl python -m pytest --cov=fungal_model
python -m mkdocs build --strict
python -m build
python -m twine check dist/*
```

## Packaged data

The wheel includes an immutable registry snapshot, frozen source evidence, and
example configurations. Public helpers return their installed locations:

```python
import fungmod as fm

registry_index = fm.default_registry_path()
example_config = fm.example_data_path("model_configs/toy_homogeneous_ab.yml")
```

Copy an asset before editing it. Curation and registry-promotion workflows must
target an explicit writable registry, not the package installation directory.
