# OpenClaw Skill Scenarios → Claw Harnessing Prompts

Based on [awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills) (5,197 skills, 30 categories).

Each entry: **Category** → example user prompts → whether Claw Harnessing can generate training tasks for it, and with what domain/verification approach.

---

## 1. Coding Agents & IDEs (1,184 skills)

**Real user prompts:**
- "Help me refactor this function to use async/await"
- "Delegate this bug fix to a coding agent"
- "Set up a multi-agent pipeline to review and fix this PR"
- "Convert this JavaScript code to TypeScript"
- "Generate unit tests for my API endpoints"

**Claw Harnessing domain:** `bug-fix`, `feature-impl`
**Verification:** pytest FAIL_TO_PASS
**Example generation prompt:** `"生成 10 个 bug-fix 任务，涵盖 async/await 重构、类型转换、测试生成"`

---

## 2. Web & Frontend Development (919 skills)

**Real user prompts:**
- "Create a React component that displays a sortable data table"
- "Fix the CSS layout issue in the navbar"
- "Convert this REST API to use GraphQL"
- "Set up a Next.js project with TailwindCSS"
- "Add form validation to the signup page"

**Claw Harnessing domain:** `feature-impl`, `bug-fix`
**Verification:** pytest (check rendered output, file structure)
**Example generation prompt:** `"生成 10 个 feature-impl 任务，web 前端开发，React/HTML/CSS"`

---

## 3. DevOps & Cloud (393 skills)

**Real user prompts:**
- "Write a Dockerfile for this Python Flask app"
- "Fix the CI/CD pipeline — tests pass locally but fail in GitHub Actions"
- "Set up Nginx reverse proxy for my Node.js app"
- "Write a Terraform config for an AWS S3 bucket with versioning"
- "Debug why the Kubernetes pod keeps crashing"

**Claw Harnessing domain:** `config-devops`
**Verification:** exit_code (validate config syntax), file_contains
**Example generation prompt:** `"生成 10 个 config-devops 任务，Docker/CI/Nginx/Terraform 配置"`

---

## 4. Search & Research (345 skills)

**Real user prompts:**
- "Search the web for recent papers on LLM agent evaluation"
- "Summarize this arXiv paper for me"
- "Find competitors to our product in the CRM space"
- "Search for Python libraries that do audio transcription"
- "Extract key findings from these 5 PDF papers"

**Claw Harnessing domain:** `data-processing`, `browser-scraping`
**Verification:** file_contains (check extracted data), pytest
**Example generation prompt:** `"生成 5 个 data-processing 任务，从文档中提取结构化数据"`

---

## 5. Browser & Automation (322 skills)

**Real user prompts:**
- "Scrape the product prices from this webpage"
- "Fill out this online form with the data from my spreadsheet"
- "Download all images from this gallery page"
- "Monitor this webpage for price changes"
- "Extract all email addresses from this company's team page"

**Claw Harnessing domain:** `browser-scraping`
**Verification:** mock_api_verify (check HTTP requests), file_contains
**Example generation prompt:** `"生成 5 个 browser-scraping 任务，从 HTML 页面提取数据"`

---

## 6. Productivity & Tasks (203 skills)

**Real user prompts:**
- "Add a task to Asana: Review Q3 report, due Friday"
- "Create a Linear issue for the login bug with priority high"
- "Move all completed tasks from 'In Progress' to 'Done' in Trello"
- "Show me my overdue tasks across all projects"
- "Generate a daily standup summary from my task updates"

**Claw Harnessing domain:** `communication` (mock task management API)
**Verification:** mock_api_verify
**Example generation prompt:** `"生成 5 个 communication 任务，任务管理 API 集成（Asana/Linear/Trello）"`

---

## 7. CLI Utilities (179 skills)

**Real user prompts:**
- "Find all files larger than 100MB in my home directory"
- "Rename all .jpeg files to .jpg in this folder"
- "Set up a cron job that backs up my database every night"
- "Write a bash script to monitor disk usage and alert at 90%"
- "Compress all log files older than 7 days"

**Claw Harnessing domain:** `shell-scripting`
**Verification:** exit_code, file_exists, file_contains
**Example generation prompt:** `"生成 10 个 shell-scripting 任务，文件管理、cron、系统监控"`

---

## 8. AI & LLMs (176 skills)

**Real user prompts:**
- "Route this request to the cheapest model that can handle it"
- "Set up a prompt chain: summarize → translate → format"
- "Compare outputs from GPT-4 and Claude on these 10 prompts"
- "Create a RAG pipeline over my documentation folder"
- "Fine-tune a prompt template for customer support classification"

