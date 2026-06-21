# Changelog

## 0.5.3

- **`eval` no longer lets one bad row silently corrupt a metric.** Two scoring bugs:
  - A `prob` outside `[0,1]` (e.g. a confidence logged as `75` for `0.75`) added a `~(75-1)²`
    term that wrecked the mean Brier score. Out-of-range probabilities are now skipped, so
    calibration reflects only valid rows.
  - Decimal odds `<= 1.0` would book a *winning* bet as flat/negative P&L (`stake*(odds-1) <= 0`).
    Such rows are now treated as invalid odds and skipped from P&L.
  Both found by routing a correctness review of `evaluate()` through modelbroker (review → claude).

## 0.5.2

- **`run` accepts a directory** like `lint` does — `loopforge run mydir/` resolves the single
  `loop.toml` inside instead of crashing with "Is a directory". Found by dogfooding (lint a dir,
  then run it). Multiple loops in one dir → a clear "name the one to run" error.

## 0.5.1

- **`eval` gate fix** — `--min-accuracy` no longer fails when no predictions are resolved yet.
  A scheduled loop whose outcomes resolve later would previously fail its gate every tick (no data
  read as failure); now the gate passes until there is real accuracy evidence to judge. CLI prints a
  note so the pass is explicit.

## 0.5.0

- **`loopforge eval`** — score recorded predictions against real outcomes (the deepest verify:
  predicted vs ground truth). Reads a CSV (`id,predicted,actual,prob,stake,odds,result`) and reports
  accuracy, calibration (Brier), and betting P&L/ROI. `--min-accuracy` makes it a verify gate, so a
  loop that keeps predicting badly fails itself. Domain-agnostic (bets, stock calls, anything). Pair
  it with a resolver that fetches the latest data + `loopforge schedule` to auto-validate on a
  cadence. See `examples/eval-soccer/`.

## 0.4.0

- **`loopforge schedule`** — turn a loop's declarative `[trigger].cron` into a real cron entry, so a
  scheduled loop actually fires. `schedule install <loop.toml>` (with `--dry-run`), `schedule list`,
  `schedule remove <name>`. Entries are tagged `# loopforge:<name>` and managed idempotently. A hard
  no-clobber guard refuses to write if the existing crontab can't be read, so it never wipes your
  other jobs. (macOS: cron needs Full Disk Access to touch protected dirs.)

## 0.3.0

- **Real worktree isolation in the runner.** When `[isolation] mode = "worktree"` and the loop is in
  a git repo, `run` now executes act/verify in an isolated `git worktree` (left in place for you to
  review and merge), while the memory ledger is written back to the original repo so the record
  survives. Previously isolation was linted but ignored by the runner — a describe-vs-do gap, now
  closed. The worktree path is reported in the run output.
- **`reviewer_command` now receives the act output.** A second-model review can finally *see* the
  work it's reviewing (it was being run with no input).
- **Memory ledger fixed.** Each iteration now records a distinct *action summary* (what act did) and
  *outcome* — previously both columns held the same string.
- **New rule `L013` — referenced files exist.** Flags `skills` / `memory` / `prompt_file` paths in
  `loop.toml` that don't exist on disk (only when linting a real file). Catches the typo'd path the
  runner would otherwise load as "(MISSING)".
- 63 tests (was 56).

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
