import pytest

from loopforge.eval import evaluate, load
from loopforge.models import LoopError


def test_accuracy_pending_and_resolution():
    rows = [
        {"id": "a", "predicted": "win", "actual": "win"},
        {"id": "b", "predicted": "win", "actual": "loss"},
        {"id": "c", "predicted": "draw", "actual": ""},  # unresolved
    ]
    r = evaluate(rows)
    assert (r.total, r.resolved, r.pending, r.scored, r.correct) == (3, 2, 1, 2, 1)
    assert r.accuracy == 0.5


def test_brier_and_pnl_for_betting_rows():
    def row(rid, pred, act, prob, odds, res):
        return {"id": rid, "predicted": pred, "actual": act, "prob": prob,
                "stake": "4", "odds": odds, "result": res}

    rows = [
        row("fra", "win", "win", "0.55", "2.10", "W"),
        row("bra", "win", "loss", "0.60", "1.80", "L"),
        row("eng", "draw", "", "0.30", "3.40", ""),
    ]
    r = evaluate(rows)
    assert (r.resolved, r.pending, r.scored, r.correct) == (2, 1, 2, 1)
    assert r.accuracy == 0.5
    assert abs(r.brier - 0.28125) < 1e-6           # (0.55-1)^2 and (0.60-0)^2, averaged
    assert abs(r.pnl - 0.4) < 1e-6                  # +4*1.10 then -4
    assert abs(r.staked - 8.0) < 1e-6
    assert abs(r.roi - 0.05) < 1e-6


def test_result_only_row_resolves_for_pnl_but_not_accuracy():
    rows = [{"id": "a", "predicted": "win", "actual": "", "stake": "4", "odds": "2.0", "result": "W"}]
    r = evaluate(rows)
    assert r.resolved == 1 and r.scored == 0      # no actual label → not in accuracy
    assert abs(r.pnl - 4.0) < 1e-6                 # 4*(2.0-1)


def test_gate():
    r = evaluate([{"id": "a", "predicted": "x", "actual": "y"}])
    assert r.accuracy == 0.0
    assert r.gate_ok(None) is True
    assert r.gate_ok(0.5) is False


def test_gate_passes_when_nothing_resolved_yet():
    # all rows pending → accuracy None → a --min-accuracy gate must NOT fail every tick
    r = evaluate([{"id": "a", "predicted": "x"}, {"id": "b", "predicted": "y"}])
    assert r.scored == 0 and r.accuracy is None
    assert r.gate_ok(0.9) is True   # no evidence of bad prediction yet
    assert r.gate_ok(None) is True


def test_load_requires_predicted_column(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("id,foo\n1,2\n", encoding="utf-8")
    with pytest.raises(LoopError, match="predicted"):
        load(p)


def test_load_empty_fails(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(LoopError):
        load(p)
