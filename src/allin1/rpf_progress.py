"""Advisory workload timing, never authority to cancel or repeat archive writes."""
from __future__ import annotations

from threading import RLock
import logging
import time

SETUP_ALLOWANCE_SECONDS = 120
SECONDS_PER_ACTION = 5
SLOW_ACTION_SECONDS = 120


class RpfProgress:
    """One reviewed operation's helper-call counters, shared with its heartbeat."""

    def __init__(self, progress, *, clock=time.monotonic):
        self.progress, self.clock = progress, clock
        self.lock = RLock()
        self.started_at = clock()
        self.active_since = None
        self.estimated = self.completed = self.entries = self.percentage = 0
        self.message = "Preparing RPF work"

    def plan(self, actions: int, entries: int = 0):
        with self.lock:
            self.estimated += actions
            self.entries = max(self.entries, entries)
        self.publish()

    def start(self, command: str, entry: str, phase: str | None = None):
        labels = {"extract-exact-entry": "Reading", "extract-exact-nested-entry": "Reading",
                  "replace-entry": "Replacing", "replace-exact-nested-entry": "Replacing",
                  "delete-entry": "Removing", "register-dlc": "Registering DLC",
                  "unregister-dlc": "Unregistering DLC"}
        with self.lock:
            # Rollback and resource canonicalization may add work beyond the plan.
            self.estimated = max(self.estimated, self.completed + 1)
            self.active_since = self.clock()
            self.message = f"{phase or labels.get(command, 'Processing')} RPF: {entry}"
        self.publish()

    def finish(self):
        with self.lock:
            self.completed += 1
            self.active_since = None
        self.publish()

    def snapshot(self):
        with self.lock:
            if not self.estimated:
                return None
            elapsed = max(0, int(self.clock() - self.started_at))
            active = 0 if self.active_since is None else max(0, int(self.clock() - self.active_since))
            budget = SETUP_ALLOWANCE_SECONDS + self.estimated * SECONDS_PER_ACTION
            return {"estimated_actions": self.estimated, "completed_actions": self.completed,
                    "entries": self.entries, "elapsed_seconds": elapsed,
                    "budget_seconds": budget, "active_seconds": active,
                    "slow_action": active >= SLOW_ACTION_SECONDS,
                    "budget_exceeded": elapsed >= budget}

    def publish(self):
        with self.lock:
            if not self.estimated:
                return
            # Extra work must not move the bar backwards or claim receipt commit.
            self.percentage = max(self.percentage, min(99, 100 * self.completed // self.estimated))
            percentage, message = self.percentage, self.message
        try:
            self.progress(percentage, message)
        except Exception:
            logging.getLogger(__name__).warning("RPF progress reporting failed; archive operation continues", exc_info=True)
