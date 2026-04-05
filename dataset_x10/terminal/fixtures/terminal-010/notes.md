# Reverse Engineering Task

## Goal
Predict the output of `mystery.py` without running it.

## Rules
1. Read `mystery.py` carefully.
2. Trace through each function manually.
3. Write your predicted output to a file.
4. Run `analyze.py` to check your answer.

## Functions
- `transform(s)`: Iterates over each character. If alpha and index is even -> uppercase; if alpha and index is odd -> lowercase. If digit -> shift by +3 mod 10. Otherwise keep as-is.
- `encode(text)`: Splits text into words, applies `transform` to each word independently (so index resets per word), then joins with spaces.

## Example Trace
Input word: `hello`
- h (i=0, even) -> H
- e (i=1, odd)  -> e
- l (i=2, even) -> L
- l (i=3, odd)  -> l
- o (i=4, even) -> O
Result: `HeLlO`
