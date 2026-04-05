# Scaled Dataset Generation Report

## Overview

Generated 1,474 tasks (10× Claw-Eval distribution) using Claude Sonnet 4.6 via OpenRouter.

| Metric | Value |
|---|---|
| **Total generated** | 1,474 / 1,530 planned (96.3%) |
| **Validity** | 1,462 / 1,474 pass validation (99.2%) |
| **API tasks** | 1,205 |
| **File-dependent tasks** | 269 |
| **Model** | `anthropic/claude-sonnet-4-6` via OpenRouter |
| **Time** | 367 minutes (~6.1 hours) |
| **Estimated cost** | ~$61.02 |
| **Avg LLM judge weight** | 34.0% |
| **Avg rule-based weight** | 66.0% |

## Task Sources (10× multiplied)

| Source | Count | Description |
|---|---|---|
| matched | 520 | Direct mock service fixture match |
| overlap | 490 | Claw-Eval overlapping task set |
| file-dep | 270 | File-dependent (OCR, terminal, PDF, CSV) |
| web-mapped | 210 | Zero-fixture tasks mapped to web_real |
| cross-ref | 40 | Cross-referenced fixtures (rss, config) |

## Token Usage

| | Tokens | Cost |
|---|---|---|
| Input | ~2.65M | ~$7.96 (@ $3/MTok) |
| Output | ~3.54M | ~$53.06 (@ $15/MTok) |
| **Total** | ~6.19M | **~$61.02** |

## Cost Efficiency

| | Per task | Per 1,000 tasks |
|---|---|---|
| Cost | $0.041 | $41.40 |
| Time | 14.9 seconds | 4.1 hours |

## Generation Config

```bash
LLM_PROVIDER=openrouter \
MODEL=anthropic/claude-sonnet-4-6 \
python3 -u scripts/generate_dataset.py \
  --multiplier 10 \
  --output dataset_scaled \
  --resume \
  --workers 4
```

## Failures

- **56 tasks not generated** (1,530 - 1,474 = 56): fixture generation failures (PDF/image) or 5× retry exhausted
- **12 tasks generated but fail validation**: likely llm_judge weight cap or minor schema issues
- **Net usable: 1,462 tasks (95.6% of planned)**

## Notes

- Initial attempt used GPT-5.4 directly ($2.50/$15 per MTok) but was ~10× slower (40-100s/task vs 5-10s/task for Sonnet)
- GPT-5.4 generated 334 tasks in 6 hours before switching to Sonnet
- `--resume` flag preserved GPT-5.4 tasks and continued with Sonnet
- Final dataset is a mix of GPT-5.4 (first ~334) and Sonnet 4.6 (remaining ~1,140)
- Parallel workers (4) provided ~3-4× speedup over sequential
- Rate limiting caused slowdowns mid-run (18s/task peaks vs 1s/task baseline)
