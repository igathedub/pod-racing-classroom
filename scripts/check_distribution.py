"""Check the staged Git source excludes local classroom data and live secrets.

Run after `git add`: uv run python scripts/check_distribution.py
Does not print or export secrets, and does not execute submitted code.
"""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {"data", "artifacts", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}


def main() -> None:
    paths = subprocess.run(["git", "ls-files", "--cached", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    files = [path.decode("utf-8") for path in paths if path]
    if not files:
        raise SystemExit("No staged source files to verify. Run git add first.")
    tokens = set()
    database = ROOT / "data" / "classroom.sqlite3"
    if database.exists():
        with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
            row = connection.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()
            if row:
                tokens.add(json.loads(row[0]))
            tokens.update(row[0] for row in connection.execute("SELECT claim_token FROM submissions"))
    for name in files:
        path = Path(name)
        if FORBIDDEN.intersection(path.parts) or path.name == ".env" or path.suffix in {".sqlite3", ".sqlite", ".db", ".pyc"}:
            raise SystemExit(f"Private/generated file is staged: {name}")
        # Inspect the exact Git blob rather than the worktree, including CRLF normalization.
        body = subprocess.run(["git", "show", ":" + name], cwd=ROOT, capture_output=True, check=True).stdout
        if any(token.encode("utf-8") in body for token in tokens if token):
            raise SystemExit(f"A live classroom secret appears in staged source: {name}")
    print(json.dumps({"staged_source_files": len(files), "private_paths": "excluded", "live_teacher_and_claim_tokens": "excluded"}, indent=2))


if __name__ == "__main__":
    main()
