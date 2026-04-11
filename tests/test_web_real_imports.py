"""Regression tests for web_real service-local imports."""

import importlib


def _exercise_web_search(monkeypatch, service_name: str) -> None:
    server = importlib.import_module(f"mock_services.{service_name}.server")
    search_mod = importlib.import_module(f"mock_services.{service_name}.search_serp")

    monkeypatch.setattr(
        search_mod,
        "search_serp",
        lambda query, num, timeout: {
            "output": [
                {
                    "link": f"https://example.com/{service_name}",
                    "title": f"{service_name} result",
                    "snippet": f"snippet for {query}",
                    "date": "2026-04-06",
                }
            ]
        },
    )
    monkeypatch.setattr(server, "_search_count", 0)
    monkeypatch.setattr(server, "_audit_log", [])
    monkeypatch.setattr(server, "_cache_get", lambda key: None)
    monkeypatch.setattr(server, "_cache_set", lambda key, data: None)

    if service_name == "web_real_injection":
        monkeypatch.setattr(server, "_inject_search_results", lambda resp: resp)

    resp = server.web_search(server.SearchRequest(query="latest benchmark setup", max_results=3))

    assert resp["total"] == 1
    assert resp["results"][0]["url"] == f"https://example.com/{service_name}"
    assert resp["query"] == "latest benchmark setup"
    assert "error" not in resp


def test_web_real_search_import_works_when_loaded_as_package(monkeypatch):
    _exercise_web_search(monkeypatch, "web_real")


def test_web_real_injection_search_import_works_when_loaded_as_package(monkeypatch):
    _exercise_web_search(monkeypatch, "web_real_injection")
