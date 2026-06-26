"""`loopforge init` — scaffold a complete, lint-clean loop with all six blocks wired."""
from __future__ import annotations

from pathlib import Path

from .models import LoopError

_LOOP_TOML = '''\
# A complete loop: every one of the six blocks is present, plus a cost brake and a human brake.
# Run `loopforge lint .` in this directory to confirm it stays complete as you edit.
name = "{name}"
goal = "{goal}"

# 1. TRIGGER — who wakes it up. Without this it's a manual run, not a loop.
[trigger]
type = "schedule"            # schedule | event | until-goal | manual
cron = "*/30 * * * *"        # every 30 minutes
max_iterations = 20          # hard stop so a single wake-up can't spin forever

# 2. ISOLATION — parallel-safe workspace so concurrent agents don't clobber each other.
[isolation]
mode = "worktree"            # worktree | none

# 3. SKILLS — durable project knowledge the agent reloads every iteration.
[skills]
files = ["skills/project.md"]

# 4. ACT — the agent invocation. {{prompt}} is replaced with skills + memory + your prompt file.
[act]
command = "agent-cli run {{prompt}}"
prompt_file = "prompts/act.md"
parallel = false

# 5. VERIFY — an INDEPENDENT check. Never the same command as act (no grading your own homework).
[verify]
command = "pytest -q"        # a real test/build, or set reviewer_command for a second model
require = "exit-zero"

# 6. MEMORY — the ledger the repo keeps. The model forgets; the repo does not.
[memory]
file = "memory/ledger.md"
trace_file = "memory/trace.jsonl"  # full act/verify state transitions for audit and recovery

# COST BRAKE — a per-run ceiling so the loop can't burn budget unbounded.
[budget]
max_tokens = 200000
max_seconds = 1800
max_cost_usd = 5.0

# HUMAN BRAKE — conditions that stop and hand control back to a person.
[handback]
owner = "project-owner"       # person/team accountable for accepting the result
on = ["budget-exceeded", "verify-failed-twice", "goal-reached", "needs-human"]
notify = "echo"              # any command; receives a one-line status on stdin
'''

_SKILL_MD = """\
# Project knowledge for the {name} loop

Durable rules the agent should follow every iteration. Prompts are one-off; this file is the
long-lived contract. Keep it short and specific.

## How to run / verify
- (fill in) how to install, run, and test this project.

## Conventions
- (fill in) naming, structure, style the agent must match.

## Do NOT touch
- (fill in) directories, generated files, or production paths that are off-limits.

## Known landmines
- (fill in) past gotchas so the loop doesn't relearn them every time.
"""

_LEDGER_MD = """\
# {name} — loop ledger

The model forgets between iterations; this file is how the repo remembers. The runner appends one
entry per iteration. You can also leave notes here for the next run.

| when | iteration | did | verified | outcome / handback |
|------|-----------|-----|----------|--------------------|
"""

_PROMPT_MD = """\
# Act prompt for {name}

You are one iteration of an autonomous loop. The goal is:

> {goal}

Before you act, read the skills file(s) and the memory ledger that precede this prompt — do not
redo work already recorded as done. Make the smallest correct change toward the goal, then stop so
the verify step can check you. If you cannot make progress safely, say `NEEDS-HUMAN: <why>`.
"""


def _slug(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.strip().lower())
    return "-".join(filter(None, cleaned.split("-"))) or "loop"


def init(name: str, dest: str | Path = ".", *, force: bool = False) -> Path:
    """Create dest/<name>/ with a complete, lint-clean loop. Raises LoopError if it exists."""
    slug = _slug(name)
    root = Path(dest) / slug
    if root.exists() and not force:
        raise LoopError(f"{root} already exists (use force=True / --force to overwrite)")

    goal = f"Describe the outcome the {slug} loop drives toward."
    files = {
        root / "loop.toml": _LOOP_TOML.format(name=slug, goal=goal),
        root / "skills" / "project.md": _SKILL_MD.format(name=slug),
        root / "memory" / "ledger.md": _LEDGER_MD.format(name=slug),
        root / "prompts" / "act.md": _PROMPT_MD.format(name=slug, goal=goal),
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root
