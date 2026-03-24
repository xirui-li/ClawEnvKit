You are generating a training task instruction for an AI coding agent.

Domain: {domain}
Skill target: {skill_target}
Difficulty: {difficulty}
Required task approach: {task_approach}

Difficulty guidelines:
- easy: single straightforward action, 1-3 steps to solve, involves 1-2 files
- medium: requires understanding context, 3-6 steps to solve, involves 2-4 files
- hard: multi-step problem requiring reasoning, 5-10 steps to solve, involves 3-6 files

Task approach guidelines (IMPORTANT — you MUST follow the required approach above):
- create: Write new code/files/scripts from scratch to accomplish a goal
- fix: Debug and fix an existing broken codebase (wrong output, crash, error)
- refactor: Improve existing working code (better structure, performance, readability) without changing behavior
- test: Write tests for existing code, or fix failing tests
- optimize: Make existing code faster, use less memory, or handle edge cases
- integrate: Connect multiple existing components or APIs together
- migrate: Convert code from one format/framework/version to another

Domain-specific guidelines:
- bug-fix: The instruction should describe a bug or failing behavior the agent must fix in an existing Python project. Mention the symptom (e.g., "function returns wrong result", "script crashes with TypeError") but NOT the root cause or solution. The agent should diagnose and fix the code.
- feature-impl: The instruction should describe a new feature to add to an existing Python project. Be specific about expected behavior, inputs, and outputs.
- git-workflow: The instruction should involve git operations (branching, merging, resolving conflicts, rebasing) on an existing repo in /workspace/.
- data-processing: The instruction should involve parsing, transforming, or analyzing data files (JSON, CSV, logs) using Python or CLI tools.
- shell-scripting: The instruction should involve writing or fixing bash scripts with pipes, loops, environment variables, or process management.
- config-devops: The instruction should involve editing configuration files (YAML, TOML, INI, Dockerfile) to fix or change system behavior.
- communication: The instruction should involve writing a Python script that interacts with a messaging API (Slack, Discord, email). The script should use HTTP requests to send messages, list channels/users, or manage conversations. The API endpoint will be available at an environment variable URL (e.g., SLACK_API_URL). Do NOT mention that it's a mock — treat it as a real API.
- smart-home: The instruction should involve writing a Python script that controls smart home devices via REST API (lights, thermostats, sensors). The API endpoint will be at an environment variable URL (e.g., HUE_API_URL).
- browser-scraping: The instruction should involve writing a Python script that downloads and parses HTML pages from a local web server to extract structured data. The server URL will be available at an environment variable.

{prior_instructions_block}

Generate ONE task instruction that:
1. Is concrete and specific — the agent should know exactly what to do
2. Is achievable using only command-line tools (bash, python3, etc.) in a Linux container
3. Matches the specified difficulty level
4. Exercises the specified skill target
5. Follows the REQUIRED task approach (create/fix/refactor/test/optimize/integrate/migrate)
6. Does NOT require network access, GUI, or interactive input
7. Is self-contained — all necessary context is in the instruction itself
8. ALL file operations MUST happen inside /workspace/ — NEVER use /tmp, /etc, /home, or any path outside /workspace/. The agent's working directory is /workspace/.
9. Must be STRUCTURALLY DIFFERENT from previously generated tasks — do NOT generate another variation of the same pattern

Return ONLY the instruction text as a plain string. No JSON, no markdown, no explanation.
