You are generating a training task instruction for an AI coding agent.

Domain: {domain}
Skill target: {skill_target}
Difficulty: {difficulty}

Difficulty guidelines:
- easy: single straightforward action, 1-3 steps to solve, involves 1-2 files
- medium: requires understanding context, 3-6 steps to solve, involves 2-4 files
- hard: multi-step problem requiring reasoning, 5-10 steps to solve, involves 3-6 files

{prior_instructions_block}

Generate ONE task instruction that:
1. Is concrete and specific — the agent should know exactly what to do
2. Is achievable using only command-line tools (bash, python3, etc.) in a Linux container
3. Matches the specified difficulty level
4. Exercises the specified skill target
5. Does NOT require network access, GUI, or interactive input
6. Is self-contained — all necessary context is in the instruction itself
7. ALL file operations MUST happen inside /workspace/ — NEVER use /tmp, /etc, /home, or any path outside /workspace/. The agent's working directory is /workspace/.

Return ONLY the instruction text as a plain string. No JSON, no markdown, no explanation.
