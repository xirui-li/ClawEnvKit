import sqlite3
import sys

def analyze_database(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cursor.fetchall()

    results = {}
    for (table_name,) in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]

        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        col_names = [col[1] for col in columns]

        results[table_name] = {
            'row_count': count,
            'columns': col_names
        }

    conn.close()
    return results

def summarize(results):
    total_rows = 0
    for table, info in sorted(results.items()):
        print(f"Table: {table}")
        print(f"  Columns: {', '.join(info['columns'])}")
        print(f"  Row count: {info['row_count']}")
        total_rows += info['row_count']
    print(f"Total rows across all tables: {total_rows}")

if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'sample.db'
    data = analyze_database(db_path)
    summarize(data)