**Claw Harnessing domain:** `feature-impl`, `data-processing`
**Verification:** pytest, file_contains
**Example generation prompt:** `"生成 5 个 feature-impl 任务，构建 LLM 工具链（prompt chain、model routing）"`

---

## 9. Git & GitHub (167 skills)

**Real user prompts:**
- "Create a PR that fixes issue #42"
- "Review this PR and leave comments on potential issues"
- "Squash the last 5 commits into one with a clean message"
- "Set up branch protection rules for the main branch"
- "Cherry-pick commit abc123 from develop to release"
- "Resolve the merge conflict in src/utils.py"

**Claw Harnessing domain:** `git-workflow`
**Verification:** exit_code (git log/status checks), file_contains
**Example generation prompt:** `"生成 10 个 git-workflow 任务，分支管理、merge conflict、rebase、PR"`

---

## 10. Image & Video Generation (164 skills)

**Real user prompts:**
- "Generate a logo for my startup using AI"
- "Create a thumbnail for my YouTube video"
- "Batch resize these images to 800x600"
- "Convert this video to GIF"
- "Add watermark to all images in this folder"

**Claw Harnessing domain:** `data-processing` (for batch operations), `feature-impl` (for scripts)
**Verification:** file_exists, exit_code (check image dimensions)
**Example generation prompt:** `"生成 5 个 data-processing 任务，图片批处理（resize、watermark、format conversion）"`

---

## 11. Communication (146 skills)

**Real user prompts:**
- "Send a message to #engineering on Slack saying the deploy is complete"
- "Reply to the last email from John with 'I'll review it tomorrow'"
- "Post a tweet: 'Just shipped v2.0! Check it out at...'"
- "Send a WhatsApp message to Mom: 'Coming home for dinner'"
- "Forward this Discord message to the #announcements channel"
- "Search my Gmail for all invoices from last month"

**Claw Harnessing domain:** `communication`
**Verification:** mock_api_verify (check correct API calls)
**Example generation prompt:** `"生成 10 个 communication 任务，Slack/Discord/email API 集成"`

---

## 12. Transportation (110 skills)

**Real user prompts:**
- "Track flight AA1234 and tell me if it's delayed"
- "Find the next train from Penn Station to Boston"
- "Find EV charging stations within 5 miles"
- "Plan a route from home to airport avoiding tolls"
- "Check public transit schedules for my commute"

**Claw Harnessing domain:** `communication` (mock transit API)
**Verification:** mock_api_verify, file_contains
**Example generation prompt:** `"生成 5 个 communication 任务，交通/航班 API 查询和数据处理"`

---

## 13. PDF & Documents (105 skills)

**Real user prompts:**
- "Extract all tables from this PDF into CSV"
- "Merge these 3 PDFs into one document"
- "Add a watermark to every page of this PDF"
- "Convert this Markdown file to a formatted PDF"
- "OCR this scanned document and save as text"

**Claw Harnessing domain:** `data-processing`
**Verification:** file_exists, file_contains, exit_code
**Example generation prompt:** `"生成 5 个 data-processing 任务，PDF 处理（提取表格、合并、OCR）"`

---

## 14. Marketing & Sales (102 skills)

**Real user prompts:**
- "Pull all leads from HubSpot that haven't been contacted in 30 days"
- "Generate a blog post outline about AI in healthcare"
- "Create a social media calendar for next week"
- "Analyze our email campaign open rates vs industry average"
- "Update the CRM contact for John Smith with new phone number"

**Claw Harnessing domain:** `communication` (mock CRM API), `data-processing`
**Verification:** mock_api_verify, file_contains
**Example generation prompt:** `"生成 5 个 communication 任务，CRM API 集成（HubSpot/Salesforce）"`

---

## 15. Health & Fitness (87 skills)

**Real user prompts:**
- "Log my lunch: grilled chicken salad, 450 calories"
- "What's my calorie count for today?"
- "Generate a workout plan for this week — focus on upper body"
- "Track my fasting timer — started at 8pm last night"
- "Find a healthy recipe with chicken and broccoli"

**Claw Harnessing domain:** `data-processing`, `feature-impl`
**Verification:** pytest, file_contains
**Example generation prompt:** `"生成 5 个 data-processing 任务，健康数据处理（卡路里计算、运动计划生成）"`

---

## 16. Media & Streaming (85 skills)

**Real user prompts:**
- "Play my Discover Weekly playlist on Spotify"
- "Pause the music in the living room"
- "Download this YouTube video as MP3"
- "Generate a podcast from this newsletter"
- "What song is currently playing?"

