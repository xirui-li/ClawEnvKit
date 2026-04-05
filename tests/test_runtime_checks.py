"""Regression tests for compatibility runtime checks."""

from clawharness.compatibility.runtime_checks import check_runtime


def _write_runtime_fixture(tmp_path, pip_packages: str) -> None:
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    (tmp_path / "mock_services").mkdir()

    (docker_dir / "entrypoint.sh").write_text("#!/bin/sh\n")
    (docker_dir / "Dockerfile.test").write_text(
        "FROM python:3.11-slim\n"
        "RUN pip install --no-cache-dir \\\n"
        f"    {pip_packages}\n"
        "COPY mock_services/ /opt/clawharness/mock_services/\n"
        "ENTRYPOINT [\"/opt/clawharness/entrypoint.sh\"]\n"
    )


def test_runtime_check_flags_missing_requests_for_real_web_services(tmp_path):
    _write_runtime_fixture(
        tmp_path,
        "fastapi uvicorn pyyaml httpx pypdf trafilatura",
    )

    findings = check_runtime(tmp_path)
    missing_requests = {
        (finding.context.get("service"), finding.context.get("dependency"))
        for finding in findings
        if finding.code == "DOCKER_MISSING_DEPENDENCY"
    }

    assert ("web_real", "requests") in missing_requests
    assert ("web_real_injection", "requests") in missing_requests


def test_runtime_check_accepts_requests_when_present(tmp_path):
    _write_runtime_fixture(
        tmp_path,
        "fastapi uvicorn pyyaml httpx requests pypdf trafilatura",
    )

    findings = check_runtime(tmp_path)
    missing_requests = [
        finding
        for finding in findings
        if finding.code == "DOCKER_MISSING_DEPENDENCY"
        and finding.context.get("dependency") == "requests"
    ]

    assert missing_requests == []
