# Claw Harnessing v0.1 — Execution Checklist

**Scope decisions (locked for v0.1):**
- Task types: `code` only (`design`, `review`, `test` → v0.2)
- LLM calls: claw delegation only (no `--backbone anthropic`)
- Docker: `subprocess` calling docker CLI (no Python Docker SDK)
- CLI entry point: deferred to v0.2 (`scripts/clawharness.py` is empty placeholder); v0.1 uses SKILL.md + serve.py only
- Tests: written per module, not TDD

---

## Phase 0: Repo Setup

- [x] Create GitHub repo `clawharness` (empty, no README)
- [x] `git remote add origin` + `git push -u origin main`
- [x] Copy `DESIGN.md` into repo root
- [x] Write `.gitignore`
  ```
  __pycache__/
  *.pyc
  .env
  ~/.clawharness/
  *.egg-info/
  dist/
  .pytest_cache/
  ```
- [x] Write `requirements.txt`
  ```
  pytest
  pydantic>=2.0
  anthropic>=0.40.0    # for mock_claw.py --api mode
  ```
- [x] Write minimal `README.md` (one paragraph + install instructions)
- [x] `git add . && git commit -m "initial repo setup"`
- [x] Symlink into OpenClaw skills:
  ```bash
  ln -s ~/XIRUILI/Research/Codebase/claw-harnessing ~/.openclaw/workspace/skills/clawharness
  ```
- [?] Verify OpenClaw sees the skill:
  ```
  (in OpenClaw session) /context list
  → clawharness should appear in skills list
  ```

---

## Phase 0.5: `mock_claw.py` — Dev Harness (moved to after Phase 9)

**Note:** Deferred until `serve.py` is implemented (Phase 9). mock_claw.py's core loop calls serve.py, so it can't be tested until serve.py exists. Implementing after Phase 9 means it can be end-to-end tested immediately.

Without a running OpenClaw instance, we need a lightweight script that simulates the claw's role in the `serve.py` protocol: read JSON output, handle `llm_needed` responses, and call back with `--llm-response`.

- [x] Write `scripts/mock_claw.py`:
  - [x] Core loop: call `serve.py` via subprocess, parse stdout JSON
  - [x] `--dry-run` mode with canned responses from `tests/fixtures/canned_responses/`
  - [x] `--api` mode calling Anthropic API
  - [x] Full pipeline orchestration (parse → generate → consistency → build → validate → export)
  - [x] CLI args: `--input`, `--output`, `--dry-run`/`--api`
- [x] Write canned response fixtures (per-task indexed: `*_0.json`, `*_1.json`, `*_2.json`)
- [x] Smoke test: dry-run pipeline runs all stages, produces train.jsonl with 3 tasks
- [x] `git commit` → a881d12

**Note:** `mock_claw.py` is a dev tool, not a production entry point. It will not be documented in README or SKILL.md. The `--api` mode is effectively the v0.2 `--backbone` feature, but scoped as internal tooling.

---

## Phase 1: `schema.py` — Data Structures

- [x] Write `scripts/core/schema.py` with all dataclasses:
  - [x] `GenerationSpec`
  - [x] `TaskSpec` (with `task_type` field, v0.1 only supports `"code"`)
    - [x] Include `base_tools: list[str]` field (copied from `GenerationSpec` at ingest time)
  - [x] `SuccessCriterion` (four deterministic types only, no `llm_judge` in v0.1)
  - [x] `ConsistencyResult`
  - [x] `ConsistencyCheckResult`
  - [x] `ValidationResult`
  - [x] `BuildResult`
  - [x] `ExportResult`
  - [x] `IntentParserResult`
- [x] Write `tests/test_schema.py`:
  - [x] `TaskSpec` serializes/deserializes to JSON correctly
  - [x] `SuccessCriterion` rejects invalid `type` values
  - [x] `GenerationSpec` applies defaults for missing fields
- [x] `pytest tests/test_schema.py` → all pass (30 tests)
- [x] `git commit -m "schema: add all dataclasses"` → d0ddd84

---

## Phase 2: Prompt Templates

- [x] Write `prompts/intent_parse.md`
  - Input variables: `{description}`
  - Output: JSON matching `GenerationSpec` fields
  - Must enforce `task_types: ["code"]` for v0.1
  - Must return JSON only, no prose
