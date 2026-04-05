# Reverse Engineering Task

## Overview
This task involves predicting the output of `analyze.py` without running it.

## Functions
- `reverse_string(s)`: Reverses a string using slicing `s[::-1]`
- `count_vowels(s)`: Counts vowels (a, e, i, o, u) case-insensitively
- `caesar_cipher(text, shift)`: Applies Caesar cipher with given shift
- `word_frequency(text)`: Returns word frequency dict sorted by count descending

## Sample Inputs
1. `"Hello World"`
2. `"The quick brown fox jumps over the lazy dog"`
3. `"Python is great and Python is fun"`

## Notes
- Caesar cipher wraps around alphabet (z+1 = a)
- word_frequency strips punctuation before counting
- Top words list shows first 3 items from sorted frequency dict
