"""`loopforge run` — execute a loop: wake → act → verify → record → decide.

This is a deliberately small, honest runner. It enforces the limits it can actually measure
(iteration count and wall-clock seconds) and refuses to start a loop with no brake at all. It does
NOT pretend to count tokens it cannot see: max_tokens / max_cost_usd are passed through to your
agent command and surfaced in the plan, but the runner's hard stops are iterations and time.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .linter import lint_text
from .models import Loop, LoopError, Severity, parse_loop, resolve_loop_file


@dataclass
class IterationLog:
    index: int
    acted: bool
    verified: bool | None
    summary: str   # what the act step did (first line of its output)
    outcome: str   # the result of this iteration (ok / needs-human / verify-failed / goal-reached)


@dataclass
class RunResult:
    loop: str
    iterations: int = 0
    outcome: str = ""
    handback_reason: str = ""
    logs: list[IterationLog] = field(default_factory=list)
    dry_run: bool = False
    worktree: str | None = None  # isolated git worktree the run executed in, if any


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


def _first_line(text: str, limit: int = 80) -> str:
    """First non-empty line of command output, made safe for a markdown table cell."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            safe = stripped.replace("|", "/")
            return safe if len(safe) <= limit else safe[: limit - 1] + "…"
    return ""


def _append_ledger(loop: Loop, root: Path, log: IterationLog) -> None:
    mem = loop.table("memory").get("file")
    if not mem:
        return
    mp = root / mem
    if not mp.exists():
        return
    when = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    verified = "—" if log.verified is None else ("yes" if log.verified else "no")
    row = f"| {when} | {log.index} | {log.summary} | {verified} | {log.outcome} |\n"
    with mp.open("a", encoding="utf-8") as fh:
        fh.write(row)


def _append_trace(loop: Loop, root: Path, payload: dict[str, object]) -> None:
    """Persist the full machine-readable transition, not only the human ledger summary."""
    rel = loop.table("memory").get("trace_file")
    if not isinstance(rel, str) or not rel:
        return
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def _git(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603,S607 - fixed git subcommands, no user input in argv[0]
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _setup_worktree(loop: Loop, root: Path) -> Path | None:
    """If isolation is 'worktree' and root is a git repo, create an isolated worktree to run in.

    Returns the worktree path (left in place for the human to review and merge — the article's
    "each agent works in its own space, you merge at the end"), or None to run in `root`.
    """
    if str(loop.table("isolation").get("mode", "")).strip().lower() != "worktree":
        return None
    rc, top = _git(root, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None  # not a git repo — can't isolate; caller falls back to root
    repo_top = Path(top.strip())
    wt = Path(tempfile.mkdtemp(prefix="loopforge-wt-"))
    branch = f"loopforge/{loop.name}-{int(time.time())}"
    if _git(root, "worktree", "add", "-b", branch, str(wt))[0] != 0:
        return None
    # run at the loop's location *inside* the worktree, so relative paths still resolve
    rel = root.resolve().relative_to(repo_top.resolve())
    target = wt / rel
    return target if target.exists() else wt


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
        f"owner: {loop.table('handback').get('owner', '(none)')}",
    ]
    return "\n".join(lines)


def run(
    source: str | Path,
    *,
    dry_run: bool = False,
    max_iterations: int | None = None,
) -> RunResult:
    """Execute a loop. Refuses to start a loop with a CRITICAL completeness finding (no brake)."""
    path = resolve_loop_file(source)  # a directory resolves to its single loop.toml, like `lint`
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
    verify = loop.table("verify")
    verify_command = verify.get("command")
    reviewer_command = verify.get("reviewer_command")
    max_seconds = loop.table("budget").get("max_seconds")
    deadline = time.monotonic() + max_seconds if isinstance(max_seconds, (int, float)) else None

    # Isolation: act/verify run in a git worktree if requested; context (committed skills) and the
    # memory ledger stay on the original repo so the record survives the worktree.
    workdir = _setup_worktree(loop, root) or root
    if workdir != root:
        result.worktree = str(workdir)
    context = _read_context(loop, root)
    consecutive_failures = 0

    for i in range(1, cap + 1):
        if deadline and time.monotonic() > deadline:
            result.outcome = "stopped"
            result.handback_reason = "budget-exceeded"
            break

        remaining = deadline - time.monotonic() if deadline else None
        iteration_started = _dt.datetime.now(_dt.UTC).isoformat()
        rc, out = _run_command(act_cmd, context, workdir, remaining)

        # verify is independent: a `command` is a test/build (no prompt); a `reviewer_command` is a
        # second model that must SEE the act output to review it.
        verified: bool | None = None
        verify_rc: int | None = None
        verify_out = ""
        if verify_command:
            verify_rc, verify_out = _run_command(verify_command, None, workdir, remaining)
            verified = verify_rc == 0
        elif reviewer_command:
            verify_rc, verify_out = _run_command(reviewer_command, out, workdir, remaining)
            verified = verify_rc == 0
        if verified is not None:
            consecutive_failures = 0 if verified else consecutive_failures + 1

        if "NEEDS-HUMAN" in out:
            outcome = "needs-human"
        elif verified and "GOAL-REACHED" in out:
            outcome = "goal-reached"
        elif verified is False:
            outcome = "verify-failed"
        else:
            outcome = "ok"
        summary = _first_line(out) or f"act rc={rc}"

        log = IterationLog(index=i, acted=rc == 0, verified=verified, summary=summary, outcome=outcome)
        result.logs.append(log)
        result.iterations = i
        _append_ledger(loop, root, log)
        _append_trace(loop, root, {
            "act": {"command": act_cmd, "exit_code": rc, "output": out},
            "finished_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "goal": loop.goal,
            "iteration": i,
            "outcome": outcome,
            "owner": loop.table("handback").get("owner"),
            "started_at": iteration_started,
            "verify": {
                "command": verify_command or reviewer_command,
                "exit_code": verify_rc,
                "output": verify_out,
                "passed": verified,
            },
            "worktree": result.worktree,
        })

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
    owner = loop.table("handback").get("owner", "unassigned")
    status = (
        f"loop={result.loop} owner={owner} outcome={result.outcome} "
        f"reason={result.handback_reason} iters={result.iterations}"
    )
    # notification is best-effort; a missing notifier must not crash a finished run
    with contextlib.suppress(LoopError):
        _run_command(cmd, status, root, timeout=30)
