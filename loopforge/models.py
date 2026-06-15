"""Parse a loop definition (TOML) into a typed Loop, plus the Finding/Severity vocabulary.

A loop is declared in `loop.toml`. The six blocks of Loop Engineering map to six tables:

    [trigger]   who wakes it up        (schedule / event / until-goal / manual)
    [isolation] parallel-safe workspace (worktree / none)
    [skills]    durable project knowledge (markdown files, not ad-hoc prompts)
    [act]       the agent invocation     (the command that does the work + its tools)
    [verify]    independent verification (a separate command / different model)
    [memory]    the ledger the repo keeps (the model forgets; the repo does not)

plus [budget] (the cost brake) and [handback] (the human brake).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any


class Severity(IntEnum):
    """Ordered so the loudest tier sorts first and gates can compare with >=."""

    INFO = 0
    MINOR = 1
    MAJOR = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def from_label(cls, label: str) -> Severity:
        try:
            return cls[label.strip().upper()]
        except KeyError as exc:
            raise LoopError(
                f"unknown severity {label!r}; expected one of "
                f"{', '.join(s.label for s in cls)}"
            ) from exc


# The six blocks every loop must answer for, in the order the article presents them.
BLOCKS = ("trigger", "isolation", "skills", "act", "verify", "memory")


class Block(str):
    """A loop block name; thin wrapper so type hints read clearly."""


class LoopError(Exception):
    """Raised when a loop definition cannot be parsed. Fails loud — never a silent default."""


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    block: str
    message: str
    fix: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.label,
            "block": self.block,
            "message": self.message,
            "fix": self.fix,
        }


@dataclass
class Loop:
    """A parsed loop definition. `raw` holds the original tables so rules can test presence."""

    name: str
    goal: str
    raw: dict[str, Any]
    path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    def table(self, name: str) -> dict[str, Any]:
        """Return a block table as a dict; {} if absent or not a table (so rules stay simple)."""
        value = self.raw.get(name)
        return value if isinstance(value, dict) else {}

    def has_block(self, name: str) -> bool:
        return isinstance(self.raw.get(name), dict) and bool(self.raw[name])


def _coerce_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_text(text: str, path: Path | None = None) -> Loop:
    """Parse loop TOML text into a Loop. Raises LoopError on malformed input or a missing name."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        where = f" in {path}" if path else ""
        raise LoopError(f"invalid TOML{where}: {exc}") from exc

    name = _coerce_str(data.get("name"))
    if not name:
        where = f" ({path})" if path else ""
        raise LoopError(f"loop is missing a top-level `name`{where}")

    loop = Loop(name=name, goal=_coerce_str(data.get("goal")), raw=data, path=path)

    known = {*BLOCKS, "budget", "handback", "name", "goal", "description"}
    for key in data:
        if key not in known:
            loop.warnings.append(f"unknown top-level key {key!r} (ignored)")
    return loop


def parse_loop(path: str | Path) -> Loop:
    """Read and parse a loop.toml file. Raises LoopError naming the file on any failure."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LoopError(f"no such loop file: {p}") from exc
    except OSError as exc:
        raise LoopError(f"cannot read loop file {p}: {exc}") from exc
    return parse_text(text, path=p)
