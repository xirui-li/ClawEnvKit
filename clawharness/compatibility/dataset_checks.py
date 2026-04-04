"""Pass B + D: Task YAML / file / tool / scoring checks."""

from __future__ import annotations

import re
import yaml
from pathlib import Path

from .models import Finding

# File-dependent task dirs: missing binary fixtures (PDF/JPG/DB) are warnings, not errors
# (binary fixtures are gitignored and regenerated on demand)
_FILE_TASK_DIRS = {"ocr", "ocr_advanced", "terminal", "comprehension", "coding",
                   "office_qa", "data_analysis", "safety", "rewriting"}


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
        is_excluded = f.parent.name.lower() in _FILE_TASK_DIRS

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

        # --- Safety checks reference valid tools/actions ---
        all_known_actions = set(tool_names)
        try:
            from clawharness.generate.task_generator import SERVICE_DEFINITIONS
            for tool in tools:
                svc = tool.get("service", "")
                svc_def = SERVICE_DEFINITIONS.get(svc, {})
                all_known_actions.update(svc_def.get("actions", []))
        except ImportError:
            pass  # Fall back to just tool_names

        for sc in config.get("safety_checks", []):
            sc_type = sc.get("type", "")
            if sc_type == "tool_not_called":
                tool_name = sc.get("tool_name", "")
                if not tool_name:
                    findings.append(Finding(
                        "TASK_SAFETY_MISSING_TOOL", "error",
                        f"safety_check tool_not_called has no tool_name",
                        file=str(f), context={"task_id": task_id},
                    ))
                elif all_known_actions and tool_name not in all_known_actions:
                    findings.append(Finding(
                        "TASK_SAFETY_UNKNOWN_TOOL", "error",
                        f"safety_check references unknown tool '{tool_name}'",
                        file=str(f), context={"task_id": task_id, "known": sorted(all_known_actions)[:10]},
                    ))
            elif sc_type == "keywords_not_in_output":
                if not sc.get("keywords"):
                    findings.append(Finding(
                        "TASK_SAFETY_MISSING_KEYWORDS", "error",
                        f"safety_check keywords_not_in_output has no keywords",
                        file=str(f), context={"task_id": task_id},
                    ))
            elif sc_type:
                findings.append(Finding(
                    "TASK_SAFETY_UNKNOWN_TYPE", "error",
                    f"Unknown safety check type '{sc_type}'",
                    file=str(f), context={"task_id": task_id},
                ))

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
