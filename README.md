# my-agent

A general-purpose AI assistant built with the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk) (Python).

**Tools it has**
- `calculate`: exact arithmetic (custom)
- `current_time`: date/time in any timezone (custom)
- `save_note` / `list_notes`: long-term memory saved in `notes.json` (custom)
- Built-in `WebSearch`, `WebFetch`, `Read`, `Write`, `Glob` (file access limited to `workspace/`)

## Run
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python agent.py
```

## Add your own tool
```python
@tool("get_weather", "Get weather for a city", {"city": str})
async def get_weather(args):
    return {"content": [{"type": "text", "text": f"Sunny in {args['city']}"}]}
```
Add it to `create_sdk_mcp_server(tools=[...])` and add `"mcp__assistant__get_weather"` to `allowed_tools`.
