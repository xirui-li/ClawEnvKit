import sys
import json

def process_data(records):
    results = []
    total = 0
    for record in records:
        name = record.get('name', 'Unknown')
        value = record.get('value', 0)
        category = record.get('category', 'misc')
        adjusted = value * 1.1 if category == 'premium' else value * 0.9
        total += adjusted
        results.append({
            'name': name,
            'original': value,
            'adjusted': round(adjusted, 2),
            'category': category
        })
    avg = round(total / len(records), 2) if records else 0
    return results, round(total, 2), avg

def main():
    data = [
        {'name': 'Alice', 'value': 100, 'category': 'premium'},
        {'name': 'Bob', 'value': 200, 'category': 'standard'},
        {'name': 'Carol', 'value': 150, 'category': 'premium'},
        {'name': 'Dave', 'value': 80, 'category': 'standard'},
        {'name': 'Eve', 'value': 300, 'category': 'premium'}
    ]

    results, total, avg = process_data(data)

    print('Processed Records:')
    for r in results:
        print(f"  {r['name']}: original={r['original']}, adjusted={r['adjusted']}, category={r['category']}")
    print(f'Total adjusted value: {total}')
    print(f'Average adjusted value: {avg}')

if __name__ == '__main__':
    main()
