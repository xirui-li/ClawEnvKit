# DB Analysis Script Notes

## Purpose
This script connects to `data.db` and runs several analytical queries against the `employees` and `projects` tables.

## Usage
```
python analyze.py data.db
```

## Queries Performed
1. Average salary grouped by department (descending)
2. Top earner in each department
3. Employees leading active projects, sorted by budget descending
4. Total salary expenditure for Engineering department
5. Employee headcount per department

## Expected Results Summary
- Engineering has 4 employees with avg salary 100000.0
- Henry Moore is the highest paid at 112000.0
- Total Engineering payroll: 400000.0
- Delta project has the largest active budget at 200000.0
