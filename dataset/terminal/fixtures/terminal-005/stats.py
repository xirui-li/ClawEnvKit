import math

def mean(data):
    return sum(data) / len(data)

def variance(data):
    m = mean(data)
    return sum((x - m) ** 2 for x in data) / len(data)

def std_dev(data):
    return math.sqrt(variance(data))

def median(data):
    s = sorted(data)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]

def mode(data):
    freq = {}
    for x in data:
        freq[x] = freq.get(x, 0) + 1
    max_freq = max(freq.values())
    modes = [k for k, v in freq.items() if v == max_freq]
    return sorted(modes)

def summarize(data):
    print(f'Count:    {len(data)}')
    print(f'Sum:      {sum(data)}')
    print(f'Min:      {min(data)}')
    print(f'Max:      {max(data)}')
    print(f'Mean:     {round(mean(data), 4)}')
    print(f'Median:   {median(data)}')
    print(f'Std Dev:  {round(std_dev(data), 4)}')
    print(f'Mode(s):  {mode(data)}')

if __name__ == '__main__':
    dataset = [4, 7, 13, 2, 7, 9, 4, 7, 1, 15, 3, 7]
    print('Dataset:', dataset)
    summarize(dataset)
