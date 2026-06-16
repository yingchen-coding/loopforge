import pytest

from loopforge import schedule
from loopforge.models import LoopError, parse_text
from tests.conftest import COMPLETE


def _loop():
    return parse_text(COMPLETE)  # name "demo", trigger schedule, cron */30


def test_cron_line_is_tagged_and_runs_the_loop(tmp_path):
    line = schedule.cron_line(_loop(), tmp_path / "loop.toml")
    assert line.startswith("*/30 * * * *")
    assert "loopforge run" in line
    assert line.rstrip().endswith("# loopforge:demo")


def test_cron_line_rejects_non_schedule_trigger():
    loop = parse_text(COMPLETE.replace('type = "schedule"', 'type = "until-goal"\nuntil = "x"'))
    with pytest.raises(LoopError, match="schedule"):
        schedule.cron_line(loop, "loop.toml")


def test_cron_line_rejects_missing_cron():
    loop = parse_text(COMPLETE.replace('cron = "*/30 * * * *"\n', ""))
    with pytest.raises(LoopError, match="cron"):
        schedule.cron_line(loop, "loop.toml")


def test_apply_preserves_existing_jobs_and_is_idempotent(tmp_path):
    existing = "0 3 * * * /usr/bin/backup.sh\n*/5 * * * * /quant/run.sh\n"
    once = schedule.apply_entry(existing, _loop(), tmp_path / "loop.toml")
    twice = schedule.apply_entry(once, _loop(), tmp_path / "loop.toml")
    assert "/usr/bin/backup.sh" in twice and "/quant/run.sh" in twice  # never clobber other jobs
    assert twice.count("# loopforge:demo") == 1  # idempotent — one entry, not two
    assert once == twice


def test_remove_drops_only_the_named_loop(tmp_path):
    existing = "0 3 * * * /usr/bin/backup.sh\n"
    with_loop = schedule.apply_entry(existing, _loop(), tmp_path / "loop.toml")
    after, removed = schedule.remove_entry(with_loop, "demo")
    assert removed
    assert "/usr/bin/backup.sh" in after
    assert "# loopforge:demo" not in after


def test_remove_missing_is_a_noop(tmp_path):
    existing = "0 3 * * * /usr/bin/backup.sh\n"
    after, removed = schedule.remove_entry(existing, "nope")
    assert not removed and "/usr/bin/backup.sh" in after


def test_managed_entries_lists_only_loopforge(tmp_path):
    existing = "0 3 * * * /usr/bin/backup.sh\n"
    with_loop = schedule.apply_entry(existing, _loop(), tmp_path / "loop.toml")
    entries = schedule.managed_entries(with_loop)
    assert len(entries) == 1 and "loopforge:demo" in entries[0]
