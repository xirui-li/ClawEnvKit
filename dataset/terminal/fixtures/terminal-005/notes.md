# Reverse Engineering Task

## Goal
Analyze `mystery.py` and predict its output for each sample input.

## Functions
- `encode(text, shift)`: Caesar cipher on letters, rotates digits by shift mod 10
- `decode(text, shift)`: Reverses encode by applying negative shift
- `count_vowels(text)`: Counts vowels (a, e, i, o, u) case-insensitively
- `reverse_words(sentence)`: Reverses the order of words in a sentence
- `checksum(text)`: Sum of ASCII values mod 256

## Sample Inputs
| Text              | Shift |
|-------------------|-------|
| Hello, World!     | 3     |
| Python3 is Fun!   | 13    |
| abcXYZ789         | 5     |
| The quick brown fox | 7   |

## Notes
- Non-alpha, non-digit characters are passed through unchanged
- Digit rotation wraps around 0-9
- Letter rotation wraps around a-z or A-Z
