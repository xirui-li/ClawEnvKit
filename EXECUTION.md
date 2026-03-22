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

## Phase 0.5: `mock_claw.py` — Dev Harness

Without a running OpenClaw instance, we need a lightweight script that simulates the claw's role in the `serve.py` protocol: read JSON output, handle `llm_needed` responses, and call back with `--llm-response`.

- [ ] Write `scripts/mock_claw.py`:
  - [ ] Core loop: call `serve.py` via subprocess, parse stdout JSON
    - `status: "ok"` → log result, advance to next pipeline step
    - `status: "llm_needed"` → get LLM response (mode-dependent), call `serve.py --mode=<callback_mode> --llm-response=<response>`
    - `status: "error"` → log and abort
  - [ ] `--dry-run` mode (default):
    - Return canned JSON responses for each `callback_mode`
    - Canned responses stored in `tests/fixtures/canned_responses/` as JSON files, keyed by `callback_mode`
    - Enough to test pipeline state transitions without any LLM or Docker
  - [ ] `--api` mode:
    - Call Anthropic API directly with the `llm_call.prompt` (and optional `llm_call.system`)
    - Requires `ANTHROPIC_API_KEY` env var
    - Model: `claude-sonnet-4-6` (fast, cheap enough for dev)
  - [ ] Full pipeline orchestration:
    - `parse` → (LLM) → `parse_ingest`
    - For each task index: `task_prompt` → (LLM) → `task_ingest` → `fs_prompt` → (LLM) → `fs_ingest`
    - For each task index: `consistency_check` → (optional LLM) → `consistency_ingest`
    - `build`
    - For each task index: `validate_prompt` → (LLM) → `validate_ingest`
    - `export`
  - [ ] CLI args: `--input` (NL description), `--output` (output dir), `--dry-run`/`--api`, `--count` (override task count)
- [ ] Write canned response fixtures:
  - [ ] `tests/fixtures/canned_responses/parse_ingest.json` — a valid `GenerationSpec`
  - [ ] `tests/fixtures/canned_responses/task_ingest.json` — a valid instruction string
  - [ ] `tests/fixtures/canned_responses/fs_ingest.json` — valid `initial_fs` + `success_criteria`
  - [ ] `tests/fixtures/canned_responses/consistency_ingest.json` — `{"passed": true, "issues": []}`
  - [ ] `tests/fixtures/canned_responses/validate_ingest.json` — valid solver actions
- [ ] Smoke test: `python scripts/mock_claw.py --dry-run --input "3 cli tasks" --output ~/clawharness-test`
  - [ ] Pipeline runs through all stages without error
  - [ ] State file written to `~/clawharness-test/.clawharness_state.json`
- [ ] `git commit -m "mock_claw: dev harness for testing pipeline without OpenClaw"`

**Note:** `mock_claw.py` is a dev tool, not a production entry point. It will not be documented in README or SKILL.md. The `--api` mode is effectively the v0.2 `--backbone` feature, but scoped as internal tooling.

---

## Phase 1: `schema.py` — Data Structures

- [ ] Write `scripts/core/schema.py` with all dataclasses:
  - [ ] `GenerationSpec`
  - [ ] `TaskSpec` (with `task_type` field, v0.1 only supports `"code"`)
    - [ ] Include `base_tools: list[str]` field (copied from `GenerationSpec` at ingest time)
  - [ ] `SuccessCriterion` (four deterministic types only, no `llm_judge` in v0.1)
  - [ ] `ConsistencyResult`
  - [ ] `ConsistencyCheckResult`
  - [ ] `ValidationResult`
  - [ ] `BuildResult`
  - [ ] `ExportResult`
  - [ ] `IntentParserResult`
- [ ] Write `tests/test_schema.py`:
  - [ ] `TaskSpec` serializes/deserializes to JSON correctly
  - [ ] `SuccessCriterion` rejects invalid `type` values
  - [ ] `GenerationSpec` applies defaults for missing fields
- [ ] `pytest tests/test_schema.py` → all pass
- [ ] `git commit -m "schema: add all dataclasses"`

---

## Phase 2: Prompt Templates

- [ ] Write `prompts/intent_parse.md`
  - Input variables: `{description}`
  - Output: JSON matching `GenerationSpec` fields
  - Must enforce `task_types: ["code"]` for v0.1
  - Must return JSON only, no prose
