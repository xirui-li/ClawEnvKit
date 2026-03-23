#!/usr/bin/env python3
"""mock_claw.py — Dev harness simulating the claw's role in the serve.py protocol.

Two modes:
  --dry-run (default): Use canned JSON responses, no LLM or Docker needed.
  --api: Call Anthropic API for real LLM responses. Requires ANTHROPIC_API_KEY.

Usage:
  python scripts/mock_claw.py --dry-run --input "3 cli tasks" --output ~/clawharness-test
  python scripts/mock_claw.py --api --input "3 cli-file-ops tasks, easy" --output ~/clawharness-test
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVE_PY = PROJECT_ROOT / "scripts" / "serve.py"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "canned_responses"


def _log(msg: str) -> None:
    print(f"[mock_claw] {msg}", file=sys.stderr)


def _call_serve(mode: str, **kwargs) -> dict:
    """Call serve.py with given mode and args. Returns parsed JSON response."""
    cmd = [sys.executable, str(SERVE_PY), "--mode", mode]
    for key, val in kwargs.items():
        if val is not None:
            flag = f"--{key.replace('_', '-')}"
            cmd.extend([flag, str(val)])

    _log(f"→ serve.py --mode={mode}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            _log(f"  stderr: {line}")

    if result.returncode != 0 and not result.stdout.strip():
        return {"status": "error", "error": f"serve.py exited with code {result.returncode}"}

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"status": "error", "error": f"serve.py returned non-JSON: {result.stdout[:200]}"}


def _load_canned(name: str) -> str:
    """Load canned response from fixtures."""
    path = FIXTURES_DIR / f"{name}.json"
    if path.exists():
        return path.read_text().strip()
    # Fallback for indexed fixtures
    _log(f"  Warning: no canned response at {path}")
    return "{}"


def _call_llm_api(prompt: str, system: str | None = None) -> str:
    """Call Anthropic API. Requires ANTHROPIC_API_KEY env var."""
    try:
        import anthropic
    except ImportError:
        _log("ERROR: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    # Load API key: env var > config.json
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        config_path = PROJECT_ROOT / "config.json"
        if config_path.exists():
            import json as _json
            config = _json.load(open(config_path))
            api_key = config.get("ANTHROPIC_API_KEY") or config.get("claude")
        if not api_key:
            _log("ERROR: ANTHROPIC_API_KEY not found in env or config.json")
            sys.exit(1)

    # Load model: env var > config.json > default
    model = os.environ.get("CLAWHARNESS_MODEL")
    if not model:
        config_path = PROJECT_ROOT / "config.json"
        if config_path.exists():
            import json as _json
            config = _json.load(open(config_path))
            model = config.get("model")
    if not model:
        model = "claude-sonnet-4-6"

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": model,
        "max_tokens": 4096,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    _log("  Calling Anthropic API...")
    response = client.messages.create(**kwargs)
    text = response.content[0].text
    _log(f"  API response: {text[:100]}...")
    return text


class MockClaw:
    def __init__(self, mode: str = "dry-run", output_dir: str = "~/clawharness-test"):
        self.mode = mode
        self.output_dir = output_dir
        self.spec_path: str | None = None
        self.task_count: int = 0

    def get_llm_response(self, callback_mode: str, prompt: str, system: str | None = None, index: int | None = None) -> str:
        """Get LLM response based on mode."""
        if self.mode == "api":
            return _call_llm_api(prompt, system)

        # dry-run: use canned responses
        if index is not None:
            return _load_canned(f"{callback_mode}_{index}")
        return _load_canned(callback_mode)

    def handle_response(self, response: dict, index: int | None = None) -> dict | None:
        """Handle a serve.py response. Returns the next response or None if done."""
        status = response.get("status")

        if status == "error":
            _log(f"ERROR: {response.get('error')}")
            return None

        if status == "ok":
            _log(f"  OK: {json.dumps(response.get('data', {}), ensure_ascii=False)[:200]}")
            return response

        if status == "llm_needed":
            llm_call = response["llm_call"]
            callback_mode = llm_call["callback_mode"]
            callback_args = llm_call.get("callback_args", {})
            prompt = llm_call["prompt"]
            system = llm_call.get("system")

            # Track spec path
            if "spec" in callback_args:
                self.spec_path = callback_args["spec"]

            llm_response = self.get_llm_response(callback_mode, prompt, system, index=index)

            # Call serve.py with the callback
            kwargs = {"spec": self.spec_path, "llm_response": llm_response}
            if "index" in callback_args:
                kwargs["index"] = callback_args["index"]

            return _call_serve(callback_mode, **kwargs)

        _log(f"Unknown status: {status}")
        return None

    def run(self, input_text: str) -> None:
        """Run the full pipeline."""
        _log(f"Starting pipeline: '{input_text}' → {self.output_dir}")

        # Step 1: Parse
        _log("=== STEP 1: Parse ===")
        resp = _call_serve("parse", input=input_text, output=self.output_dir)
        resp = self.handle_response(resp)
        if not resp:
            return

        # If parse returned llm_needed, the handle already called parse_ingest
        # Extract task count from spec
        data = resp.get("data", {})
        spec = data.get("spec", {})
        self.task_count = spec.get("task_count", 3)
        _log(f"  Parsed: {self.task_count} tasks, domain={spec.get('domain')}")

        # Step 2 + 3: Generate tasks with consistency check and retry
        MAX_RETRIES = 3
        _log("=== STEP 2+3: Generate Tasks ===")
        for i in range(self.task_count):
            for attempt in range(MAX_RETRIES):
                if attempt > 0:
                    _log(f"--- Task {i+1}/{self.task_count} (retry {attempt}/{MAX_RETRIES}) ---")
                else:
                    _log(f"--- Task {i+1}/{self.task_count} ---")

                # task_prompt → task_ingest
                resp = _call_serve("task_prompt", spec=self.spec_path, index=i)
                resp = self.handle_response(resp, index=i)
                if not resp:
                    _log(f"  Failed to generate instruction for task {i}")
                    break

                # fs_prompt → fs_ingest
                resp = _call_serve("fs_prompt", spec=self.spec_path, index=i)
                resp = self.handle_response(resp, index=i)
                if not resp:
                    _log(f"  Failed to generate fs for task {i}")
                    break

                # consistency_check
                resp = _call_serve("consistency_check", spec=self.spec_path, index=i)
                if resp.get("status") == "llm_needed":
                    resp = self.handle_response(resp, index=i)
                else:
                    self.handle_response(resp, index=i)

                # Check if consistency passed
                check_data = resp.get("data", {}) if resp else {}
                check_state = check_data.get("state", "passed")
                regenerate = check_data.get("regenerate", False)

                if check_state == "passed" or not regenerate:
                    break  # passed or soft warning only
                else:
                    _log(f"  Consistency check failed (regenerate=True), retrying...")
            else:
                _log(f"  Task {i} failed consistency after {MAX_RETRIES} retries, skipping")

        # Step 3.5: Generate test files (v0.2)
        _log("=== STEP 3.5: Generate Tests ===")
        for i in range(self.task_count):
            resp = _call_serve("test_prompt", spec=self.spec_path, index=i)
            if resp.get("status") == "llm_needed":
                resp = self.handle_response(resp, index=i)
                if resp and resp.get("status") == "ok":
                    _log(f"  Task {i+1}: test file generated")
                else:
                    _log(f"  Task {i+1}: test generation failed, continuing without tests")
            elif resp.get("status") == "error":
                _log(f"  Task {i+1}: test generation error: {resp.get('error', '')[:100]}")

        # Step 4: Build (skip in dry-run)
        _log("=== STEP 4: Build ===")
        if self.mode == "dry-run":
            _log("  Skipping Docker build in dry-run mode")
        else:
            resp = _call_serve("build", spec=self.spec_path)
            self.handle_response(resp)

        # Step 5: Validate (skip Docker in dry-run)
        _log("=== STEP 5: Validate ===")
        if self.mode == "dry-run":
            _log("  Skipping validation in dry-run mode (requires Docker)")
        else:
            for i in range(self.task_count):
                resp = _call_serve("validate_prompt", spec=self.spec_path, index=i)
                resp = self.handle_response(resp, index=i)
                if not resp:
                    _log(f"  Validation failed for task {i}")

        # Step 6: Export
        _log("=== STEP 6: Export ===")
        resp = _call_serve("export", spec=self.spec_path, output=self.output_dir)
        self.handle_response(resp)

        # Final status
        _log("=== DONE ===")
        resp = _call_serve("status", spec=self.spec_path)
        self.handle_response(resp)

        _log(f"Pipeline complete. Output: {self.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Mock claw for testing Claw Harnessing pipeline")
    parser.add_argument("--input", required=True, help="Natural language task description")
    parser.add_argument("--output", default="~/clawharness-test", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Use canned responses (default)")
    parser.add_argument("--api", action="store_true", help="Use Anthropic API for real LLM responses")

    args = parser.parse_args()
    mode = "api" if args.api else "dry-run"

    claw = MockClaw(mode=mode, output_dir=args.output)
    claw.run(args.input)


if __name__ == "__main__":
    main()
