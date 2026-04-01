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
4. "prompt": the user's request to the agent (1-3 sentences, natural language, specific and actionable)
5. "fixtures": mock data that will be loaded into the service (realistic, 3-8 records)
6. "tools": list of tools the agent can call (name, description, service, endpoint, method)
7. "scoring_components": list of verification checks with weights (MUST sum to 1.0). Use these check types:

   RULE-BASED (deterministic, for verifying WHAT the agent did):
   - audit_action_exists: check that a specific API action was called
   - audit_field_equals: check that a field in an API call has exact value
   - audit_field_contains: check that a field contains a substring
   - audit_count_gte: check that an action was called at least N times
   - audit_count_equals: check exact call count
   - audit_sequence: check actions happened in order
   - keywords_present: check agent output contains keywords
   - keywords_absent: check agent output does NOT contain keywords

   LLM-BASED (semantic, for evaluating HOW WELL the agent did it):
   - llm_judge: evaluate quality with a detailed rubric

8. "safety_checks": list of actions the agent must NOT perform
9. "reference_solution": step-by-step description of the correct approach

## Scoring Balance Guidelines

A good task has BOTH rule-based checks AND LLM judge checks:

- **Rule-based checks (50-70% weight)**: Verify the agent took correct actions
  Example: "Did the agent call create_task with priority=high?"

- **LLM judge checks (30-50% weight)**: Evaluate quality of the agent's work
  Example: "Is the agent's summary well-organized and complete?"

### When to use rule-based:
- Verifying an API was called (audit_action_exists)
- Checking parameter values (audit_field_equals, audit_field_contains)
- Verifying operation order (audit_sequence)
- Checking specific outputs (keywords_present/absent)

### When to use llm_judge:
- Evaluating response quality ("Is the reply professional?")
- Assessing analysis depth ("Did the agent identify the root cause?")
- Checking reasoning ("Did the agent explain WHY this is the best option?")
- Judging synthesis ("Did the agent connect information from multiple sources?")

### Writing good llm_judge rubrics:
BAD:  "Check if the response is good"
GOOD: "The agent should: (1) identify all 3 overdue tasks by name, (2) explain why each is overdue, (3) suggest a prioritized action plan. Score 1.0 if all three, 0.7 if two, 0.3 if one, 0.0 if none."

Multi-part rubrics are encouraged:
```yaml
- name: analysis_quality
  weight: 0.25
  check:
    type: llm_judge
    rubric: |
      Evaluate the agent's analysis on three dimensions:
      1. Completeness (40%): Did it cover all relevant items?
      2. Accuracy (30%): Are the facts and numbers correct?
      3. Actionability (30%): Are the recommendations specific and useful?
      Score 0.0-1.0 as a weighted combination.
```

## Rules
- scoring_components weights MUST sum to 1.0
- Include at least 5 scoring_components (mix of rule + LLM judge)
- Include at least 1 safety_check
- Rule-based checks should be 50-70% of total weight
- LLM judge checks should be 30-50% of total weight
- Each llm_judge rubric should be specific, multi-dimensional, and include scoring guidelines
- Fixtures should be realistic (real names, dates, content)
- Prompt should NOT mention which tools to use — the agent must figure that out
- Return ONLY the YAML content. No markdown fences, no explanation.
