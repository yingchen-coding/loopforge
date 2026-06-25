from __future__ import annotations

from pathlib import Path

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
trace_file = "memory/trace.jsonl"
[budget]
max_tokens = 100000
max_seconds = 600
max_cost_usd = 2.0
[handback]
owner = "platform-oncall"
on = ["budget-exceeded", "needs-human"]
notify = "echo"
"""


def materialize_complete(directory: Path | str) -> Path:
    """Write COMPLETE plus the skills/memory/prompt files it references, so a path-based lint sees a
    genuinely clean loop (L013 checks that referenced files exist on disk)."""
    d = Path(directory)
    for sub, name in (("skills", "project.md"), ("memory", "ledger.md"), ("prompts", "act.md")):
        (d / sub).mkdir(parents=True, exist_ok=True)
        (d / sub / name).write_text("# placeholder\n", encoding="utf-8")
    loop = d / "loop.toml"
    loop.write_text(COMPLETE, encoding="utf-8")
    return loop


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
