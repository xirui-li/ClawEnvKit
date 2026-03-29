"""IronClaw agent adapter.

IronClaw uses .env file for LLM configuration.
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
class IronClawAdapter(AgentAdapter):

    def name(self) -> str:
        return "ironclaw"

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            name="ironclaw",
            has_bash=True,
            has_file_io=True,
            has_http=True,
            has_browser=False,
            has_skills=True,
            has_memory=False,
            supported_models=[
                "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
                "gpt-4o", "gpt-5.2",
            ],
            skill_format="markdown",
            tool_call_style="bash",
        )

    def setup(self, workspace: str, model: str, api_key: str) -> None:
        self._workspace = workspace
        self._model = model

        env_path = Path.home() / ".ironclaw" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        env_vars = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

        env_vars["LLM_BACKEND"] = "openai_compatible"
        env_vars["LLM_BASE_URL"] = "http://127.0.0.1:9100/v1"
        env_vars["LLM_MODEL"] = model
        env_vars["LLM_API_KEY"] = api_key

        with open(env_path, "w") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")

        skill_dir = Path.home() / ".ironclaw" / "skills" / "eval-task"
        skill_dir.mkdir(parents=True, exist_ok=True)

    def run(self, prompt: str, tools: list[dict], timeout: int = 120) -> AgentResult:
        start = time.time()

        try:
            result = subprocess.run(
                ["ironclaw", "run", "--message", prompt, "--timeout", str(timeout)],
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )
            elapsed = time.time() - start
            return AgentResult(output=result.stdout, turns=1, wall_time_s=elapsed)

        except FileNotFoundError:
            return AgentResult(output="", error="ironclaw CLI not found", wall_time_s=time.time() - start)
        except subprocess.TimeoutExpired:
            return AgentResult(output="", error="Agent timed out", wall_time_s=timeout)
        except Exception as e:
            return AgentResult(output="", error=str(e), wall_time_s=time.time() - start)

    def cleanup(self) -> None:
        pass
