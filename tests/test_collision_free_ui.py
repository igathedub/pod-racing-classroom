"""Real Chromium playback contracts; synthetic, isolated archives only."""
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from test_moderation_ui import moderation_browser


def seed_replays(store, collisions):
    entries = [{key: entry[key] for key in ('id', 'alias')} for entry in store.submissions()[:2]]
    champion = entries[0]
    ids = {}
    for kind in ('qualification', 'final'):
        replay_id = str(uuid4())
        ids[kind] = replay_id
        frames = []
        for turn in (0, 1):
            frames.append({'turn': turn, 'pods': [
                {**entry, 'x': 1000 + turn * 100, 'y': 2000 + index * 900,
                 'vx': 100, 'vy': 0, 'angle': 0, 'next_checkpoint': 0,
                 'passed': turn, 'finished': bool(turn), 'disqualified': False,
                 'boost_available': True}
                for index, entry in enumerate(entries)]})
        replay = {'id': replay_id, 'status': 'finished', 'collisions': collisions,
                  'entries': entries, 'winner_id': champion['id'], 'laps': 2,
                  'track': {'id': 'synthetic', 'name': 'Fixture course',
                            'checkpoints': [[7000, 2000], [1000, 2000]]},
                  'frames': frames, 'results': entries}
        store.add_replay(replay_id, 'Final · 2 pods' if kind == 'final' else 'Fixture qualification', kind)
        store.write_replay(replay_id, replay)
        store.finish_replay(replay_id, champion['alias'])
    store.update(champion=champion, active_replay_id=ids['final'],
                 session={**store.initial_session(), 'status': 'finished'})
    return ids, champion


def seek(page, value):
    page.locator('#scrubber').evaluate("(input, value) => { input.value = value; input.dispatchEvent(new Event('input', {bubbles: true})); }", value)


@pytest.mark.parametrize('view', ['/', '/projector'])
@pytest.mark.parametrize('language', ['en', 'de'])
@pytest.mark.parametrize('collisions', [False, True], ids=['new-ghost-final', 'historical-contact-final'])
def test_champion_requires_final_metadata_and_playback_end(tmp_path, monkeypatch, view, language, collisions):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        store = app.state.store
        ids, champion = seed_replays(store, collisions)
        archives = {path.name: path.read_bytes() for path in store.replay_dir.glob('*.json')}
        sources = store.submissions(private=True)
        page = context.new_page()
        page.emulate_media(reduced_motion='reduce')
        page.goto('https://classroom.test/backup' + view + '?lang=' + language)
        page.wait_for_function('(language) => document.body.dataset.stateLanguage === language', arg=language)
        expect(page.locator('#scrubber')).to_be_enabled()
        expect(page.locator('#champion-label')).not_to_contain_text(champion['alias'])
        expect(page.locator('#replay-select')).not_to_contain_text('Winner:')
        expect(page.locator('#replay-select')).not_to_contain_text('Sieger:')
        expect(page.locator('#race-format')).to_contain_text(
            ('contact' if language == 'en' else 'Zusammenstöße') if collisions
            else ('ghosts' if language == 'en' else 'ohne Zusammenstöße'))
        seek(page, 1)
        expect(page.locator('#champion-label')).to_contain_text(champion['alias'])
        expect(page.locator('#winner-overlay')).to_be_visible()
        seek(page, 0)
        expect(page.locator('#champion-label')).not_to_contain_text(champion['alias'])
        page.locator('#replay-select').select_option(ids['qualification'])
        expect(page.locator('#race-heading')).to_have_text('Fixture qualification')
        expect(page.locator('#scrubber')).to_be_enabled()
        seek(page, 1)
        expect(page.locator('#winner-overlay')).to_be_visible()
        expect(page.locator('#champion-label')).not_to_contain_text(champion['alias'])
        assert store.submissions(private=True) == sources
        assert {path.name: path.read_bytes() for path in store.replay_dir.glob('*.json')} == archives
        assert not errors and not deletes


@pytest.mark.parametrize('protocol', ['legacy', 'checkpoint-only'])
@pytest.mark.parametrize('language', ['en', 'de'])
def test_student_guide_and_teacher_hint_agree_on_collision_free_racing(tmp_path, monkeypatch, protocol, language):
    monkeypatch.setenv('POD_INPUT_PROTOCOL', protocol)
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        rows = [{**entry, 'rank': index, 'completed_tracks': 3, 'total_turns': 30,
                 'disqualified': False} for index, entry in enumerate(app.state.store.submissions(), 1)]
        app.state.store.update(session={**app.state.store.initial_session(), 'status': 'qualified'}, leaderboard=rows)
        student = context.new_page()
        student.goto('https://classroom.test/backup/?lang=' + language)
        student.wait_for_function('(language) => document.body.dataset.stateLanguage === language', arg=language)
        student.locator('#student-panel .help-block').first.locator('summary').click()
        guide = student.locator('#student-panel .help-content').first
        expect(guide).to_contain_text(
            'Practice, qualification and final all run without collisions. Pods pass through each other.'
            if language == 'en' else
            'Testläufe, Qualifikation und Finale laufen immer ohne Kollisionen. Pods fahren durcheinander hindurch.')
        expect(guide).not_to_contain_text('collisions are unchanged')
        teacher = context.new_page()
        teacher.goto('https://classroom.test/backup/teacher?lang=' + language)
        teacher.wait_for_function('(language) => document.body.dataset.stateLanguage === language', arg=language)
        expect(teacher.locator('#final-hint')).to_contain_text('without collisions' if language == 'en' else 'ohne Kollisionen')
        assert not errors and not deletes
