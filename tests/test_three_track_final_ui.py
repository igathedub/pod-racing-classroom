"""Actual Chromium series UI; disposable Store fixtures, never execute bot source."""
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from test_collision_free_ui import seek, seed_replays
from test_moderation_ui import moderation_browser


FORMAT = 'three-track-total-time-v1'


def seed_series(store):
    store.submit('DNF Pilot', 'raise RuntimeError("must never execute")')
    entries = [{key: entry[key] for key in ('id', 'alias')} for entry in store.submissions()]
    tracks = [{'id': f'track-2026-{i + 3}', 'name': name,
               'checkpoints': [[7000, 2000], [1000, 2000]]}
              for i, name in enumerate(('Hairpin Run', 'Diamond Loop', 'Technical Loop'))]
    rows = [
        {**entries[0], 'rank': 1, 'completed_tracks': 3, 'disqualified': False,
         'race_times': [3.0011, 4.2222, 5.3333], 'total_time': 12.5566},
        {**entries[1], 'rank': 2, 'completed_tracks': 3, 'disqualified': False,
         'race_times': [1.1, 8.2, 6.3], 'total_time': 15.6},
        {**entries[3], 'rank': 3, 'completed_tracks': 2, 'disqualified': False,
         'race_times': [2.5, None, 5.5], 'total_time': None},
        {**entries[2], 'rank': 4, 'completed_tracks': 1, 'disqualified': True,
         'race_times': [1.5, None, None], 'total_time': None},
    ]
    ids = []
    for i, track in enumerate(tracks, 1):
        replay_id = str(uuid4())
        ids.append(replay_id)
        frames = [{'turn': turn, 'pods': [
            {**entry, 'x': 1000 + turn * 100, 'y': 2000 + index * 900,
             'vx': 100, 'vy': 0, 'angle': 0, 'next_checkpoint': 0, 'passed': turn,
             'finished': bool(turn), 'disqualified': False, 'boost_available': True}
            for index, entry in enumerate(entries)]} for turn in (0, 1)]
        winner = entries[0] if i < 3 else entries[1]
        replay = {'id': replay_id, 'status': 'finished', 'collisions': False,
                  'series_index': i, 'series_total': 3, 'entries': entries,
                  'winner_id': winner['id'], 'laps': 2, 'track': track,
                  'frames': frames, 'results': [entries[1], entries[0], *entries[2:]]}
        store.add_replay(replay_id, f'Final {i}/3 · {track["name"]} · 4 pods', 'final')
        store.write_replay(replay_id, replay)
        store.finish_replay(replay_id, winner['alias'])
    store.update(final_format=FORMAT, final_tracks=tracks, final_replay_ids=ids,
                 final_leaderboard=rows, champion=entries[0], active_replay_id=ids[-1],
                 leaderboard=[{**entry, 'rank': i, 'completed_tracks': 3, 'total_turns': 100 + i,
                               'disqualified': False} for i, entry in enumerate(entries, 1)],
                 session={**store.initial_session(), 'status': 'finished'},
                 job={'status': 'finished', 'phase': 'final', 'completed': 3, 'total': 3,
                      'message': 'Three-track final complete.'})
    return ids, entries, rows


def open_page(context, path, language):
    page = context.new_page()
    page.emulate_media(reduced_motion='reduce')
    page.goto('https://classroom.test/backup' + path + '?lang=' + language)
    page.wait_for_function('(lang) => document.body.dataset.stateLanguage === lang', arg=language)
    expect(page.locator('#scrubber')).to_be_enabled()
    return page


