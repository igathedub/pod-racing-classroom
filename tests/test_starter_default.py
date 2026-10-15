"""The requested Nadja solution is the exact default, without executing it."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from test_base_path import prefixed

EXPECTED_SHA256 = '4e9c5b1fa2ddff2733d7cd93d8fcbcaf5f72055a465568b1c48e74142d28f285'


class Editor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_editor = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'textarea' and dict(attrs).get('id') == 'code':
            self.in_editor = True

    def handle_data(self, data):
        if self.in_editor:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'textarea':
            self.in_editor = False


@pytest.mark.parametrize('base', ['', '/backup'])
def test_student_editor_contains_exact_requested_nadja_source(tmp_path, monkeypatch, base):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app) as client:
        response = client.get(base+'/?lang=de')
        assert response.status_code == 200
        editor = Editor()
        editor.feed(response.text)
        source = ''.join(editor.parts)
        assert 'BREMS_DISTANZ = 900' in source
        assert hashlib.sha256(source.encode('utf-8')).hexdigest() == EXPECTED_SHA256


@pytest.mark.parametrize('base', ['', '/backup'])
@pytest.mark.parametrize('language', ['de', 'en'])
def test_download_contains_exact_same_local_source(tmp_path, monkeypatch, base, language):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    expected = (Path(__file__).resolve().parents[1]/'examples/starters/05_Nadja.py').read_bytes()
    with TestClient(app) as client:
        response = client.get(base+'/api/starter?lang='+language)
        assert response.status_code == 200
        assert response.content.endswith(expected)
        assert 'starter.py' in response.headers['content-disposition']


def test_source_is_escaped_as_text_not_html(tmp_path, monkeypatch):
    from arena import app as app_module
    source = 'print(\'</textarea><script id="starter-injection">alert(1)</script>\')\n'
    monkeypatch.setattr(app_module, 'STARTER', source)
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH='', POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app) as client:
        response = client.get('/')
        assert '<script id="starter-injection">' not in response.text
        editor = Editor()
        editor.feed(response.text)
        assert ''.join(editor.parts) == source
