"""Step 1 (DESIGN): Parse natural language description into GenerationSpec."""

from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .schema import DEFAULTS, SUPPORTED_DOMAINS, GenerationSpec, IntentParserResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class IntentParseError(Exception):
    """Raised when intent parsing fails after retries."""
    pass


def _load_prompt_template() -> str:
    return (PROMPTS_DIR / "intent_parse.md").read_text()


def _closest_domain(domain: str) -> str:
    """Map an unknown domain string to the closest supported domain."""
    best_match = SUPPORTED_DOMAINS[0]
    best_score = 0.0
    for supported in SUPPORTED_DOMAINS:
        score = SequenceMatcher(None, domain.lower(), supported.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = supported
    return best_match


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-len("```")]
    return text.strip()


def parse(
    description: str,
    llm_response: Optional[str] = None,
) -> IntentParserResult:
    """Parse a natural language description into a GenerationSpec.

    First call (no llm_response): returns needs_clarification with a prompt
    for the LLM to extract structured intent.

    Second call (with llm_response): parses the JSON response into a
    GenerationSpec, applying defaults and validating fields.
    """
    if llm_response is None:
        # First call: return the prompt for the LLM
        template = _load_prompt_template()
        prompt = template.replace("{description}", description)
        return IntentParserResult(
            state="needs_clarification",
            clarification_prompt=prompt,
        )

    # Second call: parse the LLM response
    cleaned = _strip_json_fences(llm_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise IntentParseError(f"LLM returned invalid JSON: {e}\nResponse: {llm_response}")

    if not isinstance(data, dict):
        raise IntentParseError(f"LLM returned non-object JSON: {type(data)}")

    # Map unknown domain to closest supported domain
    if "domain" not in data:
        raise IntentParseError("LLM response missing required 'domain' field")

    if data["domain"] not in SUPPORTED_DOMAINS:
        data["domain"] = _closest_domain(data["domain"])

    # Apply defaults for missing fields
    for key, default in DEFAULTS.items():
        if key not in data:
            data[key] = default

    # Build GenerationSpec (pydantic handles validation + task_types forcing)
    try:
        spec = GenerationSpec(**data)
    except Exception as e:
        raise IntentParseError(f"Failed to build GenerationSpec: {e}")

    return IntentParserResult(state="ready", spec=spec)