- [x] Write `prompts/task_instruction.md`
  - Input variables: `{domain}`, `{skill_target}`, `{difficulty}`, `{prior_instructions}`
  - Output: a single instruction string
  - Must produce instructions that are concrete, achievable, unambiguous
- [x] Write `prompts/task_fs_criteria.md`
  - Input variables: `{domain}`, `{instruction}`, `{base_tools}`, `{difficulty}`
  - Output: JSON with `initial_fs` and `success_criteria`
  - Must restrict paths to `/workspace/`
  - Must restrict criterion types to `exit_code`, `file_exists`, `file_contains`, `file_not_contains`
- [x] Write `prompts/task_solver.md`
  - Input variables: `{instruction}`, `{initial_fs_summary}`
  - Output: JSON with `reasoning` and `actions` (list of bash commands)
- [x] Write `prompts/consistency_check.md`
  - Input variables: `{task_type}`, `{difficulty}`, `{instruction}`, `{initial_fs}`, `{success_criteria}`
  - Output: JSON with `passed` (bool) and `issues` (list of strings)
- [?] Manual test each prompt: paste into OpenClaw session, verify output format
- [x] `git commit -m "prompts: add all template files"` → 4bea08d

---

## Phase 3: `intent_parser.py`

- [x] Write `scripts/core/intent_parser.py`:
  - [x] `parse(description, llm_response=None) -> IntentParserResult`
  - [x] First call (no `llm_response`): load `prompts/intent_parse.md`, substitute `{description}`, return `needs_clarification` with prompt
  - [x] Second call (with `llm_response`): parse JSON, apply defaults, validate fields, return `ready` with `GenerationSpec`
  - [x] Handle malformed JSON: raise `IntentParseError`
  - [x] Map unknown domains to closest supported domain
- [x] Write `tests/test_intent_parser.py`:
  - [x] Valid LLM response → returns `GenerationSpec` with correct fields
  - [x] Missing fields filled with defaults
  - [x] Malformed JSON → raises `IntentParseError`
  - [x] Unknown domain maps to closest match
  - [x] `task_types` always contains only `["code"]` in v0.1
- [x] `pytest tests/test_intent_parser.py` → all pass (14 tests)
- [x] `git commit` → 3bdd4e5

---

## Phase 4: `task_generator.py`

- [x] Write `scripts/core/task_generator.py`:
  - [x] `generate_instruction_prompt(spec, index) -> str`
    - Load `prompts/task_instruction.md`
    - Substitute domain, skill_target (from `spec.skill_targets[index % len]`), difficulty, prior instructions
    - Return prompt string
  - [x] `ingest_instruction(spec, index, llm_response) -> str`
    - Strip whitespace, validate non-empty
    - Check uniqueness against already-generated instructions (Jaccard < 0.7)
    - Return instruction string
  - [x] `generate_fs_prompt(spec, instruction) -> str`
    - Load `prompts/task_fs_criteria.md`
    - Substitute domain, instruction, base_tools, difficulty
    - Return prompt string
  - [x] `ingest_fs_and_criteria(spec, instruction, llm_response) -> TaskSpec`
    - Parse JSON response
    - Validate all paths start with `/workspace/`
    - Validate no `..` in paths
    - Validate criterion types are in allowed set
    - Copy `base_tools` from `GenerationSpec` into `TaskSpec`
    - Return `TaskSpec` (without `docker_image` set yet)
- [x] Write `tests/test_task_generator.py`:
  - [x] Instruction prompt contains domain and difficulty
  - [x] Path traversal (`../etc/passwd`) is rejected
  - [x] Paths outside `/workspace/` are rejected
  - [x] Duplicate instructions (Jaccard > 0.7) trigger retry hint
  - [x] Invalid criterion type raises `TaskGenerationError`
  - Note: difficulty heuristics enforced in prompts, not code-level validation
- [x] `pytest tests/test_task_generator.py` → all pass (29 tests)
- [x] `git commit` → bf5b011

---

## Phase 5: `consistency_checker.py`