**Claw Harnessing domain:** `smart-home` (mock media API), `data-processing`
**Verification:** mock_api_verify
**Example generation prompt:** `"生成 5 个 smart-home 任务，媒体播放器 API 控制（播放、暂停、搜索）"`

---

## 17. Notes & PKM (70 skills)

**Real user prompts:**
- "Create a new note titled 'Meeting Notes: Q4 Planning'"
- "Search my notes for anything about 'database migration'"
- "Export all my Bear notes tagged 'project-alpha' to markdown"
- "Add this to my Obsidian daily note"
- "Summarize my notes from this week"

**Claw Harnessing domain:** `communication` (mock notes API), `data-processing`
**Verification:** mock_api_verify, file_contains
**Example generation prompt:** `"生成 5 个 communication 任务，笔记 API 集成（创建、搜索、导出）"`

---

## 18. Calendar & Scheduling (65 skills)

**Real user prompts:**
- "Add a meeting: 'Team standup' tomorrow at 10am for 30 minutes"
- "What's on my calendar for next Tuesday?"
- "Find a free slot this week for a 1-hour meeting with Alice"
- "Cancel the 3pm meeting today"
- "Set up a recurring weekly meeting every Monday at 9am"

**Claw Harnessing domain:** `communication` (mock calendar API)
**Verification:** mock_api_verify
**Example generation prompt:** `"生成 5 个 communication 任务，日历 API 集成（创建、查询、取消事件）"`

---

## 19. Security & Passwords (53 skills)

**Real user prompts:**
- "Generate a secure password for my new AWS account"
- "Audit my npm dependencies for known vulnerabilities"
- "Set up 2FA for this service"
- "Scan this codebase for hardcoded secrets"
- "Check if my email has been in any data breaches"

**Claw Harnessing domain:** `bug-fix` (fix security issues), `config-devops`
**Verification:** pytest, exit_code
**Example generation prompt:** `"生成 5 个 bug-fix 任务，安全漏洞修复（hardcoded secrets、SQL injection、dependency audit）"`

---

## 20. Shopping & E-commerce (51 skills)

**Real user prompts:**
- "Check my Amazon order status for the laptop"
- "Add milk, eggs, and bread to my grocery list"
- "Compare prices for AirPods Pro across Amazon and Best Buy"
- "Track my Shopify store sales for this week"
- "Reorder my last Whole Foods delivery"

**Claw Harnessing domain:** `communication` (mock e-commerce API), `data-processing`
**Verification:** mock_api_verify, file_contains
**Example generation prompt:** `"生成 5 个 communication 任务，电商 API 集成（订单查询、价格比较）"`

---

## 21. Personal Development (50 skills)

**Real user prompts:**
- "Track my daily habits: meditation ✓, reading ✓, exercise ✗"
- "Generate a study plan for learning Rust in 30 days"
- "What were my top 3 accomplishments this week?"
- "Set a goal: Run 5K in under 25 minutes by March"
- "Journal prompt for today"

**Claw Harnessing domain:** `data-processing`, `feature-impl`
**Verification:** file_contains, pytest
**Example generation prompt:** `"生成 3 个 feature-impl 任务，习惯追踪和个人数据管理工具"`

---

## 22. Speech & Transcription (45 skills)

**Real user prompts:**
- "Transcribe this meeting recording"
- "Convert this text to speech and save as MP3"
- "Generate subtitles for this video"
- "Translate this audio from Spanish to English"
- "Detect the language spoken in this audio clip"

**Claw Harnessing domain:** `data-processing`, `communication` (mock TTS/STT API)
**Verification:** file_exists, file_contains, mock_api_verify
**Example generation prompt:** `"生成 5 个 data-processing 任务，音频文本处理（转录结果解析、字幕格式转换）"`

---

## 23. Apple Apps & Services (44 skills)

**Real user prompts:**
- "Add a reminder: Call dentist tomorrow at 2pm"
- "Search my Apple Notes for recipes"
- "Send a message to John via iMessage"
- "Find my AirPods location"
- "Set a timer for 25 minutes"

**Claw Harnessing domain:** `communication` (mock Apple API)
**Verification:** mock_api_verify
**Example generation prompt:** `"生成 5 个 communication 任务，个人助理 API 集成（提醒、笔记、消息）"`

---

## 24. Smart Home & IoT (41 skills)