- [ ] Write `prompts/task_instruction.md`
  - Input variables: `{domain}`, `{skill_target}`, `{difficulty}`, `{prior_instructions}`
  - Output: a single instruction string
  - Must produce instructions that are concrete, achievable, unambiguous
- [ ] Write `prompts/task_fs_criteria.md`
  - Input variables: `{domain}`, `{instruction}`, `{base_tools}`, `{difficulty}`
  - Output: JSON with `initial_fs` and `success_criteria`
  - Must restrict paths to `/workspace/`
  - Must restrict criterion types to `exit_code`, `file_exists`, `file_contains`, `file_not_contains`
- [ ] Write `prompts/task_solver.md`
  - Input variables: `{instruction}`, `{initial_fs_summary}`
  - Output: JSON with `reasoning` and `actions` (list of bash commands)
- [ ] Write `prompts/consistency_check.md`
  - Input variables: `{task_type}`, `{difficulty}`, `{instruction}`, `{initial_fs}`, `{success_criteria}`
  - Output: JSON with `passed` (bool) and `issues` (list of strings)
- [ ] Manual test each prompt: paste into OpenClaw session, verify output format
- [ ] `git commit -m "prompts: add all template files"`

---

## Phase 3: `intent_parser.py`

- [ ] Write `scripts/core/intent_parser.py`:
  - [ ] `parse(description, llm_response=None) -> IntentParserResult`
  - [ ] First call (no `llm_response`): load `prompts/intent_parse.md`, substitute `{description}`, return `needs_clarification` with prompt
  - [ ] Second call (with `llm_response`): parse JSON, apply defaults, validate fields, return `ready` with `GenerationSpec`
  - [ ] Handle malformed JSON: retry prompt (max 2), then raise `IntentParseError`
  - [ ] Map unknown domains to closest supported domain
- [ ] Write `tests/test_intent_parser.py`:
  - [ ] Valid LLM response → returns `GenerationSpec` with correct fields
  - [ ] Missing fields filled with defaults
  - [ ] Malformed JSON → retries, then raises `IntentParseError`
  - [ ] Unknown domain maps to closest match
  - [ ] `task_types` always contains only `["code"]` in v0.1
- [ ] `pytest tests/test_intent_parser.py` → all pass
- [ ] `git commit -m "intent_parser: parse NL description into GenerationSpec"`

---

## Phase 4: `task_generator.py`

- [ ] Write `scripts/core/task_generator.py`:
  - [ ] `generate_instruction_prompt(spec, index) -> str`
    - Load `prompts/task_instruction.md`
    - Substitute domain, skill_target (from `spec.skill_targets[index % len]`), difficulty, prior instructions
    - Return prompt string
  - [ ] `ingest_instruction(spec, index, llm_response) -> str`
    - Strip whitespace, validate non-empty
    - Check uniqueness against already-generated instructions (Jaccard < 0.7)
    - Return instruction string
  - [ ] `generate_fs_prompt(spec, instruction) -> str`
    - Load `prompts/task_fs_criteria.md`
    - Substitute domain, instruction, base_tools, difficulty
    - Return prompt string
  - [ ] `ingest_fs_and_criteria(spec, instruction, llm_response) -> TaskSpec`
    - Parse JSON response
    - Validate all paths start with `/workspace/`
    - Validate no `..` in paths
    - Validate criterion types are in allowed set
    - Copy `base_tools` from `GenerationSpec` into `TaskSpec`
    - Return `TaskSpec` (without `docker_image` set yet)
- [ ] Write `tests/test_task_generator.py`:
  - [ ] Instruction prompt contains domain and difficulty
  - [ ] Path traversal (`../etc/passwd`) is rejected
  - [ ] Paths outside `/workspace/` are rejected
  - [ ] Duplicate instructions (Jaccard > 0.7) trigger retry hint
  - [ ] Invalid criterion type raises `TaskGenerationError`
  - [ ] Difficulty heuristics: easy has ≤ 2 files, hard has ≥ 3
- [ ] `pytest tests/test_task_generator.py` → all pass
- [ ] `git commit -m "task_generator: generate instruction + initial_fs + criteria"`

---

