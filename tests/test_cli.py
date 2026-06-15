import json

import pytest

from loopforge.cli import main
from tests.conftest import COMPLETE, without


def write_loop(tmp_path, text):
    p = tmp_path / "loop.toml"
    p.write_text(text)
    return p


def test_lint_clean_exits_zero(tmp_path, capsys):
    write_loop(tmp_path, COMPLETE)
    assert main(["lint", str(tmp_path)]) == 0
    assert "complete" in capsys.readouterr().out


def test_lint_findings_exit_one_at_major(tmp_path, capsys):
    write_loop(tmp_path, without("memory"))  # L003 major
    assert main(["lint", str(tmp_path), "--fail-at", "major"]) == 1


def test_lint_fail_at_critical_ignores_major(tmp_path):
    write_loop(tmp_path, without("memory"))  # only major
    assert main(["lint", str(tmp_path), "--fail-at", "critical"]) == 0


def test_lint_json_is_valid(tmp_path, capsys):
    write_loop(tmp_path, COMPLETE)
    main(["lint", str(tmp_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["grade"] == "A"


def test_lint_parse_error_exits_two(tmp_path):
    write_loop(tmp_path, 'goal = "no name"\n')
    assert main(["lint", str(tmp_path)]) == 2


def test_init_then_lint(tmp_path, capsys):
    assert main(["init", "watcher", "--dest", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "created" in out
    assert main(["lint", str(tmp_path / "watcher")]) == 0


def test_run_dry_run(tmp_path, capsys):
    main(["init", "watcher", "--dest", str(tmp_path)])
    capsys.readouterr()
    assert main(["run", str(tmp_path / "watcher" / "loop.toml"), "--dry-run"]) == 0
    assert "loop: watcher" in capsys.readouterr().out


def test_list_rules(capsys):
    assert main(["list-rules"]) == 0
    out = capsys.readouterr().out
    assert "L001" in out and "L012" in out


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
