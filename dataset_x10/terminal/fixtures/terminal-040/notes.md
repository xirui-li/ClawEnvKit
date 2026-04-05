# Caesar Cipher Reverse Engineering Task

## Objective
Predict the output of `mystery.py` without running it.

## Functions
- `encode(text, shift)`: Caesar cipher encoding for letters, digit rotation for numbers
- `decode(text, shift)`: Reverses encoding by shifting in opposite direction
- `count_vowels(text)`: Counts vowels (a, e, i, o, u) case-insensitively
- `reverse_words(sentence)`: Reverses word order in a sentence
- `caesar_checksum(text, shift)`: Encodes text then sums ASCII values mod 256

## Test Cases
| Original       | Shift | Encoded          | Vowels | Checksum |
|----------------|-------|------------------|--------|----------|
| Hello World    | 3     | Khoor Zruog      | 3      | 27       |
| Python 3.9     | 7     | Wfaovu 0.6       | 2      | 149      |
| Secret Message!| 13    | Frperg Zrffntr!  | 5      | 218      |
| abcXYZ 789     | 5     | fghCDE 234       | 1      | 93       |

## Notes
- Digits wrap around 0-9 with the given shift
- Non-alphanumeric characters are passed through unchanged
- Checksum is computed on the ENCODED string, not the original
