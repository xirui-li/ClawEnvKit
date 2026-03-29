"""NanoClaw agent adapter.

NanoClaw uses Anthropic-compatible API. To point it at our mock service,
we patch .env with ANTHROPIC_BASE_URL pointing at the proxy.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .base import AgentAdapter, AgentCapabilities, AgentResult
from .registry import register_agent


@register_agent
class NanoClawAdapter(AgentAdapter):

    def name(self) -> str:
        return "nanoclaw"

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            name="nanoclaw",
            has_bash=True,
            has_file_io=True,
            has_http=True,
            has_browser=False,
            has_skills=True,
            has_memory=True,
            supported_models=[
                "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
            ],
            skill_format="markdown",
            tool_call_style="bash",
        )

    def setup(self, workspace: str, model: str, api_key: str) -> None:
        self._workspace = workspace
        self._model = model

        # Patch NanoClaw .env to point at mock service
        env_path = Path.home() / ".nanoclaw" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        env_vars = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

        env_vars["ANTHROPIC_API_KEY"] = api_key
        env_vars["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:9100/v1"

        with open(env_path, "w") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")

        # Install skill
        skill_dir = Path.home() / ".nanoclaw" / "workspace" / "skills" / "eval-task"
        skill_dir.mkdir(parents=True, exist_ok=True)

    def run(self, prompt: str, tools: list[dict], timeout: int = 120) -> AgentResult:
        start = time.time()

        try:
            # NanoClaw uses similar CLI to OpenClaw
            result = subprocess.run(
                [
                    "nanoclaw", "agent",
                    "--local",
                    "--session-id", f"eval-{int(time.time())}",
                    "--message", prompt,
                    "--json",
                    "--timeout", str(timeout),
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 30,
                env={**os.environ, "ANTHROPIC_BASE_URL": "http://127.0.0.1:9100/v1"},
            )

            elapsed = time.time() - start

            try:
                data = json.loads(result.stdout)
                text_parts = [p["text"] for p in data.get("payloads", []) if p.get("text")]
                agent_text = "\n".join(text_parts)
                meta = data.get("meta", {}).get("agentMeta", {})
                tokens = meta.get("usage", {}).get("total", 0)
            except json.JSONDecodeError:
                agent_text = result.stdout
                tokens = 0

            return AgentResult(output=agent_text, turns=1, tokens=tokens, wall_time_s=elapsed)

        except FileNotFoundError:
            return AgentResult(output="", error="nanoclaw CLI not found", wall_time_s=time.time() - start)
        except subprocess.TimeoutExpired:
            return AgentResult(output="", error="Agent timed out", wall_time_s=timeout)
        except Exception as e:
            return AgentResult(output="", error=str(e), wall_time_s=time.time() - start)

    def cleanup(self) -> None:
        pass
