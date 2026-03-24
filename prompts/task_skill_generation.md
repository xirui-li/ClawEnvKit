You are generating a SKILL.md file that provides procedural guidance for an AI agent training task.

A SKILL.md is a document that helps the agent solve a CLASS of tasks (not this specific task). It should contain:
- Step-by-step procedures and workflows
- Code patterns and API usage examples
- Common pitfalls and how to avoid them
- Best practices for the domain

Domain: {domain}
Skill target: {skill_target}
Difficulty: {difficulty}

Task instruction (for context only — the skill should NOT contain the solution):
{instruction}

Generate a SKILL.md file with YAML frontmatter. Requirements:
1. The skill must provide PROCEDURAL GUIDANCE (how to approach), not the SOLUTION (what to output)
2. Include 2-3 code examples showing relevant patterns (but NOT solving this specific task)
3. Include a "Common Mistakes" section with 2-3 pitfalls
4. Keep it focused — 2-3 modules/sections, not comprehensive documentation
5. The skill should be useful for similar tasks, not just this one

Format:
```
---
name: <skill-name>
description: <one-line description>
---

# <Skill Title>

## When to use
<when this skill is relevant>

## Workflow
<step-by-step procedure>

## Code Examples
<2-3 relevant code patterns>

## Common Mistakes
<pitfalls to avoid>
```

Return ONLY the SKILL.md content. No JSON wrapper, no extra markdown fences around the whole thing.
