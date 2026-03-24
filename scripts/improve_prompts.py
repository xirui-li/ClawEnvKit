#!/usr/bin/env python3
"""Batch-improve skill prompts using LLM.

Reads skill_prompts.json, calls LLM to generate 3 natural user prompts
per skill, writes skill_prompts_v2.json.

Usage:
  python scripts/improve_prompts.py --batch-size 20 --output references/skill_prompts_v2.json
  python scripts/improve_prompts.py --dry-run  # show what would be sent, no API calls
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_api_key() -> str:
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.load(open(config_path))
        return config.get("ANTHROPIC_API_KEY") or config.get("claude") or ""
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _call_llm(prompt: str, api_key: str, model: str = "claude-sonnet-4-6") -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def improve_batch(skills: list[dict], api_key: str, model: str) -> list[dict]:
    """Improve a batch of skills by generating natural prompts."""
    # Build a single prompt for the whole batch
    batch_prompt = """You are generating natural user prompts for AI agent skills.

For each skill below, generate 3 different natural user prompts that someone would actually type to trigger this skill. The prompts should:
- Sound like real human requests (casual, specific, actionable)
- Cover different use scenarios for the same skill
- Be 1-2 sentences max
- NOT mention the skill name or that it's a "skill"

Return a JSON array with one object per skill:
[{"skill": "<name>", "prompts": ["prompt1", "prompt2", "prompt3"]}, ...]

Return ONLY the JSON array. No explanation, no markdown fences.

Skills:
"""
    for s in skills:
        batch_prompt += f"- {s['skill']} ({s['category']}): {s['description']}\n"

    response = _call_llm(batch_prompt, api_key, model)
    print(f"    Response length: {len(response)}, starts with: {response[:60]!r}", file=sys.stderr)

    # Parse response
    response = response.strip()
    if response.startswith("```json"):
        response = response[len("```json"):]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        results = json.loads(response)
    except json.JSONDecodeError:
        # Try to find JSON array in response
        start = response.find("[")
        end = response.rfind("]")
        if start != -1 and end != -1:
            try:
                results = json.loads(response[start:end+1])
            except json.JSONDecodeError:
                print(f"  WARNING: Failed to parse LLM response, skipping batch", file=sys.stderr)
                return []
        else:
            print(f"  WARNING: No JSON array in response, skipping batch", file=sys.stderr)
            return []

    return results


def main():
    parser = argparse.ArgumentParser(description="Improve skill prompts with LLM")
    parser.add_argument("--input", default="references/skill_prompts.json")
    parser.add_argument("--output", default="references/skill_prompts_v2.json")
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--limit", type=int, default=0, help="Only process first N skills (0=all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    args = parser.parse_args()

    input_path = PROJECT_ROOT / args.input
    output_path = PROJECT_ROOT / args.output

    with open(input_path) as f:
        skills = json.load(f)

    if args.limit:
        skills = skills[:args.limit]

    print(f"Processing {len(skills)} skills in batches of {args.batch_size}")

    if args.dry_run:
        print("DRY RUN — no API calls")
        for s in skills[:3]:
            print(f"  {s['skill']}: {s['description'][:60]}")
        return

    api_key = _load_api_key()
    if not api_key:
        print("ERROR: No API key found", file=sys.stderr)
        sys.exit(1)

    # Process in batches
    improved = {}
    for i in range(0, len(skills), args.batch_size):
        batch = skills[i:i + args.batch_size]
        print(f"  Batch {i // args.batch_size + 1}/{(len(skills) + args.batch_size - 1) // args.batch_size} ({len(batch)} skills)...")

        results = improve_batch(batch, api_key, args.model)

        for r in results:
            if isinstance(r, dict) and "skill" in r and "prompts" in r:
                # Match skill name — LLM may include category in parentheses
                skill_name = r["skill"].split(" (")[0].strip()
                improved[skill_name] = r["prompts"]

        # Rate limiting
        time.sleep(1)

    # Merge back into original data
    output = []
    for s in skills:
        entry = {**s}
        if s["skill"] in improved:
            entry["prompts"] = improved[s["skill"]]
            entry["user_prompt"] = improved[s["skill"]][0]  # primary prompt
        else:
            entry["prompts"] = [s["user_prompt"]]
        output.append(entry)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    improved_count = sum(1 for s in output if len(s.get("prompts", [])) > 1)
    print(f"\nDone. {improved_count}/{len(skills)} skills improved.")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
