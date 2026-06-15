# Changelog

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
