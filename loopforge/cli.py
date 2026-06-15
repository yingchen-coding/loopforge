"""Command-line interface for loopforge."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .linter import lint_path
from .models import LoopError, Severity, parse_loop
from .report import render_human, render_json
from .rules import all_rules
from .runner import plan, run
from .scaffold import init


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="loopforge",
        description="Lint, scaffold, and run autonomous agent loops against the six blocks a "
        "real loop needs.",
    )
    p.add_argument("--version", action="version", version=f"loopforge {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="check loop definitions for the six blocks + brakes")
    lint.add_argument("path", nargs="?", default=".", help="loop.toml or a directory of loops")
    lint.add_argument("--format", choices=("human", "json"), default="human")
    lint.add_argument("--score", action="store_true", help="show the A–F completeness grade")
    lint.add_argument("--select", default="", help="comma-separated rule codes to run (e.g. L002,L004)")
    lint.add_argument(
        "--fail-at",
        default="major",
        help="minimum severity that exits non-zero (info|minor|major|critical)",
    )

    new = sub.add_parser("init", help="scaffold a complete, lint-clean loop")
    new.add_argument("name", help="loop name (becomes the directory)")
    new.add_argument("--dest", default=".", help="where to create it (default: here)")
    new.add_argument("--force", action="store_true", help="overwrite if it exists")

    r = sub.add_parser("run", help="execute a loop (wake → act → verify → record → decide)")
    r.add_argument("path", help="path to a loop.toml")
    r.add_argument("--dry-run", action="store_true", help="print the plan without executing")
    r.add_argument("--max-iterations", type=int, default=None, help="override the iteration cap")

    sub.add_parser("list-rules", help="print the rule catalog")
    return p


def _cmd_lint(args: argparse.Namespace) -> int:
    select = {c.strip() for c in args.select.split(",") if c.strip()} or None
    try:
        results = lint_path(args.path, select=select)
    except LoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(render_json(results))
    else:
        print(render_human(results, show_score=args.score))

    if any(r.error for r in results):
        return 2
    threshold = Severity.from_label(args.fail_at)
    worst = max((s for r in results for s in (f.severity for f in r.findings)), default=None)
    return 1 if worst is not None and worst >= threshold else 0


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        root = init(args.name, args.dest, force=args.force)
    except LoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"created {root}/")
    print(f"  next: loopforge lint {root}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        if args.dry_run:
            print(plan(parse_loop(args.path)))
            return 0
        result = run(args.path, max_iterations=args.max_iterations)
    except LoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"{result.loop}: {result.outcome} "
        f"({result.iterations} iteration{'s' if result.iterations != 1 else ''}"
        f"{', ' + result.handback_reason if result.handback_reason else ''})"
    )
    return 1 if result.handback_reason == "needs-human" else 0


def _cmd_list_rules(_args: argparse.Namespace) -> int:
    for code, summary, _fn in sorted(all_rules()):
        print(f"{code}  {summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dispatch = {
        "lint": _cmd_lint,
        "init": _cmd_init,
        "run": _cmd_run,
        "list-rules": _cmd_list_rules,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
