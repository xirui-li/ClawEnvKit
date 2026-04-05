import sys

def transform(s):
    result = []
    for i, c in enumerate(s):
        if c.isalpha():
            if i % 2 == 0:
                result.append(c.upper())
            else:
                result.append(c.lower())
        elif c.isdigit():
            result.append(str((int(c) + 3) % 10))
        else:
            result.append(c)
    return ''.join(result)

def reverse_words(sentence):
    words = sentence.split()
    return ' '.join(words[::-1])

def encode(text):
    step1 = transform(text)
    step2 = reverse_words(step1)
    return step2

if __name__ == '__main__':
    inputs = [
        'hello world',
        'abc 123 xyz',
        'Python3 is great',
        'foo bar baz 456',
        'reverse me please'
    ]
    for inp in inputs:
        print(encode(inp))
