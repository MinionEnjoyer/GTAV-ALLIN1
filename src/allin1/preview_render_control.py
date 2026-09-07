"""Review-scoped live preview tuning. No process termination or game authority."""
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from statistics import median
from threading import Lock

from allin1.preview_render_pool import MAX_PREVIEW_WORKERS, available_memory, worker_limit
import os

_current = ContextVar('preview_render_control', default=None)


def current_control():
    return _current.get()


class PreviewRenderControl:
    def __init__(self):
        self._lock = Lock()
        self.review = None
        self.enabled = False
        self.requested = 1
        self.active = 0
        self.maximum = 1
        self.samples = defaultdict(lambda: deque(maxlen=12))
        self.failures = 0
        self.epoch = 0

    @contextmanager
    def session(self, review):
        with self._lock:
            if self.review is not None:
                raise ValueError('Another preview review is active')
            self.review, self.requested, self.active = review, 1, 0
            self.maximum = max(1, min(MAX_PREVIEW_WORKERS, ((os.cpu_count() or 2)-2)//2))
            self.samples.clear()
            self.failures = 0
            self.epoch += 1
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)
            with self._lock:
                self.review, self.enabled = None, False

    @contextmanager
    def rendering(self):
        with self._lock:
            self.enabled = True
            self.samples.clear()  # Do not compare weapons against vehicles/gear.
            self.epoch += 1
        try:
            yield
        finally:
            with self._lock:
                self.enabled = False

    def limit(self):
        with self._lock:
            return self.requested

    def request(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {'review_id', 'workers'}
                or not isinstance(payload['review_id'], str)
                or type(payload['workers']) is not int or not 1 <= payload['workers'] <= MAX_PREVIEW_WORKERS):
            raise ValueError(f'Preview workers requires review_id and an integer from 1 to {MAX_PREVIEW_WORKERS}')
        with self._lock:
            if not self.enabled or self.review != payload['review_id']:
                raise ValueError('Preview rendering is not active for this review')
            count = payload['workers']
            if count > self.maximum:
                raise ValueError('Worker count exceeds the CPU budget for this run')
            # Recheck memory when increasing; reducing never interrupts a render.
            free = available_memory()
            if count > self.requested and (free is None or free < 2*2**30):
                raise ValueError('Free RAM is unknown or below 2 GiB; cannot increase workers safely now')
            if count != self.requested:
                self.epoch += 1
            self.requested = count
        return {'status': 'accepted', 'preview_render': self.status()}

    def started(self):
        with self._lock:
            self.active += 1
            return self.requested, self.epoch

    def finished(self, seconds, failed, stamp):
        with self._lock:
            self.active -= 1
            self.failures += int(failed)
            # Do not attribute a render spanning a worker-count change to the
            # new setting. Failed/cache hits are not successful timing samples.
            if not failed and stamp == (self.requested, self.epoch):
                self.samples[self.requested].append(seconds)

    def status(self):
        free = available_memory()
        with self._lock:
            recent = list(self.samples[self.requested])
            baseline = list(self.samples[1])
            warnings = []
            recommended = worker_limit(os.cpu_count(), free)
            if recommended < self.maximum:
                warnings.append(f'Current free RAM recommends at most {recommended} worker(s). Higher counts risk paging or render failures.')
            if free is None:
                warnings.append('Free memory is unavailable; use one worker.')
            elif free < 4 * 2**30:
                warnings.append('Less than 4 GiB RAM is free. Reduce workers to avoid paging or render failures.')
            if self.requested > 1:
                warnings.append('Workers share the GPU. VRAM is not measured; more workers may be slower.')
            if self.requested > 1 and len(recent) >= 3 and len(baseline) >= 3 and median(recent) > 1.25 * median(baseline):
                warnings.append('Recent renders take over 25% longer per item than at one worker. Model complexity varies; consider reducing workers.')
            if self.failures:
                warnings.append(f'{self.failures} render(s) failed this run. Check the errors; resource contention is only one possible cause.')
            return dict(review_id=self.review, enabled=self.enabled,
                        workers=self.requested, active=self.active, max_workers=self.maximum,
                        recommended_workers=recommended,
                        samples=len(recent), median_seconds=round(median(recent), 2) if recent else None,
                        free_memory_gib=round(free / 2**30, 1) if free is not None else None,
                        warnings=warnings)
