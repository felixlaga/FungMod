"""FungMod: traceable models for fungal and enzyme-mediated substrate degradation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fungal-model")
except PackageNotFoundError:  # pragma: no cover - editable tree before install
    __version__ = "0.1.0"

__all__ = ["__version__"]