## Phase 5: `consistency_checker.py`

- [ ] Write `scripts/core/consistency_checker.py`:
  - [ ] `check_deterministic(task) -> list[str]`
    - Extract quoted filenames from instruction (regex)
    - Check all referenced files exist in `initial_fs`
    - Check all criterion paths exist in `initial_fs`
    - Check difficulty heuristics (file count, criteria count)
    - Return list of issue strings (empty = pass)
  - [ ] `check_semantic_prompt(task) -> str`
    - Load `prompts/consistency_check.md`
    - Substitute task fields
    - Return prompt string
  - [ ] `check_semantic_ingest(task, llm_response) -> ConsistencyResult`
    - Parse JSON response
    - Set `regenerate=True` if issues are blocking (missing files, mismatched criteria)
    - Set `regenerate=False` for soft warnings (difficulty calibration)
  - [ ] `check(task, llm_response=None, skip_semantic=False) -> ConsistencyCheckResult`
    - Run deterministic first
    - Trigger semantic only for `hard` difficulty in v0.1 (no `review` type yet)
- [ ] Write `tests/test_consistency_checker.py`:
  - [ ] Missing file referenced in instruction → issue detected
  - [ ] Criterion path not in `initial_fs` → issue detected
  - [ ] Easy task with 3 files → soft warning, `regenerate=False`
  - [ ] Hard task with 1 criterion → soft warning, `regenerate=False`
  - [ ] Missing file → hard failure, `regenerate=True`
  - [ ] Cycle detection: same issue 3x → skip task
- [ ] `pytest tests/test_consistency_checker.py` → all pass
- [ ] `git commit -m "consistency_checker: deterministic + semantic review step"`

---

## Phase 6: `image_builder.py`

- [ ] Write `scripts/core/image_builder.py`:
  - [ ] `generate_dockerfile(task, base_image="alpine:3.19") -> str`
    - Tools layer first (cached), `COPY initial_fs/` layer second
    - Include tools from `task.spec.base_tools`
  - [ ] `build(task) -> BuildResult`
    - Build context in `~/.clawharness/build/<task_id>/` (not `/tmp/` — Colima)
    - Write `Dockerfile` + `initial_fs/` files
    - Run `docker build -t clawharness/<domain>/<task_id>:v1 <build_dir>`
    - Clean up build context in `finally`
    - Check `initial_fs` total size < 10MB before building
    - Return `BuildResult`
  - [ ] `build_batch(tasks, max_workers=4) -> list[BuildResult]`
    - `ThreadPoolExecutor`, failure-isolated
- [ ] Manual smoke test:
  ```bash
  python3 -c "
  from scripts.core.schema import *
  from scripts.core.image_builder import build
  task = TaskSpec(
    task_id='smoke-001', domain='cli-file-ops', difficulty='easy',
    skill_target='file create', task_type='code',
    instruction='Create hello.txt',
    initial_fs={'/workspace/README.md': 'create hello.txt'},
    success_criteria=[SuccessCriterion(type='file_exists', path='/workspace/hello.txt')],
    docker_image=''
  )
  result = build(task)
  print(result)
  "
  ```
  - [ ] Image appears in `docker images | grep clawharness`
- [ ] Write `tests/test_image_builder.py` (mocked subprocess):
  - [ ] `generate_dockerfile` puts tools layer before COPY layer
  - [ ] Build context is under `~/`, not `/tmp/`
  - [ ] Build context cleaned up on success
  - [ ] Build context cleaned up on failure (finally block)
  - [ ] `initial_fs` > 10MB raises error before build
  - [ ] Failed build in batch doesn't cancel others
  - [ ] Image name follows `clawharness/<domain>/<task_id>:v1`
- [ ] `pytest tests/test_image_builder.py` → all pass
- [ ] `git commit -m "image_builder: build Docker image from TaskSpec"`

---

## Phase 7: `validator.py`

