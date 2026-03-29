"""Agent adapters for different claw-like agents.

Supported agents:
  openclaw, nanoclaw, ironclaw, copaw,
  picoclaw, zeroclaw, nemoclaw, hermes

Each adapter wraps a specific agent's CLI/config to provide
a uniform interface for evaluation.
"""

from .base import AgentAdapter, AgentResult, AgentCapabilities
from .registry import get_agent, list_agents, register_agent

# Import all adapters (triggers @register_agent)
from . import openclaw
from . import nanoclaw
from . import ironclaw
from . import copaw
from . import generic  # picoclaw, zeroclaw, nemoclaw, hermes
