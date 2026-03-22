You are generating the initial filesystem state and success criteria for an AI agent training task.

Domain: {domain}
Difficulty: {difficulty}
Available tools: {base_tools}

Task instruction:
{instruction}

Generate a JSON object with two fields:

1. "initial_fs": an object mapping file paths to file contents. These files will be pre-loaded into the task container at /workspace/.
   - All paths MUST start with "/workspace/"
   - Include only files that are necessary for the task (starter code, config files, input data, etc.)
   - File contents must be valid UTF-8 text
   - For easy tasks: 1-2 files. For medium: 2-4 files. For hard: 3-6 files.

2. "success_criteria": a list of verification checks that determine if the agent solved the task correctly.
   Each criterion is an object with a "type" field. Allowed types:
   - {{"type": "exit_code", "cmd": "<shell command>", "expected_exit": 0}} — run a command and check its exit code
   - {{"type": "file_exists", "path": "<path>"}} — check that a file exists
   - {{"type": "file_contains", "path": "<path>", "pattern": "<substring>"}} — check that a file contains a substring
   - {{"type": "file_not_contains", "path": "<path>", "pattern": "<substring>"}} — check that a file does NOT contain a substring

Rules:
- The initial filesystem should set up the PROBLEM, not the solution. The agent must do the work.
- Success criteria should verify the OUTCOME, not the method. Check results, not specific commands.
- All file paths in both initial_fs and success_criteria must start with "/workspace/".
- Do NOT use any criterion type other than the four listed above.
- For easy tasks: 1-2 criteria. For medium: 2-3 criteria. For hard: 3-4 criteria.
- Return ONLY the JSON object. No explanation, no markdown fences, no prose.
