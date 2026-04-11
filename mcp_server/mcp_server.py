#!/usr/bin/env python3
"""Minimal MCP server in Python — no external dependencies.

Implements just enough of the Model Context Protocol (JSON-RPC 2.0 over stdio)
to expose mock-service endpoints as tools for any MCP-compatible agent.

Usage:
    EVAL_TOOLS_FILE=/tmp/eval-tools.json python3 mcp_server.py
"""

import json
import os
import sys
import urllib.request

TOOLS_FILE = os.environ.get("EVAL_TOOLS_FILE", "/tmp/eval-tools.json")


def log(msg):
    print(f"[mcp-py] {msg}", file=sys.stderr, flush=True)


def read_tools():
    if not os.path.exists(TOOLS_FILE):
        log(f"No tools file at {TOOLS_FILE}")
        return []
    with open(TOOLS_FILE) as f:
        return json.load(f)


def tool_to_mcp_schema(t):
    """Convert eval-tools.json entry to MCP tool schema."""
    props = {}
    for key, schema in (t.get("parameters") or {}).items():
        # Determine effective type
        effective_type = schema.get("type", "string")
        if schema.get("anyOf"):
            non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
            if non_null:
                effective_type = non_null[0].get("type", "string")
        props[key] = {"type": effective_type, "description": schema.get("title", key)}
        if "default" in schema and schema["default"] is not None:
            props[key]["default"] = schema["default"]

    return {
        "name": t["name"],
        "description": t.get("description", t["name"]),
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": t.get("required", []),
        },
    }


def call_mock_service(endpoint, method, port, params):
    """POST to mock service and return result."""
    url = f"http://127.0.0.1:{port}{endpoint}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
            method=method.upper(),
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def handle_request(req, tools, tool_map):
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "clawenvkit", "version": "0.1.0"},
            },
        }

    elif method == "notifications/initialized":
        return None  # No response for notifications

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [tool_to_mcp_schema(t) for t in tools]},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        tool_def = tool_map.get(tool_name)

        if not tool_def:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        result = call_mock_service(
            tool_def["endpoint"],
            tool_def.get("method", "POST"),
            tool_def.get("port", 9100),
            arguments,
        )
        log(f"Tool {tool_name}: {json.dumps(result)[:200]}")

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            },
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    elif method.startswith("notifications/"):
        return None  # Ignore notifications

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def send_response(resp, use_content_length=False):
    """Send JSON-RPC response. Auto-detects framing from client."""
    resp_json = json.dumps(resp)
    if use_content_length:
        sys.stdout.write(f"Content-Length: {len(resp_json)}\r\n\r\n{resp_json}")
    else:
        # Newline-delimited JSON (NDJSON) — simpler, works with more clients
        sys.stdout.write(resp_json + "\n")
    sys.stdout.flush()


def main():
    tools = read_tools()
    tool_map = {t["name"]: t for t in tools}
    log(f"Loaded {len(tools)} tools")

    # Auto-detect framing: if client sends Content-Length headers, use them back
    use_content_length = False
    buffer = ""

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            # Handle Content-Length header (Claude Code / official MCP SDK)
            if line.startswith("Content-Length:"):
                use_content_length = True
                content_length = int(line.split(":")[1].strip())
                # Read until empty line (end of headers)
                while True:
                    header = sys.stdin.readline().strip()
                    if not header:
                        break
                body = sys.stdin.read(content_length)
                line = body.strip()

            if not line:
                continue

            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                buffer += line
                try:
                    req = json.loads(buffer)
                    buffer = ""
                except json.JSONDecodeError:
                    continue

            resp = handle_request(req, tools, tool_map)
            if resp is not None:
                send_response(resp, use_content_length)

        except EOFError:
            break
        except Exception as e:
            log(f"Error: {e}")
            continue

    log("Server stopped")


if __name__ == "__main__":
    main()
