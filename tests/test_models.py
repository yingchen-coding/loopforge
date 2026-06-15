import pytest

from loopforge.models import LoopError, Severity, parse_loop, parse_text
from tests.conftest import COMPLETE


def test_parse_complete_loop():
    loop = parse_text(COMPLETE)
    assert loop.name == "demo"
    assert loop.goal.startswith("Do the thing")
    assert loop.has_block("trigger")
    assert loop.table("budget")["max_tokens"] == 100000


def test_missing_name_fails_loud():
    with pytest.raises(LoopError, match="missing a top-level `name`"):
        parse_text('goal = "x"\n[trigger]\ntype = "schedule"\n')


def test_invalid_toml_fails_loud():
    with pytest.raises(LoopError, match="invalid TOML"):
        parse_text("name = \nthis is not toml")


def test_unknown_key_warns_but_parses():
    loop = parse_text('name = "x"\nbogus = 1\n')
    assert any("bogus" in w for w in loop.warnings)


def test_parse_loop_missing_file():
    with pytest.raises(LoopError, match="no such loop file"):
        parse_loop("/nonexistent/loop.toml")


def test_table_returns_empty_for_absent_block():
    loop = parse_text('name = "x"\n')
    assert loop.table("trigger") == {}
    assert loop.has_block("trigger") is False


def test_severity_ordering_and_labels():
    assert Severity.CRITICAL > Severity.MAJOR > Severity.MINOR > Severity.INFO
    assert Severity.from_label("major") is Severity.MAJOR
    with pytest.raises(LoopError):
        Severity.from_label("nope")
