# OpenRouter

InternAgent can use OpenRouter as a first-class model provider for the main
multi-agent discovery pipeline. OpenRouter uses an OpenAI-compatible API, so the
same agent code can route requests to models from OpenAI, Anthropic, Google, and
other providers through one endpoint.

## 1. Get an API key

Create an OpenRouter account, add credits, and create an API key from:

```text
https://openrouter.ai/settings/keys
```

## 2. Configure InternAgent

Copy the environment template and set your OpenRouter key:

```bash
cp .env.example .env
```

In `.env`:

```bash
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_APP_NAME=InternAgent
OPENROUTER_SITE_URL=https://discovery.intern-ai.org.cn
```

The dedicated provider config is available at `config/openrouter_config.yaml`.
It sets:

```yaml
models:
  default_provider: "openrouter"
  openai:
    model_name: "gpt-5.6-sol"
    api_mode: "responses"
  openrouter:
    model_name: "moonshotai/kimi-k2.6:free"
```

You can replace `model_name` with any OpenRouter model ID that supports chat
completions.

## 3. Run a discovery smoke test

`AutoDebug` is the smallest built-in task and does not require external datasets:

```bash
python launch_discovery.py \
    --config ./config/openrouter_config.yaml \
    --task AutoDebug \
    --exp_backend claudecode
```

The `--exp_backend claudecode` experiment backend still requires its own
Anthropic/Claude Code setup. OpenRouter is used by InternAgent's main agent
model provider layer.

## 4. Use OpenRouter from the default config

Instead of using `config/openrouter_config.yaml`, you can edit
`config/default_config.yaml`:

```yaml
models:
  default_provider: "openrouter"
```

The `openrouter` provider block is already included in the default config.

## 5. Responses-native roles

OpenRouter remains the default provider for the main multi-agent discovery
roles in this config. Deep Research and PaperOrchestra are explicitly assigned
to the separate `models.openai` block because they depend on Responses-only
features such as persisted reasoning, Pro mode, background execution, and
resumable response IDs.

```bash
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...
```

Do not point the OpenAI block at an OpenRouter Chat Completions endpoint. To run
without the OpenAI-native Deep Research stage, set `agents.dr.enabled: false`.
PaperOrchestra likewise requires the OpenAI block when dossier generation is
enabled.

QA always uses the OpenAI block:

```bash
python launch_qa.py \
  --config config/openrouter_config.yaml \
  --question "What are recent advances in memory-augmented LLMs?"
```

## Troubleshooting

- `Authentication failed`: check that `OPENROUTER_API_KEY` is set in `.env`.
- `Unsupported model`: confirm the model ID exists in the OpenRouter model list.
- `Unsupported model provider: openrouter`: make sure your checkout includes
  `internagent/mas/models/openrouter_model.py` and the updated
  `model_factory.py`.
