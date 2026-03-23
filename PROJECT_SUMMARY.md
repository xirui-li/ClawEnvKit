# Claw Harnessing 项目总结

**版本：** v0.3（当前） | **仓库：** https://github.com/xirui-li/claw-harnessing

---

## 一句话描述

从自然语言描述自动生成 OpenClaw agent 的训练/评估环境（Docker image + train.jsonl + 验证测试）。

---

## 核心架构

```
用户: "生成 3 个 bug-fix 任务"
        ↓
  intent_parser.py      ← Step 1: 解析用户意图 → GenerationSpec
        ↓
  task_generator.py     ← Step 2: 生成任务指令 + 初始文件 + 解决方案 + 测试
        ↓
  consistency_checker.py ← Step 3: 一致性检查（确定性 + LLM 语义）
        ↓
  image_builder.py      ← Step 4: 构建 Docker image（初始文件 + 测试 + mock server）
        ↓
  validator.py          ← Step 5: 在 Docker 中验证（FAIL_TO_PASS + mock API）
        ↓
  exporter.py           ← Step 6: 导出 train.jsonl
        ↓
  MetaClaw RL 训练 / OpenClaw 评估
```

**LLM 调用方式：** 所有 LLM 调用通过 `serve.py` 的 `llm_needed` 协议委托给宿主 claw（或 mock_claw.py）。Claw Harnessing 本身不调 API。

---

## 版本演进

### v0.1（已 tag）
- 基础 pipeline 跑通
- 5 个简单 domain：cli-file-ops, git-workflow, json-processing, shell-scripting, python-debugging
- 验证方式：`file_exists`, `file_contains`, `file_not_contains`, `exit_code`
- 13 个 serve.py mode
- E2E 验证通过（mock_claw --api + OpenClaw 集成）

### v0.2（已实现）
- **pytest FAIL_TO_PASS 验证**：生成 pytest 测试文件，两阶段验证（初始状态必须 FAIL，修复后 PASS）
- **3-step 任务生成**：instruction → fs+criteria+solution_patch → pytest test file
- **bug-fix domain**：生成有 seeded bug 的多文件 Python 项目
- 新 domain：bug-fix, feature-impl, data-processing, config-devops
- 新 criterion：`pytest_pass`（test_file, pytest_args）
- TaskSpec 新增：`test_files`, `solution_patch`, `schema_version`

### v0.3（当前）
- **Mock API Server 框架**：Docker 内跑 HTTP mock，记录请求，验证 expected_calls
- 新 domain：communication, smart-home, browser-scraping
- 新 criterion：`mock_api_verify`（expected_calls_file）
- `MockServerConfig`：responses, expected_calls, env_vars, strict mode
- image_builder 自动 bake mock server + Flask 到容器
- **776 个 skill-to-prompt 映射**：来自 awesome-openclaw-skills，覆盖 30 个类别

---

## 当前文件结构

```
claw-harnessing/
├── SKILL.md                     # OpenClaw skill 入口（YAML frontmatter + 7 步指令）
├── DESIGN.md                    # 完整设计文档
├── EXECUTION.md                 # 执行清单（Phase 0-12）
├── TEST_GUIDE.md                # 测试指南（5 个级别）
├── PROJECT_SUMMARY.md           # ← 本文件
├── config.json                  # API keys（gitignored）
├── scripts/
│   ├── serve.py                 # 状态机编排器（15 个 mode）
│   ├── mock_claw.py             # 开发用 harness（--dry-run / --api）
│   ├── clawharness.py           # CLI 入口（v0.2 推迟）
│   └── core/
│       ├── schema.py            # 数据结构（Pydantic models）
│       ├── intent_parser.py     # Step 1: NL → GenerationSpec
│       ├── task_generator.py    # Step 2: 指令 + fs + criteria + test 生成
│       ├── consistency_checker.py # Step 3: 确定性 + 语义一致性检查
│       ├── image_builder.py     # Step 4: Docker image 构建
│       ├── validator.py         # Step 5: 容器内验证（pytest + mock API）
│       ├── exporter.py          # Step 6: train.jsonl 导出
│       └── mock_server.py       # v0.3: 通用 mock HTTP server
├── prompts/
│   ├── intent_parse.md          # NL → GenerationSpec JSON
│   ├── task_instruction.md      # domain/skill/difficulty → 任务指令
│   ├── task_fs_criteria.md      # 指令 → initial_fs + criteria + solution_patch
│   ├── task_test_generation.md  # FAIL_TO_PASS pytest 测试生成
│   ├── task_solver.md           # 验证用 solver prompt
│   └── consistency_check.md     # 语义一致性检查
├── references/
│   ├── skill_scenarios.md       # 30 类别 → domain 映射 + 示例 prompt
│   ├── skill_prompts.md         # 776 个 skill → user prompt 表格
│   ├── skill_prompts.json       # 结构化映射数据
│   └── skills_raw.json          # 原始 skill 解析数据
├── tests/
│   ├── test_schema.py           # 42 tests
│   ├── test_intent_parser.py    # 15 tests
│   ├── test_task_generator.py   # 40 tests
│   ├── test_consistency_checker.py # 24 tests
│   ├── test_image_builder.py    # 17 tests
│   ├── test_validator.py        # 16 tests
│   ├── test_exporter.py         # 7 tests
│   ├── test_mock_server.py      # 10 tests
│   └── fixtures/canned_responses/ # dry-run 用的 canned 数据
└── .gitignore
```

---

## 支持的 Domain（9 个）

