"""`loopforge run` — execute a loop: wake → act → verify → record → decide.

This is a deliberately small, honest runner. It enforces the limits it can actually measure
(iteration count and wall-clock seconds) and refuses to start a loop with no brake at all. It does
NOT pretend to count tokens it cannot see: max_tokens / max_cost_usd are passed through to your
agent command and surfaced in the plan, but the runner's hard stops are iterations and time.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .linter import lint_text
from .models import Loop, LoopError, Severity, parse_loop


@dataclass
class IterationLog:
    index: int
    acted: bool
    verified: bool | None
    note: str


@dataclass
class RunResult:
    loop: str
    iterations: int = 0
    outcome: str = ""
    handback_reason: str = ""
    logs: list[IterationLog] = field(default_factory=list)
    dry_run: bool = False


def _read_context(loop: Loop, root: Path) -> str:
    parts: list[str] = []
    for rel in loop.table("skills").get("files", []) or []:
        p = root / rel
        if p.exists():
            parts.append(f"# SKILL: {rel}\n{p.read_text(encoding='utf-8')}")
        else:
            parts.append(f"# SKILL: {rel} (MISSING)")
    mem = loop.table("memory").get("file")
    if mem:
        mp = root / mem
        if mp.exists():
            parts.append(f"# MEMORY LEDGER ({mem})\n{mp.read_text(encoding='utf-8')}")
    prompt_file = loop.table("act").get("prompt_file")
    if prompt_file:
        pp = root / prompt_file
        if pp.exists():
            parts.append(f"# PROMPT\n{pp.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def _run_command(command: str, prompt: str | None, cwd: Path, timeout: float | None) -> tuple[int, str]:
    """Run a command. {prompt} is replaced with a temp file path; otherwise prompt goes to stdin."""
    stdin_text: str | None = None
    tmp: Path | None = None
    try:
        if "{prompt}" in command and prompt is not None:
            handle, tmp_name = tempfile.mkstemp(suffix=".md")
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                fh.write(prompt)
            tmp = Path(tmp_name)
            command = command.replace("{prompt}", shlex.quote(str(tmp)))
        elif prompt is not None:
            stdin_text = prompt
        proc = subprocess.run(  # noqa: S603 - command is operator-authored loop config
            shlex.split(command),
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError as exc:
        raise LoopError(f"command not found: {command!r} ({exc})") from exc
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _append_ledger(loop: Loop, root: Path, log: IterationLog) -> None:
    mem = loop.table("memory").get("file")
    if not mem:
        return
    mp = root / mem
    if not mp.exists():
        return
    when = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    verified = "—" if log.verified is None else ("yes" if log.verified else "no")
    row = f"| {when} | {log.index} | {log.note} | {verified} | {log.note} |\n"
    with mp.open("a", encoding="utf-8") as fh:
        fh.write(row)


def _cap(loop: Loop) -> int | None:
    for table in ("trigger", "budget"):
        v = loop.table(table).get("max_iterations")
        if isinstance(v, int) and v > 0:
            return v
    return None


def plan(loop: Loop) -> str:
    """A human-readable description of what `run` would do — used by --dry-run."""
    t = loop.table("trigger")
    lines = [
        f"loop: {loop.name}",
        f"goal: {loop.goal or '(none)'}",
        f"trigger: {t.get('type', '?')}  cap: {_cap(loop) or 'NONE'} iterations",
        f"isolation: {loop.table('isolation').get('mode', 'none')}",
        f"skills: {', '.join(loop.table('skills').get('files', []) or []) or '(none)'}",
        f"act: {loop.table('act').get('command', '(none)')}",
        f"verify: {loop.table('verify').get('command') or loop.table('verify').get('reviewer_command') or '(none)'}",
        f"memory: {loop.table('memory').get('file', '(none)')}",
        f"budget: {loop.table('budget') or '(none)'}",
        f"handback: {loop.table('handback').get('on', []) or '(none)'}",
    ]
    return "\n".join(lines)


def run(
    source: str | Path,
    *,
    dry_run: bool = False,
    max_iterations: int | None = None,
) -> RunResult:
    """Execute a loop. Refuses to start a loop with a CRITICAL completeness finding (no brake)."""
    path = Path(source)
    loop = parse_loop(path)
    root = path.parent

    pre = lint_text(path.read_text(encoding="utf-8"), path=path)
    blocking = [f for f in pre.findings if f.severity is Severity.CRITICAL]
    if blocking:
        codes = ", ".join(f.code for f in blocking)
        raise LoopError(
            f"refusing to run {loop.name}: {codes} — the loop has no brake and could run away. "
            f"Fix it (loopforge lint {path}) before running."
        )

    cap = max_iterations or _cap(loop)
    if cap is None:
        raise LoopError(f"{loop.name} has no iteration cap; pass --max-iterations or add one")

    result = RunResult(loop=loop.name, dry_run=dry_run)
    if dry_run:
        result.outcome = "dry-run"
        return result

    act_cmd = loop.table("act").get("command")
    if not act_cmd:
        raise LoopError(f"{loop.name} has no [act] command to run")
    verify_cmd = loop.table("verify").get("command") or loop.table("verify").get("reviewer_command")
    max_seconds = loop.table("budget").get("max_seconds")
    deadline = time.monotonic() + max_seconds if isinstance(max_seconds, (int, float)) else None

    context = _read_context(loop, root)
    consecutive_failures = 0

    for i in range(1, cap + 1):
        if deadline and time.monotonic() > deadline:
            result.outcome = "stopped"
            result.handback_reason = "budget-exceeded"
            break

        remaining = deadline - time.monotonic() if deadline else None
        rc, out = _run_command(act_cmd, context, root, remaining)
        note = "needs-human" if "NEEDS-HUMAN" in out else f"act rc={rc}"

        verified: bool | None = None
        if verify_cmd:
            vrc, _ = _run_command(verify_cmd, None, root, remaining)
            verified = vrc == 0
            consecutive_failures = 0 if verified else consecutive_failures + 1

        log = IterationLog(index=i, acted=rc == 0, verified=verified, note=note)
        result.logs.append(log)
        result.iterations = i
        _append_ledger(loop, root, log)

        if "NEEDS-HUMAN" in out:
            result.outcome, result.handback_reason = "handback", "needs-human"
            break
        if consecutive_failures >= 2:
            result.outcome, result.handback_reason = "handback", "verify-failed-twice"
            break
        if verified and "GOAL-REACHED" in out:
            result.outcome, result.handback_reason = "done", "goal-reached"
            break
    else:
        result.outcome, result.handback_reason = "stopped", "max-iterations"

    _notify(loop, root, result)
    return result


def _notify(loop: Loop, root: Path, result: RunResult) -> None:
    cmd = loop.table("handback").get("notify")
    if not cmd:
        return
    status = (
        f"loop={result.loop} outcome={result.outcome} "
        f"reason={result.handback_reason} iters={result.iterations}"
    )
    # notification is best-effort; a missing notifier must not crash a finished run
    with contextlib.suppress(LoopError):
        _run_command(cmd, status, root, timeout=30)
