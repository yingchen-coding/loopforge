import pytest

from loopforge.models import LoopError
from loopforge.runner import parse_loop, plan, run
from loopforge.scaffold import init


def make_loop(tmp_path, act: str, verify: str = "true", max_iter: int = 5):
    root = init("runme", tmp_path)
    p = root / "loop.toml"
    t = p.read_text()
    t = t.replace('command = "claude -p {prompt}"', f"command = {act!r}")
    t = t.replace('command = "pytest -q"', f"command = {verify!r}")
    t = t.replace("max_iterations = 20", f"max_iterations = {max_iter}")
    p.write_text(t)
    return p


def test_run_refuses_loop_with_no_brake(tmp_path):
    p = tmp_path / "loop.toml"
    p.write_text('name = "x"\n[trigger]\ntype = "schedule"\n[act]\ncommand = "echo hi"\n')
    with pytest.raises(LoopError, match="refusing to run"):
        run(p)


def test_dry_run_does_not_execute(tmp_path):
    p = make_loop(tmp_path, act="echo SHOULD-NOT-RUN")
    result = run(p, dry_run=True)
    assert result.dry_run and result.outcome == "dry-run"
    assert result.iterations == 0


def test_plan_lists_all_blocks(tmp_path):
    p = make_loop(tmp_path, act="echo hi")
    text = plan(parse_loop(p))
    for key in ("trigger", "isolation", "skills", "act", "verify", "memory", "handback"):
        assert key in text


def test_goal_reached_stops_and_records(tmp_path):
    p = make_loop(tmp_path, act="echo GOAL-REACHED", verify="true")
    result = run(p)
    assert result.outcome == "done"
    assert result.handback_reason == "goal-reached"
    assert result.iterations == 1
    ledger = (p.parent / "memory" / "ledger.md").read_text()
    assert "| 1 |" in ledger  # an entry was appended


def test_needs_human_hands_back(tmp_path):
    p = make_loop(tmp_path, act="echo NEEDS-HUMAN: cannot proceed")
    result = run(p)
    assert result.outcome == "handback"
    assert result.handback_reason == "needs-human"


def test_verify_failed_twice_hands_back(tmp_path):
    p = make_loop(tmp_path, act="echo working", verify="false", max_iter=5)
    result = run(p)
    assert result.handback_reason == "verify-failed-twice"
    assert result.iterations == 2


def test_max_iterations_override(tmp_path):
    # never reaches goal; runs to the (overridden) cap then stops
    p = make_loop(tmp_path, act="echo working", verify="true", max_iter=9)
    result = run(p, max_iterations=3)
    assert result.iterations == 3
    assert result.handback_reason == "max-iterations"
