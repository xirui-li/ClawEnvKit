# Reverse Engineering Task

## Goal
Predict the output of `mystery.py` without running it.

## Functions to Analyze

### encode(text, shift)
- Letters are shifted by `shift` positions (Caesar cipher)
- Digits are shifted by `shift % 10` positions
- Non-alphanumeric characters are unchanged

### decode(text, shift)
- Calls encode with `-shift` to reverse the encoding

### count_vowels(text)
- Counts occurrences of a, e, i, o, u (case-insensitive)

### reverse_words(sentence)
- Splits on whitespace and reverses the list of words

### checksum(text)
- Sums ASCII values of all characters, then takes modulo 256

## Sample Verification

| Original         | Shift | Encoded           | Vowels | Checksum |
|------------------|-------|-------------------|--------|----------|
| Hello, World!    | 3     | Khoor, Zruog!     | 3      | 85       |
| Python3 is Fun!  | 7     | Wfaovu0 pz Mbu!   | 3      | 218      |
| abcXYZ 789       | 13    | nopKLM 012        | 1      | 2        |
| The Quick Brown Fox | 5 | Ymj Vznhp Gwtbs Ktc | 5   | 57       |
