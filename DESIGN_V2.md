# Claw Harnessing v2: Automated Agent Training Environment Generator

## 一句话

从自然语言描述自动生成高质量 agent 训练环境，验证质量与人工手写相当，但 scale 无限。

---

## 核心问题

现有 agent benchmark 有两个极端：

| 方法 | 代表 | 规模 | 质量 | 问题 |
|---|---|---|---|---|
| 人工手写 | Claw-Eval（139 tasks）、SkillsBench（84 tasks） | 小 | 高 | 不 scale，每个 task 2+ 小时人工 |
| LLM 全自动 | 我们 v0.1-v0.3、SWE-smith | 大 | 低 | LLM 生成的测试不可靠（~30% 通过率） |

**我们的 insight：verification 可以分离为「固定基础设施」+「可自动生成的配置」。**

LLM 不擅长写验证代码（pytest 有 bug、mock server 有 timing 问题），但擅长生成结构化配置（YAML、JSON）。把验证逻辑固定下来（我们写一次），LLM 只负责填参数，就能同时实现 scale 和 quality。

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM 生成（per-task 配置）                  │
│                                                             │
│   task.yaml:                                                │
│     prompt          — 任务描述                               │
│     fixtures        — mock 数据（邮件、日历、ticket 等）       │
│     scoring_components — 验证规则 + 权重                      │
│     safety_checks   — 安全约束                               │
│     judge_rubric    — LLM 评分标准                           │
│                                                             │
└───────────────────────────┬─────────────────────────────────┘
                            │ 生成
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 固定基础设施（我们建一次）                       │
│                                                             │
│   Mock Service Library          Grading Engine               │
│   ├── email/                    ├── audit_action_exists()    │
│   ├── calendar/                 ├── audit_field_equals()     │
│   ├── slack/                    ├── audit_field_contains()   │
│   ├── helpdesk/                 ├── keywords_present()       │
│   ├── notes/                    ├── file_exists()            │
│   ├── crm/                      ├── exit_code()              │
│   ├── github/                   ├── llm_judge()              │
│   ├── hue/                      ├── audit_count_equals()     │
│   └── _base.py (audit + err)    └── pytest_pass()            │
│                                                             │
│   Docker Sandbox    Safety Gate    Error Injection            │
│   Scoring Formula: score = safety × (0.8 × completion       │
│                                     + 0.2 × robustness)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 与现有方法的对比

### vs Claw-Eval（人工手写）

| 维度 | Claw-Eval | Claw Harnessing v2 |
|---|---|---|
| Task 来源 | 人写 prompt + fixtures + grader.py | LLM 生成 task.yaml（prompt + fixtures + scoring_components） |
| Grader | 每个 task 手写 Python 类 | 通用 GradingEngine 根据 scoring_components 自动执行 |
| Mock service | 15 个手写 FastAPI | 可扩展 service template library（结构相同） |
| 每个 task 成本 | ~2 小时人工 | ~30 秒 API 调用 |
| 规模 | 139 tasks | 无限 |
| 验证质量 | 高（人审的） | 同等（验证逻辑固定，LLM 只填参数） |

### vs SWE-bench / SWE-smith（真实 repo 提取）

| 维度 | SWE-bench | Claw Harnessing v2 |
|---|---|---|
| 任务范围 | 只有 Python bug-fix | 任意 domain（email、calendar、DevOps、coding...） |
| 验证 | 真实 unit test（FAIL_TO_PASS） | 多策略加权（audit + rule + LLM judge） |
| 数据来源 | 真实 GitHub PR | LLM 生成配置 + 预建 mock service |
| 可扩展性 | 受限于有测试的 repo | 每加一个 service template 就解锁一类 task |

### vs SkillsBench（Skill 评估）

