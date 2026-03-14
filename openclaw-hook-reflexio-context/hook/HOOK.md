---
name: reflexio-context
description: "Fetch user preferences and improvement suggestions from Reflexio and inject them into agent bootstrap context"
metadata:
  openclaw:
    emoji: "🧠"
    events: ["agent:bootstrap"]
    requires:
      bins: ["python3"]
      config: ["workspace.dir"]
---

# Reflexio Context Hook

Automatically fetches user context from [Reflexio](https://github.com/reflexio-ai/reflexio) and injects it into the agent's system prompt at session start.

## What It Does

On every `agent:bootstrap` event (new session):

1. Fetches user preferences and improvement suggestions from the Reflexio API
2. Injects them as a bootstrap file so the agent always has user context
3. Adds a per-turn instruction that couples Reflexio recall with `memory_search` — whenever the agent recalls memory, it also fetches task-specific suggestions from Reflexio

## Prerequisites

- A running Reflexio server (local or remote)
- `python3` with the `requests` package installed
- `REFLEXIO_API_KEY` environment variable set (or configured in hook options)

## Configuration

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

### Environment Variables

| Variable              | Default                    | Description                |
| --------------------- | -------------------------- | -------------------------- |
| `REFLEXIO_API_KEY`    | _(required)_               | API key for authentication |
| `REFLEXIO_URL`        | `http://127.0.0.1:8081`    | Reflexio server URL        |
| `REFLEXIO_USER_ID`    | `openclaw`                 | User ID for profile search |
| `REFLEXIO_AGENT_VERSION` | `MiniMax-M2.5`          | Agent version for feedback |
