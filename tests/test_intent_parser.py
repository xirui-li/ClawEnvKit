"""Tests for scripts/core/intent_parser.py"""

import json

import pytest

from scripts.core.intent_parser import IntentParseError, parse


class TestParseFirstCall:
    def test_returns_needs_clarification(self):
        result = parse("generate 5 git tasks")
        assert result.state == "needs_clarification"
        assert result.spec is None
        assert result.clarification_prompt is not None

    def test_prompt_contains_description(self):
        result = parse("生成 10 个 CLI 文件操作任务")
        assert "生成 10 个 CLI 文件操作任务" in result.clarification_prompt

    def test_prompt_loads_template(self):
        result = parse("test")
        # Should contain content from intent_parse.md template
        assert "domain" in result.clarification_prompt
        assert "JSON" in result.clarification_prompt


class TestParseSecondCall:
    def test_valid_response(self):
        response = json.dumps({
            "domain": "git-workflow",
            "task_count": 20,
            "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
            "skill_targets": ["git merge", "git rebase"],
            "base_tools": ["git", "bash"],
            "output_dir": "~/my-tasks",
            "task_types": ["code"],
        })
        result = parse("generate git tasks", llm_response=response)
        assert result.state == "ready"
        assert result.spec.domain == "git-workflow"
        assert result.spec.task_count == 20
        assert result.spec.skill_targets == ["git merge", "git rebase"]

    def test_missing_fields_filled_with_defaults(self):
        response = json.dumps({"domain": "cli-file-ops"})
        result = parse("some tasks", llm_response=response)
        assert result.state == "ready"
        assert result.spec.task_count == 20
        assert result.spec.difficulty_distribution == {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        assert result.spec.base_tools == ["bash", "python3"]
        assert result.spec.target_agent == "metaclaw"

    def test_task_types_forced_to_code(self):
        response = json.dumps({
            "domain": "cli-file-ops",
            "task_types": ["design", "review", "test"],
        })
        result = parse("tasks", llm_response=response)
        assert result.spec.task_types == ["code"]

    def test_unknown_domain_mapped(self):
        response = json.dumps({"domain": "file-operations"})
        result = parse("file tasks", llm_response=response)
        assert result.spec.domain == "cli-file-ops"

    def test_unknown_domain_git(self):
        response = json.dumps({"domain": "git-stuff"})
        result = parse("git tasks", llm_response=response)
        assert result.spec.domain == "git-workflow"

    def test_json_with_markdown_fences(self):
        response = '```json\n{"domain": "cli-file-ops", "task_count": 5}\n```'
        result = parse("tasks", llm_response=response)
        assert result.spec.domain == "cli-file-ops"
        assert result.spec.task_count == 5

    def test_json_with_plain_fences(self):
        response = '```\n{"domain": "cli-file-ops"}\n```'
        result = parse("tasks", llm_response=response)
        assert result.spec.domain == "cli-file-ops"


class TestParseErrors:
    def test_malformed_json(self):
        with pytest.raises(IntentParseError, match="invalid JSON"):
            parse("tasks", llm_response="this is not json at all")

    def test_json_array_instead_of_object(self):
        with pytest.raises(IntentParseError, match="non-object"):
            parse("tasks", llm_response='[1, 2, 3]')

    def test_missing_domain(self):
        with pytest.raises(IntentParseError, match="missing required 'domain'"):
            parse("tasks", llm_response='{"task_count": 5}')

    def test_invalid_difficulty_keys(self):
        response = json.dumps({
            "domain": "cli-file-ops",
            "difficulty_distribution": {"super_hard": 1.0},
        })
        with pytest.raises(IntentParseError, match="Failed to build GenerationSpec"):
            parse("tasks", llm_response=response)
