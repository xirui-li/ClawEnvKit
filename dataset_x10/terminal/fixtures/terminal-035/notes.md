# Reverse Engineering Task

## Goal
Predict the output of `mystery.py` without running it.

## Functions
- `encode(text, shift)`: Caesar cipher on letters, rotates digits by shift mod 10
- `decode(text, shift)`: Reverses encode by applying negative shift
- `count_vowels(text)`: Counts a, e, i, o, u (case-insensitive)
- `reverse_words(sentence)`: Reverses word order
- `checksum(text)`: Sum of ASCII values mod 256

## Test Cases
| Original           | Shift | Encoded              | Vowels | Checksum |
|--------------------|-------|----------------------|--------|----------|
| Hello, World!      | 3     | Khoor, Zruog!        | 3      | 185      |
| Python3 is Fun!    | 7     | Wfaovu0 pz Mbu!      | 3      | 218      |
| abc XYZ 123        | 13    | nop KLM 456          | 1      | 186      |
| The quick brown fox| 5     | Ymj vznhp gwtbs ktc  | 5      | 212      |
