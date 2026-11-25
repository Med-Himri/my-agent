"""A general-purpose AI assistant built on the Claude Agent SDK.

Run:  python agent.py
Needs: ANTHROPIC_API_KEY in your environment (or `claude` logged in).
"""
import ast
import asyncio
import json
import operator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)

HERE = Path(__file__).parent
WORKSPACE = HERE / "workspace"
NOTES_FILE = HERE / "notes.json"


def text(s: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": s}]}


# ---------------------------------------------------------------- custom tools
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


@tool("calculate", "Evaluate an arithmetic expression exactly, e.g. '(3+4)*2**10'.",
      {"expression": Annotated[str, "Arithmetic expression using + - * / // % **"]})
async def calculate(args):
    try:
        return text(str(_safe_eval(ast.parse(args["expression"], mode="eval"))))
    except Exception as e:
        return {**text(f"Error: {e}"), "is_error": True}


@tool("current_time", "Get the current date and time in an IANA time zone.",
      {"timezone": Annotated[str, "IANA zone like 'Europe/Paris'; use 'UTC' if unknown"]})
async def current_time(args):
    try:
        return text(datetime.now(ZoneInfo(args["timezone"])).isoformat(timespec="seconds"))
    except Exception as e:
        return {**text(f"Error: {e}"), "is_error": True}


def _load_notes() -> list[dict]:
    return json.loads(NOTES_FILE.read_text()) if NOTES_FILE.exists() else []


@tool("save_note", "Save a note to long-term memory so it persists across sessions.",
      {"note": Annotated[str, "The fact or reminder to remember"]})
async def save_note(args):
    notes = _load_notes()
    notes.append({"note": args["note"], "saved": datetime.now().isoformat(timespec="seconds")})
    NOTES_FILE.write_text(json.dumps(notes, indent=2))
    return text(f"Saved. ({len(notes)} notes total)")


@tool("list_notes", "List all notes saved in long-term memory.", {})
async def list_notes(args):
    notes = _load_notes()
    return text("\n".join(f"- {n['note']} ({n['saved']})" for n in notes) or "No notes yet.")


tools_server = create_sdk_mcp_server(
    name="assistant", tools=[calculate, current_time, save_note, list_notes]
)

# --------------------------------------------------------------------- options
SYSTEM_PROMPT = f"""You are a helpful, concise personal assistant.
- Use `calculate` for any arithmetic instead of doing it in your head.
- Use `current_time` when the date or time matters.
- When the user tells you something worth remembering (preferences, plans, facts
  about them), save it with `save_note`. Check `list_notes` when past context helps.
- Use web search / fetch for current information, and cite sources.
- You may read and write files only inside {WORKSPACE}.
"""

options = ClaudeAgentOptions(
    model="claude-opus-5-5",
    system_prompt=SYSTEM_PROMPT,
    cwd=str(WORKSPACE),
    mcp_servers={"assistant": tools_server},
    # Only these tools are available; everything else (Bash, Edit, ...) is off.
    tools=["WebSearch", "WebFetch", "Read", "Write", "Glob"],
    allowed_tools=[
        "mcp__assistant__calculate", "mcp__assistant__current_time",
        "mcp__assistant__save_note", "mcp__assistant__list_notes",
        "WebSearch", "WebFetch", "Read", "Write", "Glob",
    ],
    permission_mode="acceptEdits",
    setting_sources=[],  # don't load any CLAUDE.md / user settings
    max_turns=30,
)


# ------------------------------------------------------------------- chat loop
async def main() -> None:
    print("Assistant ready. Type 'exit' to quit.\n")
    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                prompt = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if prompt.lower() in {"exit", "quit"}:
                break
            if not prompt:
                continue
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(f"agent> {block.text}")
                        elif isinstance(block, ToolUseBlock):
                            print(f"  [tool: {block.name} {json.dumps(block.input)[:120]}]")
                elif isinstance(msg, ResultMessage) and msg.total_cost_usd:
                    print(f"  (cost ${msg.total_cost_usd:.4f})\n")


if __name__ == "__main__":
    asyncio.run(main())
