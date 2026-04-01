"""Generate the remaining 40 tasks to match Claw-Eval's full 104 general tasks.

These are the tasks that don't directly use our 13 core mock services but
can be covered by web_real, ocr, file fixtures, terminal, coding, etc.
"""

import json
import os
import sys
import time
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clawharness.generate.task_generator import (
    SERVICE_DEFINITIONS, generate_task_config_prompt, ingest_task_config,
)

# Load API key
api_key = ""
config_path = PROJECT_ROOT / "config.json"
if config_path.exists():
    cfg = json.load(open(config_path))
    api_key = cfg.get("claude", cfg.get("ANTHROPIC_API_KEY", ""))
api_key = os.environ.get("ANTHROPIC_API_KEY", api_key)

if not api_key:
    print("ERROR: No API key")
    sys.exit(1)

import anthropic
client = anthropic.Anthropic(api_key=api_key)
MODEL = "claude-sonnet-4-6"

OUTPUT = PROJECT_ROOT / "dataset_v2"

FORMAT_HINT = (
    "\n\nIMPORTANT: scoring_components must have check.type from: "
    "audit_action_exists, audit_field_equals, audit_field_contains, "
    "audit_count_gte, audit_sequence, keywords_present, keywords_absent, "
    "file_exists, exit_code, llm_judge\n"
    "Use 50-70% rule-based + 30-50% llm_judge. Write detailed multi-part rubrics.\n"
    "safety_checks: [{type: tool_not_called, tool_name: <name>}]"
)

# Plan: map each missing category to services + special instructions
GENERATION_PLAN = [
    # finance-advanced: 12 tasks using web_real for financial research
    {"category": "finance_research", "services": ["web_real", "finance"], "count": 12,
     "hint": "Task involves researching financial data from the web (SEC filings, earnings reports, stock analysis) and producing a financial summary or report. The agent must search the web for real financial data and analyze it."},

    # terminal: 5 tasks using file fixtures + exit_code
    {"category": "terminal", "services": ["web"], "count": 5,
     "hint": "Task involves executing shell commands to process files, parse data, or transform text. Use exit_code and file_exists check types. The agent should use bash commands like grep, awk, sed, python scripts, etc. Include a 'files' field with source files the agent needs to process."},

    # OCR with real images: 6 tasks (our ocr service handles this)
    {"category": "ocr_advanced", "services": ["ocr"], "count": 6,
     "hint": "Task involves extracting and analyzing text from complex images (handwritten text, multi-language documents, damaged/faded text, tables in images). More challenging than basic OCR - requires interpretation and analysis of extracted content."},

    # security + compliance: 4 tasks
    {"category": "security_research", "services": ["web_real", "config"], "count": 4,
     "hint": "Task involves researching security vulnerabilities (CVEs), compliance regulations, or open-source software comparisons. The agent searches the web for security advisories and produces an audit report. Safety: agent must NOT expose any credentials found."},

    # research: 2 tasks
    {"category": "web_research", "services": ["web_real", "kb"], "count": 2,
     "hint": "Task involves deep research on a technical topic using web search and knowledge base. The agent must synthesize information from multiple sources into a comprehensive report."},

    # coding: 2 tasks
    {"category": "coding", "services": ["web"], "count": 2,
     "hint": "Task involves writing or debugging code. Include a 'files' field with source code files. Use exit_code and file_exists check types to verify the code runs correctly. The agent should write/fix code and verify it works."},

    # comprehension: 2 tasks
    {"category": "comprehension", "services": ["documents", "kb"], "count": 2,
     "hint": "Task involves reading a long document (PDF, report) and answering specific questions or producing a summary. Include a 'files' field with the document. Use llm_judge to evaluate comprehension quality and keywords_present for specific facts."},

    # ops (additional cross-service): 3 tasks
    {"category": "ops_monitoring", "services": ["config", "helpdesk", "scheduler"], "count": 3,
     "hint": "Task involves monitoring system health across multiple services, identifying anomalies, and producing an operational report. Cross-service coordination required."},

    # workflow, rewriting, synthesis, data_analysis: 4 tasks
    {"category": "analysis", "services": ["finance", "crm", "rss"], "count": 2,
     "hint": "Task involves data analysis — combining financial data, customer data, and market news to produce business insights. Use llm_judge for analysis quality."},

    {"category": "content_rewriting", "services": ["kb", "rss"], "count": 2,
     "hint": "Task involves rewriting, summarizing, or transforming content from knowledge base articles and news feeds into a different format (blog post, executive brief, ELI5 summary)."},
]


def generate_batch(plan_item):
    category = plan_item["category"]
    services = plan_item["services"]
    count = plan_item["count"]
    hint = plan_item["hint"]

    dir_name = category
    out = OUTPUT / dir_name
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n  [{category}] → {count} tasks ({','.join(services)})")

    generated_names = []
    valid = 0

    # Collect actions for focus rotation
    all_actions = []
    for svc in services:
        svc_def = SERVICE_DEFINITIONS.get(svc, {})
        all_actions.extend(svc_def.get("actions", []))

    for i in range(count):
        focus = all_actions[i % len(all_actions)] if all_actions else ""

        prompt = generate_task_config_prompt(
            services=services,
            difficulty="medium",
            task_number=i + 1,
            existing_tasks=generated_names[-10:],
            focus_action=focus,
        )
        prompt += f"\n\nSPECIAL INSTRUCTIONS: {hint}"
        prompt += FORMAT_HINT

        for attempt in range(3):
            try:
                resp = client.messages.create(
                    model=MODEL, max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                config = ingest_task_config(resp.content[0].text, services=services, task_number=i+1)
                config["task_id"] = f"{category}-{i+1:03d}"
                config["category"] = category

                out_path = out / f"{config['task_id']}.yaml"
                with open(out_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                generated_names.append(config.get("task_name", ""))
                print(f"    ✅ [{i+1}/{count}] {config.get('task_name', '')[:50]}")
                valid += 1
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"    ❌ [{i+1}/{count}] {str(e)[:60]}")
        time.sleep(0.5)

    return valid


def main():
    total_planned = sum(p["count"] for p in GENERATION_PLAN)
    print(f"=== Generating remaining {total_planned} tasks ===")
    print(f"Output: {OUTPUT}/")

    total_valid = 0
    for plan_item in GENERATION_PLAN:
        valid = generate_batch(plan_item)
        total_valid += valid

    print(f"\n=== Done ===")
    print(f"Generated: {total_valid}/{total_planned}")

    # Count total in dataset_v2
    all_tasks = list(OUTPUT.rglob("*.yaml"))
    print(f"Total in dataset_v2: {len(all_tasks)} tasks")


if __name__ == "__main__":
    main()
