"""Workload budgets are advisory; only finished helper calls advance progress."""
from allin1.rpf_progress import RpfProgress


def test_large_package_budget_heartbeat_snapshots_and_slow_action_are_distinct():
    now, frames = [0.0], []
    work = RpfProgress(lambda percent, message: frames.append((percent, message)), clock=lambda: now[0])
    assert work.snapshot() is None
    work.plan(420 * 3, 420)
    assert work.snapshot()["budget_seconds"] == 120 + 1260 * 5
    work.start("extract-exact-entry", "common/test.xml", "Backing up")
    now[0] = 121
    before = len(frames)
    for _ in range(10):
        snapshot = work.snapshot()
        assert snapshot["slow_action"] and snapshot["active_seconds"] == 121
        assert snapshot["completed_actions"] == 0 and not snapshot["budget_exceeded"]
    assert len(frames) == before  # A heartbeat snapshot isn't a completed action.
    work.finish()
    assert work.snapshot()["completed_actions"] == 1
    assert not work.snapshot()["slow_action"]
    now[0] = 6421
    assert work.snapshot()["budget_exceeded"]
    work.start("replace-entry", "common/test.xml")
    work.finish()  # Overrunning a budget never cancels, fails, or retries work.
    assert work.snapshot()["completed_actions"] == 2


def test_extra_calls_extend_the_plan_without_backward_or_premature_complete_progress():
    frames = []
    work = RpfProgress(lambda percent, _: frames.append(percent))
    work.plan(3, 1)
    for _ in range(3):
        work.start("extract-exact-entry", "entry")
        work.finish()
    work.plan(3)  # Canonicalization.
    for _ in range(4):  # Includes an unplanned recovery call.
        work.start("replace-entry", "entry")
        work.finish()
    assert work.snapshot()["estimated_actions"] == work.snapshot()["completed_actions"] == 7
    assert work.snapshot()["budget_seconds"] == 155
    assert frames == sorted(frames) and max(frames) == 99


def test_observer_failure_cannot_abort_an_archive_operation():
    def disconnected(*_):
        raise BrokenPipeError("UI gone")
    work = RpfProgress(disconnected)
    work.plan(3, 1)
    work.start("replace-entry", "entry")
    work.finish()
    assert work.snapshot()["completed_actions"] == 1
