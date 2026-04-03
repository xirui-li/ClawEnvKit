import sys

def encode(text, shift):
    result = []
    for ch in text:
        if ch.isalpha():
            base = ord('A') if ch.isupper() else ord('a')
            result.append(chr((ord(ch) - base + shift) % 26 + base))
        elif ch.isdigit():
            result.append(chr((ord(ch) - ord('0') + shift) % 10 + ord('0')))
        else:
            result.append(ch)
    return ''.join(result)

def decode(text, shift):
    return encode(text, -shift)

def count_vowels(text):
    return sum(1 for c in text.lower() if c in 'aeiou')

def reverse_words(sentence):
    return ' '.join(sentence.split()[::-1])

def checksum(text):
    return sum(ord(c) for c in text) % 256

if __name__ == '__main__':
    samples = [
        ('Hello, World!', 3),
        ('Python3 is Fun!', 13),
        ('abcXYZ789', 5),
        ('The quick brown fox', 7),
    ]

    for text, shift in samples:
        encoded = encode(text, shift)
        decoded = decode(encoded, shift)
        vowels = count_vowels(text)
        reversed_s = reverse_words(text)
        chk = checksum(text)
        print(f'Original : {text}')
        print(f'Encoded  : {encoded}')
        print(f'Decoded  : {decoded}')
        print(f'Vowels   : {vowels}')
        print(f'Reversed : {reversed_s}')
        print(f'Checksum : {chk}')
        print('---')
