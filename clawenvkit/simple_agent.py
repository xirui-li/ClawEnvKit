#!/usr/bin/env python3
"""Simple agent loop fallback for NanoClaw/NemoClaw evaluation.

Reads SKILL.md + eval-tools.json, calls Anthropic/OpenRouter API with tool_use,
executes tool calls against localhost mock service. Used when the native agent
binary is not available or requires infrastructure we can't provide in Docker.

Usage (inside Docker):
    python3 /opt/clawenvkit/clawenvkit/simple_agent.py
"""

import json
import os
import sys
import urllib.request
import yaml


def main():
    task_yaml = os.environ.get("TASK_YAML", "/opt/clawenvkit/task.yaml")
    port = os.environ.get("PORT", "9100")
    max_turns = 15

    config = yaml.safe_load(open(task_yaml))
    prompt = config.get("prompt", "")

    # Load SKILL.md context
    skill_md = ""
    for path in ["/workspace/SKILL.md", os.environ.get("SKILL_DIR", "/tmp") + "/SKILL.md"]:
        if os.path.exists(path):
            skill_md = open(path).read()
            break

    # Load tool definitions
    tools_file = "/tmp/eval-tools.json"
    eval_tools = json.load(open(tools_file)) if os.path.exists(tools_file) else []

    # Detect API key
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("MODEL", "claude-sonnet-4-6")

    if anthropic_key:
        use_anthropic = True
        api_key = anthropic_key
        model_name = model.split("/")[-1] if "/" in model else model
    elif openrouter_key:
        use_anthropic = False
        api_key = openrouter_key
        model_name = f"anthropic/{model}" if "/" not in model else model
    else:
        print("[simple_agent] ERROR: No API key", flush=True)
        sys.exit(1)

    # Build tool specs
    tool_endpoints = {}
    if use_anthropic:
        # Anthropic Messages API tool format
        api_tools = []
        for t in eval_tools:
            name = t["name"]
            tool_endpoints[name] = t["endpoint"]
            params = t.get("parameters", {})
            required = t.get("required", [])
            schema = {
                "type": "object",
                "properties": params if params else {},
                "required": required,
            }
            api_tools.append({
                "name": name,
                "description": t.get("description", name),
                "input_schema": schema,
            })
    else:
        # OpenAI-compatible format
        api_tools = []
        for t in eval_tools:
            name = t["name"]
            tool_endpoints[name] = t["endpoint"]
            params = t.get("parameters", {})
            required = t.get("required", [])
            api_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.get("description", name),
                    "parameters": {
                        "type": "object",
                        "properties": params if params else {},
                        "required": required,
                    },
                },
            })

    # System prompt with SKILL.md context
    system_prompt = "You are an AI assistant completing a task. "
    if skill_md:
        system_prompt += "You have access to API tools described below.\n\n" + skill_md

    # Agent loop
    final_output = ""

    if use_anthropic:
        final_output = _run_anthropic_loop(
            api_key, model_name, system_prompt, prompt, api_tools, tool_endpoints, port, max_turns
        )
    else:
        final_output = _run_openai_loop(
            api_key, model_name, system_prompt, prompt, api_tools, tool_endpoints, port, max_turns
        )

    print(final_output, flush=True)


def _run_anthropic_loop(api_key, model, system, prompt, tools, endpoints, port, max_turns):
    """Anthropic Messages API loop with tool_use."""
    messages = [{"role": "user", "content": prompt}]
    final_output = ""

    for turn in range(max_turns):
        body = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools

        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as e:
            print(f"[simple_agent] API error turn {turn}: {e}", flush=True)
            break

        # Extract text and tool_use blocks
        content = resp.get("content", [])
        text_parts = []
        tool_uses = []
        for block in content:
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_uses.append(block)

        if text_parts:
            final_output = "\n".join(text_parts)

        stop_reason = resp.get("stop_reason", "")
        if not tool_uses or stop_reason == "end_turn":
            break

        # Add assistant message
        messages.append({"role": "assistant", "content": content})

        # Execute tool calls and add results
        tool_results = []
        for tu in tool_uses:
            tool_name = tu["name"]
            tool_input = tu.get("input", {})
            result = _call_mock_service(endpoints.get(tool_name, ""), tool_input, port)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result,
            })
            print(f"[simple_agent] Tool: {tool_name} → {result[:200]}", flush=True)

        messages.append({"role": "user", "content": tool_results})

    return final_output


def _run_openai_loop(api_key, model, system, prompt, tools, endpoints, port, max_turns):
    """OpenAI-compatible loop (OpenRouter)."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    final_output = ""

    for turn in range(max_turns):
        body = {"model": model, "messages": messages, "max_tokens": 4096, "temperature": 0}
        if tools:
            body["tools"] = tools

        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            data = json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as e:
            print(f"[simple_agent] API error turn {turn}: {e}", flush=True)
            break

        choice = data["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            final_output = msg.get("content", "") or ""
            break

        for tc in tool_calls:
            func = tc["function"]
            tool_name = func["name"]
            try:
                tool_args = json.loads(func["arguments"]) if func.get("arguments") else {}
            except json.JSONDecodeError:
                tool_args = {}

            result = _call_mock_service(endpoints.get(tool_name, ""), tool_args, port)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
            print(f"[simple_agent] Tool: {tool_name} → {result[:200]}", flush=True)

    return final_output


def _call_mock_service(endpoint, params, port):
    """Call mock service endpoint and return result."""
    if not endpoint:
        return '{"error": "unknown endpoint"}'
    try:
        url = f"http://localhost:{port}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.read().decode()
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    main()
