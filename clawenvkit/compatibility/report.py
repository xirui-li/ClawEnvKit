"""Report generation: human-readable + JSON output."""

from __future__ import annotations

import json

from .models import CompatibilityReport, Finding


def format_human(report: CompatibilityReport) -> str:
    lines = []
    status = "PASSED" if report.passed else "FAILED"
    lines.append(f"Compatibility: {status}")
    lines.append(f"  Errors: {report.summary.get('errors', 0)}")
    lines.append(f"  Warnings: {report.summary.get('warnings', 0)}")
    lines.append("")

    # Group by code
    by_code: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_code.setdefault(f.code, []).append(f)

    for code in sorted(by_code.keys()):
        findings = by_code[code]
        severity = findings[0].severity.upper()
        lines.append(f"[{severity}] {code} ({len(findings)} findings)")
        for f in findings[:5]:  # Show first 5
            if f.file:
                lines.append(f"  {f.file}")
            lines.append(f"  {f.message}")
        if len(findings) > 5:
            lines.append(f"  ... and {len(findings) - 5} more")
        lines.append("")

    return "\n".join(lines)


def format_json(report: CompatibilityReport) -> str:
    return json.dumps(report.to_dict(), indent=2)