- [x] Write `scripts/core/consistency_checker.py`:
  - [x] `check_deterministic(task) -> list[str]`
    - Extract quoted filenames from instruction (regex)
    - Check all referenced files exist in `initial_fs`
    - Check all criterion paths exist in `initial_fs`
    - Check difficulty heuristics (file count, criteria count)
    - Return list of issue strings (empty = pass)
  - [x] `check_semantic_prompt(task) -> str`
    - Load `prompts/consistency_check.md`
    - Substitute task fields
    - Return prompt string
  - [x] `check_semantic_ingest(task, llm_response) -> ConsistencyResult`
    - Parse JSON response
    - Set `regenerate=True` if issues are blocking (missing files, mismatched criteria)
    - Set `regenerate=False` for soft warnings (difficulty calibration)
  - [x] `check(task, llm_response=None, skip_semantic=False) -> ConsistencyCheckResult`
    - Run deterministic first
    - Trigger semantic only for `hard` difficulty in v0.1 (no `review` type yet)
- [x] Write `tests/test_consistency_checker.py`:
  - [x] Missing file referenced in instruction → issue detected
  - [x] Criterion path not in `initial_fs` → issue detected
  - [x] Easy task with 3 files → soft warning, `regenerate=False`
  - [x] Hard task with 1 criterion → soft warning, `regenerate=False`
  - [x] Missing file → hard failure, `regenerate=True`
  - Note: cycle detection deferred to serve.py orchestration layer
- [x] `pytest tests/test_consistency_checker.py` → all pass (24 tests)
- [x] `git commit` → 05e022c

---

## Phase 6: `image_builder.py`

- [x] Write `scripts/core/image_builder.py`:
  - [x] `generate_dockerfile(task, base_image="alpine:3.19") -> str`
    - Tools layer first (cached), `COPY initial_fs/` layer second
    - Include tools from `task.base_tools`
  - [x] `build(task) -> BuildResult`
    - Build context in `~/.clawharness/build/<task_id>/` (not `/tmp/` — Colima)
    - Write `Dockerfile` + `initial_fs/` files
    - Run `docker build -t clawharness/<domain>/<task_id>:v1 <build_dir>`
    - Clean up build context in `finally`
    - Check `initial_fs` total size < 10MB before building
    - Return `BuildResult`
  - [x] `build_batch(tasks, max_workers=4) -> list[BuildResult]`
    - `ThreadPoolExecutor`, failure-isolated
- [?] Manual smoke test (requires Docker/Colima running)
- [x] Write `tests/test_image_builder.py` (mocked subprocess):
  - [x] `generate_dockerfile` puts tools layer before COPY layer
  - [x] Build context is under `~/`, not `/tmp/`
  - [x] Build context cleaned up on success
  - [x] Build context cleaned up on failure (finally block)
  - [x] `initial_fs` > 10MB raises error before build
  - [x] Failed build in batch doesn't cancel others
  - [x] Image name follows `clawharness/<domain>/<task_id>:v1`
- [x] `pytest tests/test_image_builder.py` → all pass (17 tests)
- [x] `git commit` → 874ca4c

---

## Phase 7: `validator.py`

- [x] Write `scripts/core/validator.py`:
  - [x] `validate_prompt(task) -> str`
    - Load `prompts/task_solver.md`
    - Substitute instruction + initial_fs summary
    - Return prompt string
  - [x] `validate_with_solution(task, solver_actions) -> ValidationResult`
    - `docker run -d --network none <image>` → container_id
    - `try/finally`: always `docker stop` + `docker rm`
    - For each action: `docker exec <id> sh -c "<action>"` with 10s timeout
    - Check each `SuccessCriterion` (all 4 types)
    - Return `ValidationResult`
  - [x] `parse_solver_response(llm_response) -> list[str]`
- [?] Manual smoke test (requires Docker/Colima running)
- [x] Write `tests/test_validator.py` (mocked docker calls):
  - [x] Container always stopped+removed even when criteria check raises
  - [x] `exit_code` criterion passes on correct exit code
  - [x] `file_contains` passes when pattern found
  - [x] `file_not_contains` passes when pattern absent / fails when present
  - [x] Action timeout marks task failed without crashing
  - [x] `--network none` always passed to `docker run`
- [x] `pytest tests/test_validator.py` → all pass (16 tests)
- [x] `git commit` → f2cd1da

---

## Phase 8: `exporter.py`

- [x] Write `scripts/core/exporter.py`:
  - [x] `export(tasks, output_dir, split="train") -> ExportResult`
    - Filter out tasks where `validation_result.passed == False`
    - Write `{output_dir}/{split}.jsonl`
    - Each line: `task_id`, `instruction`, `docker_image`, `success_criteria`
    - Return `ExportResult` with counts
