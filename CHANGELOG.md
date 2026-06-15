# Changelog

## 0.2.0

- **L002 now requires a *hard* stop.** A goal (`until`) no longer counts as a brake on its own — a
  goal that's never met loops forever. The runaway check is satisfied only by a positive
  `max_iterations` or a `[budget]` time/token/cost ceiling. A non-int or zero `max_iterations` no
  longer counts either (it now agrees with the runner).
- **New rule `L011` — trigger is actually wired up.** Catches a `schedule` trigger with no `cron`,
  an `event` trigger with no source, an `until-goal` trigger with no `until`, and typo'd trigger
  types (e.g. `"scheduled"`) that would silently never fire.
- 56 tests (was 50).

## 0.1.0

First release.

- **lint** — grade any loop A–F against the six blocks of Loop Engineering (trigger, isolation,
  skills, act, verify, memory) plus a cost brake and a human brake. 11 deterministic rules
  (`L001`–`L012`); only the no-brake runaway is `critical`.
- **init** — scaffold a complete, lint-clean loop (`loop.toml` + skills + memory + prompt).
- **run** — execute a loop (wake → act → verify → record → decide). Enforces iteration and
  wall-clock limits, appends every step to the memory ledger, and **refuses to start a loop that
  has no brake**.
- Zero runtime dependencies, Python ≥ 3.11. `human` and `json` output; `--score`, `--select`,
  `--fail-at`.