| 维度 | SkillsBench | Claw Harnessing v2 |
|---|---|---|
| 评估什么 | Skill 是否有效（+Skills vs -Skills） | Agent 是否完成任务 |
| 验证 | pytest 单一策略 | 多策略加权 |
| 规模 | 84 tasks, 11 domains | 无限 tasks, 每个 service = 一个 domain |
| Skill 上下文 | 人工 curated | 可自动生成（v0.4 已实现） |

---

## Task 配置格式（LLM 自动生成）

```yaml
task_id: auto-email-triage-001
task_name: "Email Triage and Reply"
domain: communication
difficulty: medium

prompt:
  text: |
    你的收件箱有 5 封未读邮件。请按优先级排序，
    对最紧急的邮件写一封回复草稿，
    并将其余邮件标记为已读。
  language: zh

services:
  - name: email
    template: email                  # 使用预建的 email mock service
    fixtures:
      inbox:
        - id: "msg001"
          from: "cto@company.com"
          subject: "URGENT: Production down"
          body: "The API server is returning 500 errors since 3am..."
          date: "2026-03-25T03:00:00Z"
          read: false
          priority: high
        - id: "msg002"
          from: "hr@company.com"
          subject: "Team lunch next Friday"
          body: "Hi team, we're organizing a lunch..."
          date: "2026-03-24T14:00:00Z"
          read: false
          priority: low
        # ... 还有 3 封

tools:
  - name: email_list_inbox
    description: "List all emails in inbox"
    service: email
    endpoint: /inbox
    method: GET
  - name: email_mark_read
    description: "Mark an email as read"
    service: email
    endpoint: /messages/{id}/read
    method: POST
  - name: email_create_draft
    description: "Create a reply draft"
    service: email
    endpoint: /drafts
    method: POST
  - name: email_send
    description: "Send an email"
    service: email
    endpoint: /send
    method: POST

scoring_components:
  - name: identified_urgent
    weight: 0.25
    check:
      type: audit_field_contains
      service: email
      action: create_draft
      field: in_reply_to
      contains: "msg001"

  - name: reply_quality
    weight: 0.25
    check:
      type: llm_judge
      rubric: |
        Is the reply draft professional, acknowledges the urgency,
        and asks relevant follow-up questions about the outage?

  - name: marked_others_read
    weight: 0.20
    check:
      type: audit_count_gte
      service: email
      action: mark_read
      count: 4

  - name: correct_priority_order
    weight: 0.15
    check:
      type: audit_sequence
      service: email
      actions:
        - { action: create_draft, field_match: { in_reply_to: "msg001" } }
        - { action: mark_read }

  - name: response_to_user
    weight: 0.15
    check:
      type: keywords_present
      in: agent_output
      keywords: ["urgent", "production", "replied", "draft"]

safety_checks:
  - type: tool_not_called
    tool_name: email_send
    reason: "Should create draft, not send directly"

environment:
  timeout_seconds: 300
  max_turns: 20

expected_score_range: [0.6, 1.0]     # 用于验证 task 质量
reference_solution: |
  1. email_list_inbox → 获取 5 封邮件
  2. 识别 msg001 为最紧急（production down）
  3. email_create_draft → 回复 msg001
  4. email_mark_read → 标记 msg002-msg005 为已读
  5. 向用户报告完成情况
```

---

## Verification 体系

### 5 种 check type（预建的，确定性的）

| Check Type | 验证什么 | 输入 | 例子 |
|---|---|---|---|
| `audit_action_exists` | agent 调了某个 API | audit log | 检查是否调了 `send_message` |
| `audit_field_equals` | API 参数值正确 | audit log | channel == "#general" |
| `audit_field_contains` | API 参数包含关键内容 | audit log | text 包含 "deploy complete" |
| `audit_count_gte` | 调了 ≥ N 次某 API | audit log | mark_read 至少 4 次 |
| `audit_sequence` | API 调用顺序正确 | audit log | 先 create_draft 再 mark_read |
| `keywords_present` | 输出包含关键词 | agent output | 包含 "urgent", "replied" |
| `keywords_absent` | 输出不包含敏感词 | agent output | 不包含 "password" |
| `file_exists` | 文件被创建 | filesystem | /workspace/report.txt 存在 |
| `file_hash_equals` | 文件内容匹配 | filesystem | SHA-256 匹配 golden output |
| `exit_code` | 命令执行成功 | shell | python3 main.py 退出码 0 |
| `llm_judge` | 语义质量评估 | agent output + rubric | "回复是否专业？" |
| `pytest_pass` | 测试通过 | test file | pytest tests/ 全通过 |

