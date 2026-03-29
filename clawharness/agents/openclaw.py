"""OpenClaw agent adapter."""

from __future__ import annotations
import json, os, subprocess, time
from .base import AgentAdapter, AgentCapabilities, AgentResult
from .registry import register_agent


@register_agent
class OpenClawAdapter(AgentAdapter):
    def name(self): return "openclaw"

    def capabilities(self):
        return AgentCapabilities(
            name="openclaw", has_bash=True, has_file_io=True, has_http=True,
            has_browser=True, has_skills=True, has_memory=True,
            supported_models=["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5", "gpt-4o", "gpt-5.2", "gemini-3-pro"],
            skill_format="markdown", tool_call_style="bash",
        )

    def setup(self, workspace, model, api_key):
        self._workspace = workspace
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.makedirs(os.path.join(workspace, ".openclaw", "workspace", "skills"), exist_ok=True)
        subprocess.run(["openclaw", "setup", "--non-interactive"], capture_output=True, timeout=30)

    def run(self, prompt, tools, timeout=120):
        start = time.time()
        try:
            result = subprocess.run(
                ["openclaw", "agent", "--local", "--session-id", f"eval-{int(time.time())}", "--message", prompt, "--json", "--timeout", str(timeout)],
                capture_output=True, text=True, timeout=timeout + 30,
            )
            elapsed = time.time() - start
            try:
                data = json.loads(result.stdout)
                text = "\n".join(p["text"] for p in data.get("payloads", []) if p.get("text"))
                tokens = data.get("meta", {}).get("agentMeta", {}).get("usage", {}).get("total", 0)
            except json.JSONDecodeError:
                text, tokens = result.stdout, 0
            return AgentResult(output=text, turns=1, tokens=tokens, wall_time_s=elapsed)
        except FileNotFoundError:
            return AgentResult(output="", error="openclaw not found", wall_time_s=time.time() - start)
        except subprocess.TimeoutExpired:
            return AgentResult(output="", error="timed out", wall_time_s=timeout)

    def cleanup(self): pass
