"""Deterministic tournament wait contracts, without wall-clock sleeps."""
from types import SimpleNamespace

import pytest

from tournament_wait import wait_tournament


class ClockWorker:
    def __init__(self, advance, *, alive=True, **job):
        self.elapsed = 0.0
        self.joins = []
        self.advance = advance
        self.alive = alive
        self.job = {'status': 'running', 'completed': 0, 'total': 3, **job}
        self.app = SimpleNamespace(state=SimpleNamespace(
            tournament=SimpleNamespace(worker=self),
            store=SimpleNamespace(get=lambda key: dict(self.job))))

    def join(self, timeout):
        self.joins.append(timeout)
        self.elapsed += timeout
        self.advance(self)

    def is_alive(self):
        return self.alive

    def monotonic(self):
        return self.elapsed


def finish_slowly(worker):
    worker.job['completed'] = min(3, int(worker.elapsed // 6))
    if worker.job['completed'] == 3:
        worker.job['status'] = 'finished'
        worker.alive = False


def test_progress_beyond_old_whole_job_budget(monkeypatch):
    worker = ClockWorker(finish_slowly)
    monkeypatch.setattr('time.monotonic', worker.monotonic)
    wait_tournament(worker.app)
    assert worker.elapsed == 18.0
    assert max(worker.joins) <= 1.0


def test_completion_observed_after_absolute_deadline_still_fails():
    def finish_late(worker):
        worker.elapsed = 121
        worker.job.update(status='finished', completed=3)
        worker.alive = False

    worker = ClockWorker(finish_late)
    with pytest.raises(AssertionError, match='absolute.*120'):
        wait_tournament(worker.app, monotonic=worker.monotonic)


@pytest.mark.parametrize('require_success', [True, False])
@pytest.mark.parametrize('terminal', [False, True])
@pytest.mark.parametrize('overshoot', ['join', 'store'])
def test_observation_after_progress_deadline_cannot_renew_or_finish(
        overshoot, terminal, require_success):
    def advance(worker):
        if len(worker.joins) == 1:
            if overshoot == 'join':
                worker.elapsed = 11
            worker.job['completed'] = 1
        if terminal or len(worker.joins) > 1:
            worker.job.update(status='finished', completed=3)
            worker.alive = False

    worker = ClockWorker(advance)
    if overshoot == 'store':
        def read_job(key):
            if worker.joins:
                worker.elapsed = 11
            return dict(worker.job)
        worker.app.state.store.get = read_job
    with pytest.raises(AssertionError, match='no progress.*10'):
        wait_tournament(worker.app, require_success=require_success, monotonic=worker.monotonic)
    assert worker.elapsed == 11
    assert worker.joins == [1.0]


@pytest.mark.parametrize('require_success', [True, False])
def test_final_store_observation_after_progress_deadline_still_fails(require_success):
    def finish(worker):
        worker.job['status'] = 'finished'
        worker.alive = False

    worker = ClockWorker(finish, completed=3)
    reads = 0

    def read_job(key):
        nonlocal reads
        reads += 1
        if reads == 3:
            worker.elapsed = 11
        return dict(worker.job)

    worker.app.state.store.get = read_job
    with pytest.raises(AssertionError, match='no progress.*10'):
        wait_tournament(worker.app, require_success=require_success, monotonic=worker.monotonic)
    assert worker.elapsed == 11
    assert worker.joins == [1.0]


@pytest.mark.parametrize('require_success', [True, False])
@pytest.mark.parametrize('event', ['progress', 'completion', 'stalled'])
def test_exact_progress_deadline_allows_progress_or_completion_but_not_another_stalled_join(
        event, require_success):
    def advance(worker):
        if worker.elapsed == 10:
            if event == 'progress':
                worker.job['completed'] = 1
            elif event == 'completion':
                worker.job['status'] = 'finished'
                worker.alive = False
        elif worker.elapsed == 11:
            worker.job.update(status='finished', completed=3)
            worker.alive = False

    # Completion must also be accepted without a new high-water mark.
    worker = ClockWorker(advance, completed=3 if event == 'completion' else 0)
    if event == 'stalled':
        with pytest.raises(AssertionError, match='no progress.*10'):
            wait_tournament(worker.app, require_success=require_success, monotonic=worker.monotonic)
    else:
        wait_tournament(worker.app, require_success=require_success, monotonic=worker.monotonic)
    expected = 11 if event == 'progress' else 10
    assert worker.elapsed == expected
    assert worker.joins == [1.0] * expected


@pytest.mark.parametrize('require_success', [True, False])
def test_completion_observed_at_exact_absolute_deadline_is_allowed(require_success):
    def advance(worker):
        worker.job['completed'] += 1
        if worker.elapsed == 120:
            worker.job.update(status='finished', total=120)
            worker.alive = False

    worker = ClockWorker(advance)
    wait_tournament(worker.app, require_success=require_success, monotonic=worker.monotonic)
    assert worker.elapsed == 120
    assert worker.joins == [1.0] * 120


def test_infinite_progress_cannot_extend_absolute_deadline():
    def advance(worker):
        if worker.elapsed > 120:
            raise RuntimeError('wait exceeded fixed absolute budget')
        worker.job['completed'] += 1
        worker.job['total'] += 1000

    worker = ClockWorker(advance)
    with pytest.raises(AssertionError, match='absolute.*120'):
        wait_tournament(worker.app, monotonic=worker.monotonic)
    assert worker.elapsed == 120
    assert worker.joins == [1.0] * 120


@pytest.mark.parametrize('mode', ['stalled', 'message', 'status', 'rewound'])
def test_only_new_completed_high_water_mark_renews_budget(mode):
    def advance(worker):
        if mode == 'message':
            worker.job['message'] = str(worker.elapsed)
            worker.job['total'] += 1
        elif mode == 'status':
            worker.job['status'] = 'finished' if worker.elapsed % 2 else 'running'
        elif mode == 'rewound':
            worker.job['completed'] = int(worker.elapsed) % 2

    worker = ClockWorker(advance, completed=1)
    with pytest.raises(AssertionError, match='no progress'):
        wait_tournament(worker.app, monotonic=worker.monotonic)
    assert worker.elapsed == 10
    assert worker.joins == [1.0] * 10


@pytest.mark.parametrize('job', [
    {'status': 'failed', 'completed': 2},
    {'status': 'running', 'completed': 3},
    {'status': 'finished', 'completed': 2},
])
def test_success_wait_rejects_wrong_or_incomplete_terminal_job(job):
    worker = ClockWorker(lambda w: None, alive=False, **job)
    with pytest.raises(AssertionError):
        wait_tournament(worker.app, monotonic=worker.monotonic)
    assert worker.joins == []


def test_teardown_can_join_failed_job_without_requiring_success():
    def fail(worker):
        worker.alive = False
        worker.job['status'] = 'failed'

    worker = ClockWorker(fail)
    wait_tournament(worker.app, require_success=False, monotonic=worker.monotonic)
    assert worker.elapsed == 1
    assert not worker.is_alive()


def test_failure_diagnostics_include_only_safe_job_fields():
    worker = ClockWorker(lambda w: None, alive=False, status='failed', completed=2,
                         message='PRIVATE_MESSAGE', error='PRIVATE_SOURCE', token='PRIVATE_TOKEN')
    with pytest.raises(AssertionError) as exc:
        wait_tournament(worker.app, monotonic=worker.monotonic)
    text = str(exc.value)
    assert 'status=failed completed=2 total=3' in text
    assert 'PRIVATE' not in text


@pytest.mark.parametrize('filename,names', [
    ('test_checkpoint_protocol_api.py', ['test_archived_checkpoint_replays_keep_protocol_identifier']),
    ('test_moderation_ui.py', ['test_delete_updates_teacher_and_cached_projector_without_reset']),
    ('test_tournament.py', ['join']),
    ('test_api.py', ['api', 'wait']),
    ('test_class_access.py', ['test_access_changes_preserve_finished_replays_and_frozen_state']),
    ('test_class_access_ui.py', ['test_chromium_archival_replays_return_after_rejoin']),
    ('test_ui_layout.py', ['test_replay_controls_and_results_return_when_races_exist',
                           'test_twenty_results_do_not_stretch_the_student_editor']),
    ('test_three_track_api_contract.py', ['test_real_referee_final_series_through_http']),
])
def test_affected_tournament_wait_paths_use_shared_contract(filename, names):
    import ast
    from pathlib import Path

    tree = ast.parse(Path(__file__).with_name(filename).read_text(encoding='utf-8'))
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'tournament_wait'
               and any(alias.name == 'wait_tournament' for alias in node.names)
               for node in tree.body)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in names:
        calls = [node.func for node in ast.walk(functions[name]) if isinstance(node, ast.Call)]
        assert any(isinstance(call, ast.Name) and call.id == 'wait_tournament' for call in calls), name
        assert not any(isinstance(call, ast.Attribute) and call.attr == 'join' for call in calls), name
