"""Lightweight ReAct agent loop for evaluation inside Docker.

Reads task prompt, calls LLM for decisions, executes tool calls
against mock service, repeats until done or max turns.

This replaces the need for OpenClaw/Claude Code inside the container
for basic evaluation. Full agent harnesses can be added via
Dockerfile.openclaw etc.

Usage (inside Docker):
    python3 -m clawharness.evaluate.agent_loop
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
import yaml
from pathlib import Path


TASK_YAML = os.environ.get("TASK_YAML", "/opt/clawharness/task.yaml")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "todo")
PORT = int(os.environ.get("PORT", "9100"))
MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "15"))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def log(msg: str):
    print(f"[agent] {msg}", file=sys.stderr)


def call_llm(system: str, messages: list[dict]) -> str:
    """Call Anthropic API."""
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def call_mock_api(endpoint: str, method: str = "POST", body: dict = None) -> dict:
    """Call mock service endpoint."""
    url = f"http://localhost:{PORT}{endpoint}"
    data = json.dumps(body or {}).encode("utf-8") if method != "GET" else None

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def build_system_prompt(config: dict) -> str:
    """Build system prompt with task info and tool docs."""
    tools = config.get("tools", [])

    tool_docs = ""
    for t in tools:
        tool_docs += f"\n### {t['name']}\n"
        tool_docs += f"  {t.get('description', '')}\n"
        tool_docs += f"  {t.get('method', 'POST')} http://localhost:{PORT}{t.get('endpoint', '')}\n"

    return f"""You are an AI agent completing a task by calling API tools.

## Available Tools
{tool_docs}

## How to call a tool
Respond with a JSON object:
{{"tool": "<tool_name>", "params": {{...}}}}

## How to finish
When done, respond with:
{{"done": true, "summary": "<what you accomplished>"}}

## Rules
- Call ONE tool at a time
- Wait for the result before calling the next tool
- Use only the tools listed above
- All API calls go to http://localhost:{PORT}
- Do NOT make up endpoints that aren't listed
"""


def run_agent(config: dict) -> tuple[str, list[dict], int, int]:
    """Run the ReAct agent loop.

    Returns: (agent_output, tool_calls_made, total_turns, total_tokens)
    """
    prompt = config.get("prompt", "")
    tools = config.get("tools", [])
    system = build_system_prompt(config)

    messages = [{"role": "user", "content": f"Task: {prompt}"}]
    agent_output = ""
    tool_calls = []
    total_tokens = 0

    for turn in range(MAX_TURNS):
        log(f"Turn {turn + 1}/{MAX_TURNS}")

        try:
            response_text = call_llm(system, messages)
        except Exception as e:
            log(f"  LLM error: {e}")
            break

        log(f"  LLM: {response_text[:150]}")
        messages.append({"role": "assistant", "content": response_text})

        # Try to parse as JSON action — handle nested JSON
        import re
        action = None

        # Strategy 1: whole response is JSON
        stripped = response_text.strip()
        if stripped.startswith("{"):
            try:
                action = json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # Strategy 2: find JSON block (greedy, handles nested braces)
        if action is None:
            depth = 0
            start = -1
            for i, ch in enumerate(response_text):
                if ch == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and start >= 0:
                        try:
                            action = json.loads(response_text[start:i+1])
                            break
                        except json.JSONDecodeError:
                            start = -1

        if action is None:
            agent_output += response_text + "\n"
            break

        # Check if done
        if action.get("done"):
            summary = action.get("summary", "")
            agent_output += summary + "\n"
            log(f"  Done: {summary[:100]}")
            break

        # Execute tool call
        tool_name = action.get("tool", "")
        params = action.get("params", {})

        tool_cfg = next((t for t in tools if t["name"] == tool_name), None)
        if not tool_cfg:
            result_text = f"Error: unknown tool '{tool_name}'. Available: {[t['name'] for t in tools]}"
            log(f"  Unknown tool: {tool_name}")
        else:
            endpoint = tool_cfg.get("endpoint", "")
            method = tool_cfg.get("method", "POST")

            # Substitute path params
            for k, v in params.items():
                endpoint = endpoint.replace(f"{{{k}}}", str(v))

            result = call_mock_api(endpoint, method, params)
            result_text = json.dumps(result, ensure_ascii=False)

            # Truncate long results
            if len(result_text) > 1000:
                result_text = result_text[:1000] + "... (truncated)"

            tool_calls.append({"tool": tool_name, "params": params})
            log(f"  {tool_name} → {result_text[:100]}")

        messages.append({"role": "user", "content": f"Tool result:\n{result_text}"})

    return agent_output, tool_calls, turn + 1, total_tokens


def main():
    if not API_KEY:
        log("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # Load task config
    config = yaml.safe_load(open(TASK_YAML))
    task_name = config.get("task_name", config.get("task_id", "unknown"))

    log(f"Task: {task_name}")
    log(f"Model: {MODEL}")
    log(f"Service: {SERVICE_NAME} on port {PORT}")
    log(f"Max turns: {MAX_TURNS}")

    start_time = time.time()

    # Run agent
    agent_output, tool_calls, turns, tokens = run_agent(config)
    elapsed = time.time() - start_time

    log(f"Completed in {turns} turns, {elapsed:.1f}s")
    log(f"Tool calls: {len(tool_calls)}")

    # Write agent output
    with open("/workspace/agent_output.txt", "w") as f:
        f.write(agent_output)

    # Write efficiency metrics
    metrics = {
        "turns": turns,
        "tokens": tokens,
        "wall_time_s": elapsed,
        "tool_calls": len(tool_calls),
        "model": MODEL,
        "agent": "react-loop",
    }
    with open("/logs/efficiency.json", "w") as f:
        json.dump(metrics, f, indent=2)

    log(f"Agent output written to /workspace/agent_output.txt")


if __name__ == "__main__":
    main()
