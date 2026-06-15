"""loopforge — a Loop Engineering toolkit.

Prompt engineering is about one good instruction. Loop Engineering is about the *system* around
it: the thing that wakes up, does work in isolation, knows your conventions, verifies its own
output with a second pair of eyes, remembers what it did, and knows when to stop and hand back to
you. loopforge lints, scaffolds, and runs loops against the six blocks a real loop needs.
"""
from importlib.metadata import PackageNotFoundError, version

from .linter import grade, lint_path, lint_text
from .models import Block, Finding, Loop, LoopError, Severity, parse_loop

try:  # single source of truth is pyproject.toml; never hardcode the version twice
    __version__ = version("loopforge")
except PackageNotFoundError:  # running from a bare source checkout
    __version__ = "0.0.0+unknown"

__all__ = [
    "Block",
    "Finding",
    "Loop",
    "LoopError",
    "Severity",
    "__version__",
    "grade",
    "lint_path",
    "lint_text",
    "parse_loop",
]