- [x] `pytest tests/test_exporter.py` → all pass (7 tests)
- [x] `git commit` → e57b013

---

## Phase 9: `serve.py` — State Machine

- [x] Write `scripts/serve.py`:
  - [x] Argument parsing: `--mode`, `--spec`, `--index`, `--llm-response`, `--input`, `--output`
  - [x] State file read/write: `{output_dir}/.clawharness_state.json`
  - [x] All JSON responses to stdout, all logs to stderr
  - [x] Implement all 13 modes: parse, parse_ingest, task_prompt, task_ingest, fs_prompt, fs_ingest, consistency_check, consistency_ingest, build, validate_prompt, validate_ingest, export, status
  - [x] Pipeline stage transitions + atomic state file writes
  - Smoke tested: parse → parse_ingest → task_prompt → task_ingest → status all work
- [x] `git commit` → 4e23cd7

---

## Phase 10: `SKILL.md`

- [x] Write `SKILL.md`:
  - [x] YAML frontmatter: name, description, requires (python3, docker)
  - [x] Trigger conditions (Chinese + English)
  - [x] Step-by-step instructions for the agent (Steps 1–7)
  - [x] Progress reporting rules (report after each step)
  - [x] Error handling rules (what to tell user on failure)
- [x] `git commit` → 182214a

---

## Phase 11: End-to-End Test

### 11a: via `mock_claw.py --api` (no OpenClaw needed)

- [ ] Make sure Colima is running: `colima start`
- [ ] Set `ANTHROPIC_API_KEY` env var
- [ ] Run:
  ```bash
  python scripts/mock_claw.py --api \
    --input "生成 3 个 cli-file-ops 的训练任务，easy 难度" \
    --output ~/clawharness-e2e-test
  ```
- [ ] Verify each step fires correctly (watch stderr logs):
  - [ ] `parse` → LLM → `parse_ingest`
  - [ ] 3x `task_prompt` → LLM → `task_ingest` → `fs_prompt` → LLM → `fs_ingest`
  - [ ] 3x `consistency_check` → pass
  - [ ] `build` → 3 images appear in `docker images | grep clawharness`
  - [ ] 3x `validate_prompt` → LLM → `validate_ingest` → pass
  - [ ] `export` → `~/clawharness-e2e-test/train.jsonl` exists with 3 lines
- [ ] Inspect output (same checks as 11b below)

### 11b: via OpenClaw (full integration)

- [ ] Make sure Colima is running: `colima start`
- [ ] Make sure OpenClaw gateway is running: `openclaw gateway status`
- [ ] Open OpenClaw session (TUI or browser)
- [ ] Send test message:
  ```
  帮我生成 3 个 cli-file-ops 的训练任务，easy 难度，输出到 ~/clawharness-e2e-test
  ```
- [ ] Verify each step fires correctly (watch stderr logs):
  - [ ] `parse` → LLM clarification → `parse_ingest`
  - [ ] 3x `task_prompt` → LLM → `task_ingest` → `fs_prompt` → LLM → `fs_ingest`
  - [ ] 3x `consistency_check` → pass
  - [ ] `build` → 3 images appear in `docker images | grep clawharness`
  - [ ] 3x `validate_prompt` → LLM → `validate_ingest` → pass
  - [ ] `export` → `~/clawharness-e2e-test/train.jsonl` exists with 3 lines
- [ ] Inspect output:
  ```bash
  cat ~/clawharness-e2e-test/train.jsonl | python3 -m json.tool
  ```
  - [ ] Each line has `task_id`, `instruction`, `docker_image`, `success_criteria`
  - [ ] `docker_image` points to a real image: `docker inspect clawharness/cli-file-ops/...`
- [ ] `git commit -m "e2e test passing"`
- [ ] `git tag v0.1.0`

---

## Phase 12: Paper Experiments (post-implementation)

- [ ] Run MetaClaw with Claw Harnessing output:
  ```bash
  metaclaw config openclaw_env_data_dir ~/clawharness-e2e-test
  metaclaw config openclaw_env_split train
  metaclaw start --mode skills_only
  ```
- [ ] Baseline: run same agent on MetaClaw-Bench hand-crafted tasks (same domain)
- [ ] Compare pass rate distributions
- [ ] Ablation: with vs without consistency checker (Phase 5)
- [ ] Write metrics to `~/clawharness-e2e-test/metrics.json` via `clawharness status --metrics`
