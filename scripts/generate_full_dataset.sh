#!/bin/bash
# Generate complete dataset: 64 matched + 40 remaining = 104 tasks
# One script, runs sequentially.
#
# Usage:
#   cd claw-harnessing
#   bash scripts/generate_full_dataset.sh

set -e
cd "$(dirname "$0")/.."

START_TIME=$(date +%s)
echo "=== Dataset Generation ==="
echo "Start: $(date)"
echo ""

echo "=== Cleaning dataset/ ==="
rm -rf dataset/*

echo "=== Step 1/2: Generating 64 matched tasks ==="
python3 scripts/generate_matched_dataset.py --output dataset

echo ""
echo "=== Step 2/2: Generating 40 remaining tasks ==="
python3 scripts/generate_remaining_40.py

echo ""
echo "=== Verifying ==="
TOTAL=$(find dataset/ -name "*.yaml" | wc -l | tr -d ' ')
echo "Total tasks: $TOTAL"

python3 -c "
import yaml
from pathlib import Path
tasks = list(Path('dataset').rglob('*.yaml'))
old_style = 0
for f in tasks:
    c = yaml.safe_load(open(f))
    for comp in c.get('scoring_components', []):
        t = comp.get('check', {}).get('type', '')
        if t in ('audit_count_gte', 'audit_count_equals', 'file_exists'):
            old_style += 1
            break
llm_weights = []
for f in tasks:
    c = yaml.safe_load(open(f))
    comps = c.get('scoring_components', [])
    llm_w = sum(comp.get('weight',0) for comp in comps if comp.get('check',{}).get('type')=='llm_judge')
    llm_weights.append(llm_w)
mean_llm = sum(llm_weights)/len(llm_weights)
print(f'  Outcome-oriented: {len(tasks) - old_style}/{len(tasks)}')
print(f'  Still prescriptive: {old_style}')
print(f'  Avg LLM judge: {mean_llm:.1%}')
print(f'  Avg rule: {1-mean_llm:.1%}')
"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS_REMAINING=$((ELAPSED % 60))

echo ""
echo "=== Done ==="
echo "End: $(date)"
echo "Wall time: ${MINUTES}m ${SECONDS_REMAINING}s"

# Estimate cost (Sonnet: ~$3/M input, ~$15/M output, ~4K tokens per task)
TOTAL=$(find dataset/ -name "*.yaml" | wc -l | tr -d ' ')
# ~2K input + ~2K output per task, with retries ~1.5x
EST_INPUT_TOKENS=$((TOTAL * 2000 * 3 / 2))
EST_OUTPUT_TOKENS=$((TOTAL * 2000 * 3 / 2))
echo "Estimated API cost: ~\$$(python3 -c "
input_t = $EST_INPUT_TOKENS
output_t = $EST_OUTPUT_TOKENS
cost = (input_t * 3 + output_t * 15) / 1_000_000
print(f'{cost:.2f}')
")"

# Save generation report
python3 -c "
import json, yaml
from pathlib import Path
from datetime import datetime

tasks = list(Path('dataset').rglob('*.yaml'))
llm_weights = []
action_drift = 0
for f in tasks:
    c = yaml.safe_load(open(f))
    comps = c.get('scoring_components', [])
    tool_names = {t.get('name','') for t in c.get('tools', []) if t.get('name')}
    llm_w = sum(comp.get('weight',0) for comp in comps if comp.get('check',{}).get('type')=='llm_judge')
    llm_weights.append(llm_w)
    for comp in comps:
        action = comp.get('check',{}).get('action','')
        if action and tool_names and action not in tool_names:
            action_drift += 1
            break

report = {
    'generated_at': datetime.now().isoformat(),
    'wall_time_seconds': $ELAPSED,
    'total_tasks': len(tasks),
    'directories': len(set(f.parent.name for f in tasks)),
    'avg_llm_judge_weight': sum(llm_weights)/len(llm_weights) if llm_weights else 0,
    'action_name_drift': action_drift,
    'estimated_cost_usd': round(($EST_INPUT_TOKENS * 3 + $EST_OUTPUT_TOKENS * 15) / 1_000_000, 2),
}
with open('dataset/generation_report.json', 'w') as f:
    json.dump(report, f, indent=2)
print(f'Report saved to dataset/generation_report.json')
print(json.dumps(report, indent=2))
"
