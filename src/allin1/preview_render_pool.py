"""Bounded Blender concurrency; publication remains on the owning thread."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from contextvars import copy_context
import os

MAX_PREVIEW_WORKERS = 8

def available_memory():
    try:
        if os.name == 'nt':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
            value = Memory()
            value.length = ctypes.sizeof(value)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
                return value.available
    except (OSError, AttributeError):
        pass
    return None


def worker_limit(cpu_count, free_bytes):
    # At most eight processes, two logical cores each, 2 GiB per worker and
    # 4 GiB free reserve. Unknown/constrained machines stay serial.
    if not cpu_count or free_bytes is None:
        return 1
    return max(1, min(MAX_PREVIEW_WORKERS, (cpu_count - 2) // 2, int((free_bytes / 2**30 - 4) // 2)))


def render_workers():
    # Every run starts conservatively. A review-scoped control may raise this.
    return 1


def blender_threads(job):
    value = job.get('render_threads', max(1,min(8,(os.cpu_count() or 2)-2)))
    if type(value) is not int or not 1 <= value <= 8:
        raise ValueError('Invalid Blender thread budget')
    return value


@contextmanager
def ordered_results(items, operation, workers, *, heartbeat=lambda: None):
    """Only a small rolling window exists; propagate review cancellation to each.

    Workers never write shared cache/index files. Joining on exit ensures the
    launch cannot continue while an owned renderer is still alive.
    """
    from allin1.launch_cancellation import checkpoint
    dynamic = hasattr(workers, 'limit')
    limit = workers.limit if dynamic else lambda: workers
    with ThreadPoolExecutor(max_workers=workers.maximum if dynamic else workers, thread_name_prefix='preview') as pool:
        pending = deque()
        source = iter(items)
        exhausted = False
        def submit():
            nonlocal exhausted
            checkpoint()
            try:
                item = next(source)
            except StopIteration:
                exhausted = True
                return
            pending.append((item, pool.submit(copy_context().run, operation, item)))
        def results():
            while pending or not exhausted:
                checkpoint()
                while not exhausted and len(pending) < limit():
                    submit()
                if not pending:
                    break
                item, future = pending[0]
                try:
                    value = future.result(timeout=.25)
                except TimeoutError:
                    if future.done():
                        value = future.result()  # Propagate an operation's own timeout.
                    else:
                        heartbeat()
                        continue
                pending.popleft()
                checkpoint()
                yield item, value
        try:
            yield results()
        finally:
            for _, future in pending:
                future.cancel()
