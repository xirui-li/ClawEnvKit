"""Generic adapters for PicoClaw, ZeroClaw, NemoClaw, Hermes.

These follow the same pattern — patch config, restart, run CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .base import AgentAdapter, AgentCapabilities, AgentResult
from .registry import register_agent


def _make_generic_adapter(
    agent_name: str,
    config_path_fn,
    patch_config_fn,
    restart_cmd: list[str],
    run_cmd_fn,
    supported_models: list[str],
    has_browser: bool = False,
    has_memory: bool = False,
):
    """Factory for generic claw agent adapters."""

    @register_agent
    class GenericAdapter(AgentAdapter):
        def name(self) -> str:
            return agent_name

        def capabilities(self) -> AgentCapabilities:
            return AgentCapabilities(
                name=agent_name,
                has_bash=True,
                has_file_io=True,
                has_http=True,
                has_browser=has_browser,
                has_skills=True,
                has_memory=has_memory,
                supported_models=supported_models,
                skill_format="markdown",
                tool_call_style="bash",
            )

        def setup(self, workspace: str, model: str, api_key: str) -> None:
            self._workspace = workspace
            self._model = model
            config_path = config_path_fn()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            patch_config_fn(config_path, model, api_key)

            try:
                subprocess.run(restart_cmd, capture_output=True, timeout=30)
            except Exception:
                pass

        def run(self, prompt: str, tools: list[dict], timeout: int = 120) -> AgentResult:
            start = time.time()
            try:
                cmd = run_cmd_fn(prompt, timeout)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
                return AgentResult(output=result.stdout, turns=1, wall_time_s=time.time() - start)
            except FileNotFoundError:
                return AgentResult(output="", error=f"{agent_name} CLI not found", wall_time_s=time.time() - start)
            except subprocess.TimeoutExpired:
                return AgentResult(output="", error="Agent timed out", wall_time_s=timeout)
            except Exception as e:
                return AgentResult(output="", error=str(e), wall_time_s=time.time() - start)

        def cleanup(self) -> None:
            pass

    GenericAdapter.__name__ = f"{agent_name.title()}Adapter"
    GenericAdapter.__qualname__ = GenericAdapter.__name__
    return GenericAdapter


# --- PicoClaw ---

def _picoclaw_config_path():
    return Path.home() / ".picoclaw" / "config.json"

def _picoclaw_patch(config_path, model, api_key):
    config = json.load(open(config_path)) if config_path.exists() else {}
    model_list = config.setdefault("model_list", [])
    # Remove existing metaclaw entry
    model_list = [m for m in model_list if m.get("name") != "metaclaw"]
    model_list.append({
        "name": "metaclaw",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:9100/v1",
        "model": model,
        "api_key": api_key,
    })
    config["model_list"] = model_list
    config["default_model"] = "metaclaw"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

PicoClawAdapter = _make_generic_adapter(
    "picoclaw",
    _picoclaw_config_path,
    _picoclaw_patch,
    ["picoclaw", "gateway", "restart"],
    lambda prompt, timeout: ["picoclaw", "agent", "--message", prompt, "--timeout", str(timeout)],
    ["claude-sonnet-4-6", "claude-haiku-4-5", "gpt-4o"],
)


# --- ZeroClaw ---

def _zeroclaw_config_path():
    return Path.home() / ".zeroclaw" / "config.toml"

def _zeroclaw_patch(config_path, model, api_key):
    lines = []
    if config_path.exists():
        lines = config_path.read_text().splitlines()
    # Simple TOML patching
    new_lines = [l for l in lines if not any(k in l for k in ["provider", "base_url", "model", "api_key"])]
    new_lines.extend([
        'provider = "openai-compatible"',
        f'base_url = "http://127.0.0.1:9100/v1"',
        f'model = "{model}"',
        f'api_key = "{api_key}"',
    ])
    config_path.write_text("\n".join(new_lines))

ZeroClawAdapter = _make_generic_adapter(
    "zeroclaw",
    _zeroclaw_config_path,
    _zeroclaw_patch,
    ["zeroclaw", "service", "restart"],
    lambda prompt, timeout: ["zeroclaw", "run", "--message", prompt, "--timeout", str(timeout)],
    ["claude-sonnet-4-6", "gpt-4o"],
)


# --- NemoClaw ---

def _nemoclaw_config_path():
    return Path.home() / ".nemoclaw" / "config.json"

def _nemoclaw_patch(config_path, model, api_key):
    config = json.load(open(config_path)) if config_path.exists() else {}
    config["providers"] = config.get("providers", {})
    config["providers"]["metaclaw"] = {
        "type": "openai_compatible",
        "base_url": "http://127.0.0.1:9100/v1",
        "model": model,
        "api_key": api_key,
    }
    config["active_provider"] = "metaclaw"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

NemoClawAdapter = _make_generic_adapter(
    "nemoclaw",
    _nemoclaw_config_path,
    _nemoclaw_patch,
    ["openshell", "inference", "set", "metaclaw"],
    lambda prompt, timeout: ["nemoclaw", "agent", "--message", prompt, "--timeout", str(timeout)],
    ["claude-sonnet-4-6", "gpt-4o", "gemini-3-pro"],
)


# --- Hermes ---

def _hermes_config_path():
    return Path.home() / ".hermes" / "config.yaml"

def _hermes_patch(config_path, model, api_key):
    import yaml
    config = yaml.safe_load(open(config_path)) if config_path.exists() else {}
    providers = config.setdefault("custom_providers", {})
    providers["metaclaw"] = {
        "type": "openai_compatible",
        "base_url": "http://127.0.0.1:9100/v1",
        "model": model,
        "api_key": api_key,
    }
    config["model"] = {"provider": "custom:metaclaw"}
    with open(config_path, "w") as f:
        yaml.dump(config, f)

HermesAdapter = _make_generic_adapter(
    "hermes",
    _hermes_config_path,
    _hermes_patch,
    ["hermes", "gateway", "restart"],
    lambda prompt, timeout: ["hermes", "agent", "--message", prompt, "--timeout", str(timeout)],
    ["claude-sonnet-4-6", "gpt-4o"],
)
