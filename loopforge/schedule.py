"""Install a loop's `[trigger]` into the system scheduler (cron), so the declarative schedule
actually fires — the missing half of the trigger block.

Safety: the crontab is shared. `install`/`remove` preserve every existing entry and only touch the
single line tagged for this loop. If the current crontab can't be read for any reason other than
"there is no crontab yet", we refuse to write rather than risk clobbering unrelated jobs.

macOS note: cron needs Full Disk Access to run jobs that touch ~/Documents.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .models import Loop, LoopError, parse_loop

_TAG = "# loopforge:"


def cron_line(loop: Loop, loop_path: str | Path) -> str:
    """Build the tagged crontab line for a schedule-triggered loop. Raises if it isn't schedulable."""
    trig = loop.table("trigger")
    ttype = str(trig.get("type", "")).strip().lower()
    if ttype != "schedule":
        raise LoopError(
            f"{loop.name}: only a type=\"schedule\" loop can be cron-scheduled (this is {ttype or 'unset'!r}). "
            "Event and until-goal loops are driven differently."
        )
    cron = trig.get("cron")
    if not isinstance(cron, str) or len(cron.split()) < 5:
        raise LoopError(f"{loop.name}: [trigger].cron must be a 5-field cron expression to schedule")
    path = str(Path(loop_path).resolve())
    loop_dir = str(Path(path).parent)
    log = f"{loop_dir}/.loopforge-run/{loop.name}.log"
    command = (
        f"cd {shlex.quote(loop_dir)} && loopforge run {shlex.quote(path)} "
        f">> {shlex.quote(log)} 2>&1"
    )
    return f"{cron} {command}  {_TAG}{loop.name}"


def apply_entry(current: str, loop: Loop, loop_path: str | Path) -> str:
    """Return new crontab text with this loop's line added or replaced (idempotent by tag)."""
    tag = f"{_TAG}{loop.name}"
    kept = [ln for ln in current.splitlines() if not ln.rstrip().endswith(tag)]
    kept.append(cron_line(loop, loop_path))
    return "\n".join(kept).strip() + "\n"


def remove_entry(current: str, name: str) -> tuple[str, bool]:
    """Return (new crontab text, removed?) with the named loop's line dropped."""
    tag = f"{_TAG}{name}"
    kept = [ln for ln in current.splitlines() if not ln.rstrip().endswith(tag)]
    removed = len(kept) != len(current.splitlines())
    text = ("\n".join(kept).strip() + "\n") if any(ln.strip() for ln in kept) else ""
    return text, removed


def managed_entries(current: str) -> list[str]:
    return [ln for ln in current.splitlines() if _TAG in ln]


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)  # noqa: S603,S607
    if result.returncode == 0:
        return result.stdout
    if "no crontab" in (result.stderr or "").lower():
        return ""  # no crontab yet — safe to create one
    raise LoopError(
        f"cannot read the current crontab (refusing to overwrite it): "
        f"{result.stderr.strip() or 'crontab -l failed'}"
    )


def _write_crontab(text: str) -> None:
    result = subprocess.run(["crontab", "-"], input=text, capture_output=True, text=True)  # noqa: S603,S607
    if result.returncode != 0:
        raise LoopError(f"failed to write crontab: {result.stderr.strip()}")


def install(loop_path: str | Path, *, dry_run: bool = False) -> tuple[str, str]:
    """Schedule a loop. Returns (the cron line, the resulting full crontab). Preserves all other
    entries; refuses to write if the existing crontab can't be read."""
    loop = parse_loop(loop_path)
    line = cron_line(loop, loop_path)  # validates schedulability before touching anything
    new_crontab = apply_entry(_read_crontab(), loop, loop_path)
    if not dry_run:
        log_dir = Path(loop_path).resolve().parent / ".loopforge-run"
        log_dir.mkdir(parents=True, exist_ok=True)
        _write_crontab(new_crontab)
    return line, new_crontab


def uninstall(name: str) -> bool:
    new_crontab, removed = remove_entry(_read_crontab(), name)
    if removed:
        _write_crontab(new_crontab)
    return removed


def installed() -> list[str]:
    return managed_entries(_read_crontab())
