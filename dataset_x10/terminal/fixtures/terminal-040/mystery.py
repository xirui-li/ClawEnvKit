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
    return encode(text, 26 - shift)

def count_vowels(text):
    return sum(1 for c in text if c.lower() in 'aeiou')

def reverse_words(sentence):
    return ' '.join(sentence.split()[::-1])

def caesar_checksum(text, shift):
    encoded = encode(text, shift)
    return sum(ord(c) for c in encoded) % 256

if __name__ == '__main__':
    samples = [
        ('Hello World', 3),
        ('Python 3.9', 7),
        ('Secret Message!', 13),
        ('abcXYZ 789', 5),
    ]

    for text, shift in samples:
        enc = encode(text, shift)
        dec = decode(enc, shift)
        vowels = count_vowels(text)
        rev = reverse_words(text)
        chk = caesar_checksum(text, shift)
        print(f'Original : {text}')
        print(f'Shift    : {shift}')
        print(f'Encoded  : {enc}')
        print(f'Decoded  : {dec}')
        print(f'Vowels   : {vowels}')
        print(f'Reversed : {rev}')
        print(f'Checksum : {chk}')
        print('---')
