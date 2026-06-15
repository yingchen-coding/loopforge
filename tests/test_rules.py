from loopforge.linter import lint_text
from loopforge.models import Severity
from tests.conftest import COMPLETE, without


def codes(text: str) -> set[str]:
    return {f.code for f in lint_text(text).findings}


def test_complete_loop_is_clean():
    assert codes(COMPLETE) == set()


def test_missing_trigger_flags_l001():
    found = codes(without("trigger"))
    assert "L001" in found  # not self-starting
    assert "L002" not in found  # [budget] still provides a brake, so not a runaway


def test_manual_trigger_is_not_a_loop():
    text = COMPLETE.replace('type = "schedule"', 'type = "manual"')
    assert "L001" in codes(text)


def test_missing_memory_flags_l003():
    assert "L003" in codes(without("memory"))


def test_missing_verify_flags_l004():
    assert "L004" in codes(without("verify"))


def test_self_review_flags_l005():
    text = COMPLETE.replace('command = "pytest -q"', 'command = "claude -p {prompt}"')
    assert "L005" in codes(text)


def test_parallel_without_isolation_is_major():
    text = without("isolation").replace("prompt_file", "parallel = true\nprompt_file")
    findings = [f for f in lint_text(text).findings if f.code == "L006"]
    assert findings and findings[0].severity is Severity.MAJOR


def test_serial_without_isolation_is_minor():
    findings = [f for f in lint_text(without("isolation")).findings if f.code == "L006"]
    assert findings and findings[0].severity is Severity.MINOR


def test_missing_skills_flags_l007():
    assert "L007" in codes(without("skills"))


def test_iteration_cap_but_no_cost_ceiling_flags_l008():
    # keep max_iterations, drop the [budget] cost ceiling
    text = without("budget")
    found = codes(text)
    assert "L008" in found
    assert "L002" not in found  # there's still a brake (max_iterations), so not a runaway


def test_no_brake_at_all_is_critical_l002():
    text = without("budget").replace("max_iterations = 10\n", "")
    findings = lint_text(text).findings
    l002 = [f for f in findings if f.code == "L002"]
    assert l002 and l002[0].severity is Severity.CRITICAL


def test_goal_alone_is_not_a_brake():
    # an until-goal loop with no hard cap can loop forever if the goal is never met
    text = (
        without("budget")
        .replace("max_iterations = 10\n", "")
        .replace('cron = "*/30 * * * *"\n', "")
        .replace('type = "schedule"', 'type = "until-goal"\nuntil = "all tests pass"')
    )
    assert "L002" in codes(text)


def test_zero_iterations_is_not_a_brake():
    text = without("budget").replace("max_iterations = 10", "max_iterations = 0")
    assert "L002" in codes(text)


def test_schedule_without_cron_flags_l011():
    text = COMPLETE.replace('cron = "*/30 * * * *"\n', "")
    findings = [f for f in lint_text(text).findings if f.code == "L011"]
    assert findings and findings[0].severity is Severity.MAJOR


def test_unknown_trigger_type_flags_l011():
    text = COMPLETE.replace('type = "schedule"', 'type = "scheduled"')  # typo
    findings = [f for f in lint_text(text).findings if f.code == "L011"]
    assert findings and findings[0].severity is Severity.MINOR


def test_until_goal_without_until_flags_l011():
    text = COMPLETE.replace('type = "schedule"', 'type = "until-goal"')
    assert "L011" in codes(text)


def test_complete_loop_has_no_trigger_config_finding():
    assert "L011" not in codes(COMPLETE)


def test_missing_handback_flags_l009():
    assert "L009" in codes(without("handback"))


def test_missing_act_command_flags_l010():
    assert "L010" in codes(without("act"))


def test_missing_goal_flags_l012():
    text = COMPLETE.replace('goal = "Do the thing and verify it."', 'goal = ""')
    assert "L012" in codes(text)


def test_select_runs_only_requested_rule():
    findings = lint_text(without("memory"), select={"L004"}).findings
    assert {f.code for f in findings} <= {"L004"}
