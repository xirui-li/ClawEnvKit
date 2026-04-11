"""Main orchestration: runs all compatibility checks and produces report.

Usage:
    python -m clawenvkit.compatibility.checker
    python -m clawenvkit.compatibility.checker --format json
    python -m clawenvkit.compatibility.checker --check dataset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import Finding, CompatibilityReport
from .dataset_checks import check_dataset
from .generator_checks import check_generator
from .runtime_checks import check_runtime
from .packaging_checks import check_packaging
from .report import format_human, format_json


ALL_CHECKS = {
    "dataset": check_dataset,
    "generator": check_generator,
    "runtime": check_runtime,
    "packaging": check_packaging,
}


def run_checks(
    project_root: Path,
    check_names: list[str] | None = None,
) -> CompatibilityReport:
    """Run selected (or all) compatibility checks."""
    checks_to_run = check_names or list(ALL_CHECKS.keys())
    all_findings: list[Finding] = []

    for name in checks_to_run:
        check_fn = ALL_CHECKS.get(name)
        if not check_fn:
            print(f"Unknown check: {name}", file=sys.stderr)
            continue
        findings = check_fn(project_root)
        all_findings.extend(findings)

    errors = sum(1 for f in all_findings if f.severity == "error")
    warnings = sum(1 for f in all_findings if f.severity == "warning")

    return CompatibilityReport(
        passed=errors == 0,
        findings=all_findings,
        summary={
            "errors": errors,
            "warnings": warnings,
            "total_findings": len(all_findings),
            "checks_run": checks_to_run,
        },
    )


def main():
    parser = argparse.ArgumentParser(description="ClawEnvKit compatibility gate")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    parser.add_argument("--check", action="append", help="Run specific check(s)")
    parser.add_argument("--root", default=None, help="Project root (auto-detected)")
    args = parser.parse_args()

    # Detect project root
    if args.root:
        root = Path(args.root)
    else:
        # Try common locations
        for candidate in [
            Path.cwd(),
            Path(__file__).resolve().parent.parent.parent,
        ]:
            if (candidate / "mock_services").exists():
                root = candidate
                break
        else:
            print("Cannot find project root. Use --root.", file=sys.stderr)
            sys.exit(2)

    report = run_checks(root, args.check)

    if args.format == "json":
        print(format_json(report))
    else:
        print(format_human(report))

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
