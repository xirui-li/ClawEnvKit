"""Intent Parser: Natural Language → Structured Task Generator Input.

Disentangled from task generation — this module ONLY handles:
  NL request → {services: list[str], difficulty: str}

The task generator then takes this structured input to produce task.yaml.

Pipeline:
  User NL → IntentParser → {services, difficulty} → TaskGenerator → task.yaml

Usage:
    from clawharness.generate.intent_parser import parse_intent

    result = parse_intent("Test if the agent can schedule a cross-team meeting")
    # → {"services": ["calendar", "contacts", "gmail"], "difficulty": "medium"}

    result = parse_intent("Hard task about auditing API security configurations")
    # → {"services": ["config"], "difficulty": "hard"}
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from clawharness.paths import PROJECT_ROOT

# Available services for the LLM to choose from
from clawharness.generate.task_generator import SERVICE_DEFINITIONS, CROSS_SERVICE_CATEGORIES

AVAILABLE_SERVICES = list(SERVICE_DEFINITIONS.keys())
AVAILABLE_CATEGORIES = {k: v["services"] for k, v in CROSS_SERVICE_CATEGORIES.items()}

PARSE_PROMPT = """You are a task environment planner for an AI agent evaluation system.

Given a user's natural language request, extract:
1. Which mock services are needed
2. What difficulty level is appropriate
3. **Intent atoms** — the discrete things the agent must do, see, or produce

## Available Services (pick 1 or more):
{services_list}

## Pre-defined Categories (shortcuts for common service combos):
{categories_list}

## Difficulty Levels:
- easy: simple single-action tasks
- medium: multi-step tasks requiring reasoning
- hard: complex cross-service tasks with edge cases

## Intent Atoms (decompose request into verifiable units)

Each atom is one of:
- **action**: a verb the agent must perform (e.g., "schedule_meeting", "send_notification", "list_tasks")
- **object**: a noun the env must contain (e.g., "attendees", "overdue_tasks", "high_priority_items")
- **constraint**: a rule the agent must respect (e.g., "no_destructive_actions", "must_cite_sources")

Atoms must be SPECIFIC and VERIFIABLE — "do good work" is NOT an atom; "summarize_by_status" IS.

## User Request:
{request}

## Instructions:
- Pick the MINIMUM set of services needed
- If a service is missing from the list, include it with a short lowercase name (system will offer to create it)
- Decompose the request into 3-8 intent atoms — every important verb/noun/rule should be one
- Default difficulty: medium

Respond with JSON only:
{{
  "services": ["service1", "service2"],
  "difficulty": "medium",
  "atoms": [
    {{"type": "action", "name": "atom_name", "description": "what this means"}},
    {{"type": "object", "name": "atom_name", "description": "what this means"}},
    {{"type": "constraint", "name": "atom_name", "description": "what this means"}}
  ],
  "reasoning": "brief explanation"
}}"""


def _build_services_list() -> str:
    lines = []
    for name, svc in sorted(SERVICE_DEFINITIONS.items()):
        lines.append(f"  - {name}: {svc['description']}")
    return "\n".join(lines)


def _build_categories_list() -> str:
    lines = []
    for name, cat in sorted(CROSS_SERVICE_CATEGORIES.items()):
        svcs = ", ".join(cat["services"])
        lines.append(f"  - {name} → [{svcs}]: {cat['description']}")
    return "\n".join(lines)


def parse_intent(
    request: str,
    api_key: str = "",
    model: str = "claude-haiku-4-5",
) -> dict:
    """Parse natural language request into structured task generator input.

    Args:
        request: Natural language description of what to test
        api_key: (deprecated, uses detect_provider instead)
        model: (deprecated, uses detect_provider instead)

    Returns:
        {"services": ["gmail", "contacts"], "difficulty": "medium", "reasoning": "..."}
    """
    from clawharness.llm_client import call_llm

    prompt = PARSE_PROMPT.format(
        services_list=_build_services_list(),
        categories_list=_build_categories_list(),
        request=request,
    )

    content = call_llm(prompt, max_tokens=200, temperature=0)

    try:
        # Strip markdown fences: ```json ... ```
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```\w*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        result = json.loads(cleaned.strip())
        services = result.get("services", [])
        difficulty = result.get("difficulty", "medium")
        reasoning = result.get("reasoning", "")
        atoms = result.get("atoms", [])

        # Validate services — split into known and unknown
        valid_services = [s for s in services if s in SERVICE_DEFINITIONS]
        missing_services = [s for s in services if s not in SERVICE_DEFINITIONS]

        # Validate difficulty
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        # Validate atoms — keep only well-formed ones
        valid_atoms = []
        for a in atoms:
            if isinstance(a, dict) and a.get("type") in ("action", "object", "constraint") and a.get("name"):
                valid_atoms.append({
                    "type": a["type"],
                    "name": a["name"],
                    "description": a.get("description", ""),
                })

        return {
            "services": valid_services,
            "missing_services": missing_services,
            "difficulty": difficulty,
            "atoms": valid_atoms,
            "reasoning": reasoning,
        }
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Failed to parse intent: {content[:200]}") from e
