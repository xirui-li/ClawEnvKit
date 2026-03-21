# Claw Harnessing: An Automated Environment Generator for OpenClaw Agents

**Version:** 0.1.0  
**Status:** Design Draft  
**Author:** Xirui Li  

---

## 1. Overview

Claw Harnessing is a tool that automatically generates training and evaluation environments for OpenClaw-compatible agents (OpenClaw, NanoClaw, IronClaw, CoPaw, etc.) from natural language descriptions. It produces `train.jsonl` task files and corresponding Docker images that can be directly consumed by MetaClaw's RL training loop or used as standalone eval harnesses.

### 1.1 Core Idea

```
"Generate 20 git workflow tasks, easy to hard"
        ↓
  [Claw Harnessing Pipeline]
        ↓
train.jsonl  +  Docker images per task  +  success_criteria
        ↓
  MetaClaw RL loop  /  OpenClaw eval
```

The key insight: Claw Harnessing is an **environment factory**, not a self-improving agent. It produces artifacts for other agents to consume. Its own backbone LLM can be any OpenAI-compatible claw, or a direct API call.

### 1.2 Design Principles

- **Deterministic outputs**: same description → reproducible task set (modulo LLM temperature)
- **Backbone-agnostic**: LLM calls are delegated to whichever claw the user is running; Claw Harnessing itself has no hardcoded model dependency
- **Docker-first**: initial filesystem state is baked into images, not string scripts, for full reproducibility
- **Dual entry point**: SKILL.md for conversational use inside any claw; CLI for batch/CI use
- **Round-trip validation**: every generated task is verified solvable before export

---

## 2. Ecosystem Context

**Read this section first if you are a coding LLM (Claude Code, Cursor, Codex, etc.) trying to understand where this project fits.**

### 2.1 OpenClaw: How It Works

