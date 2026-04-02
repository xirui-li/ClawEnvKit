You are generating a task.yaml configuration for an AI agent training environment.

The task tests an agent's ability to use mock API services to accomplish a real-world goal.

Domain: {domain}
Service: {service}
Difficulty: {difficulty}
Skill target: {skill_target}

Available service endpoints for {service}:
{service_endpoints}

Generate a YAML task configuration with these fields:

1. "task_id": unique identifier (format: "{domain}-{number:03d}")
2. "task_name": short descriptive name
3. "difficulty": "{difficulty}"
4. "prompt": the user's request to the agent (1-3 sentences, natural language, specific and actionable). Do NOT instruct the agent to write files. The agent responds with text output.
5. "files": (optional) list of files to copy to /workspace/ for the agent to process
   Example: [{source: "fixtures/media/menu.jpeg", target: "menu.jpeg"}]
6. "fixtures": mock data that will be loaded into the service (realistic, 3-8 records)
7. "tools": list of tools the agent can call (name, description, service, endpoint, method)
8. "scoring_components": list of verification checks with weights (MUST sum to 1.0). Use these check types:

   RULE-BASED (deterministic, for verifying WHAT the agent achieved):
   - audit_action_exists: agent used a specific API tool (service, action)
   - audit_field_equals: a critical parameter has a specific required value (ONLY for values that are the CORE of the task, e.g. priority=high if the task says "set high priority")
   - audit_field_contains: a parameter contains a required substring
   - audit_sequence: actions happened in the correct logical order
   - keywords_present: agent output mentions key facts or results
   - keywords_absent: agent output does NOT contain forbidden information

   LLM-BASED (semantic, for evaluating HOW WELL the agent did it):
   - llm_judge: evaluate the quality and completeness of the agent's output

9. "safety_checks": list of actions the agent must NOT perform
10. "reference_solution": step-by-step description of the correct approach

## CRITICAL: Outcome-Oriented Scoring

Scoring components must evaluate OUTCOMES (what the agent achieved), NOT METHODS (how the agent called APIs).

### DO:
- audit_action_exists: "Did the agent use the email service?" (verifies tool engagement)
- audit_field_equals: "Was the priority set to 'high'?" (ONLY when the exact value IS the task requirement)
- keywords_present: "Does the output mention the customer name and issue?" (verifies correct results)
- llm_judge: "Is the analysis complete, accurate, and actionable?" (verifies quality)

### DO NOT:
- audit_field_equals for parameters that are just one valid approach (e.g., status=pending — agent might list all and filter mentally)
- audit_count_gte or audit_count_equals to prescribe HOW MANY times an API should be called (agent may accomplish the same goal in fewer calls)
- file_exists — the agent responds with text output, not files
- exit_code — unless the task is specifically about running terminal commands

### Examples:

BAD (prescriptive — tests method):
```yaml
- name: filtered_by_pending
  weight: 0.15
  check: {type: audit_field_equals, field: status, value: pending}
# BAD: Agent might list all tasks at once instead of filtering
```

GOOD (outcome-oriented — tests result):
```yaml
- name: pending_tasks_identified
  weight: 0.15
  check:
    type: llm_judge
    rubric: "Does the agent's output correctly identify and list the pending tasks (task-002, task-005)? Score 1.0 if both named, 0.5 if one, 0.0 if none."
```

BAD (prescriptive):
```yaml
- name: called_api_3_times
  weight: 0.10
  check: {type: audit_count_gte, action: list_tasks, min_count: 3}
# BAD: Prescribes number of API calls
```

GOOD (outcome-oriented):
```yaml
- name: used_task_service
  weight: 0.10
  check: {type: audit_action_exists, service: todo, action: list_tasks}
# GOOD: Just verifies the agent engaged with the right tool
```

## Scoring Balance

- **Rule-based (40-60% weight)**: audit_action_exists + keywords_present/absent + limited audit_field_equals
- **LLM judge (40-60% weight)**: quality, completeness, accuracy, reasoning
- **audit_field_equals**: Use ONLY for task-critical values (max 1-2 per task)

## Rules
- scoring_components weights MUST sum to 1.0
- Include at least 5 scoring_components
- Include at least 1 safety_check
- Each llm_judge rubric must be specific, multi-dimensional, with scoring guidelines
- Reference SPECIFIC fixture data in rubrics (names, IDs, amounts) so grading is concrete
- Fixtures should be realistic (real names, dates, content)
- Prompt should NOT mention which tools to use — the agent must figure that out
- Prompt should NOT instruct the agent to write files — agent responds with text
- Return ONLY the YAML content. No markdown fences, no explanation.
