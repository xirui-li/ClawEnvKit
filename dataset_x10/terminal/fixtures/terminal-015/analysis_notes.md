# Mystery Script Analysis

## What the script does

1. **transform(s)**: Iterates over each character:
   - If alphabetic: uppercase if index is even, lowercase if index is odd
   - If digit: adds 3 (mod 10)
   - Otherwise: keeps as-is

2. **reverse_words(sentence)**: Splits on whitespace and reverses the word order.

3. **encode(text)**: Applies transform first, then reverses word order.

## Example trace

Input: `hello world`
- transform: H(0)e(1)L(2)l(3)O(4) W(6)o(7)R(8)l(9)D(10) => `HeLlO WoRlD`
- reverse_words: `WoRlD HeLlO`

Wait, spaces reset index? No - index is global across the full string.

Actual trace for `hello world` (indices 0-10):
- h(0)->H, e(1)->e, l(2)->L, l(3)->l, o(4)->O, ' '(5)->' ', w(6)->W, o(7)->o, r(8)->R, l(9)->l, d(10)->D
- transform result: `HeLlO WoRlD`
- reverse_words: `WoRlD HeLlO`

## Digit shift

Digits are shifted by +3 mod 10:
- 0->3, 1->4, 2->5, 3->6, 4->7, 5->8, 6->9, 7->0, 8->1, 9->2
