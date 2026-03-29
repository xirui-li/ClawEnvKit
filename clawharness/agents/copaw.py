"""CoPaw agent adapter.

CoPaw uses config.json with openai_compatible provider.
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
class CoPawAdapter(AgentAdapter):

    def name(self) -> str:
        return "copaw"

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            name="copaw",
            has_bash=True,
            has_file_io=True,
            has_http=True,
            has_browser=False,
            has_skills=True,
            has_memory=True,
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

        config_path = Path.home() / ".copaw" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config = {}
        if config_path.exists():
            config = json.load(open(config_path))

        config.setdefault("models", {}).setdefault("default", {})
        config["models"]["default"]["provider"] = "openai_compatible"
        config["models"]["default"]["base_url"] = "http://127.0.0.1:9100/v1"
        config["models"]["default"]["model"] = model
        config["models"]["default"]["api_key"] = api_key

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        skill_dir = Path.home() / ".copaw" / "skills" / "eval-task"
        skill_dir.mkdir(parents=True, exist_ok=True)

    def run(self, prompt: str, tools: list[dict], timeout: int = 120) -> AgentResult:
        start = time.time()

        try:
            result = subprocess.run(
                ["copaw", "agent", "--message", prompt, "--timeout", str(timeout)],
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )
            elapsed = time.time() - start
            return AgentResult(output=result.stdout, turns=1, wall_time_s=elapsed)

        except FileNotFoundError:
            return AgentResult(output="", error="copaw CLI not found", wall_time_s=time.time() - start)
        except subprocess.TimeoutExpired:
            return AgentResult(output="", error="Agent timed out", wall_time_s=timeout)
        except Exception as e:
            return AgentResult(output="", error=str(e), wall_time_s=time.time() - start)

    def cleanup(self) -> None:
        pass
