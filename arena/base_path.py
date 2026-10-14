"""Strict opt-in URL namespace configuration."""
import os
import re


def configured_base_path():
    value = os.environ.get('POD_BASE_PATH', '')
    if value and not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+', value):
        raise ValueError('POD_BASE_PATH must be empty or slash-separated ASCII letters, digits, underscores and hyphens, without a trailing slash.')
    return value


def application_path(scope):
    """Route path inside an ASGI mount, not the external URL pathname."""
    path = scope["path"]
    root = scope.get("root_path", "")
    if root and (path == root or path.startswith(root + "/")):
        return path[len(root):] or "/"
    return path
