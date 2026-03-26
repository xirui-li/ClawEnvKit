# v2 Batch Generation Results

## Test: 1 task per service, 13 services, medium difficulty

**Pass rate: 85% (11/13) on first try, zero retries**

| Service | Status | Task Name | Components | Safety |
|---|---|---|---|---|
| gmail | 💥 YAML error | — | — | — |
| calendar | ✅ | Schedule Team Sync Avoiding Conflicts | 8 | 1 |
| todo | ✅ | Organize high-priority overdue tasks | 13 | 1 |
| contacts | ✅ | Find and Message Engineering Managers | 9 | 4 |
| helpdesk | ✅ | Triage and escalate critical network tickets | 9 | 3 |
| notes | ✅ | Find and Share Q3 Budget Meeting Notes | 8 | 1 |
| crm | 💥 YAML error | — | — | — |
| inventory | ✅ | Restock Low-Stock Electronics Products | 11 | 1 |
| scheduler | ✅ | Disable and Reschedule Stale Nightly Jobs | 9 | 2 |
| finance | ✅ | Compile and Submit Q3 Travel Expense Report | 9 | 1 |
| rss | ✅ | Curate and Publish Weekly AI Newsletter | 9 | 1 |
| kb | ✅ | Update Outdated Password Reset Article | 7 | 1 |
| config | ✅ | Rotate Expired API Keys and Notify Team | 10 | 1 |

## Failure analysis

2 failures were **YAML syntax errors** (long text in fixtures not properly quoted), NOT logical errors. With 1 retry, expected pass rate: ~95%.

Zero config **validation** failures — every parsed YAML had valid check types, correct weight sums, and proper safety checks.

## Key statistics

- Average components per task: 9.3
- Average safety checks per task: 1.5
- All weight sums = 1.00 exactly
- Model: claude-sonnet-4-6
- Total API calls: 13 (one per service)
- Total time: ~45 seconds
