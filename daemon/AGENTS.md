# Agent Integration Notes

Vibe Lamp keeps the ESP32 firmware agent-agnostic. New coding tools should be
adapted in the Mac daemon, then normalized into the same lamp wire protocol.

## Generic Event Endpoint

`POST http://127.0.0.1:8787/event/generic`

Preferred payload:

```json
{
  "agent": "opencode",
  "session_id": "session-123",
  "state": "working",
  "tool": "command"
}
```

Allowed states:

- `idle`
- `working`
- `done`
- `error`
- `needs_you`

Allowed tools:

- `none`
- `code`
- `command`
- `search`

The daemon namespaces sessions as `<agent>:<session_id>`, so `claude:x`,
`codex:x`, `opencode:x`, and `qwen:x` can coexist without overwriting each other.

Simple event aliases are also accepted when a wrapper cannot produce a direct
state:

```json
{"agent": "qwen", "session_id": "abc", "event": "permission"}
```

Known aliases:

- `start`, `prompt`, `tool_start`, `tool_end` -> `working`
- `permission`, `approval`, `needs_you` -> `needs_you`
- `done`, `complete`, `stop` -> `done`
- `error`, `fail` -> `error`
- `session_start` -> `idle`
- `session_end`, `remove` -> remove the session

## Adapter Priority

1. OpenCode: use its plugin/event system and post to `/event/generic` first.
   Add `/event/opencode` only if its raw payload needs richer handling.
2. Qwen Code: use hooks, SDK, or daemon mode when available; otherwise wrap the
   CLI and post generic events.
3. Gemini CLI: prefer structured stream output if running headless; otherwise use
   a wrapper for start/done/error.
4. Aider: use notification command for completion/attention, plus a wrapper for
   start/error.
5. Trae, MarsCode/Doubao, CodeBuddy, Cursor, Windsurf: treat as weak integrations
   until a stable local hook, structured output, or extension API is confirmed.

## Wrapper Fallback

For tools without hooks, wrap the command:

```sh
curl -s -o /dev/null --max-time 1 -X POST http://127.0.0.1:8787/event/generic \
  -d '{"agent":"qwen","session_id":"default","state":"working","tool":"code"}' || true

qwen "$@"
status=$?

if [ "$status" -eq 0 ]; then
  state=done
else
  state=error
fi

curl -s -o /dev/null --max-time 1 -X POST http://127.0.0.1:8787/event/generic \
  -d "{\"agent\":\"qwen\",\"session_id\":\"default\",\"state\":\"$state\",\"tool\":\"none\"}" || true
exit "$status"
```

This fallback cannot detect fine-grained tool calls or approval prompts. Prefer a
native hook/plugin whenever the tool exposes one.