- [ ] Write `scripts/core/validator.py`:
  - [ ] `validate_prompt(task) -> str`
    - Load `prompts/task_solver.md`
    - Substitute instruction + initial_fs summary
    - Return prompt string
  - [ ] `validate_with_solution(task, solver_actions) -> ValidationResult`
    - `docker run -d --network none <image>` → container_id
    - `try/finally`: always `docker stop` + `docker rm`
    - For each action: `docker exec <id> sh -c "<action>"` with 10s timeout
    - Check each `SuccessCriterion`:
      - `exit_code`: run cmd, check exit code
      - `file_exists`: `docker exec <id> test -f <path>`
      - `file_contains`: `docker exec <id> grep -q "<pattern>" <path>`
      - `file_not_contains`: `docker exec <id> grep -q "<pattern>" <path>` (expect failure)
    - Return `ValidationResult`
- [ ] Manual smoke test:
  ```bash
  # Build smoke image first (Phase 6 smoke test)
  # Then:
  python3 -c "
  from scripts.core.validator import validate_with_solution
  from scripts.core.schema import *
  task = TaskSpec(...)  # use smoke-001 from Phase 6
  task.docker_image = 'clawharness/cli-file-ops/smoke-001:v1'
  result = validate_with_solution(task, ['echo hello > /workspace/hello.txt'])
  print(result)
  "
  ```
  - [ ] `result.passed == True`
  - [ ] Container is removed after validation (`docker ps -a | grep smoke-001` → empty)
- [ ] Write `tests/test_validator.py` (mocked docker calls):
  - [ ] Container always stopped+removed even when criteria check raises
  - [ ] `exit_code` criterion passes on correct exit code
  - [ ] `file_contains` passes when pattern found
  - [ ] `file_not_contains` passes when pattern absent
  - [ ] Action timeout marks task failed without crashing
  - [ ] `--network none` always passed to `docker run`
- [ ] `pytest tests/test_validator.py` → all pass
- [ ] `git commit -m "validator: round-trip validation in Docker container"`

---

## Phase 8: `exporter.py`

- [ ] Write `scripts/core/exporter.py`:
  - [ ] `export(tasks, output_dir, split="train") -> ExportResult`
    - Filter out tasks where `validation_result.passed == False`
    - Write `{output_dir}/{split}.jsonl`
    - Each line: `task_id`, `instruction`, `docker_image`, `success_criteria`
    - Return `ExportResult` with counts
- [ ] `git commit -m "exporter: write train.jsonl"`

---

## Phase 9: `serve.py` — State Machine

- [ ] Write `scripts/serve.py`:
  - [ ] Argument parsing: `--mode`, `--spec`, `--index`, `--llm-response`, `--input`, `--output`
  - [ ] State file read/write: `{output_dir}/.clawharness_state.json`
  - [ ] All JSON responses to stdout, all logs to stderr
  - [ ] Implement all modes:
    - [ ] `parse`
    - [ ] `parse_ingest`
    - [ ] `task_prompt`
    - [ ] `task_ingest`
    - [ ] `fs_prompt`
    - [ ] `fs_ingest`
    - [ ] `consistency_check`
    - [ ] `consistency_ingest`
    - [ ] `build`
    - [ ] `validate_prompt`
    - [ ] `validate_ingest`
    - [ ] `export`
    - [ ] `status`
  - [ ] Pipeline stage transitions:
    `init → parsed → generating → consistency_checked → built → validating → exported`
  - [ ] Resume from last completed stage on re-run
- [ ] `git commit -m "serve.py: state machine orchestrator"`

---

## Phase 10: `SKILL.md`

- [ ] Write `SKILL.md`:
  - [ ] YAML frontmatter: name, description, requires (python3, docker)
  - [ ] Trigger conditions (Chinese + English)
  - [ ] Step-by-step instructions for the agent:
    - [ ] Step 1: call `serve.py --mode=parse`
    - [ ] Step 2: run LLM on returned prompt, call `serve.py --mode=parse_ingest`
    - [ ] Step 3: loop for each task — `task_prompt` → LLM → `task_ingest` → `fs_prompt` → LLM → `fs_ingest`
    - [ ] Step 4: call `serve.py --mode=consistency_check` for each task
    - [ ] Step 5: call `serve.py --mode=build`
    - [ ] Step 6: loop for each task — `validate_prompt` → LLM → `validate_ingest`
    - [ ] Step 7: call `serve.py --mode=export`
  - [ ] Progress reporting rules (report after each step)
  - [ ] Error handling rules (what to tell user on failure)
- [ ] `git commit -m "SKILL.md: OpenClaw skill entry point"`

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