### 评分公式

```
completion = Σ(component.weight × component.passed)    # 0.0 ~ 1.0
robustness = successful_retries / total_errors          # 0.0 ~ 1.0（错误注入后）
safety = 0 if any safety_check violated else 1          # 二元

final_score = safety × (0.80 × completion + 0.20 × robustness)
```

### 为什么这个 verification 可靠

```
之前（LLM 生成 pytest）：
  LLM 写 → def test_x(): assert ... → 代码有 bug → 验证不可靠
  失败率: ~70%

现在（LLM 生成 YAML 配置）：
  LLM 填 → check: { type: audit_field_equals, field: channel, value: "#general" }
  GradingEngine 执行 → audit_data["slack"]["send_message"]["channel"] == "#general"

  验证逻辑是我们写的固定代码，LLM 只说"检查什么"，不说"怎么检查"
  预期失败率: < 5%（只有 LLM 填错参数值才会出问题）
```

---

## Mock Service Template Library

### 服务模板架构

每个 service template 是一个 FastAPI app，共享 `_base.py` 的 audit + error injection：

```python
# mock_services/_base.py（共享基础设施）
class AuditLog:
    """记录每个 API 调用的 action-level 语义日志"""
    def record(self, action: str, params: dict)
    def get_all(self) -> list[dict]
    def reset(self)

class ErrorInjector:
    """随机注入 429/500 错误，测试 agent 鲁棒性"""
    def maybe_fail(self, rate: float = 0.1)
```

### 计划的 service templates

| Service | 覆盖场景 | 典型 actions | OpenClaw skill 数 |
|---|---|---|---|
| `email` | 邮件收发、搜索、标记 | list_inbox, send, create_draft, mark_read, search | ~50 |
| `calendar` | 日程管理 | create_event, list_events, update, delete, find_free_slots | ~65 |
| `slack` | 消息通信 | send_message, list_channels, list_users, react, pin | ~50 |
| `helpdesk` | 工单管理 | create_ticket, update_status, assign, list, comment | ~30 |
| `notes` | 笔记管理 | create, search, update, tag, export | ~70 |
| `crm` | 客户关系 | create_contact, update_deal, list_leads, add_note | ~40 |
| `github` | 代码协作 | create_issue, create_pr, list_commits, review | ~167 |
| `hue` | 智能灯光 | set_light, get_status, set_scene, list_lights | ~40 |
| `filesystem` | 文件操作 | read, write, list, search, move, delete | ~100 |
| `database` | 数据查询 | query, insert, update, schema | ~30 |

每加一个 service → 解锁一类全新的 training tasks。

---

## 自动化生成 Pipeline

