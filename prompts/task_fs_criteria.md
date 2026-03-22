You are generating the initial filesystem state and success criteria for an AI agent training task.

Domain: {domain}
Difficulty: {difficulty}
Available tools: {base_tools}

Task instruction:
{instruction}

Generate a JSON object with three fields:

1. "initial_fs": an object mapping file paths to file contents. These files will be pre-loaded into the task container at /workspace/.
   - All paths MUST start with "/workspace/"
   - Include only files that are necessary for the task (starter code, config files, input data, etc.)
   - File contents must be valid UTF-8 text
   - For easy tasks: 1-2 files. For medium: 2-4 files. For hard: 3-6 files.

   Domain-specific initial_fs guidelines:
   - bug-fix: Generate a realistic Python project with a SEEDED BUG. Include:
     - Source files under /workspace/src/ (with __init__.py)
     - The bug should be a real coding error (off-by-one, wrong operator, missing edge case, broken import, wrong variable name, etc.)
     - Include a /workspace/README.md describing the project
     - For medium/hard: include multiple source files where the bug requires cross-file understanding
   - feature-impl: Generate a Python project with EXISTING working code. The agent must ADD new functionality.
   - git-workflow: Generate a git repository (include /workspace/.git/ setup commands in solution_patch)
   - data-processing: Include input data files (JSON, CSV, logs) that need to be processed
   - config-devops: Include config files with issues to fix
   - communication: Include a Python script skeleton that the agent must complete. The script should use the `requests` library to call a REST API (e.g., Slack). Include a /workspace/README.md with API documentation. Do NOT include the API URL — the agent reads it from an environment variable (SLACK_API_URL, DISCORD_API_URL, etc.).
   - smart-home: Similar to communication — include a script skeleton + API docs. The agent reads the API URL from an environment variable.
   - browser-scraping: Include HTML files under /workspace/pages/ that the agent must parse. Include a script skeleton.

2. "success_criteria": a list of verification checks that determine if the agent solved the task correctly.
   Each criterion is an object with a "type" field. Allowed types:
   - {{"type": "exit_code", "cmd": "<shell command>", "expected_exit": 0}} — run a command and check its exit code
   - {{"type": "file_exists", "path": "<path>"}} — check that a file exists
   - {{"type": "file_contains", "path": "<path>", "pattern": "<substring>"}} — check that a file contains a substring
   - {{"type": "file_not_contains", "path": "<path>", "pattern": "<substring>"}} — check that a file does NOT contain a substring

   For bug-fix and feature-impl domains, ALWAYS include at least one exit_code criterion that runs the code:
   - {{"type": "exit_code", "cmd": "cd /workspace && python3 -m pytest tests/ -v", "expected_exit": 0}}

3. "solution_patch": a string containing the bash commands that correctly solve the task. This is the gold solution used to validate that the task is solvable and to generate verification tests. Format as one command per line.

Rules:
- The initial filesystem should set up the PROBLEM, not the solution. The agent must do the work.
- Success criteria should verify the OUTCOME, not the method. Check results, not specific commands.
- CRITICAL: ALL file paths in both initial_fs and success_criteria MUST start with "/workspace/". NEVER use /tmp, /etc, /home, or any path outside /workspace/. If the instruction mentions paths outside /workspace/, remap them to /workspace/ equivalents.
- initial_fs MUST NOT be empty — include at least one file (e.g. a README or instruction file).
- Do NOT use any criterion type other than the four listed above.
- For easy tasks: 1-2 criteria. For medium: 2-3 criteria. For hard: 3-4 criteria.
- Return ONLY the JSON object. No explanation, no markdown fences, no prose.
