# Analyze mystery.py and predict its output
# Run mystery.py and compare with expected_output.txt

import subprocess
import sys

def main():
    result = subprocess.run(
        [sys.executable, 'mystery.py'],
        capture_output=True,
        text=True
    )
    actual = result.stdout
    with open('expected_output.txt', 'r') as f:
        expected = f.read()
    if actual == expected:
        print('PASS: Output matches expected.')
    else:
        print('FAIL: Output does not match expected.')
        print('--- Expected ---')
        print(expected)
        print('--- Actual ---')
        print(actual)

if __name__ == '__main__':
    main()
