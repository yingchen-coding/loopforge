import pytest

from loopforge.linter import lint_path
from loopforge.models import LoopError
from loopforge.scaffold import init


def test_init_creates_complete_lint_clean_loop(tmp_path):
    root = init("My Watcher", tmp_path)
    assert root.name == "my-watcher"
    assert (root / "loop.toml").exists()
    assert (root / "skills" / "project.md").exists()
    assert (root / "memory" / "ledger.md").exists()
    assert (root / "prompts" / "act.md").exists()
    # the whole point: a scaffolded loop passes the linter with zero findings
    results = lint_path(root)
    assert len(results) == 1 and results[0].ok


def test_init_refuses_to_overwrite(tmp_path):
    init("dup", tmp_path)
    with pytest.raises(LoopError, match="already exists"):
        init("dup", tmp_path)


def test_init_force_overwrites(tmp_path):
    init("dup", tmp_path)
    root = init("dup", tmp_path, force=True)
    assert root.exists()


def test_slug_normalizes_messy_names(tmp_path):
    root = init("  Nightly!! Cleanup  ", tmp_path)
    assert root.name == "nightly-cleanup"
