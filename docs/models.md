# Backbone Models

ClawEnvKit can run with provider-native Anthropic and OpenAI configurations or with tool-calling models routed through OpenRouter. In practice, any model that can follow the task prompt and call tools reliably can be evaluated, but the list below captures the main tested backbone IDs used in the repo.

## Model Routing

- Anthropic-native and OpenAI-native setups can be passed directly through environment variables or agent-specific config.
- OpenRouter-backed runs use `MODEL=<provider/model-id>` and route tool calls through the same Docker runtime.
- The runtime is not limited to this table; these are simply the most common tested examples.

## Tested Backbone IDs

| # | Model | Provider | OpenRouter ID | $/MTok (in/out) |
|---|---|---|---|---|
| 1 | **Claude Sonnet 4.6** | Anthropic | `anthropic/claude-sonnet-4.6` | $3 / $15 |
| 2 | **GPT 5.4** | OpenAI | `openai/gpt-5.4` | $2.50 / $15 |
| 3 | **Claude Opus 4.6** | Anthropic | `anthropic/claude-opus-4.6` | $5 / $25 |
| 4 | **MiMo V2 Pro** | Xiaomi | `xiaomi/mimo-v2-pro` | $1 / $3 |
| 5 | **GLM 5** | Zhipu AI | `z-ai/glm-5` | $0.72 / $2.30 |
| 6 | **MiMo V2 Omni** | Xiaomi | `xiaomi/mimo-v2-omni` | $0.40 / $2 |
| 7 | **Step 3.5 Flash** | StepFun | `stepfun/step-3.5-flash` | $0.10 / $0.30 |
| 8 | **GLM 5 Turbo** | Zhipu AI | `z-ai/glm-5-turbo` | $1.20 / $4 |
| 9 | **Grok 4.1 Fast** | xAI | `x-ai/grok-4.1-fast` | $0.20 / $0.50 |
| 10 | **Kimi K2.5** | Moonshot AI | `moonshotai/kimi-k2.5` | $0.38 / $1.72 |
| 11 | **MiniMax M2.7** | MiniMax | `minimax/minimax-m2.7` | $0.30 / $1.20 |
| 12 | **DeepSeek V3.2** | DeepSeek | `deepseek/deepseek-v3.2` | $0.26 / $0.38 |
| 13 | **MiniMax M2.5** | MiniMax | `minimax/minimax-m2.5` | $0.12 / $0.99 |
| 14 | **GPT 5.2 Pro** | OpenAI | `openai/gpt-5.2-pro` | $21 / $168 |
| 15 | **Gemini 3.1 Pro** | Google | `google/gemini-3.1-pro-preview` | $2 / $12 |
| 16 | **MiMo V2 Flash** | Xiaomi | `xiaomi/mimo-v2-flash` | $0.09 / $0.29 |
| 17 | **Qwen3.5 397A17B** | Alibaba | `qwen/qwen3.5-397b-a17b` | $0.39 / $2.34 |
| 18 | **Qwen3.5 122A10B** | Alibaba | `qwen/qwen3.5-122b-a10b` | $0.26 / $2.08 |
| 19 | **Gemini 3 Flash** | Google | `google/gemini-3-flash-preview` | $0.50 / $3 |
| 20 | **MiniMax M2.1** | MiniMax | `minimax/minimax-m2.1` | $0.27 / $0.95 |
| 21 | **GPT 5 Nano** | OpenAI | `openai/gpt-5-nano` | $0.05 / $0.40 |
| 22 | **GLM 4.5 Air** | Zhipu AI | `z-ai/glm-4.5-air` | $0.13 / $0.85 |
| 23 | **Mistral Small 2603** | Mistral AI | `mistralai/mistral-small-2603` | $0.15 / $0.60 |
| 24 | **Gemini 2.5 Flash** | Google | `google/gemini-2.5-flash` | $0.30 / $2.50 |
| 25 | **Qwen3.5 27B** | Alibaba | `qwen/qwen3.5-27b` | $0.20 / $1.56 |
| 26 | **Nemotron 3 Super** | NVIDIA | `nvidia/nemotron-3-super-120b-a12b` | $0.10 / $0.50 |
| 27 | **Gemini 2.5 Flash Lite** | Google | `google/gemini-2.5-flash-lite` | $0.10 / $0.40 |

Any OpenRouter model with tool calling can usually be evaluated as long as the agent runtime supports it. Browse the broader [OpenRouter tool-calling collection](https://openrouter.ai/collections/tool-calling-models) for additional options.
