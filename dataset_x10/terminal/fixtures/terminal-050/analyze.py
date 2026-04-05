import sys
import json

def reverse_string(s):
    return s[::-1]

def count_vowels(s):
    return sum(1 for c in s.lower() if c in 'aeiou')

def caesar_cipher(text, shift):
    result = []
    for ch in text:
        if ch.isalpha():
            base = ord('A') if ch.isupper() else ord('a')
            result.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            result.append(ch)
    return ''.join(result)

def word_frequency(text):
    freq = {}
    for word in text.lower().split():
        word = word.strip('.,!?;:')
        freq[word] = freq.get(word, 0) + 1
    return dict(sorted(freq.items(), key=lambda x: x[1], reverse=True))

def main():
    samples = [
        "Hello World",
        "The quick brown fox jumps over the lazy dog",
        "Python is great and Python is fun"
    ]

    for text in samples:
        print(f"Original: {text}")
        print(f"Reversed: {reverse_string(text)}")
        print(f"Vowel count: {count_vowels(text)}")
        print(f"Caesar shift 3: {caesar_cipher(text, 3)}")
        freq = word_frequency(text)
        top = list(freq.items())[:3]
        print(f"Top words: {top}")
        print("---")

if __name__ == '__main__':
    main()
