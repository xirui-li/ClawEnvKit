# Reverse Engineering Task

## Goal
Predict the output of `analyze.py` without running it.

## Functions
- `reverse_string(s)`: Reverses the input string character by character.
- `count_vowels(s)`: Counts vowels (a, e, i, o, u) case-insensitively.
- `caesar_cipher(s, shift)`: Applies Caesar cipher with given shift, preserving case and non-alpha chars.
- `word_frequency(s)`: Returns a dict of word frequencies (lowercased).

## Input Data
1. "Hello World"
2. "Python is great"
3. "The quick brown fox jumps over the lazy dog"

## Expected Output
See `expected_output.txt` for the full predicted output.

## Notes
- Caesar cipher wraps around the alphabet (mod 26).
- Word frequency splits on whitespace and lowercases all words.
- The separator line is 50 dashes.
