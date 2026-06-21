import subprocess
from pathlib import Path

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


def test_run_accepts_a_directory_like_lint(tmp_path):
    # `loopforge run <dir>` must work like `lint <dir>` — resolve the single loop.toml inside.
    make_loop(tmp_path, act="echo hi")          # writes <tmp>/runme/loop.toml
    result = run(tmp_path / "runme", dry_run=True)
    assert result.loop == "runme" and result.outcome == "dry-run"


def test_run_directory_with_multiple_loops_is_ambiguous(tmp_path):
    make_loop(tmp_path, act="echo a")           # <tmp>/runme/loop.toml
    (tmp_path / "other.loop.toml").write_text(
        (tmp_path / "runme" / "loop.toml").read_text(), encoding="utf-8")
    with pytest.raises(LoopError, match="multiple loops"):
        run(tmp_path, dry_run=True)


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


def test_ledger_records_action_and_outcome_separately(tmp_path):
    p = make_loop(tmp_path, act="echo DID-A-THING", verify="true")
    run(p, max_iterations=1)
    ledger = (p.parent / "memory" / "ledger.md").read_text()
    assert "DID-A-THING" in ledger  # the summary column = what act did
    assert "| ok |" in ledger or "| goal-reached |" in ledger  # distinct outcome column


def test_reviewer_command_sees_act_output(tmp_path):
    # verify has only a reviewer_command; the runner must pipe act's output to it
    root = init("rev", tmp_path)
    p = root / "loop.toml"
    t = p.read_text()
    t = t.replace('command = "claude -p {prompt}"', 'command = "echo HELLO"')
    t = t.replace('command = "pytest -q"', 'reviewer_command = "grep HELLO"')
    p.write_text(t)
    result = run(p, max_iterations=1)
    assert result.logs[0].verified is True  # reviewer found HELLO in the act output


def test_reviewer_command_fails_when_output_is_wrong(tmp_path):
    root = init("rev2", tmp_path)
    p = root / "loop.toml"
    t = p.read_text()
    t = t.replace('command = "claude -p {prompt}"', 'command = "echo BYE"')
    t = t.replace('command = "pytest -q"', 'reviewer_command = "grep HELLO"')
    p.write_text(t)
    result = run(p, max_iterations=1)
    assert result.logs[0].verified is False  # reviewer did not find HELLO


def test_worktree_isolation_runs_in_worktree_ledger_stays_home(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    root = init("iso", repo)  # scaffold uses isolation mode = worktree
    p = root / "loop.toml"
    t = p.read_text()
    t = t.replace('command = "claude -p {prompt}"', 'command = "touch MARKER"')
    t = t.replace('command = "pytest -q"', 'command = "true"')
    p.write_text(t)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True, capture_output=True)

    result = run(p, max_iterations=1)
    try:
        assert result.worktree is not None
        wt = Path(result.worktree)
        assert wt.exists() and wt != root
        assert (wt / "MARKER").exists()          # act executed inside the isolated worktree
        assert not (root / "MARKER").exists()     # the original working tree was untouched
        # memory is written back to the ORIGINAL repo so the record survives the worktree
        assert "| 1 |" in (root / "memory" / "ledger.md").read_text()
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt.parent)],
            capture_output=True,
        )


def test_max_iterations_override(tmp_path):
    # never reaches goal; runs to the (overridden) cap then stops
    p = make_loop(tmp_path, act="echo working", verify="true", max_iter=9)
    result = run(p, max_iterations=3)
    assert result.iterations == 3
    assert result.handback_reason == "max-iterations"
