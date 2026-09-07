import threading
import time
import pytest
from allin1.preview_render_pool import ordered_results, worker_limit
from allin1.launch_cancellation import LaunchCancellation, LaunchCancelled, checkpoint


@pytest.mark.parametrize('cpus,gib,expected', [(32,24,8),(32,20,8),(64,64,8),(16,24,7),(32,12,4),(32,10,3),(8,8,2),(2,32,1),(32,2,1),(None,20,1),(32,None,1)])
def test_budget_keeps_cpu_and_memory_headroom(cpus,gib,expected):
    assert worker_limit(cpus,None if gib is None else gib*2**30)==expected


def test_every_run_starts_with_one_worker_even_with_spare_memory(monkeypatch):
    from allin1 import preview_render_pool as pool
    monkeypatch.setattr(pool.os,'cpu_count',lambda:32)
    monkeypatch.setattr(pool,'available_memory',lambda:16*2**30)
    assert pool.render_workers()==1
    monkeypatch.setattr(pool,'available_memory',lambda:2*2**30)
    assert pool.render_workers()==1


@pytest.mark.parametrize('threads',[0,9,True,'8',None])
def test_invalid_blender_thread_budget_is_rejected(threads):
    from allin1.preview_render_pool import blender_threads
    with pytest.raises(ValueError):blender_threads({'render_threads':threads})


def test_parallel_work_is_bounded_ordered_and_joined():
    lock=threading.Lock(); state={'active':0,'peak':0}; gate=threading.Barrier(3)
    def operation(item):
        with lock:
            state['active']+=1;state['peak']=max(state['peak'],state['active'])
        try:
            gate.wait(timeout=3)
            return item*2
        finally:
            with lock: state['active']-=1
    with ordered_results(range(6),operation,3) as results:
        assert list(results)==[(i,i*2) for i in range(6)]
    assert state=={'active':0,'peak':3}


def test_cancellation_reaches_running_workers_and_no_worker_survives():
    cancel=LaunchCancellation(); entered=threading.Barrier(3); stopped=[]
    def operation(item):
        try:
            entered.wait(timeout=3)
            if item==0:cancel.request({'review_id':'test'})
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                checkpoint();time.sleep(.01)
            pytest.fail('Worker lost cancellation context')
        finally:stopped.append(item)
    with cancel.preparing('test'):
        with pytest.raises(LaunchCancelled):
            with ordered_results(range(20),operation,3) as results:
                list(results)
    assert sorted(stopped)==[0,1,2]
