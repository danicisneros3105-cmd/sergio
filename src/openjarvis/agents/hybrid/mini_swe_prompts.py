"""The mini-SWE agent's system prompt and its one tool (``bash``) in the
Anthropic, OpenAI and Gemini schema shapes. Split out of
``mini_swe_agent.py``, which re-exports every name.
"""

from __future__ import annotations

from typing import Any, Dict

# Gemini's FunctionDeclaration.parameters expects a Schema-shaped dict (or
# Schema object) with capitalized type strings ("OBJECT", "STRING"). The
# OpenAI/Anthropic JSON-Schema lower-case form is silently dropped — the
# model then can't call the tool. Build a fresh dict instead of reusing
# BASH_TOOL_OPENAI's parameters.
BASH_TOOL_GEMINI_PARAMETERS: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "command": {
            "type": "STRING",
            "description": "The bash command to run.",
        },
    },
    "required": ["command"],
}


SYSTEM_PROMPT = """\
You are an expert software engineer fixing a bug in a Python repository. \
You have one tool, `bash`, that runs a shell command and returns stdout, \
stderr, and the exit code.

Your task:
1. Read the issue.
2. Use `bash` to explore the repo, read relevant files, and understand the bug.
3. Edit files to fix the bug. You can use `bash` for that too (sed, python -c '...', cat > file <<EOF, etc.).
4. Run the relevant tests with `bash` to confirm your fix.
5. When you are confident the bug is fixed, send one final assistant message \
WITH NO TOOL CALLS containing a brief one-line summary of what you changed. \
That ends the loop; the harness will read your changes via `git diff` against \
the base commit.

Rules:
- Each `bash` call already runs INSIDE the repository's working tree as cwd. \
You do NOT need to `cd` anywhere — just run `ls`, `cat path/to/file`, etc. \
relative to the repo root.
- Each `bash` call is a fresh shell — there's no persistent cwd, env, or \
shell state carried between calls (but cwd is reset to the repo root each \
call, so this is fine for normal exploration).
- Don't run `git commit`, `git stash`, or anything that mutates git state — \
your edits should live in the working tree so `git diff` picks them up.
- Keep individual command outputs under ~10K chars (use `head`, `tail`, \
`grep -n`, `wc`). Long outputs will be truncated.
- Don't ``exit``, ``logout``, or kill the shell.
"""


BASH_TOOL_ANTHROPIC = {
    "name": "bash",
    "description": (
        "Run a bash command in the repository root and return stdout, stderr, "
        "and the exit code. Each call is a fresh shell — no persistent state."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to run.",
            },
        },
        "required": ["command"],
    },
}


BASH_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": BASH_TOOL_ANTHROPIC["description"],
        "parameters": BASH_TOOL_ANTHROPIC["input_schema"],
    },
}