@pytest.mark.parametrize('language', ['en', 'de'])
def test_teacher_overall_table_is_separate_server_ranked_and_fractional(tmp_path, monkeypatch, language):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        ids, entries, rows = seed_series(app.state.store)
        archives = {p.name: p.read_bytes() for p in app.state.store.replay_dir.glob('*.json')}
        sources = app.state.store.submissions(private=True)
        page = open_page(context, '/teacher', language)
        expect(page.locator('#champion-label')).to_contain_text(entries[0]['alias'])
        page.get_by_role('tab', name='Final overall' if language == 'en' else 'Finale gesamt', exact=True).click()
        expect(page.locator('#rank-heading')).to_have_text('Final overall standings' if language == 'en' else 'Finale – Gesamtwertung')
        expect(page.locator('#rankings th')).to_have_text(['#', 'Pilot' if language == 'en' else 'Bot',
            'Final 1' if language == 'en' else 'Finale 1', 'Final 2' if language == 'en' else 'Finale 2',
            'Final 3' if language == 'en' else 'Finale 3', 'Total' if language == 'en' else 'Gesamt'])
        table_rows = page.locator('#rankings tbody tr')
        expect(table_rows).to_have_count(4)
        expect(table_rows.nth(0)).to_contain_text(entries[0]['alias'])
        expect(table_rows.nth(0)).to_contain_text('12.557' if language == 'en' else '12,557')
        expect(table_rows.nth(0)).to_contain_text('3.001' if language == 'en' else '3,001')
        expect(table_rows.nth(2).locator('td').last).to_have_text('DNF')
        expect(table_rows.nth(3).locator('td').last).to_have_text('DQ')
        expect(page.locator('#rank-scoring')).to_contain_text('simulated turns' if language == 'en' else 'Spielzüge')
        page.locator('#tab-qualification').click()
        expect(page.locator('#rankings th')).to_have_count(4)
        page.locator('#tab-race').click()
        seek(page, 1)
        expect(page.locator('#rankings tbody tr').first).to_contain_text(entries[1]['alias'])
        assert app.state.store.submissions(private=True) == sources
        assert {p.name: p.read_bytes() for p in app.state.store.replay_dir.glob('*.json')} == archives
        assert not errors and not deletes


@pytest.mark.parametrize('language', ['en', 'de'])
def test_three_track_help_controls_progress_and_turn_units(tmp_path, monkeypatch, language):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        seed_series(app.state.store)
        teacher = open_page(context, '/teacher', language)
        expect(teacher.locator('#run-final')).to_contain_text('three-track final' if language == 'en' else 'Drei-Strecken-Finale')
        expect(teacher.locator('#job-detail')).to_contain_text('Three-track final complete.' if language == 'en' else 'Das Drei-Strecken-Finale ist abgeschlossen.')
        app.state.store.update(session={**app.state.store.initial_session(), 'status': 'qualified'})
        expect(teacher.locator('#final-hint')).to_contain_text('three other tracks' if language == 'en' else 'drei anderen Strecken', timeout=7000)
        expect(teacher.locator('#final-hint')).to_contain_text('lowest total' if language == 'en' else 'kleinste Summe')
        student = open_page(context, '/', language)
        student.locator('#student-panel .help-block summary').first.click()
        guide = student.locator('#student-panel .help-content').first
        expect(guide).to_contain_text('Qualification times do not count' if language == 'en' else 'Qualifikationszeiten zählen nicht')
        seek(student, 1)
        expect(student.locator('#race-time')).to_have_text('1 turns' if language == 'en' else '1 Spielzüge')
        expect(student.locator('#race-heading')).to_contain_text('Final 3/3' if language == 'en' else 'Finale 3/3')
        expect(student.locator('#race-heading')).to_contain_text('Technical Loop' if language == 'en' else 'Technikrunde')
        expect(teacher.locator('#submission-duration')).to_have_attribute('min', '1')
        expect(teacher.locator('#submission-duration')).to_have_attribute('max', '1440')
        assert not errors and not deletes


