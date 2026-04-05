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

def encode(text):
    words = text.split()
    transformed = [transform(w) for w in words]
    return ' '.join(transformed)

if __name__ == '__main__':
    inputs = [
        'hello world',
        'Python3 is great',
        'abc 123 xyz',
        'foo bar baz 999',
        'Test Case 42'
    ]
    for inp in inputs:
        print(f'{inp!r} -> {encode(inp)!r}')
