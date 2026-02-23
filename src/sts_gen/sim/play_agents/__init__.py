"""Play agent implementations for headless combat simulation.

Re-exports the base class and all concrete agent implementations so
consumers can do::

    from sts_gen.sim.play_agents import PlayAgent, RandomAgent
"""

from .base import PlayAgent
from .random_agent import RandomAgent

__all__ = ["PlayAgent", "RandomAgent"]
