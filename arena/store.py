"""Private SQLite classroom state and atomically written public replays."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid


class Store:
    def __init__(self, data_dir=None):
        self.directory = Path(data_dir or os.environ.get("POD_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.replay_dir = self.directory / "replays"
        self.replay_dir.mkdir(exist_ok=True)
        self.path = self.directory / "classroom.sqlite3"
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY, alias TEXT NOT NULL, alias_key TEXT UNIQUE NOT NULL,
                    code TEXT NOT NULL, claim_token TEXT NOT NULL, version INTEGER NOT NULL,
                    submitted_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS replays (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
                    created_at REAL NOT NULL, winner_alias TEXT);
            """)
            row = db.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()
            self.new_installation = row is None
            if row is None:
                token = os.environ.get("POD_ADMIN_TOKEN") or secrets.token_urlsafe(32)
                db.execute("INSERT INTO config VALUES ('admin_token', ?)", (json.dumps(token),))
                self._set(db, "session", self.initial_session())
                self._set(db, "job", self.initial_job())
            self.admin_token = json.loads(db.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()[0])
        # Never keep a stale worker claim after a process restart.
        job = self.get("job", self.initial_job())
        if job["status"] == "running":
            job.update(status="failed", message="Job interrupted by server restart.", error="Server restarted; reset or retry the competition.")
            self.update(job=job)
            active = self.get("active_replay_id")
            if active:
                replay = self.read_replay(active)
                if replay and replay.get("status") == "running":
                    replay["status"] = "interrupted"
                    self.write_replay(active, replay)

    @staticmethod
    def initial_session():
        return {"status": "waiting", "deadline": None, "duration_seconds": 7200}

    @staticmethod
    def initial_job():
        return {"status": "idle", "phase": None, "completed": 0, "total": 0, "message": ""}

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _set(db, key, value):
        db.execute("INSERT INTO config(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, allow_nan=False)))

    def get(self, key, default=None):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def update(self, **values):
        with self.lock, self.connection() as db:
            for key, value in values.items():
                self._set(db, key, value)

    def submissions(self, private=False):
        columns = "*" if private else "id,alias,version,submitted_at"
        with self.lock, self.connection() as db:
            return [dict(row) for row in db.execute(f"SELECT {columns} FROM submissions ORDER BY submitted_at,id")]

    def submit(self, alias, code, claim_token=None):
        with self.lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM submissions WHERE alias_key=?", (alias.casefold(),)).fetchone()
            if row:
                if not claim_token or not secrets.compare_digest(row["claim_token"].encode("utf-8"), claim_token.encode("utf-8", errors="replace")):
                    raise PermissionError("This alias is already claimed. Use its original claim token to update it.")
                entry_id, token, version = row["id"], row["claim_token"], row["version"] + 1
                db.execute("UPDATE submissions SET alias=?,code=?,version=?,submitted_at=? WHERE id=?", (alias, code, version, time.time(), entry_id))
            else:
                if db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] >= 60:
                    raise OverflowError("The classroom already has 60 submissions.")
                entry_id, token, version = str(uuid.uuid4()), secrets.token_urlsafe(32), 1
                db.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?)", (entry_id, alias, alias.casefold(), code, token, version, time.time()))
            return {"id": entry_id, "alias": alias, "claim_token": token, "version": version}

    def seed(self, entries):
        with self.lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]:
                raise ValueError("Demo requires an empty classroom.")
            for alias, code in entries:
                db.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?)", (str(uuid.uuid4()), alias, alias.casefold(), code, secrets.token_urlsafe(32), 1, time.time()))

    @staticmethod
    def valid_id(value):
        try:
            return str(uuid.UUID(value)) == value
        except (ValueError, TypeError, AttributeError):
            return False

    def add_replay(self, replay_id, title, kind):
        if not self.valid_id(replay_id):
            raise ValueError("Invalid replay ID")
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO replays VALUES (?,?,?,?,NULL)", (replay_id, title, kind, time.time()))

    def write_replay(self, replay_id, replay):
        if not self.valid_id(replay_id):
            raise ValueError("Invalid replay ID")
        # Serialize before replacing so an interrupted write never damages a replay.
        payload = json.dumps(replay, allow_nan=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError("Replay exceeds the storage limit")
        with self.lock:
            target = self.replay_dir / f"{replay_id}.json"
            temporary = target.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)

    def read_replay(self, replay_id):
        if not self.valid_id(replay_id):
            return None
        with self.lock:
            try:
                return json.loads((self.replay_dir / f"{replay_id}.json").read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None

    def finish_replay(self, replay_id, winner_alias):
        with self.lock, self.connection() as db:
            db.execute("UPDATE replays SET winner_alias=? WHERE id=?", (winner_alias, replay_id))

    def replays(self):
        with self.lock, self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM replays ORDER BY created_at,id")]

    def reset(self):
        with self.lock, self.connection() as db:
            db.execute("DELETE FROM submissions")
            db.execute("DELETE FROM replays")
            db.execute("DELETE FROM config WHERE key != 'admin_token'")
            self._set(db, "session", self.initial_session())
            self._set(db, "job", self.initial_job())
            for path in self.replay_dir.glob("*.json"):
                path.unlink(missing_ok=True)
            for path in self.replay_dir.glob("*.tmp"):
                path.unlink(missing_ok=True)
