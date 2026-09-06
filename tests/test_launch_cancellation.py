"""Cancellation cannot become a game kill, stale signal, or swallowed render error."""
import threading

import pytest

from allin1.launch_cancellation import LaunchCancellation, LaunchCancelled, checkpoint, commit_dispatch


def test_scope_idempotency_and_new_launch_isolation():
    control = LaunchCancellation()
    assert not control.request({"review_id": "old"})["accepted"]
    with control.preparing("one"):
        assert control.status()["cancellable"]
        assert not control.request({"review_id": "old"})["accepted"]
        assert control.request({"review_id": "one"})["accepted"]
        assert control.request({"review_id": "one"})["accepted"]
        assert not control.status()["cancellable"]
        with pytest.raises(LaunchCancelled): checkpoint()
        with pytest.raises(LaunchCancelled): commit_dispatch()
    assert control.status()["launch_review_id"] is None
    with control.preparing("two"):
        assert not control.request({"review_id": "one"})["accepted"]
        checkpoint()
        commit_dispatch()
        assert control.request({"review_id": "two"}) == {"status": "already_dispatched", "accepted": False}
        checkpoint()


@pytest.mark.parametrize("payload", [{}, {"review_id": None}, {"review_id": []}, {"review_id": ""}, {"review_id": "one", "pid": 123}])
def test_arbitrary_process_or_missing_identity_is_rejected(payload):
    with pytest.raises(ValueError): LaunchCancellation().request(payload)


def test_cancel_dispatch_race_has_exactly_one_winner():
    for _ in range(50):
        control = LaunchCancellation()
        barrier = threading.Barrier(2)
        result = []
        def cancel():
            barrier.wait()
            result.append(control.request({"review_id": "race"})["accepted"])
        with control.preparing("race"):
            thread = threading.Thread(target=cancel)
            thread.start()
            barrier.wait()
            try:
                commit_dispatch()
                dispatched = True
            except LaunchCancelled:
                dispatched = False
            thread.join(timeout=2)
            assert not thread.is_alive()
            assert result == [not dispatched]


def test_token_does_not_interrupt_unrelated_work_on_another_thread():
    control = LaunchCancellation()
    with control.preparing("one"):
        control.request({"review_id": "one"})
        results = []
        def unrelated():
            checkpoint()
            results.append("safe")
        thread = threading.Thread(target=unrelated)
        thread.start(); thread.join(timeout=2)
        assert results == ["safe"]
        with pytest.raises(LaunchCancelled): checkpoint()
