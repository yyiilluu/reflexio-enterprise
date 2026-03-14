# openclaw-hook-reflexio-context

An [OpenClaw](https://openclaw.ai) hook that connects your AI agent to [Reflexio](https://github.com/reflexio-ai/reflexio) for automatic self-improvement.

## What It Does

At every new session, this hook:

1. **Fetches your user preferences** from Reflexio (communication style, tools, accounts)
2. **Injects them into the agent's system prompt** so it always knows your preferences
3. **Couples per-turn recall with memory** — whenever the agent searches memory, it also fetches task-specific improvement suggestions from Reflexio

This means your agent learns from past mistakes and improves over time, automatically.

## Install

```bash
# From npm
openclaw hooks install openclaw-hook-reflexio-context

# Or from local path
openclaw hooks install /path/to/openclaw-hook-reflexio-context --link
```

## Setup

### 1. Set environment variables

```bash
export REFLEXIO_API_KEY="your-api-key"
export REFLEXIO_URL="http://127.0.0.1:8081"     # default
export REFLEXIO_USER_ID="openclaw"               # default
export REFLEXIO_AGENT_VERSION="MiniMax-M2.5"     # default
```

Or add them to your shell profile (`~/.zshrc`, `~/.bashrc`).

### 2. Enable the hook

```bash
openclaw hooks enable reflexio-context
```

Or add to `~/.openclaw/openclaw.json`:

```json
{
  "hooks": {
    "internal": {
      "entries": {
        "reflexio-context": {
          "enabled": true
        }
      }
    }
  }
}
```

### 3. Restart the gateway

```bash
openclaw gateway restart
```

### 4. Verify

```bash
openclaw hooks list
# Should show: ✓ ready  │ 🧠 reflexio-context
```

## Requirements

- OpenClaw 2026.3.8+
- Python 3 with `requests` package (`pip install requests`)
- A running Reflexio server

## How It Works

```
User sends message
        │
        ▼
  ┌─────────────┐
  │ agent:boot  │  Hook fires once per session
  │  strap      │  → Fetches user preferences from Reflexio
  │             │  → Injects into system prompt
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │ Agent runs  │  On each turn, agent is instructed to:
  │ memory_     │  → Search memory (built-in)
  │ search      │  → Also run fetch_context.py (coupled)
  └─────────────┘
        │
        ▼
  Agent responds with context from both
  memory AND Reflexio improvements
```
