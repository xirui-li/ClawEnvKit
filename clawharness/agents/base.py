"""Base agent adapter interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentResult:
    output: str
    tool_calls: list[dict] = field(default_factory=list)
    turns: int = 0
    tokens: int = 0
    wall_time_s: float = 0.0
    error: Optional[str] = None


@dataclass
class AgentCapabilities:
    name: str
    has_bash: bool = True
    has_file_io: bool = True
    has_http: bool = True
    has_browser: bool = False
    has_skills: bool = False
    has_memory: bool = False
    supported_models: list[str] = field(default_factory=list)
    skill_format: str = "markdown"
    tool_call_style: str = "bash"


class AgentAdapter(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> AgentCapabilities: ...

    @abstractmethod
    def setup(self, workspace: str, model: str, api_key: str) -> None: ...

    @abstractmethod
    def run(self, prompt: str, tools: list[dict], timeout: int = 120) -> AgentResult: ...

    @abstractmethod
    def cleanup(self) -> None: ...

    def generate_skill_md(self, task_config: dict, api_base_url: str) -> str:
        tools = task_config.get("tools", [])
        tool_docs = ""
        for t in tools:
            tool_docs += f"\n### {t['name']}\n{t.get('description', '')}\n"
            tool_docs += f"```\ncurl -s -X {t.get('method', 'POST')} {api_base_url}{t.get('endpoint', '')} -H 'Content-Type: application/json' -d '{{...}}'\n```\n"

        return f"---\nname: eval-task\ndescription: Complete the evaluation task\n---\n\n# Task\n\n{task_config.get('prompt', '')}\n\n## API\nBase URL: {api_base_url}\n{tool_docs}"
