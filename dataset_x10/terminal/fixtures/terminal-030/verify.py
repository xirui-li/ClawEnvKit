import subprocess
import sys

test_cases = [
    ('encode', 'Hello', 'Igomq'),
    ('encode', 'abc', 'bdf'),
    ('encode', 'Python3', 'Rzwkrp3'),
    ('encode', 'Hello World', 'Igomq Yosng'),
    ('encode', 'test123', 'vgwv234'),
    ('decode', 'Igomq', 'Hello'),
    ('decode', 'bdf', 'abc'),
    ('decode', 'Rzwkrp3', 'Python3'),
    ('decode', 'Igomq Yosng', 'Hello World'),
    ('decode', 'vgwv234', 'test123'),
]

passed = 0
failed = 0

for mode, inp, expected in test_cases:
    result = subprocess.run(
        [sys.executable, 'mystery.py', mode, inp],
        capture_output=True, text=True
    )
    actual = result.stdout.strip()
    if actual == expected:
        print(f'PASS: {mode}({inp!r}) => {actual!r}')
        passed += 1
    else:
        print(f'FAIL: {mode}({inp!r}) => {actual!r} (expected {expected!r})')
        failed += 1

print(f'\nResults: {passed} passed, {failed} failed')
