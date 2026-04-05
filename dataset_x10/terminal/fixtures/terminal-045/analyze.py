import sys
import json

def reverse_string(s):
    return s[::-1]

def count_vowels(s):
    return sum(1 for c in s.lower() if c in 'aeiou')

def caesar_cipher(s, shift):
    result = []
    for c in s:
        if c.isalpha():
            base = ord('A') if c.isupper() else ord('a')
            result.append(chr((ord(c) - base + shift) % 26 + base))
        else:
            result.append(c)
    return ''.join(result)

def word_frequency(s):
    words = s.lower().split()
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq

def main():
    data = [
        "Hello World",
        "Python is great",
        "The quick brown fox jumps over the lazy dog"
    ]

    results = []
    for text in data:
        entry = {
            "original": text,
            "reversed": reverse_string(text),
            "vowel_count": count_vowels(text),
            "caesar_shift3": caesar_cipher(text, 3),
            "word_freq": word_frequency(text)
        }
        results.append(entry)

    for r in results:
        print(f"Original     : {r['original']}")
        print(f"Reversed     : {r['reversed']}")
        print(f"Vowel Count  : {r['vowel_count']}")
        print(f"Caesar (+3)  : {r['caesar_shift3']}")
        print(f"Word Freq    : {r['word_freq']}")
        print("-" * 50)

if __name__ == '__main__':
    main()
