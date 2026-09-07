import threading
import pytest
from allin1.preview_render_control import PreviewRenderControl
from allin1.preview_render_pool import ordered_results


@pytest.fixture
def control(monkeypatch):
    from allin1 import preview_render_control as module
    monkeypatch.setattr(module.os, 'cpu_count', lambda: 32)
    monkeypatch.setattr(module, 'available_memory', lambda: 24 * 2**30)
    return PreviewRenderControl()


def test_increase_while_first_render_is_busy_and_decrease_drains(control):
    entered = [threading.Event() for _ in range(4)]
    release = [threading.Event() for _ in range(4)]
    result, errors = [], []
    def operation(i):
        stamp = control.started()
        entered[i].set()
        try:
            assert release[i].wait(5)
            return i
        finally:
            control.finished(1, False, stamp)
    def run():
        try:
            with control.session('review'), control.rendering():
                with ordered_results(range(4), operation, control) as rows:
                    result.extend(rows)
        except BaseException as e: errors.append(e)
    thread = threading.Thread(target=run); thread.start()
    try:
        assert entered[0].wait(3)
        assert control.status()['workers'] == 1
        assert not entered[1].is_set()
        control.request({'review_id':'review','workers':2})
        assert entered[1].wait(3)  # Must not wait for the first render to finish.
        control.request({'review_id':'review','workers':1})
        assert control.status()['active'] == 2  # Decrease never kills active work.
        release[0].set(); release[1].set()
        assert entered[2].wait(3)
        assert not entered[3].wait(.2)
        release[2].set()
        assert entered[3].wait(3)
    finally:
        for event in release: event.set()
        thread.join(6)
    assert not thread.is_alive() and not errors
    assert result == [(i,i) for i in range(4)]
    assert control.status()['active'] == 0 and not control.status()['enabled']
    with pytest.raises(ValueError): control.request({'review_id':'review','workers':2})


@pytest.mark.parametrize('count', [0,9,True,2.0,'2',None])
def test_invalid_count_never_changes_limit(control, count):
    with control.session('review'), control.rendering():
        with pytest.raises(ValueError): control.request({'review_id':'review','workers':count})
        assert control.limit() == 1


def test_eight_workers_are_supported_but_cpu_cap_remains(control, monkeypatch):
    with control.session('review'), control.rendering():
        assert control.status()['max_workers'] == 8
        assert control.status()['recommended_workers'] == 8
        control.request({'review_id': 'review', 'workers': 8})
        assert control.limit() == 8
    monkeypatch.setattr('allin1.preview_render_control.os.cpu_count', lambda: 8)
    with control.session('small'), control.rendering():
        assert control.limit() == 1 and control.status()['max_workers'] == 3
        with pytest.raises(ValueError, match='CPU budget'):
            control.request({'review_id': 'small', 'workers': 8})


def test_scheduler_runs_eight_concurrent_workers(control):
    gate = threading.Barrier(8)
    def operation(item):
        stamp = control.started()
        try:
            gate.wait(timeout=5)
            return item
        finally:
            control.finished(1, False, stamp)
    with control.session('review'), control.rendering():
        control.request({'review_id': 'review', 'workers': 8})
        with ordered_results(range(8), operation, control) as results:
            assert list(results) == [(i, i) for i in range(8)]
        assert control.status()['active'] == 0 and control.status()['samples'] == 8


def test_warnings_use_successful_stable_samples_and_disclose_uncertainty(control, monkeypatch):
    with control.session('review'), control.rendering():
        for _ in range(3): control.finished(10, False, control.started())
        transition = control.started()
        control.request({'review_id':'review','workers':2})
        control.finished(999, False, transition)
        assert control.status()['samples'] == 0
        for _ in range(3): control.finished(20, False, control.started())
        control.finished(99, True, control.started())
        snapshot = control.status()
        assert snapshot['samples'] == 3 and snapshot['median_seconds'] == 20
        assert any('25%' in w and 'complexity' in w for w in snapshot['warnings'])
        assert any('VRAM is not measured' in w for w in snapshot['warnings'])
        assert any('1 render(s) failed' in w for w in snapshot['warnings'])
        monkeypatch.setattr('allin1.preview_render_control.available_memory', lambda: 3*2**30)
        assert any('4 GiB' in w for w in control.status()['warnings'])
        assert control.status()['recommended_workers'] == 1
        control.request({'review_id':'review','workers':3})  # Advisory, not a hidden cap.
        monkeypatch.setattr('allin1.preview_render_control.available_memory', lambda: 1*2**30)
        with pytest.raises(ValueError): control.request({'review_id':'review','workers':4})
        control.request({'review_id':'review','workers':1})
    with control.session('next'), control.rendering():
        assert control.status()['workers'] == 1 and control.status()['samples'] == 0
        with pytest.raises(ValueError): control.request({'review_id':'review','workers':1})
