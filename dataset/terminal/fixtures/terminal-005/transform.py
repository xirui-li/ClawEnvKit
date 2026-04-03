def encode_string(s):
    return ''.join(chr(ord(c) + 3) for c in s)

def decode_string(s):
    return ''.join(chr(ord(c) - 3) for c in s)

def caesar_cipher(text, shift):
    result = []
    for ch in text:
        if ch.isalpha():
            base = ord('A') if ch.isupper() else ord('a')
            result.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            result.append(ch)
    return ''.join(result)

def run_transforms():
    words = ['hello', 'world', 'python', 'test']
    print('Encoded strings:')
    for w in words:
        enc = encode_string(w)
        dec = decode_string(enc)
        print(f'  {w} -> {enc} -> {dec}')

    messages = ['Attack at dawn', 'Hello World', 'Secret Message']
    shift = 13
    print(f'Caesar cipher (shift={shift}):')
    for msg in messages:
        encrypted = caesar_cipher(msg, shift)
        decrypted = caesar_cipher(encrypted, -shift)
        print(f'  "{msg}" -> "{encrypted}" -> "{decrypted}"')

if __name__ == '__main__':
    run_transforms()
