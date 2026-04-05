import sqlite3
import sys

def get_connection(db_path):
    return sqlite3.connect(db_path)

def avg_salary_by_department(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT department, ROUND(AVG(salary), 2) as avg_sal "
        "FROM employees GROUP BY department ORDER BY avg_sal DESC"
    )
    return cursor.fetchall()

def top_earner_per_department(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT department, name, salary FROM employees e1 "
        "WHERE salary = (SELECT MAX(salary) FROM employees e2 WHERE e2.department = e1.department) "
        "ORDER BY department"
    )
    return cursor.fetchall()

def active_project_leads(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT e.name, p.name as project, p.budget "
        "FROM projects p JOIN employees e ON p.lead_id = e.id "
        "WHERE p.status = 'active' ORDER BY p.budget DESC"
    )
    return cursor.fetchall()

def total_engineering_salary(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(salary) FROM employees WHERE department = 'Engineering'"
    )
    result = cursor.fetchone()
    return result[0]

def count_by_department(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT department, COUNT(*) as cnt FROM employees GROUP BY department ORDER BY cnt DESC"
    )
    return cursor.fetchall()

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'data.db'
    conn = get_connection(db_path)

    print('=== Average Salary by Department ===')
    for dept, avg in avg_salary_by_department(conn):
        print(f'  {dept}: {avg}')

    print('\n=== Top Earner per Department ===')
    for dept, name, sal in top_earner_per_department(conn):
        print(f'  {dept}: {name} ({sal})')

    print('\n=== Active Project Leads ===')
    for name, project, budget in active_project_leads(conn):
        print(f'  {name} leads {project} (budget: {budget})')

    print('\n=== Total Engineering Salary ===')
    total = total_engineering_salary(conn)
    print(f'  {total}')

    print('\n=== Employee Count by Department ===')
    for dept, cnt in count_by_department(conn):
        print(f'  {dept}: {cnt}')

    conn.close()

if __name__ == '__main__':
    main()