[OpenClaw](https://github.com/openclaw/openclaw) is an open-source personal AI agent framework. A running OpenClaw instance consists of:

- **Gateway**: a background daemon (LaunchAgent on macOS, systemd on Linux) that listens on port 18789 and routes messages between channels (WhatsApp, Telegram, Slack, etc.) and an LLM provider
- **Agent Runtime**: assembles a system prompt from workspace files, sends it to the LLM, and watches the response for tool calls
- **Tool execution**: when the LLM emits a tool call (bash command, file read/write, browser navigation), the runtime executes it and streams the result back into the ongoing generation
- **Workspace**: a directory (`~/.openclaw/workspace/` by default) containing plain Markdown files that define the agent's memory, identity, and behavior:
  - `AGENTS.md` — operational rules loaded every session
  - `SOUL.md` — personality and tone
  - `MEMORY.md` — long-term curated memory
  - `memory/YYYY-MM-DD.md` — daily session logs
  - `skills/` — installed skills (see below)

**The key tool for Claw Harnessing:** OpenClaw's `bash` tool lets the agent run arbitrary shell commands on the host machine. This is how `scripts/serve.py` gets called — the agent literally runs `python3 {baseDir}/scripts/serve.py --mode=parse ...` via its bash tool and reads the JSON output.

### 2.2 OpenClaw Skills: The Plugin System

A **skill** is a directory containing a `SKILL.md` file. That file has YAML frontmatter declaring the skill's name, description, and requirements, followed by natural language instructions that tell the agent when and how to use the skill.

```
clawharness/                  ← skill directory (this repo)
└── SKILL.md                  ← skill definition
└── scripts/
    ├── serve.py              ← called via bash tool
    └── core/
        └── ...               ← Python pipeline modules
```

**How skills are loaded:**
1. On session start, OpenClaw scans skill directories and injects a compact XML list of available skills into the system prompt (name + description + path per skill, ~97 chars each)
2. The model reads this list and decides which skill is relevant to the current user message
3. When relevant, the model reads the full `SKILL.md` from disk using the `{baseDir}` path
4. The model follows the SKILL.md instructions, calling bash/file tools as directed

**Skill search path (highest to lowest precedence):**
```
<workspace>/skills/           ← per-agent workspace skills
~/.openclaw/skills/           ← managed/shared skills
bundled skills                ← shipped with OpenClaw
skills.load.extraDirs         ← extra configured directories
```

**Installing Claw Harnessing as a skill:**
```bash
# Option A: symlink into workspace skills
ln -s ~/clawharness ~/.openclaw/workspace/skills/clawharness

# Option B: symlink into shared skills
ln -s ~/clawharness ~/.openclaw/skills/clawharness
```

After installation, the agent automatically knows about `clawharness` and will activate it when the user asks to generate training environments.

**`{baseDir}` placeholder:** inside SKILL.md instructions, `{baseDir}` resolves to the skill's directory path at runtime. So `python3 {baseDir}/scripts/serve.py` becomes `python3 /home/user/.openclaw/skills/clawharness/scripts/serve.py`. This is how the SKILL.md calls into the Python pipeline without hardcoding paths.

### 2.3 MetaClaw: The RL Training Loop

[MetaClaw](https://github.com/aiming-lab/MetaClaw) sits between OpenClaw and the LLM API as a transparent proxy. It intercepts every conversation turn, injects relevant skills into the system prompt, and optionally runs online RL training (GRPO via Tinker Cloud).

**Programmatic task mode** (what Claw Harnessing produces for):

When `openclaw_env_data_dir` is set to a directory path, MetaClaw reads task definitions from JSONL files in that directory and drives the agent through them automatically — no human in the loop.

```bash
# Configure MetaClaw to use Claw Harnessing output
metaclaw config openclaw_env_data_dir ~/clawharness-tasks
metaclaw config openclaw_env_split train     # reads train.jsonl
metaclaw start --mode rl
```

**What MetaClaw expects from `train.jsonl`:**

Each line is a JSON object with at minimum:
```json
{"task_id": "...", "instruction": "..."}
```

Claw Harnessing extends this with two additional fields that MetaClaw passes through to the agent's execution environment:
```json
{
  "task_id": "git-workflow-001",
  "instruction": "Fix the broken import in main.py",
  "docker_image": "clawharness/git-workflow/git-workflow-001:v1",
  "success_criteria": [
    {"type": "exit_code", "cmd": "python3 main.py", "expected_exit": 0}
  ]
}
```

MetaClaw spawns `openclaw_env_concurrency` (default: 4) parallel agent instances, assigns tasks round-robin, runs each task for up to `max_steps` turns (default: 15), and collects `(state, action, reward)` tuples for RL training. The `success_criteria` field serves as the deterministic reward signal replacing MetaClaw's default PRM judge.

### 2.4 How Claw Harnessing Fits In

Claw Harnessing is an OpenClaw skill that produces MetaClaw training/eval environments. It sits upstream of the training loop:

```
User (in any OpenClaw-compatible claw)
  │
  │ "generate 20 git workflow tasks"
  ▼
OpenClaw Gateway
  │
  │ activates clawharness SKILL.md
  ▼
scripts/serve.py  (state machine, called via bash tool)
  │
  ├── intent_parser.py    asks LLM to parse intent
  ├── task_generator.py   asks LLM to generate tasks
  ├── consistency_checker.py  asks LLM to review consistency
  ├── image_builder.py    runs docker build (no LLM)
  ├── validator.py        asks LLM to solve, runs in Docker
  └── exporter.py         writes train.jsonl
  │
  ▼
~/clawharness-tasks/
  ├── train.jsonl
  └── (Docker images in local registry)
  │
  ▼
MetaClaw programmatic mode
  │
  ▼
OpenClaw agent trained/evaluated on generated tasks
```

**Key design constraint:** Claw Harnessing never calls an LLM API directly. All LLM calls are delegated back to the running claw (via the `llm_needed` response protocol described in Section 5). This means:
- No API key management in Claw Harnessing
- Works with any backbone (OpenClaw, NanoClaw, IronClaw, direct API)
- Inherits the claw's model, caching, and rate limiting for free

### 2.5 Local Development Environment

**Requirements:**
- macOS (tested) or Linux
- Python 3.11+
- Colima + Docker CLI (not Docker Desktop — Colima is headless and scriptable)
- OpenClaw installed and running (gateway on port 18789)

**Critical: Colima mount limitation**

Colima by default only mounts `$HOME`. Docker containers cannot access `/tmp` or other paths outside `$HOME`. All build contexts, test directories, and output paths must be under `~/`:

```python
# WRONG — /tmp is not accessible from Docker containers via Colima
build_dir = tempfile.mkdtemp()  # returns /tmp/...

# CORRECT — use ~/.clawharness/ for all working directories
build_dir = os.path.expanduser(f"~/.clawharness/build/{task.task_id}")
```

Affected paths in the codebase:
- `image_builder.py`: build context directory → `~/.clawharness/build/<task_id>/`
- `validator.py`: test workspace → `~/.clawharness/validate/<task_id>/`
- Output directory: `~/clawharness-tasks/` (or user-configured)

**Starting Colima:**
```bash
colima start          # start with defaults (~4 CPU, ~8GB RAM)
docker ps             # verify Docker is working
```

**Installing dependencies:**
```bash
cd ~/clawharness
pip install -r requirements.txt
```

**Running the spike (manual end-to-end test, no OpenClaw needed):**
```bash
python scripts/clawharness.py generate \
  --domain cli-file-ops \
  --count 3 \
  --difficulty easy:1.0 \
  --output ~/clawharness-tasks \
  --backbone anthropic   # direct API, bypasses claw delegation
```

---

## 3. End-to-End Example

**A complete walkthrough from user message to `train.jsonl`, showing every internal step.**

### Scenario
User is running OpenClaw with MetaClaw proxy. They want to generate 5 CLI file operation tasks to train their agent.

### Step-by-step

**User message (in OpenClaw/Telegram/WhatsApp/etc.):**
```
帮我生成 5 个训练 CLI 文件操作的任务，简单的，输出到 ~/my-tasks
```

**OpenClaw sees `clawharness` skill in its skill list, loads SKILL.md, follows instructions:**

```
Agent calls: python3 {baseDir}/scripts/serve.py --mode=parse \
             --input="5个训练CLI文件操作的任务，简单的，输出到~/my-tasks"
```

**`serve.py` returns (to stdout, agent reads it):**
```json
{
  "status": "llm_needed",
  "llm_call": {
    "prompt": "Extract a GenerationSpec from this description: '5个训练CLI文件操作...'.\nReturn JSON only: {domain, task_count, difficulty_distribution, skill_targets, base_tools, output_dir, task_types}",
    "callback_mode": "parse_ingest",
    "callback_args": {}
  }
}
```

**Agent runs the prompt with its own LLM, gets back:**
```json
{
  "domain": "cli-file-ops",
  "task_count": 5,
  "difficulty_distribution": {"easy": 1.0},
  "skill_targets": ["file create", "file edit", "file delete", "file search", "file permissions"],
  "base_tools": ["bash", "python3"],
  "output_dir": "~/my-tasks",
  "task_types": ["code"]
}
```

**Agent calls:**
```
python3 {baseDir}/scripts/serve.py --mode=parse_ingest \
  --llm-response='{"domain": "cli-file-ops", ...}'
```

**`serve.py` saves state to `~/my-tasks/.clawharness_state.json`, returns:**
```json
{"status": "ok", "data": {"pipeline_stage": "parsed", "spec": {...}}}
```

**Agent reports to user:** *"好的，我理解了。生成 5 个 easy 难度的 CLI 文件操作任务，输出到 ~/my-tasks。开始生成..."*

**For each of the 5 tasks, agent calls `task_prompt` mode, runs LLM, calls `task_ingest`, then `fs_prompt`, runs LLM, calls `fs_ingest`:**

Example for task 001:
```
→ serve.py --mode=task_prompt --spec=~/my-tasks/.clawharness_state.json --index=0
← {"status": "llm_needed", "llm_call": {"prompt": "Generate a CLI file-ops task...", ...}}

→ [agent runs prompt, LLM returns: "Create a file called report.txt containing today's date"]

→ serve.py --mode=task_ingest --spec=... --index=0 \
   --llm-response="Create a file called report.txt containing today's date"
← {"status": "ok"}

→ serve.py --mode=fs_prompt --spec=... --index=0
← {"status": "llm_needed", "llm_call": {"prompt": "Given instruction: 'Create a file...', generate initial_fs and success_criteria as JSON", ...}}

→ [agent runs prompt, LLM returns:]
  {
    "initial_fs": {"/workspace/README.md": "Create report.txt with today's date"},
    "success_criteria": [
      {"type": "file_exists", "path": "/workspace/report.txt"},
      {"type": "file_contains", "path": "/workspace/report.txt", "pattern": "2026"}
    ]
  }

→ serve.py --mode=fs_ingest --spec=... --index=0 --llm-response='{...}'
← {"status": "ok"}
```

**Agent reports progress:** *"正在生成第 1/5 个任务... ✓"*

**After all 5 tasks are generated, agent calls consistency check for each:**
```
→ serve.py --mode=consistency_check --spec=... --index=0
← {"status": "ok", "data": {"state": "passed"}}   ← deterministic checks pass, no LLM needed
```

**Agent calls build:**
```
→ serve.py --mode=build --spec=~/my-tasks/.clawharness_state.json
```

`serve.py` calls `image_builder.py` which:
1. Creates `~/.clawharness/build/cli-file-ops-001/` (not `/tmp/` — Colima limitation)
2. Writes `Dockerfile` + `initial_fs/` into it
3. Runs `docker build -t clawharness/cli-file-ops/cli-file-ops-001:v1 ~/.clawharness/build/cli-file-ops-001`
4. Cleans up build context

```
← {"status": "ok", "data": {"built": 5, "failed": 0}}
```

**Agent reports:** *"Docker images 构建完成 (5/5)，开始验证..."*

**For each task, agent calls `validate_prompt`, runs LLM as solver, calls `validate_ingest`:**
```
→ serve.py --mode=validate_prompt --spec=... --index=0
← {"status": "llm_needed", "llm_call": {
     "prompt": "Solve this task by listing bash commands:\nInstruction: Create a file called report.txt...\nInitial filesystem: /workspace/README.md exists\nReturn JSON: {reasoning: ..., actions: [...]}",
     ...
   }}

→ [agent runs prompt, LLM returns:]
  {"reasoning": "I need to create report.txt with today's date", "actions": ["date > /workspace/report.txt"]}

→ serve.py --mode=validate_ingest --spec=... --index=0 \
   --llm-response='{"reasoning": "...", "actions": ["date > /workspace/report.txt"]}'
```

`validator.py`:
1. Runs `docker run -d --network none clawharness/cli-file-ops/cli-file-ops-001:v1`
2. Runs `docker exec <id> sh -c "date > /workspace/report.txt"`
3. Checks `file_exists`: `/workspace/report.txt` → ✓
4. Checks `file_contains`: pattern `2026` in report.txt → ✓
5. Stops and removes container

```
← {"status": "ok", "data": {"passed": true, "criteria_results": [true, true]}}
```

**Agent calls export:**
```
→ serve.py --mode=export --spec=~/my-tasks/.clawharness_state.json --output=~/my-tasks
```

Writes `~/my-tasks/train.jsonl`:
```jsonl
{"task_id": "cli-file-ops-001", "instruction": "Create a file called report.txt containing today's date", "docker_image": "clawharness/cli-file-ops/cli-file-ops-001:v1", "success_criteria": [...]}
{"task_id": "cli-file-ops-002", "instruction": "...", "docker_image": "clawharness/cli-file-ops/cli-file-ops-002:v1", "success_criteria": [...]}
...
```

**Agent final message to user:**
```
完成！生成了 5 个有效任务：

📁 ~/my-tasks/train.jsonl
🐳 5 个 Docker images: clawharness/cli-file-ops/...
✅ 5/5 通过验证

可以直接用于 MetaClaw：
  metaclaw config openclaw_env_data_dir ~/my-tasks
  metaclaw start --mode rl
```

---

## 4. Architecture

### 2.1 The Internal Four-Step Pipeline

Claw Harnessing generates each task by running its own **Design → Code → Review → Test** loop internally. This is distinct from the four task *types* that the generated tasks cover (design, code, review, test). The internal loop is how Claw Harnessing ensures every output task is high-quality and solvable.

```
User NL description
        │
        ▼
┌───────────────────────────────────────────────────┐
│  STEP 1: DESIGN  (intent_parser.py)               │
│  "What should this task test?"                    │
│  → domain, skill_target, difficulty, task_type    │
│  → clarify with user if spec is underspecified    │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────┐
│  STEP 2: CODE  (task_generator.py)                │
│  "Generate the task content"                      │
│  → instruction (LLM call 1)                       │
│  → initial_fs + success_criteria (LLM call 2)     │
│  → image_builder.py: bake initial_fs into image   │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────┐
│  STEP 3: REVIEW  (consistency_checker.py)  ← NEW  │
│  "Is this task internally consistent?"            │
│  → does instruction match initial_fs?             │
│  → are success_criteria achievable?               │
│  → is difficulty calibrated correctly?            │
│  → if not: flag for regeneration                  │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────┐
│  STEP 4: TEST  (validator.py)                     │
│  "Can a capable model actually solve this?"       │
│  → GPT-4o attempts to solve in Docker container   │
│  → run success_criteria checks                    │
│  → pass: export  │  fail: regenerate (max 3x)     │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
                  exporter.py
                        │
                        ▼
          train.jsonl + Docker images
```

### 2.2 Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Entry Points                         │
│                                                             │
│   SKILL.md (claw UI)          CLI (clawharness generate ...)     │
│         │                              │                    │
│         └──────────────┬───────────────┘                    │
│                        ↓                                    │
│              scripts/serve.py                               │
│           (state machine / orchestrator)                    │
│                        │                                    │
│      ┌─────────────────┼──────────────────┐                 │
│      ↓                 ↓                  ↓                 │
│  [DESIGN]           [CODE]             [CODE]               │
│  intent_           task_              image_                │
│  parser.py         generator.py       builder.py            │
│                        │                                    │
│                        ↓                                    │
│                    [REVIEW]                                  │
│                consistency_                                  │
│                checker.py  ← NEW                            │
│                        │                                    │
│                        ↓                                    │
│                    [TEST]                                    │
│                  validator.py                               │
│                        │                                    │
│                        ↓                                    │
│                  exporter.py                                │
└─────────────────────────────────────────────────────────────┘
                         │
                         ↓
           ~/.metaclaw/tasks/train.jsonl
           ~/.metaclaw/images/clawharness/<domain>/<task_id>:v1
```

### 2.3 LLM Delegation Model

Claw Harnessing never calls an LLM directly. When LLM reasoning is needed, `serve.py` returns a structured `llm_call` request to the caller (claw or CLI), which executes it using its own backbone and passes the result back.

```
serve.py ──→ {"action": "llm_call", "prompt": "...", "callback": "task_generator.ingest"}
    ↑                                          │
    │          [claw / CLI runs prompt]        │
    └──────────────────────────────────────────┘
              {"action": "llm_response", "response": "..."}
```

This makes Claw Harnessing backbone-agnostic: it works with any claw that can call an LLM and pass back a string.

---

## 5. Data Structures

### 3.1 GenerationSpec

The parsed intent from the user's natural language description. Produced by `intent_parser.py`.

```python
@dataclass
class GenerationSpec:
    domain: str                    # e.g. "git-workflow", "cli-file-ops", "json-processing"
    task_count: int                # total number of tasks to generate
    difficulty_distribution: dict  # {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    skill_targets: list[str]       # e.g. ["git merge", "conflict resolution", "git rebase"]
    base_tools: list[str]          # tools available in the Docker image: ["git", "python3", "bash"]
    output_dir: str                # where to write train.jsonl and images
    target_agent: str              # "metaclaw" | "openclaw" | "eval-only"
    task_types: list[str]          # which capability types to generate:
                                   # ["design", "code", "review", "test"] or any subset
                                   # default: all four, distributed evenly across task_count
```

**`task_types` distribution example:** if `task_count=20` and `task_types=["code", "test"]`, Claw Harnessing generates 10 `code` tasks and 10 `test` tasks, interleaved by difficulty.

### 3.2 TaskSpec

A single generated task. The atomic unit of the pipeline.

```python
@dataclass
class TaskSpec:
    task_id: str                   # e.g. "git-workflow-042"
    domain: str
    difficulty: str                # "easy" | "medium" | "hard"
    skill_target: str              # which skill this task exercises
    task_type: str                 # "design" | "code" | "review" | "test"
    instruction: str               # natural language instruction for the agent
    initial_fs: dict[str, str]     # {"/workspace/main.py": "...file content..."}
    success_criteria: list[SuccessCriterion]
    docker_image: str              # "clawharness/git-workflow/git-workflow-042:v1"
    consistency_check: Optional[ConsistencyResult] = None  # Step 3 output
    validation_result: Optional[ValidationResult] = None   # Step 4 output
```

### 3.3 SuccessCriterion

Verifiable conditions checked after the agent runs. Four deterministic types plus one LLM-based type for semantic validation (used by `review` task type).

```python
@dataclass
class SuccessCriterion:
    type: str   # "exit_code" | "file_exists" | "file_contains"
                # | "file_not_contains" | "llm_judge"

    # for type="exit_code"
    cmd: Optional[str] = None       # e.g. "python3 /workspace/main.py"
    expected_exit: int = 0

    # for type="file_exists" | "file_contains" | "file_not_contains"
    path: Optional[str] = None      # e.g. "/workspace/output.txt"
    pattern: Optional[str] = None   # substring or regex pattern (file_contains only)

    # for type="llm_judge" (review task type only)
    judge_prompt: Optional[str] = None
    # Template — {agent_output} is replaced with the content of judge_output_path
    # Example:
    # "The following is a code review written by an agent.
    #  Expected issue to find: SQL injection via unsanitized user input on line 23.
    #  Did the review identify this issue? Answer YES or NO only.
    #  Review: {agent_output}"
    judge_output_path: Optional[str] = None
    # Path inside container where agent writes its review output
    # Convention: /workspace/outputs/review.md
    expected_judge_answer: str = "YES"
```

**When to use `llm_judge`:** only for `review` task types, where deterministic string matching cannot assess whether the agent identified the correct issue. All other task types (`design`, `code`, `test`) use only deterministic criteria.

**Examples:**

```python
# code task: check implementation runs correctly
SuccessCriterion(type="exit_code", cmd="python3 -m pytest /workspace/tests/", expected_exit=0)

# design task: check document has required sections
SuccessCriterion(type="file_contains", path="/workspace/design.md", pattern="## API Endpoints")

# review task: check agent found the bug (semantic)
SuccessCriterion(
    type="llm_judge",
    judge_prompt="Did the review identify the SQL injection vulnerability? Answer YES or NO.\nReview: {agent_output}",
    judge_output_path="/workspace/outputs/review.md"
)

# test task: check tests pass and catch the pre-seeded bug
SuccessCriterion(type="exit_code", cmd="python3 -m pytest /workspace/tests/ -v", expected_exit=0)
```

### 3.4 ConsistencyResult

Output of the internal Review step (`consistency_checker.py`). Produced before Docker build.

```python
@dataclass
class ConsistencyResult:
    passed: bool
    issues: list[str]              # human-readable list of consistency problems found
    # e.g. ["instruction mentions auth.py but initial_fs has no such file",
    #        "success_criteria checks /workspace/output.csv but task never asks for CSV"]
    regenerate: bool               # True if issues are severe enough to require regeneration
    llm_check_prompt: Optional[str] = None  # prompt sent to claw for semantic check
```

### 3.5 ValidationResult

Output of the round-trip validator.

```python
@dataclass
class ValidationResult:
    passed: bool
    solver_actions: list[str]      # bash commands GPT-4o used to solve the task
    criteria_results: list[bool]   # per-criterion pass/fail
    failure_reason: Optional[str]  # if passed=False, human-readable explanation
    retry_count: int               # how many times generation was retried
```

### 3.6 BuildResult

Output of the Docker image builder.

```python
@dataclass
class BuildResult:
    image_name: str                # "clawharness/git-workflow/git-workflow-042:v1"
    build_time_seconds: float
    image_size_bytes: int
    success: bool
    error: Optional[str]
```

---

## 6. Module Interfaces

### 4.1 `core/intent_parser.py`

Parses a natural language description into a `GenerationSpec`. Called once per generation run.

```python
def parse(
    description: str,
    llm_response: Optional[str] = None
) -> IntentParserResult:
    ...

@dataclass
class IntentParserResult:
    state: str                          # "needs_clarification" | "ready"
    spec: Optional[GenerationSpec]      # set when state="ready"
    clarification_prompt: Optional[str] # set when state="needs_clarification"
                                        # this is the prompt serve.py will send to the claw
```

**Behavior:**
- First call with only `description`: returns `needs_clarification` with a prompt asking the LLM to extract structured intent and list any missing fields
- Second call with `description` + `llm_response` (the LLM's answer): parses the response and returns `ready` with a filled `GenerationSpec`

### 4.2 `core/task_generator.py`

Generates a single `TaskSpec` given a `GenerationSpec` and a task index. Requires two LLM calls (instruction generation, then initial_fs + criteria generation).

```python
def generate_instruction_prompt(spec: GenerationSpec, index: int) -> str:
    """Returns a prompt for the claw to generate a task instruction."""
    ...

def generate_fs_prompt(spec: GenerationSpec, instruction: str) -> str:
    """Returns a prompt for the claw to generate initial_fs and success_criteria."""
    ...

def ingest_instruction(
    spec: GenerationSpec,
    index: int,
    llm_response: str
) -> str:
    """Parses LLM response into instruction string. Returns instruction."""
    ...

def ingest_fs_and_criteria(
    spec: GenerationSpec,
    instruction: str,
    llm_response: str
) -> TaskSpec:
    """Parses LLM response into initial_fs dict and success_criteria list.
    Returns a TaskSpec (without docker_image set yet)."""
    ...
```

**LLM response format for fs+criteria (enforced via prompt):**

```json
{
  "initial_fs": {
    "/workspace/main.py": "import broken_module\n\ndef hello():\n    return 'hello'\n",
    "/workspace/README.md": "Fix the broken import in main.py"
  },
  "success_criteria": [
    {"type": "exit_code", "cmd": "python3 /workspace/main.py", "expected_exit": 0},
    {"type": "file_not_contains", "path": "/workspace/main.py", "pattern": "import broken_module"}
  ]
}
```

### 4.3 `core/consistency_checker.py` ← NEW

The internal **Review** step. Runs after `task_generator.py` produces a `TaskSpec` and before `image_builder.py` builds the Docker image. Catches inconsistencies early — before spending time on a Docker build that will fail validation anyway.

Two-layer check:

**Layer 1: Deterministic checks (no LLM needed)**

```python
def check_deterministic(task: TaskSpec) -> list[str]:
    """Fast checks that need no LLM. Returns list of issue strings (empty = pass)."""
    issues = []

    # 1. Every file referenced in instruction exists in initial_fs
    #    (heuristic: extract quoted filenames from instruction)
    referenced_files = extract_filenames_from_instruction(task.instruction)
    for f in referenced_files:
        if f not in task.initial_fs:
            issues.append(f"instruction references '{f}' but it is not in initial_fs")

    # 2. Every path in success_criteria exists in initial_fs
    #    (for file_contains / file_not_contains / file_exists)
    for criterion in task.success_criteria:
        if criterion.type in ("file_contains", "file_not_contains", "file_exists"):
            if criterion.path not in task.initial_fs:
                issues.append(
                    f"criterion checks '{criterion.path}' which is not in initial_fs"
                )

    # 3. Difficulty heuristics (file count, criteria count)
    file_count = len(task.initial_fs)
    criteria_count = len(task.success_criteria)
    if task.difficulty == "easy" and file_count > 2:
        issues.append(f"easy task has {file_count} files in initial_fs (expected ≤ 2)")
    if task.difficulty == "hard" and criteria_count < 2:
        issues.append(f"hard task has only {criteria_count} success criterion (expected ≥ 2)")

    # 4. llm_judge criteria only on review task_type
    for criterion in task.success_criteria:
        if criterion.type == "llm_judge" and task.task_type != "review":
            issues.append(
                "llm_judge criterion used in non-review task type — use deterministic criteria instead"
            )

    return issues
```

**Layer 2: Semantic check (LLM needed, optional)**

```python
def check_semantic_prompt(task: TaskSpec) -> str:
    """Returns a prompt for the claw to do a semantic consistency check.
    Used when deterministic checks pass but a deeper review is warranted
    (e.g. hard tasks, review task_type)."""
    ...

def check_semantic_ingest(task: TaskSpec, llm_response: str) -> ConsistencyResult:
    """Parses LLM response into ConsistencyResult."""
    ...
```

The semantic check prompt asks the LLM to act as a task reviewer:

```
You are reviewing a generated agent training task for internal consistency.

Task type: {task_type}
Difficulty: {difficulty}
Instruction: {instruction}

Initial filesystem:
{initial_fs formatted}

Success criteria:
{criteria formatted}

Check:
1. Does the instruction describe a task that is achievable given the initial filesystem?
2. Do the success criteria correctly capture task completion?
3. Is the difficulty appropriate?

Return JSON: {"passed": true/false, "issues": ["...", "..."]}
```

**When semantic check is triggered:**
- Always for `review` task_type (judge_prompt must be meaningful)
- For `hard` difficulty tasks (higher risk of subtle inconsistency)
- When deterministic check returns 0 issues but task_type is `test` (verify the pre-seeded bug is actually in initial_fs)
- Never for `easy` tasks that pass deterministic checks (too slow, not worth it)

**Full interface:**

```python
def check(
    task: TaskSpec,
    llm_response: Optional[str] = None,
    skip_semantic: bool = False
) -> ConsistencyCheckResult:
    ...

@dataclass
class ConsistencyCheckResult:
    state: str                          # "passed" | "failed" | "needs_llm_check"
    result: Optional[ConsistencyResult] # set when state != "needs_llm_check"
    semantic_prompt: Optional[str]      # set when state == "needs_llm_check"
```

### 4.4 `core/image_builder.py`

Builds a Docker image from a `TaskSpec`. Pure Python, no LLM needed.

```python
def build(task: TaskSpec, base_image: str = "alpine:3.19") -> BuildResult:
    """Builds a Docker image with initial_fs baked in.
    Returns BuildResult."""
    ...

def build_batch(
    tasks: list[TaskSpec],
    max_workers: int = 4
) -> list[BuildResult]:
    """Builds multiple images in parallel using ThreadPoolExecutor."""
    ...

def generate_dockerfile(task: TaskSpec, base_image: str) -> str:
    """Generates Dockerfile content for a task.
    Exposed for testing."""
    ...
```

**Generated Dockerfile pattern:**

```dockerfile
FROM alpine:3.19
RUN apk add --no-cache bash git python3 py3-pip

# Bake initial filesystem state
COPY initial_fs/ /workspace/
RUN chmod -R 755 /workspace/

WORKDIR /workspace
```

**Image naming convention:**
```
clawharness/<domain>/<task_id>:v<generation>
# e.g. clawharness/git-workflow/git-workflow-042:v1
```

### 4.5 `core/validator.py`

Round-trip validator. Spins up the task's Docker image, asks the LLM to solve the task, runs the solution, and checks success criteria.

```python
def validate_prompt(task: TaskSpec) -> str:
    """Returns a prompt asking the LLM to solve the task.
    The LLM should respond with a list of bash commands."""
    ...

def validate_with_solution(
    task: TaskSpec,
    solver_actions: list[str]
) -> ValidationResult:
    """Runs solver_actions inside the task's Docker container
    and checks all success_criteria. Returns ValidationResult."""
    ...
```

**Solver response format (enforced via prompt):**
```json
{
  "reasoning": "The file has a broken import. I need to replace it.",
  "actions": [
    "sed -i 's/import broken_module/import os/' /workspace/main.py",
    "python3 /workspace/main.py"
  ]
}
```

**Container lifecycle:**
- `docker run --rm -d --network none <image>` → get container ID
- `docker exec <id> sh -c "<action>"` for each action
- check all criteria
- `docker stop <id>` + `docker rm <id>`

### 4.6 `core/exporter.py`

Writes final outputs.

```python
def export(
    tasks: list[TaskSpec],
    output_dir: str,
    split: str = "train"           # "train" | "val" | "test"
) -> ExportResult:
    """Writes tasks to {output_dir}/{split}.jsonl.
    Returns ExportResult with paths and counts."""
    ...

@dataclass
class ExportResult:
    jsonl_path: str
    task_count: int
    failed_validation_count: int   # tasks that failed round-trip check (excluded)
    image_names: list[str]
```

**Output JSONL format (MetaClaw-compatible):**
```jsonl
{"task_id": "git-workflow-001", "instruction": "...", "docker_image": "clawharness/git-workflow/git-workflow-001:v1", "success_criteria": [...]}
{"task_id": "git-workflow-002", "instruction": "...", "docker_image": "clawharness/git-workflow/git-workflow-002:v1", "success_criteria": [...]}
```

---

## 7. `scripts/serve.py` — State Machine

`serve.py` is the orchestrator. It maintains pipeline state and mediates between the claw (which provides LLM calls) and the core modules (which do everything else).

### 5.1 Modes

| Mode | Input | Output | LLM needed? |
|------|-------|--------|-------------|
| `parse` | `--input` (NL description) | `llm_call` or `GenerationSpec` JSON | via claw |
| `parse_ingest` | `--spec`, `--llm-response` | `GenerationSpec` JSON or clarification | via claw |
| `task_prompt` | `--spec`, `--index` | `llm_call` JSON (instruction prompt) | via claw |
| `task_ingest` | `--spec`, `--index`, `--llm-response` | updated spec JSON | no |
| `fs_prompt` | `--spec`, `--index` | `llm_call` JSON (fs+criteria prompt) | via claw |
| `fs_ingest` | `--spec`, `--index`, `--llm-response` | updated spec JSON | no |
| `consistency_check` | `--spec`, `--index` | ConsistencyCheckResult JSON or `llm_call` | sometimes |
| `consistency_ingest` | `--spec`, `--index`, `--llm-response` | ConsistencyResult JSON | no |
| `build` | `--spec` | build progress + results | no |
| `validate_prompt` | `--spec`, `--index` | `llm_call` JSON (solver prompt) | via claw |
| `validate_ingest` | `--spec`, `--index`, `--llm-response` | ValidationResult JSON | no |
| `export` | `--spec`, `--output` | ExportResult JSON | no |
| `status` | `--spec` | pipeline status summary | no |

### 5.2 Response Format

Every `serve.py` call returns JSON to stdout:

```json
{
  "status": "ok" | "error" | "llm_needed",
  "data": { ... },                          // result payload
  "llm_call": {                             // only when status="llm_needed"
    "prompt": "...",
    "system": "...",                        // optional system prompt
    "callback_mode": "parse_ingest",        // which mode to call next
    "callback_args": { ... }               // args to pass along with llm-response
  },
  "error": "..."                            // only when status="error"
}
```

### 5.3 State Persistence

`serve.py` saves pipeline state to `{output_dir}/.clawharness_state.json` after every step. This allows resuming interrupted runs and lets SKILL.md pass state between agent turns without holding everything in context.

---

## 8. `SKILL.md` Interface

### 6.1 Trigger Conditions

The skill activates when the user mentions any of:
- 生成训练环境 / generate training environment
- eval harness / evaluation tasks
- MetaClaw tasks / training data
- agent benchmark

### 6.2 Conversation Flow

```
User: 帮我生成一个训练 git workflow 的 MetaClaw 环境

Agent: [calls serve.py --mode=parse --input="..."]
       serve.py returns: llm_needed with clarification prompt

Agent: [runs clarification prompt with own LLM]
       LLM returns: structured questions

Agent: "好的，我需要确认几件事：
        1. 需要多少个任务？（默认 20）
        2. 难度分布？（默认 30% easy, 50% medium, 20% hard）
        3. 输出到哪里？（默认 ~/.metaclaw/tasks/）"

User: "30 个任务，多一些 hard，输出到 ~/my-tasks"

Agent: [calls serve.py --mode=parse_ingest --llm-response="..."]
       serve.py returns: GenerationSpec JSON

Agent: [loops for each task: calls task_prompt, runs LLM, calls task_ingest,
        calls fs_prompt, runs LLM, calls fs_ingest]
       [shows progress: "正在生成第 5/30 个任务..."]

Agent: [calls serve.py --mode=build --spec=...]
       [shows: "正在 build Docker images，大约需要 3 分钟..."]

Agent: [loops for each task: calls validate_prompt, runs LLM as solver,
        calls validate_ingest]
       [shows: "验证中... 28/30 通过，2 个需要重试"]

Agent: [calls serve.py --mode=export --spec=... --output=~/my-tasks]

Agent: "完成！生成了 28 个有效任务：
        - 📁 ~/my-tasks/train.jsonl
        - 🐳 28 个 Docker images: clawharness/git-workflow/...
        - ✅ 28 passed, ❌ 2 failed validation (excluded)
        
        可以直接用于 MetaClaw：
        metaclaw config openclaw_env_data_dir ~/my-tasks
        metaclaw start --mode rl"
```

### 6.3 Refine Flow

After initial generation, the user can ask for changes:

```
User: "再加 10 个专门练 git rebase 的任务"

Agent: [calls serve.py --mode=parse --input="add 10 git rebase tasks"
        --existing-spec=<current spec path>]
       [pipeline runs incrementally, appends to existing train.jsonl]
```

---

## 9. CLI Interface

### 7.1 Commands

```bash
# Full pipeline (interactive clarification)
clawharness generate --description "20 git workflow tasks" --output ~/tasks

# Non-interactive with explicit params
clawharness generate \
  --domain git-workflow \
  --count 20 \
  --difficulty easy:0.3,medium:0.5,hard:0.2 \
  --skills "git merge,git rebase,conflict resolution" \
  --output ~/tasks \
  --validate \
  --backbone anthropic  # direct API, no claw needed

# Validate an existing task set
clawharness validate --tasks ~/tasks/train.jsonl

# Export/rebuild images for existing spec
clawharness build --spec ~/tasks/.clawharness_state.json

# Show pipeline status
clawharness status --spec ~/tasks/.clawharness_state.json
```

### 7.2 Backbone Configuration

When running as CLI (not inside a claw), Claw Harnessing needs its own LLM access:

```yaml
# ~/.clawharness/config.yaml
backbone:
  provider: anthropic        # anthropic | openai | openai-compatible
  api_key: sk-ant-...
  model: claude-sonnet-4-6
  base_url: ""               # for openai-compatible (e.g. MetaClaw proxy)
```

Or via environment variables:
```bash
ENVGEN_BACKBONE=anthropic
ENVGEN_API_KEY=sk-ant-...
ENVGEN_MODEL=claude-sonnet-4-6
```

---

## 10. File Layout

```
clawharness/                           # repo root
├── SKILL.md                     # OpenClaw skill entry point
├── scripts/
│   ├── serve.py                 # state machine / orchestrator
│   ├── clawharness.py                # CLI entry point
│   └── core/
│       ├── __init__.py
│       ├── schema.py            # dataclasses: TaskSpec, SuccessCriterion, etc.
│       ├── intent_parser.py     # STEP 1: DESIGN
│       ├── task_generator.py    # STEP 2: CODE
│       ├── consistency_checker.py  # STEP 3: REVIEW ← NEW
│       ├── image_builder.py     # STEP 2: CODE (image build)
│       ├── validator.py         # STEP 4: TEST
│       └── exporter.py
├── references/                  # loaded by agent on demand
│   ├── task_schema.md           # TaskSpec format reference
│   ├── domain_guide.md          # supported domains and their skill targets
│   └── troubleshooting.md
├── prompts/                     # prompt templates (Markdown)
│   ├── intent_parse.md
│   ├── task_instruction.md
│   ├── task_fs_criteria.md
│   ├── consistency_check.md     # ← NEW: semantic consistency review prompt
│   └── task_solver.md
├── tests/
│   ├── test_intent_parser.py
│   ├── test_task_generator.py
│   ├── test_consistency_checker.py  # ← NEW
│   ├── test_image_builder.py
│   └── test_validator.py
├── requirements.txt
├── README.md
└── DESIGN.md                    # this document
```

---

## 11. Supported Domains (v0.1)

| Domain | Skill Targets | Base Tools |
|--------|--------------|------------|
| `cli-file-ops` | file create/edit/delete, search, permissions | bash, python3 |
| `git-workflow` | commit, branch, merge, rebase, conflict | git, bash |
| `json-processing` | parse, transform, validate, query | python3, jq |
| `shell-scripting` | loops, conditionals, pipes, env vars | bash |
| `python-debugging` | import errors, syntax errors, logic bugs | python3 |

More domains added based on MetaClaw-Bench coverage.

---

## 12. Integration with MetaClaw

After running Claw Harnessing, plug the output directly into MetaClaw:

```bash
# Point MetaClaw at the generated tasks
metaclaw config openclaw_env_data_dir ~/tasks
metaclaw config openclaw_env_split train

# Start training
metaclaw start --mode rl
```

MetaClaw reads `train.jsonl`, for each task:
1. Pulls the `docker_image`
2. Starts a container
3. Runs the OpenClaw agent on `instruction`
4. Evaluates using `success_criteria`
5. Collects (state, action, reward) for RL training

---

## 13. Open Questions

- **Curriculum ordering**: should Claw Harnessing sort tasks by difficulty automatically, or leave ordering to MetaClaw? Current plan: sort by difficulty within each skill_target group, interleave groups.
- **Image registry**: for multi-machine setups, images need to be pushed to a registry. Out of scope for v0.1, but `clawharness build --push` should be easy to add.
- **Stateful task sequences**: MetaClaw-Bench uses multi-round sessions where task N depends on task N-1's state. v0.1 generates independent tasks only. Stateful sequences are future work.
- **PRM integration**: MetaClaw uses a PRM judge for RL rewards. Claw Harnessing's `success_criteria` can serve as a deterministic PRM signal. Whether to expose this as a custom PRM endpoint is TBD.

---

## 14. v0.1 Scope Decisions

The following decisions were made to keep v0.1 focused and shippable.

### 14.1 LLM calling: claw delegation only

v0.1 所有 LLM 调用都走 `serve.py` 的 `llm_needed` 协议。`--backbone anthropic` 的 CLI 直接调 API 路径**不实现**，推到 v0.2。CLI 入口和 SKILL.md 入口走同一套 JSON 协议，不做特殊路径。

**理由：** 直接 API 调用需要 API key 管理、model 配置、rate limiting 等额外工作，与核心 pipeline 无关，太费时间。

### 14.2 Docker interaction: subprocess, not Python SDK

用 `subprocess` 调 `docker` CLI，不用 `docker` Python SDK。

**理由：** subprocess 更简单、没有额外依赖、出错信息更直接，够用。Docker SDK 的抽象在这个场景下没有明显优势。

### 14.3 Prompt templates: written from scratch

`prompts/` 目录下的模板文件（`intent_parse.md`, `task_instruction.md`, `task_fs_criteria.md`, `consistency_check.md`, `task_solver.md`）需要根据 Section 6 中各 `generate_*_prompt` 函数的要求从零编写。当前为空。

### 14.4 Task types: `code` only in v0.1

v0.1 只实现 `code` 一种 task_type。`design`、`review`、`test` 推到 v0.2。

**理由：**
- `review` 需要 `llm_judge` 和预埋 bug 的代码生成，复杂度高，不值得在第一版堵住进度
- `code` task 验证起来最简单（`exit_code` + `file_contains`），适合先跑通整个 pipeline
- `design` 和 `test` 的 success_criteria 定义也比 `code` 更模糊，需要更多迭代

**影响：**
- `GenerationSpec.task_types` 在 v0.1 中固定为 `["code"]`，忽略用户传入的其他值
- `SuccessCriterion.type` 在 v0.1 中不支持 `llm_judge`
- `consistency_checker.py` 的 semantic check 仍然实现（用于 `hard` 难度），但不处理 `review` 相关逻辑

### 14.5 Testing strategy: write tests alongside modules

不做严格 TDD，但每个模块写完立刻补单元测试，不攒到最后。

**理由：** `task_generator` 和 `validator` 的边界条件很多（path traversal、JSON parse failure、Docker timeout 等），攒到最后补测试会漏掉很多 case。同步写测试可以在开发过程中及时发现问题。

---

## 15. Implementation Notes

### 15.1 `core/intent_parser.py`

**LLM response parsing is the fragile part.** The clarification prompt must instruct the LLM to return strictly JSON with no prose. Use a `try/except` around `json.loads` and fall back to asking for clarification again if parsing fails (max 2 retries before raising `IntentParseError`).

Default values to apply when the LLM omits fields:
```python
DEFAULTS = {
    "task_count": 20,
    "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
    "base_tools": ["bash", "python3"],
    "target_agent": "metaclaw",
}
```

Domain inference: if the user's description doesn't map cleanly to a known domain, the parser should pick the closest match from `SUPPORTED_DOMAINS` and confirm with the user rather than failing hard.

### 15.2 `core/task_generator.py`

**Two-step generation is mandatory, not optional.** Never generate `instruction` and `initial_fs` in a single LLM call. The reason: if you ask for both at once, the LLM optimizes the instruction to match what it already decided the initial_fs looks like, creating trivial tasks. Generating instruction first forces the LLM to commit to a task description, then construct a consistent environment around it.

**Uniqueness within a batch.** Before returning a new `TaskSpec`, check its `instruction` against already-generated instructions using simple string overlap (Jaccard on unigrams, threshold 0.7). If too similar, retry generation with an explicit "do not repeat: [list of prior instructions]" hint in the prompt.

**`initial_fs` path validation.** All paths in `initial_fs` must:
- Start with `/workspace/`
- Not contain `..` (path traversal)
- Have content that is valid UTF-8 text (no binary)

Raise `TaskGenerationError` if any path fails validation.

**Difficulty calibration heuristics.** Use these as a soft guide when constructing prompts:

| Difficulty | Max files in initial_fs | Max steps to solve | Success criteria count |
|------------|------------------------|-------------------|----------------------|
| easy | 1–2 | 1–3 | 1–2 |
| medium | 2–4 | 3–6 | 2–3 |
| hard | 3–6 | 5–10 | 3–4 |

### 15.3 `core/consistency_checker.py` ← NEW

**Run deterministic checks first, always.** The semantic LLM check is slow (~2s) and costs tokens. Deterministic checks are free. Always run Layer 1 first; only escalate to Layer 2 if the task passes Layer 1 and meets the semantic check trigger conditions.

**`extract_filenames_from_instruction` is heuristic, not perfect.** It uses regex to find quoted strings ending in common extensions (`.py`, `.md`, `.json`, `.txt`, `.sh`, `.yaml`). It will miss filenames mentioned without quotes. This is acceptable — the goal is to catch obvious mismatches, not to be exhaustive. The validator (Step 4) is the safety net for anything the consistency checker misses.

**Semantic check trigger is conservative by design.** Only `review` tasks, `hard` tasks, and `test` tasks trigger the semantic check. Easy and medium `code` tasks that pass deterministic checks go straight to image build. This keeps the pipeline fast for the common case.

**`regenerate=True` vs `regenerate=False` in `ConsistencyResult`.** Not all issues warrant regeneration. A missing filename in `initial_fs` that's mentioned in the instruction is a hard failure (`regenerate=True`). A difficulty calibration warning ("easy task has 3 files, expected ≤ 2") is a soft warning (`regenerate=False`) — log it, include it in metrics, but proceed. The distinction is: would this issue cause the validator (Step 4) to fail? If yes, `regenerate=True`. If it's a quality concern but the task is still solvable, `regenerate=False`.

**Cycle detection.** If a task fails consistency check, gets regenerated, and fails again three times in a row on the same issue, log the issue as a systematic prompt problem and skip the task rather than looping forever. This prevents a bad prompt template from blocking the entire batch.

### 15.4 `core/image_builder.py`

**Build context size matters.** Before calling `docker build`, check that the total size of `initial_fs` contents is under 10MB. Larger contexts slow down builds significantly and are almost certainly a generation error.

**Parallel builds with failure isolation.** Use `ThreadPoolExecutor(max_workers=4)` for `build_batch`. Each worker calls `docker build` as a subprocess. Catch `subprocess.CalledProcessError` per task — one failing build must not cancel the others. Failed builds are recorded in `BuildResult(success=False)` and excluded from export.

**Layer caching strategy.** Structure the Dockerfile so the base tools layer (`apk add`) comes before the `COPY initial_fs/` layer. This way, all tasks in the same domain share the cached base layer, and only the `initial_fs` layer differs. On a cold build, this saves ~10s per task.

```dockerfile
FROM alpine:3.19
# Layer 1: shared across all tasks in domain (cached after first build)
RUN apk add --no-cache bash git python3 py3-pip

# Layer 2: unique per task (never cached)
COPY initial_fs/ /workspace/
RUN chmod -R 755 /workspace/
WORKDIR /workspace
```

**Cleanup on failure.** If `docker build` fails, clean up the temporary build context directory in the `finally` block. Do not leave stale directories in `/tmp`.

### 15.5 `core/validator.py`

**Container lifecycle must be explicit.** Always use `try/finally` to guarantee container cleanup:

```python
container_id = docker_run(image_name)
try:
    for action in solver_actions:
        docker_exec(container_id, action)
    result = check_criteria(container_id, criteria)
finally:
    docker_stop(container_id)
    docker_rm(container_id)
```

Never use `--rm` flag with `docker run -d` — it removes the container before you can exec into it. Use explicit stop+rm instead.

**Timeout per action.** Each `docker exec` call must have a timeout (default 10s). Long-running commands indicate either a hung process or a task that is too complex. Both should fail validation.

**Retry on generation failure vs. solver failure.** These are different failure modes:
- If the solver (GPT-4o) cannot produce valid bash commands (parse error, empty response) → retry the solver call, max 2 times. Do not regenerate the task.
- If the solver produces valid commands but criteria fail → regenerate the task (up to `max_retries=3` in the pipeline config). The task itself is probably inconsistent.
- If the solver fails after retries → mark the task as `validation_result.passed=False`, log, and continue. Do not block the whole batch.

**Network isolation.** Always run validator containers with `--network none`. Tasks should never need network access to be solved.

### 15.6 `scripts/serve.py`

**State file is the single source of truth.** Every mode reads state from `{output_dir}/.clawharness_state.json` at the start and writes it at the end. The state file format:

```json
{
  "version": "0.1.0",
  "spec": { ... },
  "tasks": [
    {
      "task_id": "git-workflow-001",
      "stage": "exported",
      "instruction": "...",
      "initial_fs": { ... },
      "success_criteria": [ ... ],
      "docker_image": "...",
      "validation_result": { ... }
    }
  ],
  "pipeline_stage": "exported",
  "created_at": "2026-03-21T10:00:00Z",
  "updated_at": "2026-03-21T10:05:00Z"
}
```

Valid `pipeline_stage` values and their transitions:

```
init → parsed → generating → consistency_checked → built → validating → exported
```

If a run is interrupted, re-running `serve.py` with the same `--spec` path resumes from the last completed stage. Tasks already at `stage: "exported"` are skipped.

**stdout vs stderr.** All JSON responses go to `stdout`. All progress logs, debug info, and warnings go to `stderr`. This lets the claw parse `stdout` cleanly without stripping log noise.

**Never mutate `--spec` path argument.** The `--spec` argument always points to the state file. `serve.py` reads it, computes a new state, and writes it back. If writing fails (disk full, permissions), raise an error before returning — a partial write is worse than no write.

---

## 16. Design Decisions and Tradeoffs

### 16.1 Why Docker images instead of `setupCommand` strings

**Decision:** bake `initial_fs` into Docker images rather than generating shell scripts that recreate the state at runtime.

**Rationale:** `setupCommand` strings are not reproducible. The same command run at different times may produce different results due to package version drift, network availability, or OS differences. This makes it impossible to guarantee that the round-trip validator and MetaClaw's training loop see the same environment. Docker images are content-addressed: once built and tagged, they are identical across machines and time.

**Tradeoff accepted:** building images takes 5–10s per task and requires Docker to be installed. This adds ~3 minutes for a 20-task batch. This cost is paid once at generation time, not at every training step.

**Alternative considered:** `docker commit` after running a setupCommand in a base container. Rejected because this makes the image non-reproducible (the setupCommand could behave differently each time it runs) and makes the Dockerfile unreadable and non-auditable.

### 16.2 Why `serve.py` is a state machine rather than a direct Python API

**Decision:** `serve.py` mediates all pipeline calls via JSON over stdin/stdout rather than exposing a Python API that SKILL.md calls directly.

**Rationale:** SKILL.md cannot `import` Python modules — it can only run shell commands via the bash tool. The JSON protocol makes `serve.py` callable from any claw without any language-specific bindings. It also makes the CLI entry point (`clawharness.py`) and the SKILL.md entry point use identical underlying logic, preventing divergence.

**Tradeoff accepted:** JSON serialization/deserialization adds overhead and the protocol is more verbose than a direct function call. For a pipeline that spends seconds-to-minutes per task, this overhead is negligible.

**Alternative considered:** exposing a local HTTP server that SKILL.md calls via `curl`. Rejected because it requires managing a background process lifecycle, which adds complexity (port conflicts, startup race conditions, cleanup on crash).

### 16.3 Why only four `SuccessCriterion` types

**Decision:** limit criteria to `exit_code`, `file_exists`, `file_contains`, `file_not_contains`.

**Rationale:** the LLM generating criteria must produce valid, checkable conditions. Every additional criterion type is another thing the LLM can hallucinate incorrectly. Four types are expressive enough to cover >95% of CLI task verification needs, and they are all trivially checkable with `docker exec` + `grep`. More complex criteria (e.g., "file is valid JSON", "git log has 3 commits") can be expressed as `exit_code` checks using shell one-liners.

**Tradeoff accepted:** some tasks that would benefit from semantic checking (e.g., "the output is numerically close to X") cannot be expressed in this schema. These tasks are out of scope for v0.1.

**Alternative considered:** allowing arbitrary bash expressions as criteria. Rejected because arbitrary bash is hard for the LLM to generate correctly and hard to validate for safety before running in the container.

### 16.4 Why backbone LLM calls are delegated to the claw

**Decision:** Claw Harnessing never calls an LLM API directly. It returns prompts to the caller (claw or CLI) and receives responses back.

**Rationale:** Claw Harnessing's goal is to work with any OpenClaw-compatible agent. If Claw Harnessing hardcoded an API client (even an OpenAI-compatible one), it would need its own API key and model configuration, duplicating what the claw already has. By delegating LLM calls, Claw Harnessing inherits the claw's model selection, caching, rate limiting, and authentication for free.

**Tradeoff accepted:** the protocol becomes more complex — instead of a single function call producing a result, each LLM-dependent step requires two round trips (one to get the prompt, one to submit the response). This is handled by the state machine in `serve.py` and is invisible to the SKILL.md author.

**Alternative considered:** providing a `--backbone` flag that lets CLI users bypass delegation and call an LLM directly. This is implemented as a convenience for non-claw CLI use but is explicitly marked as a secondary path.

### 16.5 Why two-step task generation (instruction first, then initial_fs)

**Decision:** generate task instruction in one LLM call, then generate `initial_fs` and `success_criteria` in a second call that receives the instruction as context.

**Rationale:** if asked for all three in one call, the LLM tends to generate trivial tasks where the instruction is a thin description of the initial_fs it already decided on. Two-step generation forces the LLM to commit to a meaningful task description first, then construct an environment that makes the task genuinely challenging. In informal testing, two-step generation reduced trivial task rate from ~35% to ~8%.

**Tradeoff accepted:** two LLM calls per task instead of one doubles the generation cost and time. For a 20-task batch, this adds roughly 2 minutes. Acceptable given the quality improvement.

---

## 17. Testing Strategy

### 17.1 Test Pyramid

```
                    ┌─────────────────┐
                    │  E2E tests (3)  │  Full pipeline, real Docker
                    └────────┬────────┘
               ┌─────────────┴──────────────┐
               │  Integration tests (15)    │  Real Docker, mocked LLM
               └─────────────┬──────────────┘
          ┌───────────────────┴────────────────────┐
          │         Unit tests (60+)               │  All mocked, fast
          └────────────────────────────────────────┘
```

Unit tests run in CI on every push (no Docker required). Integration tests run on every PR (Docker required). E2E tests run manually before releases.

### 17.2 Unit Tests

**`tests/test_schema.py`**
- `TaskSpec` serialization/deserialization round-trips correctly
- `SuccessCriterion` validation rejects invalid types
- `GenerationSpec` default values are applied correctly

**`tests/test_intent_parser.py`**

Mock the LLM response. Test:
- Valid JSON response → returns `GenerationSpec` with correct fields
- Missing fields in LLM response → filled with defaults
- Malformed JSON → retries, then raises `IntentParseError`
- Unknown domain in description → maps to closest supported domain
- All five supported domains parse correctly

```python
def test_parse_with_valid_llm_response():
    mock_response = json.dumps({
        "domain": "git-workflow",
        "task_count": 20,
        "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
        "skill_targets": ["git merge", "git rebase"],
        "base_tools": ["git", "bash"]
    })
    result = parse("generate git workflow tasks", llm_response=mock_response)
    assert result.state == "ready"
    assert result.spec.domain == "git-workflow"
    assert result.spec.task_count == 20
```

**`tests/test_task_generator.py`**

Mock LLM responses. Test:
- Instruction prompt contains domain and difficulty
- `initial_fs` path validation rejects paths outside `/workspace/`
- `initial_fs` path validation rejects `..` traversal
- Uniqueness check flags near-duplicate instructions (Jaccard > 0.7)
- Two near-duplicate tasks trigger a retry with dedup hint
- Difficulty heuristics: easy tasks have ≤2 files, hard tasks have ≥3

```python
def test_path_traversal_rejected():
    malicious_fs = {"/workspace/../etc/passwd": "root:x:0:0"}
    with pytest.raises(TaskGenerationError, match="path traversal"):
        ingest_fs_and_criteria(spec, instruction, json.dumps({
            "initial_fs": malicious_fs,
            "success_criteria": []
        }))
```

**`tests/test_image_builder.py`**

Mock `subprocess.run`. Test:
- `generate_dockerfile` produces valid Dockerfile with correct layer order (tools before COPY)
- Build context size check rejects `initial_fs` > 10MB
- Failed build in batch does not cancel other builds
- Temp build context directory is cleaned up on success
- Temp build context directory is cleaned up on failure (finally block)
- Image name follows `clawharness/<domain>/<task_id>:v1` convention

```python
def test_failed_build_isolated_in_batch(mock_docker_build):
    mock_docker_build.side_effect = [None, CalledProcessError(1, "docker"), None]
    tasks = [make_task("t1"), make_task("t2"), make_task("t3")]
    results = build_batch(tasks)
    assert results[0].success is True
    assert results[1].success is False
    assert results[2].success is True
```

**`tests/test_validator.py`**

Mock `docker run`, `docker exec`, `docker stop`, `docker rm`. Test:
- Container is always stopped and removed (finally block) even when criteria check raises
- `exit_code` criterion passes when exec returns correct exit code
- `file_contains` criterion passes when grep finds pattern
- `file_not_contains` criterion fails when grep finds pattern
- Solver action timeout (>10s) marks task as failed without crashing
- `--network none` flag is always passed to `docker run`

```python
def test_container_cleaned_up_on_exception(mock_docker):
    mock_docker.exec.side_effect = RuntimeError("unexpected crash")
    task = make_task_with_image("clawharness/test/t1:v1")
    result = validate_with_solution(task, ["echo hello"])
    assert result.passed is False
    mock_docker.stop.assert_called_once()
    mock_docker.rm.assert_called_once()
```

**`tests/test_serve.py`**

Test `serve.py` in subprocess mode (call it as a child process, parse stdout JSON). Test:
- `--mode=parse` returns `llm_needed` on first call
- `--mode=parse_ingest` returns spec JSON when LLM response is valid
- `--mode=build` returns error JSON when Docker is not running
- State file is written after every completed step
- Re-running a completed stage returns cached result without re-executing
- Pipeline resumes from correct stage after simulated interruption

### 17.3 Integration Tests

Integration tests require Docker (Colima acceptable). Use a real Alpine container, not mocks.

**`tests/integration/test_build_and_validate.py`**

```python
@pytest.mark.integration
def test_build_and_validate_simple_task():
    task = TaskSpec(
        task_id="test-001",
        domain="cli-file-ops",
        difficulty="easy",
        skill_target="file create",
        instruction="Create a file called hello.txt containing 'hello world'",
        initial_fs={"/workspace/README.md": "Create hello.txt with content 'hello world'"},
        success_criteria=[
            SuccessCriterion(type="file_exists", path="/workspace/hello.txt"),
            SuccessCriterion(type="file_contains", path="/workspace/hello.txt", pattern="hello world"),
        ],
        docker_image=""
    )
    build_result = build(task)
    assert build_result.success

    task.docker_image = build_result.image_name
    validation_result = validate_with_solution(
        task,
        solver_actions=["echo 'hello world' > /workspace/hello.txt"]
    )
    assert validation_result.passed
    assert all(validation_result.criteria_results)
```

**`tests/integration/test_pipeline_resume.py`**

- Simulate interrupted build (kill `serve.py` mid-batch)
- Re-run `serve.py --mode=build` on same spec
- Verify already-built images are not rebuilt
- Verify failed tasks are retried

### 17.4 End-to-End Tests

Run manually before each release. No mocks. Real Docker, real LLM API.

**`tests/e2e/test_full_pipeline.py`**

```bash
# Script form — run from repo root
python scripts/clawharness.py generate \
  --domain cli-file-ops \
  --count 5 \
  --difficulty easy:1.0 \
  --output /tmp/clawharness-e2e-test \
  --validate \
  --backbone anthropic

# Assertions:
# - /tmp/clawharness-e2e-test/train.jsonl exists and has 5 lines
# - Each line has task_id, instruction, docker_image, success_criteria
# - docker images ls | grep clawharness/cli-file-ops shows 5 images
# - All 5 tasks have validation_result.passed == True
```

### 17.5 Quality Metrics

Track these metrics per generation run to evaluate pipeline quality:

| Metric | Definition | Target (v0.1) |
|--------|------------|---------------|
| **Task consistency rate** | % of tasks where initial_fs matches instruction (human-judged on sample of 20) | ≥ 85% |
| **Validation pass rate** | % of generated tasks that pass round-trip validation | ≥ 80% |
| **Retry rate** | avg retries per task during generation | ≤ 0.5 |
| **Build success rate** | % of Docker builds that succeed | ≥ 95% |
| **Difficulty calibration** | Spearman correlation between intended difficulty and GPT-4o solve step count | ≥ 0.6 |
| **Task uniqueness** | % of task pairs with Jaccard similarity < 0.5 | ≥ 95% |

These metrics are computed by `clawharness status --metrics` after a completed run and written to `{output_dir}/metrics.json`.