def test_final_tab_keyboard_and_all_six_columns_survive_projector_mobile(tmp_path, monkeypatch):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        seed_series(app.state.store)
        page = open_page(context, '/projector', 'de')
        page.locator('#tab-qualification').click()
        page.locator('#tab-qualification').press('ArrowRight')
        expect(page.locator('#tab-race')).to_be_focused()
        page.locator('#tab-race').press('ArrowRight')
        expect(page.locator('#tab-final')).to_be_focused()
        expect(page.locator('#tab-final')).to_have_attribute('aria-selected', 'true')
        expect(page.locator('#rankings')).to_have_attribute('aria-labelledby', 'tab-final')
        page.locator('#tab-final').press('ArrowRight')
        expect(page.locator('#tab-qualification')).to_be_focused()
        page.locator('#tab-qualification').press('End')
        expect(page.locator('#tab-final')).to_be_focused()
        seek(page, 1)
        expect(page.locator('#rankings th').nth(3)).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        expect(page.locator('#rankings th').nth(3)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('#rankings').evaluate('(el) => el.scrollWidth > el.clientWidth')
        assert not errors and not deletes


@pytest.mark.parametrize('language', ['en', 'de'])
@pytest.mark.parametrize('view', ['/', '/projector'])
def test_incomplete_failed_or_running_series_never_reveals_overall(tmp_path, monkeypatch, view, language):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        store = app.state.store
        ids, entries, _ = seed_series(store)
        finished_job = store.get('job')
        for blocker in ('missing-replay', 'running', 'failed', 'unfinished-session', 'wrong-series-total'):
            store.update(final_replay_ids=ids[:2] if blocker == 'missing-replay' else ids,
                         session={**store.initial_session(), 'status': 'final' if blocker == 'unfinished-session' else 'finished'},
                         job={**finished_job, 'status': blocker if blocker in ('running', 'failed') else 'finished'})
            replay = store.read_replay(ids[-1])
            replay['series_total'] = 2 if blocker == 'wrong-series-total' else 3
            store.write_replay(ids[-1], replay)
            page = open_page(context, view, language)
            page.locator('#tab-final').click()
            seek(page, 1)
            expect(page.locator('#rankings table')).to_have_count(0)
            expect(page.locator('#champion-label')).not_to_contain_text(entries[0]['alias'])
            expect(page.locator('#winner-overlay .eyebrow')).not_to_have_text('FINAL OVERALL' if language == 'en' else 'FINALE – GESAMTWERTUNG')
            page.close()
        assert not errors and not deletes


@pytest.mark.parametrize('language', ['en', 'de'])
def test_no_valid_aggregate_finisher_is_explicit_only_at_series_finish(tmp_path, monkeypatch, language):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        ids, entries, rows = seed_series(app.state.store)
        for row in rows:
            row.update(completed_tracks=2, total_time=None, race_times=[1.1, None, 2.2])
        app.state.store.update(champion=None, final_leaderboard=rows)
        page = open_page(context, '/projector', language)
        page.locator('#tab-final').click()
        expect(page.locator('#rankings table')).to_have_count(0)
        seek(page, 1)
        expect(page.locator('#winner-name')).to_have_text('No overall champion' if language == 'en' else 'Kein Gesamtsieger')
        expect(page.locator('#champion-label')).to_have_text('No bot finished all three final tracks.' if language == 'en' else 'Kein Bot hat alle drei Finalstrecken beendet.')
        expect(page.locator('#rankings tbody tr')).to_have_count(4)
        assert not errors and not deletes


def test_rendering_untrusted_alias_track_and_rounded_totals_never_changes_server_rank(tmp_path, monkeypatch):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        store = app.state.store
        ids, entries, rows = seed_series(store)
        hostile = '<img src=x onerror=window.injected=true>'
        rows[0].update(alias=hostile, rank=7, total_time=10.00041)
        rows[1].update(rank=9, total_time=10.00049)
        replay = store.read_replay(ids[-1])
        replay['track']['name'] = hostile
        store.write_replay(ids[-1], replay)
        with store.connection() as db:
            db.execute('UPDATE replays SET title=? WHERE id=?', (f'Final 3/3 · {hostile} · 4 pods', ids[-1]))
        store.update(final_leaderboard=rows, champion={**entries[0], 'alias': hostile},
                     job={**store.get('job'), 'status': 'running'})
        archives = {p.name: p.read_bytes() for p in store.replay_dir.glob('*.json')}
        sources = store.submissions(private=True)
        page = open_page(context, '/teacher', 'de')
        page.locator('#tab-final').click()
        expect(page.locator('#rankings tbody tr').first).to_contain_text(hostile)
        expect(page.locator('#rankings tbody tr').nth(0).locator('td').first).to_have_text('7')
        expect(page.locator('#rankings tbody tr').nth(1).locator('td').first).to_have_text('9')
        expect(page.locator('#rankings tbody tr').nth(0).locator('td').last).to_have_text('10,000')
        expect(page.locator('#rankings tbody tr').nth(1).locator('td').last).to_have_text('10,000')
        expect(page.locator('#race-heading')).to_contain_text(hostile)
        expect(page.locator('#rankings img, #race-heading img, #champion-label img')).to_have_count(0)
        assert page.evaluate('window.injected === undefined')
        page.locator('#language-switch').select_option('en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        expect(page.locator('#rankings tbody tr').nth(0).locator('td').last).to_have_text('10.000')
        expect(page.locator('#rankings tbody tr').first).to_contain_text(hostile)
        assert store.submissions(private=True) == sources
        assert {p.name: p.read_bytes() for p in store.replay_dir.glob('*.json')} == archives
        assert not errors and not deletes


@pytest.mark.parametrize('language', ['en', 'de'])
@pytest.mark.parametrize('view', ['/', '/projector'])
def test_series_reveal_requires_last_current_replay_end_not_its_race_winner(tmp_path, monkeypatch, view, language):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        store = app.state.store
        old_ids, _ = seed_replays(store, True)
        ids, entries, _ = seed_series(store)
        stale_id = str(uuid4())
        stale_replay = store.read_replay(ids[-1])
        stale_replay.update(id=stale_id, winner_id=entries[0]['id'])
        store.add_replay(stale_id, 'Final 3/3 · Technical Loop · 4 pods', 'final')
        store.write_replay(stale_id, stale_replay)
        sources = store.submissions(private=True)
        archives = {p.name: p.read_bytes() for p in store.replay_dir.glob('*.json')}
        page = open_page(context, view, language)
        page.locator('#tab-final').click()
        expect(page.locator('#rankings table')).to_have_count(0)
        expect(page.locator('#champion-label')).not_to_contain_text(entries[0]['alias'])
        for replay_id in [*ids[:2], stale_id, old_ids['final'], old_ids['qualification']]:
            page.locator('#replay-select').select_option(replay_id)
            page.wait_for_function('(id) => document.querySelector("#replay-select").value === id && !document.querySelector("#scrubber").disabled', arg=replay_id)
            seek(page, 1)
            expect(page.locator('#winner-overlay')).to_be_visible()
            expect(page.locator('#champion-label')).not_to_contain_text(entries[0]['alias'])
            expect(page.locator('#rankings table')).to_have_count(0)
        page.locator('#replay-select').select_option(ids[-1])
        expect(page.locator('#race-heading')).to_contain_text('3/3')
        expect(page.locator('#scrubber')).to_be_enabled()
        expect(page.locator('#rankings table')).to_have_count(0)
        seek(page, 1)
        expect(page.locator('#champion-label')).to_contain_text(entries[0]['alias'])
        expect(page.locator('#rankings tbody tr')).to_have_count(4)
        expect(page.locator('#winner-name')).to_have_text(entries[0]['alias'])
        expect(page.locator('#winner-detail')).to_contain_text(entries[1]['alias'])
        expect(page.locator('#replay-select')).not_to_contain_text('Winner:')
        expect(page.locator('#replay-select')).not_to_contain_text('Sieger:')
        seek(page, 0)
        expect(page.locator('#rankings table')).to_have_count(0)
        expect(page.locator('#champion-label')).not_to_contain_text(entries[0]['alias'])
        assert store.submissions(private=True) == sources
        assert {p.name: p.read_bytes() for p in store.replay_dir.glob('*.json')} == archives
        assert not errors and not deletes
