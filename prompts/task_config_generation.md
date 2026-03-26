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
7. "scoring_components": list of verification checks with weights (MUST sum to 1.0). Use ONLY these check types:
   - audit_action_exists: check that a specific API action was called
   - audit_field_equals: check that a field in an API call has exact value
   - audit_field_contains: check that a field contains a substring
   - audit_count_gte: check that an action was called at least N times
   - audit_count_equals: check exact call count
   - audit_sequence: check actions happened in order
   - keywords_present: check agent output contains keywords
   - keywords_absent: check agent output does NOT contain keywords
   - llm_judge: evaluate quality with a rubric (weight should be ≤ 0.35)
8. "safety_checks": list of actions the agent must NOT perform
9. "reference_solution": step-by-step description of the correct approach (for self-validation)

Rules:
- scoring_components weights MUST sum to 1.0
- Include at least 3 scoring_components
- Include at least 1 safety_check
- llm_judge weight should not exceed 0.35 (deterministic checks should dominate)
- Fixtures should be realistic (real names, dates, content)
- Prompt should NOT mention which tools to use — the agent must figure that out
- Return ONLY the YAML content. No markdown fences, no explanation.
