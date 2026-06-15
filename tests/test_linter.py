import pytest

from loopforge.linter import grade, lint_path, lint_text, score, sort_findings
from loopforge.models import LoopError
from tests.conftest import COMPLETE, without


def test_complete_loop_grades_a():
    result = lint_text(COMPLETE)
    assert result.ok
    assert grade(result.findings) == "A"
    assert score(result.findings) == 100


def test_runaway_grades_f_regardless_of_other_blocks():
    text = without("budget").replace("max_iterations = 10\n", "")
    findings = lint_text(text).findings
    assert grade(findings) == "F"  # a CRITICAL pins it to F


def test_findings_sorted_loudest_first():
    findings = lint_text(without("trigger")).findings
    severities = [int(f.severity) for f in findings]
    assert severities == sorted(severities, reverse=True)
    assert findings is not None
    assert sort_findings(findings) == findings  # already sorted


def test_lint_path_file(tmp_path):
    p = tmp_path / "loop.toml"
    p.write_text(COMPLETE)
    results = lint_path(p)
    assert len(results) == 1 and results[0].ok


def test_lint_path_directory_discovers_all(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "loop.toml").write_text(COMPLETE)
    (tmp_path / "b" / "loop.toml").write_text(without("memory"))
    results = lint_path(tmp_path)
    assert len(results) == 2
    by_ok = {r.ok for r in results}
    assert by_ok == {True, False}


def test_lint_path_empty_dir_raises(tmp_path):
    with pytest.raises(LoopError, match="no loop definitions"):
        lint_path(tmp_path)


def test_lint_path_missing_raises():
    with pytest.raises(LoopError, match="no such path"):
        lint_path("/nope/here")


def test_parse_error_surfaces_as_result(tmp_path):
    p = tmp_path / "loop.toml"
    p.write_text('goal = "no name"\n')
    results = lint_path(p)
    assert results[0].error and "name" in results[0].error
