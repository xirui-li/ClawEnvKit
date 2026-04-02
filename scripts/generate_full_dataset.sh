#!/bin/bash
# Generate complete dataset: 64 matched + 40 remaining = 104 tasks
# One script, runs sequentially.
#
# Usage:
#   cd claw-harnessing
#   bash scripts/generate_full_dataset.sh

set -e
cd "$(dirname "$0")/.."

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

echo ""
echo "=== Done ==="
