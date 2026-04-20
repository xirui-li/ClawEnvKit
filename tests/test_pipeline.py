"""Tests for the modular pipeline API (Parser, Generator, Validator).

Verifies that the wrapper classes correctly delegate to existing functions
and that backward-compatible import paths still work.
"""

from __future__ import annotations

import pytest


# ── Import tests ──

def test_import_from_generate_package():
    from clawenvkit.generate import Parser, Generator, Validator
    assert Parser is not None
    assert Generator is not None
    assert Validator is not None


def test_import_from_pipeline_module():
    from clawenvkit.generate.pipeline import Parser, Generator, Validator
    assert Parser is not None
    assert Generator is not None
    assert Validator is not None


def test_backward_compat_imports():
    """Existing import paths must still work."""
    from clawenvkit.generate.task_generator import validate_task_config
    from clawenvkit.generate.task_generator import SERVICE_DEFINITIONS
    from clawenvkit.generate.task_generator import resolve_services
    assert callable(validate_task_config)
    assert isinstance(SERVICE_DEFINITIONS, dict)
    assert callable(resolve_services)


# ── Generator tests ──

def test_generator_resolve_services():
    from clawenvkit.generate import Generator
    gen = Generator()
    result = gen.resolve_services(services=["todo"])
    assert result == ["todo"]


def test_generator_resolve_services_category():
    from clawenvkit.generate import Generator
    gen = Generator()
    result = gen.resolve_services(category="communication")
    assert isinstance(result, list)
    assert len(result) >= 2


def test_generator_service_definitions_property():
    from clawenvkit.generate import Generator
    gen = Generator()
    defs = gen.service_definitions
    assert isinstance(defs, dict)
    assert "todo" in defs
    assert "gmail" in defs


def test_generator_cross_service_categories_property():
    from clawenvkit.generate import Generator
    gen = Generator()
    cats = gen.cross_service_categories
    assert isinstance(cats, dict)
    assert "communication" in cats


# ── Validator tests ──

def test_validator_validate_task_config_empty():
    from clawenvkit.generate import Validator
    val = Validator()
    issues = val.validate_task_config({})
    assert isinstance(issues, list)
    assert len(issues) > 0  # empty config should have issues


def test_validator_verify_coverage_no_atoms():
    from clawenvkit.generate import Validator
    val = Validator()
    gaps = val.verify_coverage({"tools": [], "scoring_components": []}, [])
    assert gaps == []  # no atoms = no gaps


def test_validator_verify_coverage_with_gap():
    from clawenvkit.generate import Validator
    val = Validator()
    gaps = val.verify_coverage(
        {"tools": [], "scoring_components": [], "fixtures": {}, "safety_checks": [], "prompt": ""},
        [{"type": "action", "name": "send_email", "description": ""}],
    )
    assert len(gaps) > 0
    assert "send_email" in gaps[0]


def test_validator_verify_feasibility_callable():
    from clawenvkit.generate import Validator
    val = Validator()
    assert callable(val.verify_feasibility)


# ── Parser tests ──

def test_parser_is_callable():
    from clawenvkit.generate import Parser
    p = Parser()
    assert callable(p.parse_intent)


# ── Statelessness ──

def test_classes_are_stateless():
    """Classes should work without __init__ args and be reusable."""
    from clawenvkit.generate import Parser, Generator, Validator
    p1, p2 = Parser(), Parser()
    g1, g2 = Generator(), Generator()
    v1, v2 = Validator(), Validator()
    # Both instances should give same results
    assert g1.resolve_services(services=["todo"]) == g2.resolve_services(services=["todo"])
    assert v1.validate_task_config({}) == v2.validate_task_config({})
