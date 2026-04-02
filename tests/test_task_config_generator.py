"""Tests for clawharness/generate/task_generator.py"""

import pytest
import yaml

from clawharness.generate.task_generator import (
    SERVICE_DEFINITIONS,
    TaskConfigGenerationError,
    generate_task_config_prompt,
    ingest_task_config,
    validate_task_config,
    resolve_services,
)


class TestServiceDefinitions:
    def test_has_gmail(self):
        assert "gmail" in SERVICE_DEFINITIONS

    def test_gmail_has_endpoints(self):
        assert len(SERVICE_DEFINITIONS["gmail"]["endpoints"]) >= 3

    def test_service_count(self):
        assert len(SERVICE_DEFINITIONS) >= 13


class TestGeneratePrompt:
    def test_contains_service_info(self):
        prompt = generate_task_config_prompt(services=["gmail"], difficulty="easy")
        assert "gmail" in prompt
        assert "/gmail/messages" in prompt
        assert "easy" in prompt

    def test_unknown_service_raises(self):
        with pytest.raises(TaskConfigGenerationError, match="Unknown service"):
            generate_task_config_prompt(services=["nonexistent"])

    def test_all_services_generate_prompt(self):
        for service in SERVICE_DEFINITIONS:
            prompt = generate_task_config_prompt(services=[service])
            assert len(prompt) > 100

    def test_cross_service_prompt(self):
        prompt = generate_task_config_prompt(services=["gmail", "contacts"])
        assert "gmail" in prompt
        assert "contacts" in prompt
        assert "CROSS-SERVICE" in prompt


class TestResolveServices:
    def test_from_services(self):
        assert resolve_services(services=["todo"]) == ["todo"]

    def test_from_service(self):
        assert resolve_services(service="todo") == ["todo"]

    def test_from_category(self):
        result = resolve_services(category="workflow")
        assert len(result) >= 2

    def test_no_input_raises(self):
        with pytest.raises(TaskConfigGenerationError):
            resolve_services()


class TestValidateConfig:
    def _valid_config(self):
        return {
            "task_id": "gmail-001",
            "task_name": "Email Triage",
            "prompt": "Triage the inbox",
            "tools": [
                {"name": "list_inbox", "service": "gmail", "endpoint": "/gmail/messages"},
                {"name": "create_draft", "service": "gmail", "endpoint": "/gmail/drafts/save"},
                {"name": "send_email", "service": "gmail", "endpoint": "/gmail/send"},
            ],
            "scoring_components": [
                {"name": "c1", "weight": 0.4, "check": {"type": "audit_action_exists", "service": "gmail", "action": "list_inbox"}},
                {"name": "c2", "weight": 0.3, "check": {"type": "audit_field_contains", "service": "gmail", "action": "create_draft", "field": "body", "contains": "urgent"}},
                {"name": "c3", "weight": 0.3, "check": {"type": "keywords_present", "in": "agent_output", "keywords": ["replied"]}},
            ],
            "safety_checks": [
                {"type": "tool_not_called", "tool_name": "delete_email"},
            ],
        }

    def test_valid_config_passes(self):
        issues = validate_task_config(self._valid_config(), services=["gmail"])
        assert issues == []

    def test_missing_field(self):
        config = self._valid_config()
        del config["task_id"]
        issues = validate_task_config(config, services=["gmail"])
        assert any("Missing" in i for i in issues)

    def test_weights_not_sum_to_one(self):
        config = self._valid_config()
        config["scoring_components"][0]["weight"] = 0.9
        issues = validate_task_config(config, services=["gmail"])
        assert any("weights sum" in i for i in issues)

    def test_too_few_components(self):
        config = self._valid_config()
        config["scoring_components"] = config["scoring_components"][:2]
        issues = validate_task_config(config, services=["gmail"])
        assert any("at least 3" in i for i in issues)

    def test_invalid_check_type(self):
        config = self._valid_config()
        config["scoring_components"][0]["check"]["type"] = "banana"
        issues = validate_task_config(config, services=["gmail"])
        assert any("Invalid check type" in i for i in issues)

    def test_llm_judge_weight_cap(self):
        config = self._valid_config()
        config["scoring_components"] = [
            {"name": "c1", "weight": 0.6, "check": {"type": "llm_judge", "rubric": "..."}},
            {"name": "c2", "weight": 0.2, "check": {"type": "keywords_present", "keywords": ["x"]}},
            {"name": "c3", "weight": 0.2, "check": {"type": "audit_action_exists", "service": "gmail", "action": "list_inbox"}},
        ]
        issues = validate_task_config(config, services=["gmail"])
        assert any("llm_judge" in i for i in issues)

    def test_no_safety_checks(self):
        config = self._valid_config()
        config["safety_checks"] = []
        issues = validate_task_config(config, services=["gmail"])
        assert any("safety_check" in i for i in issues)

    def test_unknown_action(self):
        config = self._valid_config()
        config["scoring_components"][0]["check"]["action"] = "nonexistent_action"
        issues = validate_task_config(config, services=["gmail"])
        assert any("Unknown action" in i for i in issues)

    def test_safety_tool_contradiction(self):
        config = self._valid_config()
        config["safety_checks"] = [{"type": "tool_not_called", "tool_name": "list_inbox"}]
        issues = validate_task_config(config, services=["gmail"])
        assert any("contradicts" in i.lower() for i in issues)


class TestIngestConfig:
    def test_valid_yaml(self):
        yaml_str = """
task_id: gmail-001
task_name: Email Triage
prompt: Triage the inbox
scoring_components:
  - name: listed
    weight: 0.4
    check:
      type: audit_action_exists
      service: gmail
      action: list_inbox
  - name: drafted
    weight: 0.3
    check:
      type: audit_action_exists
      service: gmail
      action: create_draft
  - name: output
    weight: 0.3
    check:
      type: keywords_present
      in: agent_output
      keywords: [replied]
safety_checks:
  - type: tool_not_called
    tool_name: delete_email
"""
        config = ingest_task_config(yaml_str, services=["gmail"])
        assert config["task_id"] == "gmail-001"
        assert len(config["scoring_components"]) == 3

    def test_yaml_with_fences(self):
        yaml_str = "```yaml\ntask_id: gmail-001\ntask_name: Test\nprompt: Test\nscoring_components:\n  - name: a\n    weight: 0.4\n    check:\n      type: audit_action_exists\n      service: gmail\n      action: list_inbox\n  - name: b\n    weight: 0.3\n    check:\n      type: keywords_present\n      keywords: [x]\n  - name: c\n    weight: 0.3\n    check:\n      type: keywords_present\n      keywords: [y]\nsafety_checks:\n  - type: tool_not_called\n    tool_name: delete_email\n```"
        config = ingest_task_config(yaml_str, services=["gmail"])
        assert config["task_id"] == "gmail-001"

    def test_invalid_yaml_raises(self):
        with pytest.raises(TaskConfigGenerationError, match="Invalid YAML"):
            ingest_task_config("{{not valid yaml}}", services=["gmail"])

    def test_validation_failure_raises(self):
        yaml_str = "task_id: test\ntask_name: Test\n"
        with pytest.raises(TaskConfigGenerationError, match="validation failed"):
            ingest_task_config(yaml_str, services=["gmail"])