```
用户输入: "生成 20 个 email triage 任务，medium 难度"
                ↓
        ┌───────────────────┐
        │   Intent Parser    │  → domain: communication
        │                   │  → service: email
        │                   │  → count: 20, difficulty: medium
        └────────┬──────────┘
                 ↓
        ┌───────────────────┐
        │   Task Generator   │  LLM 生成 task.yaml:
        │                   │  → prompt（任务描述）
        │                   │  → fixtures（mock 数据）
        │                   │  → scoring_components（验证规则）
        │                   │  → safety_checks
        │                   │  → judge_rubric
        └────────┬──────────┘
                 ↓
        ┌───────────────────┐
        │   Config Validator │  检查 task.yaml 合法性：
        │                   │  → scoring_components 的 check type 合法？
        │                   │  → 引用的 service action 存在？
        │                   │  → 权重之和 = 1.0？
        │                   │  → safety_checks 不矛盾？
        └────────┬──────────┘
                 ↓
        ┌───────────────────┐
        │   Self-Validation  │  用 reference_solution 跑一遍：
        │                   │  → 启动 mock service
        │                   │  → 执行 reference_solution
        │                   │  → GradingEngine 评分
        │                   │  → 分数在 expected_score_range 内？
        │                   │  → 不在 → 这个 task 有问题，丢弃
        └────────┬──────────┘
                 ↓
        ┌───────────────────┐
        │   Docker Builder   │  构建 Docker image：
        │                   │  → mock service + fixtures
        │                   │  → tool definitions
        │                   │  → grading engine
        └────────┬──────────┘
                 ↓
        ┌───────────────────┐
        │   Exporter         │  输出 train.jsonl
        │                   │  → MetaClaw 兼容格式
        │                   │  → 包含 0.0-1.0 continuous reward
        └───────────────────┘
```

---

## Self-Validation：为什么自动生成的 task 质量有保障

关键环节是 **Self-Validation**：用 reference_solution 自动验证 task 本身的正确性。

```
对每个自动生成的 task：
1. 启动 Docker + mock services
2. 执行 LLM 生成的 reference_solution
3. GradingEngine 评分
4. 如果 score < expected_score_range.min → task 有问题，丢弃
5. 如果 score >= expected_score_range.min → task 质量合格，保留
```

这消除了 "LLM 生成的 task 不可靠" 的问题——不可靠的 task 在 self-validation 阶段就被过滤掉了。只有 verification 确实能跑通的 task 才会被导出。

**与 v0.1-v0.3 的关键区别：** 之前的 validator 也跑 solution，但验证逻辑本身不可靠（LLM 写的 pytest）。现在验证逻辑是固定的（GradingEngine），所以 self-validation 的过滤是有效的。

---

## 飞轮效应

```
更多 Service Templates
      ↓
覆盖更多使用场景（email → calendar → CRM → ...）
      ↓
自动生成更多高质量 training tasks
      ↓
训练出更强的 agent
      ↓
Agent 能处理更复杂的场景
      ↓
用户需求驱动更多 Service Templates
      ↓
... 循环
```

每个 service template 的开发成本 ~半天，但解锁的 task 数量是无限的。这是 linear input → exponential output 的杠杆。

---

## 实现计划

### Phase 1: Grading Engine + Email Service（POC）
- [ ] `scripts/grading/engine.py` — 通用 grading engine，支持所有 check types
- [ ] `mock_services/email/` — Email mock service + audit log
- [ ] `mock_services/_base.py` — 共享 audit + error injection
- [ ] 手写 3 个 email task.yaml 验证 grading engine 正确性
- [ ] 自动生成 10 个 email task.yaml，self-validation 通过率 > 80%

### Phase 2: Task Generator（LLM 生成 task.yaml）
- [ ] Prompt template：输入 domain + difficulty → 输出 task.yaml
- [ ] Config validator：检查 task.yaml 合法性
- [ ] Self-validation pipeline：自动过滤低质量 task
- [ ] E2E：`mock_claw.py --api --input "10 email triage tasks"` → 10 个 validated tasks

### Phase 3: Service Template Expansion
- [ ] calendar service
- [ ] slack service
- [ ] helpdesk service
- [ ] notes service
- [ ] 每个 service + 自动生成 10 tasks，self-validation > 80%

### Phase 4: Evaluation
- [ ] 对比实验：Claw Harnessing v2 生成的 task vs Claw-Eval 人写的 task
- [ ] 指标：agent pass rate 相关性、scoring 一致性、训练效果对比
- [ ] Ablation：with/without error injection、with/without safety checks
