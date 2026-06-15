"""Render lint results as human-readable text or JSON."""
from __future__ import annotations

import json
import os
import sys

from .linter import LoopResult, grade, score
from .models import Severity

_COLORS = {
    Severity.CRITICAL: "\033[31m",  # red
    Severity.MAJOR: "\033[33m",  # yellow
    Severity.MINOR: "\033[36m",  # cyan
    Severity.INFO: "\033[2m",  # dim
}
_RESET = "\033[0m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_MARK = {Severity.CRITICAL: "✖", Severity.MAJOR: "✖", Severity.MINOR: "▲", Severity.INFO: "·"}


def _use_color(stream: object) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def render_human(results: list[LoopResult], show_score: bool = False, stream: object = None) -> str:
    stream = stream or sys.stdout
    color = _use_color(stream)
    lines: list[str] = []
    total_findings = 0
    counts = {s: 0 for s in Severity}
    loops_with_findings = 0
    errored = 0

    for r in results:
        if r.error:
            errored += 1
            head = f"{r.path or r.name}"
            lines.append(f"\n{head}")
            lines.append(f"  parse error: {r.error}")
            continue

        head = f"{r.path or r.name}"
        suffix = f"  {_DIM}(loop: {r.name}){_RESET}" if color else f"  (loop: {r.name})"
        if r.findings:
            loops_with_findings += 1
            lines.append(f"\n{head}{suffix}")
            for f in r.findings:
                total_findings += 1
                counts[f.severity] += 1
                c = _COLORS[f.severity] if color else ""
                rst = _RESET if color else ""
                mark = _MARK[f.severity]
                lines.append(f"  {c}{mark} {f.severity.label:<8}{rst} {f.code}  {f.message}")
                lines.append(f"        {_DIM if color else ''}↳ fix: {f.fix}{rst}")
        if show_score:
            g = grade(r.findings)
            gc = (_GREEN if g in ("A", "B") else _COLORS[Severity.MAJOR]) if color else ""
            rst = _RESET if color else ""
            lines.append(
                f"\n{head}{suffix}\n  {gc}Loop completeness: {g} ({score(r.findings)}/100){rst}"
                if not r.findings
                else f"  {gc}→ completeness: {g} ({score(r.findings)}/100){rst}"
            )

    n = len(results)
    if total_findings == 0 and errored == 0:
        ok = f"{_GREEN}✓ complete{_RESET}" if color else "✓ complete"
        lines.append(f"\n{ok} — {n} loop{'s' if n != 1 else ''} checked, all six blocks present")
    else:
        parts = ", ".join(f"{counts[s]} {s.label}" for s in reversed(Severity) if counts[s])
        summary = (
            f"\n✖ {total_findings} finding{'s' if total_findings != 1 else ''} "
            f"in {loops_with_findings}/{n} loops"
        )
        if parts:
            summary += f"  ({parts})"
        if errored:
            summary += f"  · {errored} parse error{'s' if errored != 1 else ''}"
        lines.append(summary)
    return "\n".join(lines).lstrip("\n")


def render_json(results: list[LoopResult]) -> str:
    payload = []
    for r in results:
        payload.append(
            {
                "path": str(r.path) if r.path else None,
                "loop": r.name,
                "error": r.error,
                "grade": grade(r.findings) if not r.error else None,
                "score": score(r.findings) if not r.error else None,
                "findings": [f.as_dict() for f in r.findings],
            }
        )
    return json.dumps({"results": payload}, indent=2)