**Real user prompts:**
- "Turn on the living room lights to 50% brightness"
- "Set the thermostat to 72°F"
- "What's the current temperature in the bedroom?"
- "Turn off all lights in the house"
- "Set the bedroom light to warm white"
- "Start the robot vacuum"

**Claw Harnessing domain:** `smart-home`
**Verification:** mock_api_verify (check correct API calls to Hue/HA)
**Example generation prompt:** `"生成 10 个 smart-home 任务，智能家居 API 控制（灯光、温控、传感器）"`

---

## 25. Clawdbot Tools (37 skills)

**Real user prompts:**
- "Update OpenClaw to the latest version"
- "List all installed skills"
- "Check my agent's security permissions"
- "Sync my skills across devices"
- "Show my usage stats for this month"

**Claw Harnessing domain:** `shell-scripting`, `config-devops`
**Verification:** exit_code, file_contains
**Example generation prompt:** `"生成 3 个 shell-scripting 任务，CLI 工具管理（安装、更新、配置）"`

---

## 26. Gaming (35 skills)

**Real user prompts:**
- "Play a round of 20 questions with me"
- "Generate a random D&D character"
- "What's the optimal strategy for this chess position?"
- "Start a text adventure game"
- "Manage my Minecraft server — restart it"

**Claw Harnessing domain:** `feature-impl`
**Verification:** pytest
**Example generation prompt:** `"生成 3 个 feature-impl 任务，游戏逻辑实现（棋盘游戏、文字冒险）"`

---

## 27. Moltbook / AI Social (29 skills)

**Real user prompts:**
- "Post an update to Moltbook about my latest project"
- "Check my agent's social feed"
- "Reply to the latest post in my timeline"

**Claw Harnessing domain:** `communication` (mock social API)
**Verification:** mock_api_verify
**Example generation prompt:** `"生成 3 个 communication 任务，社交平台 API 集成（发帖、回复、查询）"`

---

## 28. iOS & macOS Development (29 skills)

**Real user prompts:**
- "Fix the SwiftUI layout issue in ContentView.swift"
- "Add a new Instruments profiling template"
- "Package this app for TestFlight distribution"
- "Audit my Homebrew packages for outdated versions"
- "Create an Xcode build scheme for staging"

**Claw Harnessing domain:** `bug-fix`, `config-devops`
**Verification:** pytest, exit_code
**Example generation prompt:** `"生成 5 个 config-devops 任务，Xcode/Swift 项目配置和构建"`

---

## 29. Data & Analytics (28 skills)

**Real user prompts:**
- "Query my Google Analytics for page views this month"
- "Create a dashboard showing revenue by region"
- "Run this SQL query against the DuckDB database"
- "Generate a chart of user signups over the last 90 days"
- "Export this data visualization as PNG"

**Claw Harnessing domain:** `data-processing`
**Verification:** file_exists, file_contains, pytest
**Example generation prompt:** `"生成 5 个 data-processing 任务，数据分析（SQL 查询、图表生成、指标计算）"`

---

## 30. Self-Hosted & Automation (33 skills)

**Real user prompts:**
- "Create an n8n workflow that sends Slack alerts on new GitHub issues"
- "Set up a backup cron job for my Postgres database"
- "Configure Paperless-NGX to auto-tag incoming documents"
- "Check the status of all my self-hosted services"
- "Set up a reverse proxy for my local services"

**Claw Harnessing domain:** `config-devops`, `shell-scripting`
**Verification:** exit_code, file_contains
**Example generation prompt:** `"生成 5 个 config-devops 任务，自托管服务配置（cron、Nginx、Docker Compose）"`

---

## Summary: Domain Coverage

| Claw Harnessing Domain | Awesome Skills Categories Covered | # Skills |
|---|---|---|
| `bug-fix` | Coding Agents, Security, iOS/macOS | ~1,266 |
| `feature-impl` | Coding Agents, Web/Frontend, AI/LLMs, Gaming | ~2,314 |
| `git-workflow` | Git & GitHub | 167 |
| `shell-scripting` | CLI Utilities, Clawdbot Tools, Self-Hosted | 249 |
| `data-processing` | Search, PDF/Docs, Health, Speech, Data/Analytics, Image/Video | 774 |
| `config-devops` | DevOps/Cloud, iOS/macOS, Self-Hosted | 455 |
| `communication` | Communication, Productivity, Calendar, Marketing, Shopping, Notes, Apple, Transportation, Moltbook | 891 |
| `smart-home` | Smart Home/IoT, Media/Streaming | 126 |
| `browser-scraping` | Browser/Automation | 322 |
| **Total coverage** | | **5,564** (covers all 5,197 unique + overlaps) |
