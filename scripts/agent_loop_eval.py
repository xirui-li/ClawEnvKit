#!/usr/bin/env python3
"""Agent Loop Evaluator — no Docker needed.

Runs mock services locally, executes LLM agent loop with real tool calls,
collects audit logs, grades with GradingEngine. All three dimensions supported:
safety, completion, robustness.

Usage:
    python scripts/agent_loop_eval.py                                    # all 10 models
    python scripts/agent_loop_eval.py --model openai/gpt-5.4            # single model
    python scripts/agent_loop_eval.py --model openai/gpt-5.4 z-ai/glm-5 # pick models
    python scripts/agent_loop_eval.py --resume                           # resume
    python scripts/agent_loop_eval.py --dataset dataset --workers 5      # options
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import yaml
import urllib.request
import threading
import uvicorn
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clawharness.evaluate.engine import GradingEngine
from clawharness.llm_client import detect_provider

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# ── Default models ──────────────────────────────────────────────────

ALL_MODELS = [
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-5.4",
    "openai/gpt-5-nano",
    "z-ai/glm-5-turbo",
    "z-ai/glm-5",
    "minimax/minimax-m2.7",
    "minimax/minimax-m2.5",
    "xiaomi/mimo-v2-pro",
    "xiaomi/mimo-v2-omni",
]

# ── Mock Service Manager ────────────────────────────────────────────

class MockServiceManager:
    """Start/stop mock services on localhost."""

    def __init__(self, port: int = 9100, error_rate: float = 0.25):
        self.port = port
        self.error_rate = error_rate
        self._server = None
        self._thread = None

    def start(self, services: list[str], fixtures: dict):
        """Start mock services for given service list with fixtures."""
        os.environ["ERROR_RATE"] = str(self.error_rate)

        # Write fixtures to temp files
        for svc in services:
            svc_data = fixtures.get(svc, fixtures)
            env_key = f"{svc.upper()}_FIXTURES"
            if env_key not in os.environ or True:
                import tempfile
                f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                # Handle nested fixtures: {svc: {key: [...]}} or flat list
                if isinstance(svc_data, dict) and svc not in svc_data:
                    json.dump(svc_data, f)
                elif isinstance(svc_data, dict) and svc in svc_data:
                    json.dump(svc_data[svc], f)
                else:
                    json.dump(svc_data if isinstance(svc_data, list) else [], f)
                f.close()
                os.environ[env_key] = f.name

        # Use multi_server for multiple services
        if len(services) > 1:
            from mock_services.multi_server import create_multi_app
            app = create_multi_app(services)
        else:
            import importlib
            svc = services[0]
            mod = importlib.import_module(f"mock_services.{svc}.server")
            app = mod.app
            # Reload fixtures
            if hasattr(mod, "_load_fixtures"):
                mod._load_fixtures()

        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        # Wait for ready
        for _ in range(30):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/docs", timeout=1)
                return True
            except Exception:
                time.sleep(0.1)
        return False

    def collect_audit(self, services: list[str]) -> dict:
        """Collect audit logs from all services."""
        audit = {}
        for svc in services:
            prefix = {"web_real": "web", "web_real_injection": "web"}.get(svc, svc)
            try:
                data = json.loads(
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/{prefix}/audit", timeout=5
                    ).read()
                )
                audit[svc] = data
            except Exception:
                audit[svc] = {"calls": []}
        return audit

    def reset(self, services: list[str]):
        """Reset all services to fixture state."""
        for svc in services:
            prefix = {"web_real": "web", "web_real_injection": "web"}.get(svc, svc)
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/{prefix}/reset",
                    method="POST",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass

    def stop(self):
        if self._server:
            self._server.should_exit = True
            self._thread.join(timeout=5)
            self._server = None


# ── Agent Loop ──────────────────────────────────────────────────────

def run_agent_loop(
    prompt: str,
    tools: list[dict],
    model: str,
    provider: str,
    api_key: str,
    base_url: str,
    port: int = 9100,
    max_turns: int = 10,
) -> tuple[str, int]:
    """Run LLM agent loop with tool calling.

    Returns: (final_text_output, num_tool_calls)
    """
    # Build OpenAI-format tools
    openai_tools = []
    tool_endpoints = {}
    for t in tools:
        name = t.get("name", "")
        endpoint = t.get("endpoint", "")
        tool_endpoints[name] = endpoint

        # Build parameter schema from endpoint description
        params = t.get("parameters", {})
        if not params:
            params = {"type": "object", "properties": {}, "required": []}

        openai_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": t.get("description", name),
                "parameters": params,
            },
        })

    messages = [{"role": "user", "content": prompt}]
    total_tool_calls = 0
    final_output = ""

    for turn in range(max_turns):
        # Call LLM
        token_key = "max_completion_tokens" if model.startswith("gpt-5") else "max_tokens"
        body = {
            "model": model,
            "messages": messages,
            token_key: 4096,
            "temperature": 0,
        }
        if openai_tools:
            body["tools"] = openai_tools

        req_data = json.dumps(body).encode("utf-8")

        if provider == "anthropic" and not base_url:
            # Anthropic native — doesn't support OpenAI tools format
            # Fall back to text-only mode
            body_anthropic = {
                "model": model,
                "max_tokens": 4096,
                "temperature": 0,
                "messages": messages,
            }
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(body_anthropic).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read())
            final_output = data["content"][0]["text"]
            break
        else:
            if not base_url:
                base_url = "https://openrouter.ai/api/v1"
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read())

        choice = data["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        # Check for tool calls
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            final_output = msg.get("content", "") or ""
            break

        # Execute tool calls
        for tc in tool_calls:
            func = tc["function"]
            tool_name = func["name"]
            try:
                tool_args = json.loads(func["arguments"]) if func.get("arguments") else {}
            except json.JSONDecodeError:
                tool_args = {}

            total_tool_calls += 1
            endpoint = tool_endpoints.get(tool_name, "")

            if endpoint:
                # Call mock service
                try:
                    tool_req = urllib.request.Request(
                        f"http://127.0.0.1:{port}{endpoint}",
                        data=json.dumps(tool_args).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    tool_resp = urllib.request.urlopen(tool_req, timeout=10)
                    tool_result = tool_resp.read().decode("utf-8")
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)[:100]})
            else:
                tool_result = json.dumps({"error": f"Unknown tool: {tool_name}"})

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

        # If last choice was stop, extract content
        if choice.get("finish_reason") == "stop":
            final_output = msg.get("content", "") or ""
            break

    # If we exhausted turns, get whatever content we have
    if not final_output and messages:
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("content"):
                final_output = m["content"]
                break

    return final_output, total_tool_calls


# ── Evaluator ───────────────────────────────────────────────────────

class AgentLoopEvaluator:
    """Evaluate models using local agent loop (no Docker)."""

    def __init__(self, dataset: str, results_dir: str, workers: int = 1,
                 port: int = 9100, error_rate: float = 0.25, resume: bool = False):
        self.dataset = Path(dataset)
        self.results_dir = Path(results_dir)
        self.workers = workers
        self.port = port
        self.error_rate = error_rate
        self.resume = resume
        self.engine = GradingEngine()

        self.tasks = sorted(
            f for f in self.dataset.rglob("*.yaml")
            if f.name != "generation_report.json"
        )

    def _load_api_keys(self):
        provider, api_key, base_url, model = detect_provider()
        return provider, api_key, base_url

    def run_one_task(self, task_path: Path, model: str, provider: str,
                     api_key: str, base_url: str, model_dir: Path) -> dict:
        """Run one task through agent loop + grading."""
        config = yaml.safe_load(open(task_path))
        if not isinstance(config, dict) or "scoring_components" not in config:
            return {"task_id": task_path.stem, "error": "invalid yaml"}

        task_id = config.get("task_id", task_path.stem)
        result_file = model_dir / task_id / "result.json"

        # Resume
        if self.resume and result_file.exists():
            try:
                return json.load(open(result_file))
            except Exception:
                pass

        tools = config.get("tools", [])
        services = sorted(set(t.get("service", "") for t in tools if t.get("service")))
        fixtures = config.get("fixtures", {})
        prompt = config.get("prompt", "")
        category = config.get("category", "")

        # Start mock services
        mgr = MockServiceManager(port=self.port + threading.current_thread().ident % 100,
                                  error_rate=self.error_rate)
        actual_port = mgr.port

        agent_output = ""
        num_tool_calls = 0
        audit_data = {}
        latency = 0

        try:
            if services:
                mgr.start(services, fixtures)
                mgr.reset(services)

            t0 = time.time()
            agent_output, num_tool_calls = run_agent_loop(
                prompt=prompt,
                tools=tools,
                model=model,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                port=actual_port,
                max_turns=10,
            )
            latency = time.time() - t0

            # Collect audit
            if services:
                raw_audit = mgr.collect_audit(services)
                # Build audit_data in engine format
                for svc in services:
                    audit_data[svc] = []
                    svc_audit = raw_audit.get(svc, {})
                    for call in svc_audit.get("calls", []):
                        endpoint = call.get("endpoint", "")
                        # Map endpoint to action name
                        action = endpoint.strip("/").split("/")[-1]
                        for t in tools:
                            if t.get("endpoint") == endpoint:
                                action = t.get("name", action)
                                break
                        audit_data[svc].append({
                            "action": action,
                            "params": call.get("request_body", {}),
                            "status": call.get("status", 200),
                        })
        except Exception as e:
            agent_output = f"Error: {str(e)[:200]}"
        finally:
            mgr.stop()

        # Grade
        try:
            grading = self.engine.grade(config, audit_data, agent_output)
        except Exception:
            grading = None

        if grading:
            result = {
                "task_id": task_id,
                "model": model,
                "category": category,
                "services": services,
                "safety": round(grading.safety, 4),
                "completion": round(grading.completion, 4),
                "robustness": round(grading.robustness, 4),
                "final_score": round(grading.final_score, 4),
                "num_tool_calls": num_tool_calls,
                "safety_violations": grading.safety_violations,
                "components": [
                    {"name": c.name, "passed": c.passed, "score": round(c.score, 4), "weight": c.weight}
                    for c in grading.component_results
                ],
                "agent_output": agent_output[:5000],
                "latency_seconds": round(latency, 2),
            }
        else:
            result = {
                "task_id": task_id, "model": model, "category": category,
                "services": services, "safety": 0, "completion": 0,
                "robustness": 0, "final_score": 0, "error": "grading failed",
                "agent_output": agent_output[:5000],
            }

        # Save
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)

        return result

    def run_model(self, model: str) -> dict:
        """Run all tasks for one model."""
        provider, api_key, base_url = self._load_api_keys()
        model_dir = self.results_dir / model.replace("/", "_")
        model_dir.mkdir(parents=True, exist_ok=True)

        # Check if already complete
        summary_file = model_dir / "summary.json"
        if self.resume and summary_file.exists():
            try:
                s = json.load(open(summary_file))
                if s.get("completed", 0) == len(self.tasks):
                    print(f"  SKIP {model} (complete, score={s.get('mean_score', '?')})")
                    return s
            except Exception:
                pass

        results = []
        lock = Lock()
        pbar = tqdm(total=len(self.tasks), desc=model.split("/")[-1], unit="task") if tqdm else None

        start_time = time.time()

        def _worker(task_path):
            r = self.run_one_task(task_path, model, provider, api_key, base_url, model_dir)
            with lock:
                results.append(r)
            if pbar:
                score = r.get("final_score", 0)
                pbar.set_postfix_str(f"score={score:.2f}")
                pbar.update(1)
            # Save summary periodically
            if len(results) % 10 == 0:
                self._save_summary(model, results, model_dir, time.time() - start_time)

        # Sequential for now (mock service port conflicts with parallel)
        for t in self.tasks:
            _worker(t)

        if pbar:
            pbar.close()

        elapsed = time.time() - start_time
        summary = self._save_summary(model, results, model_dir, elapsed)
        scored = [r for r in results if not r.get("error")]
        n = len(scored)
        print(f"  {model}: score={summary['mean_score']:.3f} safety={summary['mean_safety']:.2f} "
              f"completion={summary['mean_completion']:.2f} ({n}/{len(self.tasks)}) "
              f"time={elapsed/60:.1f}m cost=${summary.get('estimated_cost_usd', 0):.2f}")
        return summary

    def _save_summary(self, model, results, model_dir, elapsed_seconds=0):
        scored = [r for r in results if not r.get("error")]
        n = len(scored)
        mean = lambda key: round(sum(r.get(key, 0) for r in scored) / n, 4) if n else 0
        total_latency = sum(r.get("latency_seconds", 0) for r in scored)

        # Estimate cost from pricing
        try:
            from clawharness.llm_client import detect_provider
            # Rough estimate: ~2K input + ~1K output per task
            _load_pricing = globals().get("_load_pricing")
        except Exception:
            pass

        summary = {
            "model": model,
            "agent": "agent-loop",
            "total_tasks": len(self.tasks),
            "completed": n,
            "mean_safety": mean("safety"),
            "mean_completion": mean("completion"),
            "mean_robustness": mean("robustness"),
            "mean_score": mean("final_score"),
            "mean_latency": mean("latency_seconds"),
            "total_latency_seconds": round(total_latency, 1),
            "elapsed_seconds": round(elapsed_seconds, 1),
            "elapsed_minutes": round(elapsed_seconds / 60, 1),
            "safety_violation_rate": round(sum(1 for r in scored if r.get("safety", 1) < 1) / n, 4) if n else 0,
            "mean_tool_calls": round(sum(r.get("num_tool_calls", 0) for r in scored) / n, 1) if n else 0,
        }
        with open(model_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        return summary

    def run(self, models: list[str]):
        print(f"{'='*60}")
        print(f"  Agent Loop Evaluation (no Docker)")
        print(f"{'='*60}")
        print(f"  Dataset:  {self.dataset}/ ({len(self.tasks)} tasks)")
        print(f"  Models:   {len(models)}")
        print(f"  Error rate: {self.error_rate}")
        print(f"  Results:  {self.results_dir}/")
        print(f"{'='*60}\n")

        all_summaries = {}
        for model in models:
            print(f"\n--- {model} ---")
            summary = self.run_model(model)
            all_summaries[model] = summary

        # Combined
        combined = {
            "agent": "agent-loop",
            "dataset": str(self.dataset),
            "models": all_summaries,
        }
        with open(self.results_dir / "eval_combined.json", "w") as f:
            json.dump(combined, f, indent=2)

        print(f"\n{'='*60}")
        print(f"  Done. Results: {self.results_dir}/")
        print(f"{'='*60}")


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agent Loop Evaluator (no Docker)",
        epilog="""
Examples:
  python scripts/agent_loop_eval.py                           # all 10 models
  python scripts/agent_loop_eval.py --model openai/gpt-5.4   # single model
  python scripts/agent_loop_eval.py --resume                  # resume
  python scripts/agent_loop_eval.py --dataset dataset         # 104 tasks
        """,
    )
    parser.add_argument("--model", nargs="+", help="Model ID(s). Default: all 10")
    parser.add_argument("--dataset", default="dataset_x10")
    parser.add_argument("--results", default="loop_results")
    parser.add_argument("--error-rate", type=float, default=0.25)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    models = args.model if args.model else ALL_MODELS

    evaluator = AgentLoopEvaluator(
        dataset=args.dataset,
        results_dir=args.results,
        error_rate=args.error_rate,
        resume=args.resume,
    )
    evaluator.run(models)


if __name__ == "__main__":
    main()
