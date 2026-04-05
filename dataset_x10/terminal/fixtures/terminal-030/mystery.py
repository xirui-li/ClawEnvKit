import sys

def transform(s):
    result = []
    for i, c in enumerate(s):
        if c.isalpha():
            shift = (i % 3) + 1
            if c.islower():
                result.append(chr((ord(c) - ord('a') + shift) % 26 + ord('a')))
            else:
                result.append(chr((ord(c) - ord('A') + shift) % 26 + ord('A')))
        elif c.isdigit():
            result.append(str((int(c) + i) % 10))
        else:
            result.append(c)
    return ''.join(result)

def reverse_transform(s):
    result = []
    for i, c in enumerate(s):
        if c.isalpha():
            shift = (i % 3) + 1
            if c.islower():
                result.append(chr((ord(c) - ord('a') - shift) % 26 + ord('a')))
            else:
                result.append(chr((ord(c) - ord('A') - shift) % 26 + ord('A')))
        elif c.isdigit():
            result.append(str((int(c) - i) % 10))
        else:
            result.append(c)
    return ''.join(result)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: mystery.py <encode|decode> <text>')
        sys.exit(1)
    mode = sys.argv[1]
    text = sys.argv[2]
    if mode == 'encode':
        print(transform(text))
    elif mode == 'decode':
        print(reverse_transform(text))
    else:
        print('Unknown mode:', mode)
        sys.exit(1)
