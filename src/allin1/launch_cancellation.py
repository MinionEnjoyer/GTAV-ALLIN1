"""Cooperative, review-scoped cancellation; never terminates a GTA process."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock


class LaunchCancelled(Exception):
    """Not an optional-preview error: must unwind all the way to the launch."""


_current = ContextVar("launcher_launch_cancellation", default=None)


class LaunchCancellation:
    def __init__(self):
        self._lock = Lock()
        self._review = None
        self._requested = False
        self._dispatched = False

    @contextmanager
    def preparing(self, review_id):
        with self._lock:
            if self._review is not None:
                raise ValueError("Another launch is already preparing")
            self._review, self._requested, self._dispatched = review_id, False, False
        token = _current.set(self)
        try:
            yield
        finally:
            _current.reset(token)
            with self._lock:
                self._review = None

    def status(self):
        with self._lock:
            return {"launch_review_id": self._review,
                    "cancellable": self._review is not None and not self._dispatched and not self._requested,
                    "cancel_requested": self._review is not None and self._requested}

    def request(self, payload):
        if set(payload) != {"review_id"} or not isinstance(payload["review_id"], str) or not payload["review_id"]:
            raise ValueError("Cancel launch requires the active review_id")
        with self._lock:
            if payload["review_id"] != self._review:
                return {"status": "not_active", "accepted": False}
            if self._dispatched:
                return {"status": "already_dispatched", "accepted": False}
            self._requested = True
            return {"status": "requested", "accepted": True}

    def check(self, *, dispatch=False):
        # One lock decides the cancellation/OS-launch race. After dispatch the
        # cancel path cannot kill GTA or claim a launch was prevented.
        with self._lock:
            if self._requested:
                raise LaunchCancelled("Launch cancelled. GTA was not started.")
            if dispatch:
                self._dispatched = True


def checkpoint():
    if control := _current.get():
        control.check()


def commit_dispatch():
    if control := _current.get():
        control.check(dispatch=True)
