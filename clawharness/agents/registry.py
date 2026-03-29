"""Agent registry."""

from __future__ import annotations
from typing import Type
from .base import AgentAdapter

_REGISTRY: dict[str, Type[AgentAdapter]] = {}


def register_agent(cls: Type[AgentAdapter]) -> Type[AgentAdapter]:
    instance = cls()
    _REGISTRY[instance.name()] = cls
    return cls


def get_agent(name: str) -> AgentAdapter:
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown agent '{name}'. Available: {available}")
    return _REGISTRY[name]()


def list_agents() -> list[str]:
    return sorted(_REGISTRY.keys())