| Domain | 描述 | 验证方式 | 版本 |
|---|---|---|---|
| `bug-fix` | 修复 Python 项目中的 bug | pytest FAIL_TO_PASS | v0.2 |
| `feature-impl` | 实现新功能 | pytest FAIL_TO_PASS | v0.2 |
| `git-workflow` | Git 操作（分支、合并、rebase） | exit_code + file_contains | v0.1 |
| `shell-scripting` | Bash 脚本编写 | exit_code + file_contains | v0.1 |
| `data-processing` | JSON/CSV/日志解析转换 | exit_code + file_contains | v0.2 |
| `config-devops` | YAML/TOML/Docker 配置 | exit_code + file_contains | v0.2 |
| `communication` | Slack/Discord/email API | mock_api_verify | v0.3 |
| `smart-home` | Hue/HomeAssistant API | mock_api_verify | v0.3 |
| `browser-scraping` | HTML 页面数据提取 | file_contains + pytest | v0.3 |

---

## 验证体系（6 种 criterion）

| Criterion | 描述 | 引入版本 |
|---|---|---|
| `exit_code` | 运行命令检查退出码 | v0.1 |
| `file_exists` | 检查文件存在 | v0.1 |
| `file_contains` | 检查文件包含子串 | v0.1 |
| `file_not_contains` | 检查文件不包含子串 | v0.1 |
| `pytest_pass` | 运行 pytest 测试文件 | v0.2 |
| `mock_api_verify` | 验证 mock server 收到正确的 API 调用 | v0.3 |

---

## 测试统计

- **单元测试：** 177 个（全部通过）
- **Dry-run 集成测试：** mock_claw.py --dry-run，canned responses
- **E2E 测试（已通过）：**
  - v0.1: cli-file-ops 3/3 pass（mock_claw --api + OpenClaw 集成）
  - v0.2: bug-fix domain，pytest 验证
  - v0.3: communication domain，mock API 验证

---

## 入口方式

### 1. OpenClaw Skill（生产）
```bash
ln -s /path/to/claw-harnessing ~/.openclaw/workspace/skills/clawharness
# 然后在 OpenClaw session 中说：
# "帮我生成 3 个 bug-fix 训练任务"
```

### 2. mock_claw.py --api（开发/测试）
```bash
export ANTHROPIC_API_KEY=...
python scripts/mock_claw.py --api \
  --input "生成 3 个 communication 任务，Slack API" \
  --output ~/test-tasks
```

### 3. mock_claw.py --dry-run（无 LLM/Docker）
```bash
python scripts/mock_claw.py --dry-run \
  --input "3 tasks" --output /tmp/test
```

### 4. serve.py 直接调用
```bash
python scripts/serve.py --mode=parse --input="3 bug-fix tasks" --output=~/tasks
python scripts/serve.py --mode=status --spec=~/tasks/.clawharness_state.json
```

---

## 输出格式

### train.jsonl（MetaClaw 兼容）
```json
{
  "task_id": "bug-fix-001",
  "task_type": "bug-fix",
  "instruction": "Fix the off-by-one error in calculator.py...",
  "docker_image": "clawharness/bug-fix/bug-fix-001:v1",
  "success_criteria": [
    {"type": "pytest_pass", "test_file": "/workspace/tests/test_solution.py"},
    {"type": "exit_code", "cmd": "python3 /workspace/src/calc.py"}
  ],
  "test_files": {"/workspace/tests/test_solution.py": "...pytest code..."},
  "schema_version": "0.3.0"
}
```

### Docker Image 内容
```
/workspace/
├── src/calc.py                 # 初始代码（有 bug）
├── tests/test_solution.py      # FAIL_TO_PASS 测试
├── mock_server/                # v0.3: mock API server（如有）
│   ├── server.py
│   ├── responses.json
│   └── expected_calls.json
└── README.md
```

---

## 研究背景

- **SWE-bench**：FAIL_TO_PASS 单元测试是 industry standard
- **SWE-smith**：50K 合成任务，bug injection + test filtering
- **SkillsBench**：84 tasks, 11 domains, curated Skills +16.2pp，self-generated Skills 无效
- **awesome-openclaw-skills**：5,197 skills, 30 categories，776 个代表性 skill 已映射

---

## 待优化 / 未来方向

### 已知问题
- [ ] v0.1 domain（cli-file-ops 等）的 prompt 质量一般，LLM 经常生成 /tmp 路径
- [ ] mock_claw.py 的 `--api` 模式 model 硬编码为 `claude-sonnet-4-6`
- [ ] consistency_checker 对 "agent 创建的文件" 只能做 soft warning，无法区分输入/输出文件
- [ ] 776 个 skill prompt 是模板生成的，不够自然（部分 prompt 是 "Help me with: ..."）
- [ ] serve.py 没有 test_prompt/test_ingest 的 canned fixtures 给 dry-run 用
- [ ] exporter 不导出 mock_server_config

### v0.4 候选功能
- [ ] **776 prompt 批量生成**：用 skill_prompts.json 驱动 mock_claw.py 批量生成训练任务
- [ ] **真实代码库提取**：从 GitHub PR 拉取真实 bug（类似 SWE-smith）
- [ ] **多轮任务序列**：task N 依赖 task N-1 的状态
- [ ] **CLI 入口**：`clawharness generate --domain bug-fix --count 20`
- [ ] **质量指标**：validation pass rate, retry rate, uniqueness score
- [ ] **SkillsBench 兼容格式导出**：instruction.md + task.toml + solve.sh + test_outputs.py
