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
- [x] Verify OpenClaw sees the skill:
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

- [x] Make sure Colima is running: `colima start`
- [x] Set `ANTHROPIC_API_KEY` env var
- [x] Run mock_claw.py --api with claude-sonnet-4-6
- [x] Verify each step fires correctly:
  - [x] `parse` → LLM → `parse_ingest`
  - [x] 3x `task_prompt` → LLM → `task_ingest` → `fs_prompt` → LLM → `fs_ingest`
  - [x] 3x `consistency_check` → pass (soft warnings only)
  - [x] `build` → 3/3 images built successfully
  - [x] 3x `validate_prompt` → LLM → `validate_ingest` → 3/3 pass
  - [x] `export` → `~/clawharness-e2e-test/train.jsonl` with 3 tasks, 0 failed

### 11b: via OpenClaw (full integration)

- [ ] Make sure Colima is running: `colima start`
- [ ] Make sure OpenClaw gateway is running: `openclaw gateway status`
- [ ] Open OpenClaw session (TUI or browser)
- [ ] Send test message:
  ```
  帮我生成 3 个 cli-file-ops 的训练任务，easy 难度，输出到 ~/clawharness-e2e-test
  ```
- [x] Verify each step fires correctly:
  - [x] `parse` → LLM → `parse_ingest`
  - [x] 3x `task_prompt` → LLM → `task_ingest` → `fs_prompt` → LLM → `fs_ingest`
  - [x] 3x `consistency_check` → pass
  - [x] `build` → 3/3 Docker images built
  - [x] 3x `validate_prompt` → LLM → `validate_ingest` → 3/3 pass
  - [x] `export` → `~/clawharness-e2e-test/train.jsonl` with 3 tasks, 0 failed
- [x] Agent correctly reported results with task descriptions and MetaClaw usage instructions
- [x] `git tag v0.1.0` (tagged after 11a)

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

---

## v0.4 Roadmap: Core Quality Issues

从 E2E demo 中发现的 6 个系统性问题，按优先级排序。

---

### Issue 1: 任务同质化严重 (Task Diversity)

**问题：** 给定一个 prompt（如 "profile page"），LLM 反复生成同类任务（全是 "Create a Python script that generates HTML"）。20 个任务缺少多样性。

**根因：** `task_instruction.md` prompt 没有 diversity control。`ingest_instruction` 的 Jaccard 去重只检查文本相似度，不检查语义/结构多样性。

**修复方案：**
- [x] 在 `task_instruction.md` 加入 **7 种 task approach**（create, fix, refactor, test, optimize, integrate, migrate）
- [x] `generate_instruction_prompt()` 加入 **approach rotation**（index % 7）+ diversity stats in prior block
- [x] 增加 **structural dedup**：`_extract_structure()` 提取结构模式，>50% 同结构时拒绝
- [x] 在 prior_instructions_block 中加入 diversity note
- [x] 8 个新测试（structural dedup + approach rotation），185 tests total
- [x] `git commit` → f91ccb8

---

### Issue 2: Skill Prompts 不够自然 (Prompt Quality)

**问题：** 776 个 skill_prompts.json 中的 user_prompt 是从 skill description 模板转换的，很多不像用户真正会说的话（e.g. "I need to sync OpenClaw workspace between multiple machines"）。

**根因：** skill description 描述的是 skill 本身的功能，不是用户的请求。

**修复方案：**
- [ ] 用 LLM 批量重写 776 个 prompt：输入 skill name + description + category，输出 3 条自然的用户 prompt
- [ ] 每个 skill 生成 3 个变体 prompt（不同语气：命令式、提问式、描述式）
- [ ] 输出格式：`skill_prompts_v2.json`，每个 skill 有 `prompts: [str, str, str]`
- [ ] 人工抽样检查 50 条质量
- [ ] `git commit`

---

### Issue 3: 缺少 Skill 上下文注入 (Skill Context)

**问题：** 真实场景中 agent 带着 SKILL.md 的 procedural knowledge 做任务。我们只生成了 instruction + initial_fs，没有注入 skill 内容。SkillsBench 发现 curated Skills +16.2pp。

**根因：** Claw Harnessing 生成的环境没有 `environment/skills/` 目录。

**修复方案：**
- [ ] TaskSpec 增加 `skill_files: dict[str, str]` 字段（SKILL.md + scripts/）
- [ ] image_builder 把 skill_files 写入 Docker image 的 `/root/.claude/skills/` 或 `/workspace/skills/`
- [ ] 新增 `generate_skill_prompt()` — 让 LLM 为每个任务生成配套的 SKILL.md（procedural guidance，不是 solution）
- [ ] serve.py 增加 `skill_prompt` / `skill_ingest` mode
- [ ] 评估：同一任务 with/without skill 的 pass rate 差异
- [ ] `git commit`

---

### Issue 4: 缺少 Multi-step 交互 (Interactive Tasks)

**问题：** 所有任务都是 one-shot。真实使用中 agent 会多轮交互（clarify → execute → check → iterate）。

**根因：** 当前 validator 只支持单次 solver_actions 执行。

**修复方案：**
- [ ] 定义 `InteractiveTask` 类型：包含多个 step，每个 step 有 instruction + expected_state
- [ ] validator 支持多轮执行：step1 → check intermediate state → step2 → check → ... → final check
- [ ] 适用场景：git-workflow（create branch → make changes → commit → merge）、communication（list channels → find user → send message）
- [ ] 先为 git-workflow domain 实现，因为它天然有 sequential steps
- [ ] `git commit`

---

### Issue 5: 缺少真实数据 (Real-World Data)

**问题：** initial_fs 里的文件内容全是 LLM 编造的。SWE-bench 强在用真实 GitHub repo。

**根因：** 当前只有 LLM 生成路径，没有从真实 repo 提取。

**修复方案：**
- [ ] 新增 `scripts/core/repo_extractor.py`：给定 GitHub repo URL + commit range，提取有意义的 commit 对
- [ ] 参考 SWE-smith 方法：找有 test 改动的 PR，提取 base_commit state 作为 initial_fs，test changes 作为 verification
- [ ] 需要 GitHub API token（加到 config.json）
- [ ] 先对 3 个小型 Python repo 做 POC：提取 10 个真实 bug-fix 任务
- [ ] 与 LLM 生成的任务做 quality comparison
- [ ] `git commit`

---

### Issue 6: 难度梯度控制不足 (Difficulty Calibration)

**问题：** 虽然有 easy/medium/hard 参数，但实际生成的任务难度都差不多。E2E demo 中 20 个任务全是 easy level 的 "create a script"。

**根因：** difficulty 只影响 prompt 中的 guideline 文字，没有结构性约束。

**修复方案：**
- [ ] 定义 **difficulty template**：每个难度级别对应具体的结构约束
  - easy: 1 file, 1 function, <20 lines of code to write
  - medium: 2-3 files, needs to understand existing code, 20-50 lines
  - hard: 4+ files, cross-file dependencies, needs debugging/refactoring, 50+ lines
- [ ] `generate_fs_prompt()` 根据 difficulty 注入不同的 initial_fs 复杂度模板
- [ ] consistency_checker 验证生成的 initial_fs 复杂度匹配 difficulty
- [ ] 新增 difficulty metric：solver 需要的步骤数、修改的文件数、代码行数
- [ ] 测试：生成 easy/medium/hard 各 5 个任务，验证 hard 任务的 solver 步骤数 > easy
- [ ] `git commit`
