You are reviewing a generated agent training task for internal consistency.

Task type: {task_type}
Difficulty: {difficulty}
Instruction: {instruction}

Initial filesystem:
{initial_fs}

Success criteria:
{success_criteria}

Check the following:
1. Does the instruction describe a task that is achievable given the initial filesystem?
2. Do the success criteria correctly capture task completion? (i.e., if the agent follows the instruction correctly, will all criteria pass?)
3. Is the difficulty appropriate? (easy = 1-3 steps, medium = 3-6 steps, hard = 5-10 steps)
4. Are there any contradictions between the instruction and the initial filesystem?
5. Are there any success criteria that would pass WITHOUT the agent doing any work?

Return a JSON object with:
- "passed": boolean — true if no blocking issues found, false otherwise
- "issues": list of strings — each string describes one issue found. Empty list if no issues.

Rules:
- Only flag issues that would cause the task to be unsolvable or the criteria to be incorrect.
- Minor style concerns are NOT issues.
- Return ONLY the JSON object. No explanation, no markdown fences, no prose.
