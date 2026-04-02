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

Given a user's natural language request, determine:
1. Which mock services are needed (from the available list)
2. What difficulty level is appropriate

## Available Services (pick 1 or more):
{services_list}

## Pre-defined Categories (shortcuts for common service combos):
{categories_list}

## Difficulty Levels:
- easy: simple single-action tasks (e.g., "list all tasks")
- medium: multi-step tasks requiring reasoning (e.g., "triage inbox and draft replies")
- hard: complex cross-service tasks with edge cases (e.g., "coordinate onboarding across 6 systems")

## User Request:
{request}

## Instructions:
- Pick the MINIMUM set of services needed to fulfill the request
- If the request implies cross-service coordination, include all relevant services
- Default to "medium" difficulty unless the request explicitly mentions easy/hard or the complexity is obvious
- If the request is vague, pick the most likely services based on keywords

Respond with JSON only:
{{"services": ["service1", "service2"], "difficulty": "medium", "reasoning": "brief explanation"}}"""


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

        # Validate services
        valid_services = [s for s in services if s in SERVICE_DEFINITIONS]
        if not valid_services:
            raise ValueError(f"No valid services parsed from: {services}")

        # Validate difficulty
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        return {
            "services": valid_services,
            "difficulty": difficulty,
            "reasoning": reasoning,
        }
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Failed to parse intent: {content[:200]}") from e
