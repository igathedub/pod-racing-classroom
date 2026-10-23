"""Shared completion wait for trusted synthetic tournament tests only."""
import time


def wait_tournament(app, *, require_success=True, monotonic=None):
    """Join until exit, with 10s no-progress and a fixed 120s absolute limit.

    Only a new completed-race high-water mark renews the no-progress budget.
    Observations at a deadline are allowed for progress or completion, but an
    alive worker without progress gets no further join at the exact deadline.
    Check observation time after store reads, before renewal or terminal success;
    when both bounds are exceeded, report the absolute bound first.
    120s gives trusted synthetic jobs headroom for durable Windows writes without
    allowing an endlessly progressing worker (or changing total) to wait forever.
    It is a test budget, not a production SLA or a per-race/total-derived limit.
    Teardown opts out of success checks so intentionally failed jobs can clean up.
    """
    def summary(job):
        return f"status={job['status']} completed={job['completed']} total={job['total']}"

    monotonic = monotonic or time.monotonic
    worker = app.state.tournament.worker
    job = app.state.store.get('job')
    completed = job['completed']
    started = monotonic()
    deadline = started + 10
    absolute_deadline = started + 120
    while worker.is_alive():
        now = monotonic()
        assert now < absolute_deadline, f'Tournament exceeded absolute bound of 120 seconds: {summary(job)}'
        remaining = deadline - now
        assert remaining > 0, f'Tournament made no progress for 10 seconds: {summary(job)}'
        worker.join(min(1.0, remaining, absolute_deadline - now))
        job = app.state.store.get('job')
        now = monotonic()
        assert now <= absolute_deadline, f'Tournament exceeded absolute bound of 120 seconds: {summary(job)}'
        assert now <= deadline, f'Tournament made no progress for 10 seconds: {summary(job)}'
        if job['completed'] > completed:
            completed = job['completed']
            deadline = now + 10
    job = app.state.store.get('job')
    now = monotonic()
    assert now <= absolute_deadline, f'Tournament exceeded absolute bound of 120 seconds: {summary(job)}'
    assert now <= deadline, f'Tournament made no progress for 10 seconds: {summary(job)}'
    if require_success:
        assert job['status'] == 'finished', summary(job)
        assert job['completed'] == job['total'], summary(job)
