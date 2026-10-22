"""Rendered numeric table headers must align with their numeric columns."""
import pytest
from playwright.sync_api import expect

from test_collision_free_ui import seek
from test_moderation_ui import moderation_browser
from test_three_track_final_ui import open_page, seed_series


@pytest.mark.parametrize('view', ['/teacher', '/', '/projector'])
@pytest.mark.parametrize('language', ['en', 'de'])
@pytest.mark.parametrize('width', [1440, 390])
def test_numeric_headers_match_values_in_all_three_rankings(tmp_path, monkeypatch, view, language, width):
    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        seed_series(app.state.store)
        archives = {path.name: path.read_bytes() for path in app.state.store.replay_dir.glob('*.json')}
        sources = app.state.store.submissions(private=True)
        context.set_default_timeout(5000)
        page = open_page(context, view, language)
        page.set_viewport_size({'width': width, 'height': 900})
        seek(page, 1)  # Reveal the current third final for student/projector.
        for mode in ('qualification', 'race', 'final'):
            page.locator('#tab-' + mode).click()
            expect(page.locator('#rankings tbody tr').first).to_be_visible()
            columns = page.locator('#rankings table').evaluate('''table => {
                const headers = [...table.querySelectorAll('thead th')];
                const cells = [...table.querySelector('tbody tr').cells];
                return cells.map((cell, index) => ({
                    numeric: cell.classList.contains('number'),
                    visible: getComputedStyle(cell).display !== 'none',
                    headerAlign: getComputedStyle(headers[index]).textAlign,
                    valueAlign: getComputedStyle(cell).textAlign,
                    headerPadding: getComputedStyle(headers[index]).paddingRight,
                    valuePadding: getComputedStyle(cell).paddingRight,
                    headerRight: headers[index].getBoundingClientRect().right,
                    valueRight: cell.getBoundingClientRect().right
                }));
            }''')
            numeric = [column for column in columns if column['numeric'] and column['visible']]
            assert numeric
            for column in numeric:
                assert column['headerAlign'] == column['valueAlign'] == 'right', (mode, column)
                assert column['headerPadding'] == column['valuePadding']
                assert abs(column['headerRight'] - column['valueRight']) < 0.1
            assert columns[1]['headerAlign'] == 'left'
            assert columns[1]['valueAlign'] in ('left', 'start')
        assert app.state.store.submissions(private=True) == sources
        assert {path.name: path.read_bytes() for path in app.state.store.replay_dir.glob('*.json')} == archives
        assert not errors and not deletes
