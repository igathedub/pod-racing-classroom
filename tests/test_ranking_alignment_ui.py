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
            columns = ranking_columns(page, mode)
            assert_columns_aligned(columns, mode)
        assert app.state.store.submissions(private=True) == sources
        assert {path.name: path.read_bytes() for path in app.state.store.replay_dir.glob('*.json')} == archives
        assert not errors and not deletes


def ranking_columns(page, mode):
    # Query, readiness check and measurement share one browser task. A locator
    # ElementHandle can be detached by a periodic ranking paint before evaluate.
    snapshot = page.wait_for_function('''mode => {
        const rankings = document.querySelector('#rankings');
        const table = rankings.querySelector('table');
        const row = table?.querySelector('tbody tr');
        if (rankings.getAttribute('aria-labelledby') !== `tab-${mode}` ||
            !table?.isConnected || !row || !row.getBoundingClientRect().height) return false;
        const headers = [...table.querySelectorAll('thead th')];
        const cells = [...row.cells];
        if (!cells.length || headers.length !== cells.length) return false;
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
    }''', arg=mode)
    try:
        return snapshot.json_value()
    finally:
        snapshot.dispose()


def assert_columns_aligned(columns, mode):
    numeric = [column for column in columns if column['numeric'] and column['visible']]
    assert numeric
    for column in numeric:
        assert column['headerAlign'] == column['valueAlign'] == 'right', (mode, column)
        assert column['headerPadding'] == column['valuePadding']
        assert abs(column['headerRight'] - column['valueRight']) < 0.1
    assert columns[1]['headerAlign'] == 'left'
    assert columns[1]['valueAlign'] in ('left', 'start')


@pytest.mark.parametrize('mode', ['race', 'final'])
def test_alignment_snapshot_survives_table_replacement(tmp_path, monkeypatch, mode):
    # Locator.evaluate resolves an ElementHandle, then evaluates in a separate
    # protocol call. Force the real renderer into that gap, without timing sleeps.
    from playwright._impl._locator import Locator

    with moderation_browser(tmp_path, monkeypatch) as (app, _, context, errors, deletes):
        seed_series(app.state.store)
        page = open_page(context, '/projector', 'en')
        seek(page, 1)
        page.locator('#tab-' + mode).click()
        expect(page.locator('#rankings tbody tr').first).to_be_visible()
        original_element_handle = Locator.element_handle
        detached = []

        async def resolve_then_render(locator, *args, **kwargs):
            handle = await original_element_handle(locator, *args, **kwargs)
            if locator._selector == '#rankings table':
                # Clicking the selected tab calls renderRankings/replaceChildren,
                # just as the application's recurring animation/state paints do.
                await locator._frame.evaluate('''() => {
                    document.querySelector('.ranking-tabs [aria-selected="true"]').click();
                }''')
                detached.append(await handle.evaluate('''table => ({
                    connected: table.isConnected,
                    align: getComputedStyle(table.querySelector('td.number')).textAlign
                })'''))
            return handle

        monkeypatch.setattr(Locator, 'element_handle', resolve_then_render)
        # Prove this seam reaches the observed browser symptom, not a fake style.
        assert page.locator('#rankings table').evaluate('table => table.isConnected') is False
        assert detached == [{'connected': False, 'align': ''}]
        assert_columns_aligned(ranking_columns(page, mode), mode)
        assert not errors and not deletes
