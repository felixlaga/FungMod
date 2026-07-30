"""Convenience import namespace for the FungMod distribution.

The implementation namespace remains :mod:`fungal_model` for backward
compatibility. New users may install ``fungmod`` and import either namespace.
"""

import fungal_model as _implementation
from fungal_model import *  # noqa: F401,F403

__version__ = _implementation.__version__
__all__ = _implementation.__all__  # pyright: ignore[reportUnsupportedDunderAll]
