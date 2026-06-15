"""Lint loop definitions and grade their completeness."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .models import Finding, LoopError, Severity, parse_loop, parse_text
from .rules import run_rules

# How many points each finding costs. A runaway loop (CRITICAL) is disqualifying on its own.
_WEIGHTS = {
    Severity.CRITICAL: 45,
    Severity.MAJOR: 15,
    Severity.MINOR: 5,
    Severity.INFO: 0,
}


@dataclass
class LoopResult:
    path: Path | None
    name: str
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.findings

    def max_severity(self) -> Severity | None:
        return max((f.severity for f in self.findings), default=None)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Loudest first, then by rule code for a stable, reproducible order."""
    return sorted(findings, key=lambda f: (-int(f.severity), f.code))


def score(findings: list[Finding]) -> int:
    """0–100 completeness score; deterministic from the findings alone."""
    penalty = sum(_WEIGHTS[f.severity] for f in findings)
    return max(0, 100 - penalty)


def grade(findings: list[Finding]) -> str:
    s = score(findings)
    if any(f.severity is Severity.CRITICAL for f in findings):
        return "F"  # a loop that can't stop is not shippable regardless of the rest
    for cutoff, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if s >= cutoff:
            return letter
    return "F"


def lint_text(text: str, path: Path | None = None, select: set[str] | None = None) -> LoopResult:
    try:
        loop = parse_text(text, path=path)
    except LoopError as exc:
        return LoopResult(path=path, name=path.name if path else "<text>", error=str(exc))
    return LoopResult(path=path, name=loop.name, findings=sort_findings(run_rules(loop, select)))


def _discover(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    found = sorted(
        {*path.rglob("loop.toml"), *path.rglob("*.loop.toml")},
        key=lambda p: str(p),
    )
    return found


def lint_path(path: str | Path, select: set[str] | None = None) -> list[LoopResult]:
    """Lint a loop file or every loop.toml under a directory. Empty discovery raises LoopError."""
    p = Path(path)
    if not p.exists():
        raise LoopError(f"no such path: {p}")
    targets = _discover(p)
    if not targets:
        raise LoopError(f"no loop definitions (loop.toml / *.loop.toml) found under {p}")

    results: list[LoopResult] = []
    for target in targets:
        try:
            loop = parse_loop(target)
        except LoopError as exc:
            results.append(LoopResult(path=target, name=target.name, error=str(exc)))
            continue
        results.append(
            LoopResult(path=target, name=loop.name, findings=sort_findings(run_rules(loop, select)))
        )
    return results
