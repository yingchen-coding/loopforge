# Walkthrough: build a loop that won't run away

This is a hands-on tour. In ~10 minutes you'll scaffold a loop, see loopforge grade it, break it on
purpose to watch each of the six blocks get flagged, wire in a real verify step, run it safely, and
gate it in CI. Every command here is real — run them as you read.

## 0. Install

```bash
pip install git+https://github.com/yingchen-coding/loopforge
loopforge --version
```

Zero dependencies, Python ≥ 3.11.

## 1. Scaffold a complete loop

```bash
loopforge init ci-green
```

You get a directory with all six blocks already wired:

```
ci-green/
  loop.toml          # the six blocks + a cost brake + a human brake
  skills/project.md  # durable project knowledge
  memory/ledger.md   # what the repo remembers across iterations
  prompts/act.md     # the per-iteration instruction
```

Confirm it's complete:

```bash
loopforge lint ci-green --score
# ✓ complete — all six blocks present
#   Loop completeness: A (100/100)
```

That's the baseline: a loop that answers all six questions.

## 2. The six blocks, and what each one is for

Open `ci-green/loop.toml`. Each table is one block:

| Block | Question | Why a loop dies without it |
|-------|----------|----------------------------|
| `[trigger]` | Who wakes it up? | A loop you start by hand is a manual run, not a loop. |
| `[isolation]` | Parallel-safe workspace? | Two agents editing the same file clobber each other. |
| `[skills]` | How does it know your conventions? | Every iteration restarts as a new hire who doesn't know the codebase. |
| `[act]` | What does it do? | No command, no work. |
| `[verify]` | Who checks it — *not itself*? | The author is the worst reviewer of their own work; in a loop the error compounds. |
| `[memory]` | How does it remember? | The model forgets; without a ledger it re-litigates settled questions. |

Plus two disciplines the loop dies *expensively* without:

- `[budget]` — a **cost brake**, so it can't burn tokens forever.
- `[handback]` — a **human brake**, so judgment, acceptance, and the stop button stay with you.

## 3. Break it on purpose

Delete the `[verify]` table from `loop.toml` and re-lint:

```bash
loopforge lint ci-green
# ✖ major  L004  No verification step — the agent grades its own homework.
```

Now make `verify.command` identical to `act.command` (e.g. both `claude -p {prompt}`):

```bash
# ✖ major  L005  Self-review — the verify step runs the exact same command as act.
```

Delete every limit — remove `trigger.max_iterations` and the whole `[budget]` table:

```bash
# ✖ critical  L002  No hard stop — a goal alone can loop forever; it can burn budget with no cap.
```

`L002` is the only **critical** rule, on purpose: a loop that can't stop is the one failure that
turns "unattended" into "expensive." Note a goal (`until`) does *not* satisfy it — only a hard cap
(iterations / time / cost) guarantees the loop stops. Run `loopforge list-rules` for the full catalog.

## 4. Wire a real verify step

The scaffold uses `pytest -q` as the independent check. Point `act` at your agent and `verify` at
whatever actually proves the work — a test suite, a build, a typecheck, or a *different* model
reviewing the diff:

```toml
[act]
command = "claude -p {prompt}"
prompt_file = "prompts/act.md"

[verify]
command = "pytest -q"        # or: reviewer_command = "claude --model <other> -p {review}"
require = "exit-zero"
```

The rule of thumb the article borrows from code review: **the writer shouldn't review themselves.**

## 5. Run it — safely

See exactly what it would do, without executing:

```bash
loopforge run ci-green/loop.toml --dry-run
```

When you run for real, loopforge:

1. **Refuses** to start if the loop has a `critical` finding (no brake).
2. Builds each iteration's prompt from `skills` + the `memory` ledger + `prompts/act.md`.
3. Runs `act`, then the independent `verify`.
4. Appends a row to `memory/ledger.md` — the repo remembers even after the process exits.
5. Stops on: goal reached, verify failed twice, budget/iteration cap, or the agent saying
   `NEEDS-HUMAN`, and hands back to you.

> Honesty note: loopforge enforces the limits it can *measure* — iteration count and wall-clock
> time. It passes your `max_tokens` / `max_cost_usd` through to your agent and shows them in the
> plan, but it does not pretend to count tokens it never sees.

## 6. Gate it in CI

Keep a loop from regressing into a runaway by linting it on every PR:

```yaml
# .github/workflows/loops.yml
name: loops
on: [push, pull_request]
jobs:
  loopforge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: yingchen-coding/loopforge@v0.2.0
        with:
          path: loops/
          fail-at: major
          score: "true"
```

## Where to go next

- `loopforge list-rules` — the full rule catalog.
- `examples/ci-green/` — the complete reference loop.
- `examples/half-baked/` — what most "loops" actually look like (and what loopforge says about them).
- The six blocks come from Addy Osmani's *Loop Engineering* writeup; loopforge just makes them
  checkable.
