You are generating a pytest verification test for an AI agent training task.

The test must follow the FAIL_TO_PASS principle:
- It must FAIL when run against the initial filesystem (before the agent acts)
- It must PASS after the correct solution is applied

Task instruction:
{instruction}

Initial filesystem:
{initial_fs_summary}

Solution (what a correct fix looks like):
{solution_patch}

Generate a single Python test file using pytest. Requirements:
1. Import only from standard library + pytest (no external packages)
2. Test functions must start with `test_`
3. Tests must be deterministic (no randomness, no timing-dependent assertions)
4. Tests must be self-contained (read from /workspace/, no network access)
5. Tests should verify BEHAVIOR/OUTPUT, not implementation details
6. Include at least 2 test functions that cover different aspects of the solution
7. Each test function should have a clear docstring explaining what it checks

Example structure:
```python
import subprocess

def test_function_returns_correct_result():
    """Verify the fixed function produces correct output."""
    result = subprocess.run(
        ["python3", "/workspace/src/main.py"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "expected output" in result.stdout

def test_edge_case():
    """Verify the fix handles edge cases."""
    # ...
```

Return ONLY the Python code. No JSON wrapper, no markdown fences, no explanation.
