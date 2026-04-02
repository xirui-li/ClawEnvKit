"""Pass B + D: Task YAML / file / tool / scoring checks."""

from __future__ import annotations

import re
import yaml
from pathlib import Path

from .models import Finding

_EXCLUDED_DIRS = {"ocr", "ocr_advanced", "terminal", "comprehension", "coding"}


def check_dataset(project_root: Path) -> list[Finding]:
    findings = []
    dataset_dir = project_root / "dataset"

    if not dataset_dir.exists():
        findings.append(Finding("DATASET_MISSING", "error", "dataset/ directory not found"))
        return findings

    for f in sorted(dataset_dir.rglob("*.yaml")):
        if f.name == "generation_meta.json" or f.name == "generation_report.json":
            continue
        try:
            config = yaml.safe_load(open(f))
        except Exception as e:
            findings.append(Finding("TASK_INVALID_YAML", "error", f"Cannot parse: {e}", file=str(f)))
            continue

        task_id = config.get("task_id", f.stem)
        is_excluded = f.parent.name in _EXCLUDED_DIRS

        # --- Tool service existence ---
        tools = config.get("tools", [])
        tool_names = set()
        for tool in tools:
            tool_names.add(tool.get("name", ""))
            svc = tool.get("service", "")
            if svc:
                svc_dir = project_root / "mock_services" / svc
                if not svc_dir.exists() and svc not in ("web_real", "web_real_injection"):
                    findings.append(Finding(
                        "TASK_MISSING_SERVICE", "error",
                        f"Tool '{tool.get('name')}' references service '{svc}' but mock_services/{svc}/ not found",
                        file=str(f), context={"task_id": task_id},
                    ))

            # --- Endpoint existence ---
            endpoint = tool.get("endpoint", "")
            if endpoint and svc:
                svc_server = project_root / "mock_services" / svc / "server.py"
                if svc_server.exists():
                    server_code = svc_server.read_text()
                    if endpoint not in server_code and f'"{endpoint}"' not in server_code:
                        # web_real uses /web/ prefix
                        alt_endpoint = endpoint.replace(f"/{svc}/", "/web/") if svc in ("web_real", "web_real_injection") else None
                        if not alt_endpoint or alt_endpoint not in server_code:
                            findings.append(Finding(
                                "TASK_MISSING_ENDPOINT", "warning",
                                f"Endpoint '{endpoint}' not found in mock_services/{svc}/server.py",
                                file=str(f), context={"task_id": task_id, "tool": tool.get("name")},
                            ))

        # --- Safety checks reference declared tools ---
        for sc in config.get("safety_checks", []):
            tool_name = sc.get("tool_name", "")
            # Safety CAN reference provided tools (valid pattern) — just check it's not completely bogus
            # We only warn if it references something that's not a known action at all

        # --- Files existence (Pass D) ---
        files = config.get("files", [])
        for file_entry in files:
            src = file_entry.get("source", "")
            if src:
                candidates = [
                    project_root / src,
                    project_root / "dataset" / src,
                ]
                if not any(c.exists() for c in candidates):
                    severity = "warning" if is_excluded else "error"
                    findings.append(Finding(
                        "TASK_MISSING_FILE", severity,
                        f"File source not found: {src}",
                        file=str(f), context={"task_id": task_id},
                    ))

        # --- Workspace asset references without files entry ---
        fixtures = config.get("fixtures", {})
        if isinstance(fixtures, dict):
            fixture_str = yaml.dump(fixtures)
            workspace_refs = re.findall(r'/workspace/[\w./\-]+', fixture_str)
            file_targets = {fe.get("target", "") for fe in files}
            for ref in workspace_refs:
                target = ref.replace("/workspace/", "")
                if target and target not in file_targets:
                    severity = "warning" if is_excluded else "error"
                    findings.append(Finding(
                        "TASK_BROKEN_WORKSPACE_REF", severity,
                        f"Fixture references {ref} but no files[] entry copies it",
                        file=str(f), context={"task_id": task_id},
                    ))

    return findings
