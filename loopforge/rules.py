"""Deterministic completeness rules for a loop definition.

Each rule is a pure function `(Loop) -> list[Finding]`. They encode Addy Osmani's six blocks plus
the two disciplines the article keeps hammering — a cost brake and a human brake. No LLM, no
network, no randomness: the same loop always yields the same findings.

Calibration follows the hard-won agentguard rule — the loudest tier means real danger. Only the
*runaway* (a loop that can never stop or run out of budget) is CRITICAL; everything else that
merely degrades quality is MAJOR/MINOR.
"""
from __future__ import annotations

from collections.abc import Callable

from .models import Finding, Loop, Severity

Rule = Callable[[Loop], list[Finding]]
_REGISTRY: list[tuple[str, str, Rule]] = []


def rule(code: str, summary: str) -> Callable[[Rule], Rule]:
    def register(fn: Rule) -> Rule:
        _REGISTRY.append((code, summary, fn))
        return fn

    return register


def _norm_cmd(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _has_any(table: dict[str, object], *keys: str) -> bool:
    return any(table.get(k) not in (None, "", [], {}) for k in keys)


def _positive_int(table: dict[str, object], key: str) -> bool:
    """True only for a real positive integer — not a string, not 0, not a bool (True is int 1)."""
    value = table.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


_KNOWN_TRIGGERS = {"schedule", "event", "until-goal", "manual"}


@rule("L001", "trigger: the loop can wake itself")
def trigger_self_starting(loop: Loop) -> list[Finding]:
    trig = loop.table("trigger")
    ttype = str(trig.get("type", "")).strip().lower()
    if not trig or ttype in ("", "manual"):
        return [Finding("L001", Severity.MAJOR, "trigger",
                        "No automatic trigger — a loop you start by hand is a manual run, not a "
                        "loop. Nothing wakes it on a schedule, an event, or until a goal is met.",
                        'Add a [trigger] with type = "schedule" (cron), "event", or "until-goal".')]
    return []


@rule("L002", "brake: the loop has a guaranteed hard stop")
def has_a_brake(loop: Loop) -> list[Finding]:
    trig = loop.table("trigger")
    budget = loop.table("budget")
    # A goal (`until`) is NOT a brake — if it's never met the loop runs forever. Only a hard cap
    # (iterations / time / token / cost) is guaranteed to fire.
    hard_stop = (
        _positive_int(trig, "max_iterations")
        or _positive_int(budget, "max_iterations")
        or _has_any(budget, "max_tokens", "max_seconds", "max_cost_usd")
    )
    if not hard_stop:
        return [Finding("L002", Severity.CRITICAL, "budget",
                        "No hard stop — no iteration cap and no token/time/cost ceiling. A goal "
                        "alone (`until`) does not count: if the goal is never met, the loop runs "
                        "forever. This is the runaway every skeptic warns about.",
                        "Add a guaranteed stop: trigger.max_iterations (a positive integer), or a "
                        "[budget] with max_seconds / max_cost_usd / max_tokens. Keep your goal too — "
                        "but the hard cap is what makes it stop.")]
    return []


@rule("L003", "memory: the repo remembers across iterations")
def has_memory(loop: Loop) -> list[Finding]:
    if not _has_any(loop.table("memory"), "file"):
        return [Finding("L003", Severity.MAJOR, "memory",
                        "No memory ledger — the model forgets between iterations, so the loop "
                        "re-checks settled facts and re-proposes rejected ideas. The model forgets; "
                        "the repo must not.",
                        'Add [memory] with file = "memory/ledger.md" — a durable record of what '
                        "was done, confirmed, and still needs a human.")]
    return []


@rule("L004", "verify: a step checks the work")
def has_verification(loop: Loop) -> list[Finding]:
    verify = loop.table("verify")
    if not _has_any(verify, "command", "reviewer_command"):
        return [Finding("L004", Severity.MAJOR, "verify",
                        "No verification step — the agent grades its own homework. A loop with no "
                        "independent check accepts 'looks done' as done and the error rides the "
                        "loop forward.",
                        "Add [verify] with a command (e.g. `pytest -q`) or a reviewer_command that "
                        "uses a different model/perspective.")]
    return []


@rule("L005", "verify: the checker is not the author")
def verify_is_independent(loop: Loop) -> list[Finding]:
    act = _norm_cmd(loop.table("act").get("command"))
    verify = loop.table("verify")
    vcmd = _norm_cmd(verify.get("command"))
    rcmd = _norm_cmd(verify.get("reviewer_command"))
    if act and act in (vcmd, rcmd):
        return [Finding("L005", Severity.MAJOR, "verify",
                        "Self-review — the verify step runs the exact same command as act, so the "
                        "author reviews itself. The writer of the code is the worst reviewer of it; "
                        "in an unattended loop a missed bug compounds.",
                        "Make verify independent: a real test/build command, or a reviewer_command "
                        "on a different model than act.")]
    return []


@rule("L006", "isolation: parallel work can't collide")
def has_isolation(loop: Loop) -> list[Finding]:
    iso = str(loop.table("isolation").get("mode", "")).strip().lower()
    parallel = bool(loop.table("act").get("parallel"))
    if iso in ("", "none"):
        if parallel:
            return [Finding("L006", Severity.MAJOR, "isolation",
                            "Parallel agents with no isolation — concurrent iterations will edit "
                            "the same files and clobber each other. Parallelism without isolation "
                            "manufactures conflicts instead of speed.",
                            'Set [isolation] mode = "worktree" so each agent gets its own '
                            "workspace and results merge at the end.")]
        return [Finding("L006", Severity.MINOR, "isolation",
                        "No isolation declared — fine for a single serial agent, but the moment you "
                        "run more than one you'll get overwrites.",
                        'Set [isolation] mode = "worktree" before you parallelize.')]
    return []


@rule("L007", "skills: durable project knowledge")
def has_skills(loop: Loop) -> list[Finding]:
    if not _has_any(loop.table("skills"), "files"):
        return [Finding("L007", Severity.MINOR, "skills",
                        "No skills/knowledge files — every iteration starts as a new hire who "
                        "doesn't know your conventions, what not to touch, or past gotchas. A "
                        "prompt is a one-off instruction; a skill is the durable rule.",
                        'Add [skills] files = ["skills/project.md"] capturing setup, conventions, '
                        "and landmines.")]
    return []


@rule("L008", "budget: a single iteration has a ceiling")
def has_cost_ceiling(loop: Loop) -> list[Finding]:
    trig = loop.table("trigger")
    budget = loop.table("budget")
    has_iter_cap = _positive_int(trig, "max_iterations") or _positive_int(budget, "max_iterations")
    has_cost = _has_any(budget, "max_tokens", "max_seconds", "max_cost_usd")
    # Only meaningful once a brake exists at all (L002 owns the no-brake-whatsoever case).
    if (has_iter_cap or _has_any(trig, "until")) and not has_cost:
        return [Finding("L008", Severity.MAJOR, "budget",
                        "Iterations are capped but a single iteration has no token/time/cost "
                        "ceiling — one pass can still read, retry, and re-verify until it burns a "
                        "fortune. Token cost is the failure mode people actually hit.",
                        "Add [budget] max_tokens / max_seconds / max_cost_usd as a per-run ceiling.")]
    return []


@rule("L009", "handback: a human keeps the brake")
def has_handback(loop: Loop) -> list[Finding]:
    on = loop.table("handback").get("on")
    if not (isinstance(on, list) and on):
        return [Finding("L009", Severity.MAJOR, "handback",
                        "No handback conditions — nothing ever returns control to a human. The loop "
                        "moves the work, but it can't hold the responsibility; an unattended loop "
                        "with no brake fails unattended.",
                        'Add [handback] on = ["budget-exceeded", "verify-failed-twice", '
                        '"needs-human"] and a notify connector.')]
    return []


@rule("L010", "act: the loop actually does something")
def has_act_command(loop: Loop) -> list[Finding]:
    if not _has_any(loop.table("act"), "command"):
        return [Finding("L010", Severity.MAJOR, "act",
                        "No act command — the loop has no agent invocation, so there is nothing for "
                        "it to run each iteration.",
                        'Add [act] command = "claude -p {prompt}" (or any agent CLI) and a '
                        "prompt_file.")]
    return []


@rule("L011", "trigger: the trigger is actually wired up")
def trigger_is_configured(loop: Loop) -> list[Finding]:
    trig = loop.table("trigger")
    if not trig:
        return []  # L001 owns the missing-trigger case
    ttype = str(trig.get("type", "")).strip().lower()
    if ttype and ttype not in _KNOWN_TRIGGERS:
        return [Finding("L011", Severity.MINOR, "trigger",
                        f"Unknown trigger type {ttype!r} — looks like a typo, so nothing will wake "
                        f"the loop. Expected one of: {', '.join(sorted(_KNOWN_TRIGGERS))}.",
                        'Fix the type, e.g. type = "schedule".')]
    if ttype == "schedule" and not trig.get("cron"):
        return [Finding("L011", Severity.MAJOR, "trigger",
                        "Schedule trigger with no `cron` — there's a type but no schedule, so it "
                        "never fires.",
                        'Add cron = "*/30 * * * *" (or your cadence).')]
    if ttype == "event" and not _has_any(trig, "event", "source", "on"):
        return [Finding("L011", Severity.MAJOR, "trigger",
                        "Event trigger with no source — nothing says which event wakes it.",
                        'Add the event source, e.g. on = "issue.opened" or source = "...".')]
    if ttype == "until-goal" and not trig.get("until"):
        return [Finding("L011", Severity.MAJOR, "trigger",
                        "until-goal trigger with no `until` — there's no goal to run toward or stop "
                        "at.",
                        'Add until = "<the condition that means done>".')]
    return []


@rule("L012", "goal: the loop knows what done means")
def has_goal(loop: Loop) -> list[Finding]:
    if not loop.goal:
        return [Finding("L012", Severity.MINOR, "goal",
                        "No goal stated — a loop with no goal can't tell progress from motion or "
                        "know when it's finished.",
                        'Add a top-level goal = "..." describing the outcome the loop drives toward.')]
    return []


def all_rules() -> list[tuple[str, str, Rule]]:
    return list(_REGISTRY)


def run_rules(loop: Loop, select: set[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for code, _summary, fn in _REGISTRY:
        if select and code not in select:
            continue
        findings.extend(fn(loop))
    return findings
