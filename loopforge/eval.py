"""loopforge eval — score recorded predictions against real outcomes.

The strongest verify a loop can have is not "the command exited 0" but "the prediction matched what
actually happened." `eval` reads a CSV of predictions; once a row's real outcome is known it scores:

  - accuracy   — predicted vs actual (rows that carry an `actual` label)
  - calibration — Brier score, if a predicted probability is given
  - P&L / ROI  — for betting rows that carry `stake` + `odds` (decimal) + a W/L/push result

Use it standalone, or as a loop's verify step: `--min-accuracy` makes it exit non-zero, so a loop
that keeps predicting badly fails its own gate instead of quietly continuing.

CSV columns (all optional except an id and `predicted`):
    id, predicted, actual, prob, stake, odds, result
`actual` blank (and no W/L `result`) = not resolved yet; those rows are reported as pending.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .models import LoopError

_WIN = {"w", "win"}
_LOSS = {"l", "loss", "lose"}
_PUSH = {"push", "p"}
_RESOLVED_RESULTS = _WIN | _LOSS | _PUSH


@dataclass
class EvalReport:
    total: int
    resolved: int
    pending: int
    scored: int          # rows with an `actual` label (accuracy denominator)
    correct: int
    accuracy: float | None
    brier: float | None
    staked: float
    pnl: float
    roi: float | None

    def gate_ok(self, min_accuracy: float | None) -> bool:
        if min_accuracy is None:
            return True
        if self.accuracy is None:
            return True  # nothing resolved yet — no evidence of bad prediction, don't fail the tick
        return self.accuracy >= min_accuracy


def _num(row: dict[str, str], key: str) -> float | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _lower(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip().lower()


def evaluate(rows: list[dict[str, str]]) -> EvalReport:
    total = len(rows)
    pending = scored = correct = resolved = 0
    brier_terms: list[float] = []
    staked = pnl = 0.0

    for row in rows:
        predicted = _lower(row, "predicted")
        actual = _lower(row, "actual")
        result = _lower(row, "result")
        if not actual and result not in _RESOLVED_RESULTS:
            pending += 1
            continue
        resolved += 1

        hit: bool | None = None
        if actual:
            scored += 1
            hit = predicted == actual
            if hit:
                correct += 1
            prob = _num(row, "prob")
            # Brier needs a probability in [0,1]. A confidence logged as a percent (75 for 0.75)
            # would add a term of ~(75-1)**2 and a single such row silently wrecks the mean — so an
            # out-of-range prob is skipped rather than allowed to corrupt the calibration score.
            if prob is not None and 0.0 <= prob <= 1.0:
                brier_terms.append((prob - (1.0 if hit else 0.0)) ** 2)

        stake, odds = _num(row, "stake"), _num(row, "odds")
        # decimal odds must be > 1.0; at odds <= 1 a "win" pays stake*(odds-1) <= 0, which would
        # book a winning bet as flat/negative P&L. Treat such a row as invalid odds and skip it.
        if stake and odds and stake > 0 and odds > 1.0:
            outcome = result or ("w" if hit else "l")
            if outcome in _WIN:
                staked += stake
                pnl += stake * (odds - 1.0)
            elif outcome in _LOSS:
                staked += stake
                pnl -= stake
            elif outcome in _PUSH:
                staked += stake

    return EvalReport(
        total=total,
        resolved=resolved,
        pending=pending,
        scored=scored,
        correct=correct,
        accuracy=(correct / scored) if scored else None,
        brier=(sum(brier_terms) / len(brier_terms)) if brier_terms else None,
        staked=round(staked, 2),
        pnl=round(pnl, 2),
        roi=(pnl / staked) if staked > 0 else None,
    )


def load(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise LoopError(f"cannot read predictions file {p}: {exc}") from exc
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise LoopError(f"no prediction rows found in {p}")
    if "predicted" not in rows[0]:
        raise LoopError(f"{p} must have a 'predicted' column (got: {', '.join(rows[0].keys())})")
    return rows


def render(report: EvalReport) -> str:
    lines = [
        f"predictions: {report.total}  ·  resolved: {report.resolved}  ·  pending: {report.pending}",
    ]
    if report.scored:
        acc = f"{report.accuracy:.0%}" if report.accuracy is not None else "—"
        lines.append(f"accuracy: {acc}  ({report.correct}/{report.scored} correct)")
    if report.brier is not None:
        lines.append(f"calibration (Brier, lower=better): {report.brier:.3f}")
    if report.staked > 0:
        roi = f"{report.roi:+.1%}" if report.roi is not None else "—"
        lines.append(f"P&L: {report.pnl:+.2f}  ·  staked: {report.staked:.2f}  ·  ROI: {roi}")
    return "\n".join(lines)
