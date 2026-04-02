"""Core types for compatibility gate findings."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Finding:
    code: str           # e.g. TASK_MISSING_FILE
    severity: str       # "error" | "warning"
    message: str
    file: str | None = None
    context: dict = field(default_factory=dict)


@dataclass
class CheckResult:
    name: str
    findings: list[Finding] = field(default_factory=list)


@dataclass
class CompatibilityReport:
    passed: bool
    findings: list[Finding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "findings": [
                {"code": f.code, "severity": f.severity, "message": f.message,
                 "file": f.file, "context": f.context}
                for f in self.findings
            ],
        }
