from __future__ import annotations

COMPLETE = """\
name = "demo"
goal = "Do the thing and verify it."
[trigger]
type = "schedule"
cron = "*/30 * * * *"
max_iterations = 10
[isolation]
mode = "worktree"
[skills]
files = ["skills/project.md"]
[act]
command = "claude -p {prompt}"
prompt_file = "prompts/act.md"
[verify]
command = "pytest -q"
[memory]
file = "memory/ledger.md"
[budget]
max_tokens = 100000
max_seconds = 600
max_cost_usd = 2.0
[handback]
on = ["budget-exceeded", "needs-human"]
notify = "echo"
"""


def without(block: str) -> str:
    """Return COMPLETE with one [block] table removed (for rule-isolation tests)."""
    lines = COMPLETE.splitlines(keepends=True)
    out, skip = [], False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            skip = stripped == f"[{block}]"
        if not skip:
            out.append(line)
    return "".join(out)
