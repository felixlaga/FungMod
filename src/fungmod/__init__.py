"""FungMod — the canonical import namespace for the distribution.

``fungmod`` is the supported, canonical way to use this package::

    import fungmod as fm

    study = fm.virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="SABIO-RK Reaction 618 selected assay conditions",
    )

The implementation currently lives in :mod:`fungal_model`, which remains
importable for backward compatibility. ``fungmod`` re-exports the complete
public API of :mod:`fungal_model` (so the two namespaces expose the same flat
names and version), and additionally forwards submodule access. Advanced
subpackages are reachable canonically through ``fungmod``::

    from fungmod import uncertainty, calibration, transport
    import fungmod.uncertainty as u

New code should import ``fungmod``.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
from types import ModuleType

import fungal_model as _implementation
from fungal_model import *  # noqa: F401,F403

__version__ = _implementation.__version__
# Copy so downstream mutation of ``fungmod.__all__`` cannot corrupt the
# implementation module's own ``__all__``.
__all__ = list(_implementation.__all__)  # pyright: ignore[reportUnsupportedDunderAll]

_IMPL_NAME = _implementation.__name__
_PREFIX = __name__ + "."


class _SubmoduleForwarder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Map every ``fungmod.<sub...>`` import onto ``fungal_model.<sub...>``.

    Inserted at the front of ``sys.meta_path`` so it also intercepts *nested*
    submodules (e.g. ``fungmod.core.units``). Without this, the default
    path-based finder would build a nested submodule from the parent package's
    path, producing a distinct module object with, for example, its own pint
    unit registry — so ``fungmod.core.units`` and ``fungal_model.core.units``
    would not share state. Mapping every level guarantees they are the same
    object. ``fungmod`` has no real submodules of its own, so this never
    shadows one.
    """

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001, ARG002
        if not fullname.startswith(_PREFIX):
            return None
        return importlib.machinery.ModuleSpec(fullname, self)

    def create_module(self, spec):  # noqa: ANN001
        subname = spec.name[len(_PREFIX):]
        module = importlib.import_module(f"{_IMPL_NAME}.{subname}")
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):  # noqa: ANN001, ARG002
        # The module is fully initialised by the implementation package.
        return None


sys.meta_path.insert(0, _SubmoduleForwarder())


def __getattr__(name: str) -> ModuleType:
    """Forward attribute access for submodules to the implementation package."""
    try:
        module = importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    setattr(sys.modules[__name__], name, module)
    return module
