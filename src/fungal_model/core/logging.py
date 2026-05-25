"""Simulation logging interfaces.

The name of this module follows the project structure. It intentionally keeps
only thin exports to avoid competing with Python's standard ``logging`` module.
"""

from .simulation import SimulationRecord

__all__ = ["SimulationRecord"]

