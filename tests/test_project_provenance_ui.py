"""Public project provenance is visible and translated in every platform view."""
import pytest
from playwright.sync_api import expect
from test_moderation_ui import moderation_browser

REPOSITORY = 'https://github.com/igathedub/pod-racing-classroom'


@pytest.mark.parametrize('base', ['', '/backup'])
@pytest.mark.parametrize('view', ['/', '/teacher', '/projector'])
@pytest.mark.parametrize('width', [1440, 390])
def test_repository_link_and_codeweek_credit_are_visible_and_translated(tmp_path, monkeypatch, base, view, width):
    with moderation_browser(tmp_path, monkeypatch, base) as (_, _, context, errors, deletes):
        page = context.new_page()
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto('https://classroom.test' + base + view + '?lang=en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        footer = page.locator('.site-footer')
        link = footer.locator('a[href="' + REPOSITORY + '"]')
        expect(link).to_have_count(1)
        expect(link).to_be_visible()
        expect(link).to_have_text('Source code on GitHub')
        assert link.get_attribute('target') == '_blank'
        assert {'noopener', 'noreferrer'} <= set(link.get_attribute('rel').split())
        expect(footer).to_contain_text('Made for Codeweek 2026 in Wiesbaden.')
        page.locator('#language-switch').select_option('de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        expect(link).to_have_text('Quellcode auf GitHub')
        expect(footer).to_contain_text('Entwickelt für die Codeweek 2026 in Wiesbaden.')
        expect(link).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors and not deletes
