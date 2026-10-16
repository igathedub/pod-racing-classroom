"""Private SQLite classroom state and atomically written public replays."""
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

MAX_SUBMISSIONS = 100


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
        self._recover_moderation()
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
                if db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] >= MAX_SUBMISSIONS:
                    raise OverflowError(f"The classroom already has {MAX_SUBMISSIONS} submissions.")
                entry_id, token, version = str(uuid.uuid4()), secrets.token_urlsafe(32), 1
                db.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?)", (entry_id, alias, alias.casefold(), code, token, version, time.time()))
            return {"id": entry_id, "alias": alias, "claim_token": token, "version": version}

    def delete_submission(self, submission_id):
        """Remove one pilot and derived publications, never reset or rerun races."""
        if not self.valid_id(submission_id):
            raise ValueError("Invalid submission ID")
        with self.lock:
            self._recover_moderation()
            try:
                with self.connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    entry = db.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
                    if entry is None:
                        raise LookupError("Submission not found")
                    config = {row['key']: json.loads(row['value']) for row in db.execute("SELECT * FROM config")}
                    alias_key = entry['alias'].casefold()

                    def matches(row):
                        return row.get('id') == submission_id or str(row.get('alias', '')).casefold() == alias_key

                    updates = {}
                    for key in ('snapshot', 'leaderboard', 'finalists'):
                        rows = config.get(key)
                        if rows is not None:
                            if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('alias'), str) for row in rows):
                                raise ValueError("Invalid competition state")
                            updates[key] = [row for row in rows if not matches(row)]
                    if 'leaderboard' in updates:
                        updates['leaderboard'] = [{**row, 'rank': index} for index, row in enumerate(updates['leaderboard'], 1)]
                        if config.get('session', {}).get('status') == 'qualified':
                            updates['finalists'] = [{'id': row['id'], 'alias': row['alias']} for row in updates['leaderboard'] if not row.get('disqualified', False)][:5]
                    champion = config.get('champion')
                    if champion is not None:
                        if not isinstance(champion, dict):
                            raise ValueError("Invalid champion")
                        if matches(champion):
                            updates['champion'] = None
                    revision = config.get('moderation_revision', 0)
                    if type(revision) is not int or revision < 0:
                        raise ValueError("Invalid moderation revision")
                    revision += 1

                    # Validate every public archive before touching any files or rows.
                    # Include orphan archives and interrupted atomic-write files.
                    metadata = {row['id']: dict(row) for row in db.execute("SELECT * FROM replays")}
                    paths = {}
                    for pattern in ('*.json', '*.tmp'):
                        for path in self.replay_dir.glob(pattern):
                            paths.setdefault(path.stem, []).append(path)
                    removed = set()
                    for replay_id in sorted(metadata.keys() | paths.keys()):
                        if not self.valid_id(replay_id):
                            raise ValueError("Invalid stored replay ID")
                        meta = metadata.get(replay_id, {})
                        # With an archive present its structured pilot IDs are
                        # authoritative. A name can also be "Final", "finished"
                        # or the reference ghost's label; never match arbitrary
                        # protocol/status strings or another pilot's alias.
                        title = str(meta.get('title', '')).casefold()
                        if not paths.get(replay_id) and (
                                (meta.get('kind') == 'qualification' and
                                 (title == alias_key or title.startswith(alias_key + ' · ')))
                                or str(meta.get('winner_alias', '')).casefold() == alias_key):
                            removed.add(replay_id)
                        for path in paths.get(replay_id, []):
                            if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
                                raise ValueError("Invalid replay file")
                            replay = self._moderation_json(path.read_text(encoding='utf-8'))
                            self._validate_moderation_replay(replay, replay_id)
                            if self._replay_mentions(replay, submission_id, alias_key):
                                removed.add(replay_id)
                    for replay_id in removed:
                        for path in paths.get(replay_id, []):
                            staged = self._moderation_path(path)
                            if staged.exists() or staged.is_symlink():
                                raise ValueError("Conflicting moderation staging file")
                    if config.get('active_replay_id') in removed:
                        updates['active_replay_id'] = None
                    updates['moderation_revision'] = revision
                    db.execute("DELETE FROM submissions WHERE id=?", (submission_id,))
                    db.executemany("DELETE FROM replays WHERE id=?", [(key,) for key in sorted(removed)])
                    for key, value in updates.items():
                        self._set(db, key, value)
                    staged_ids = [key for key in sorted(removed) if key in paths]
                    if staged_ids:
                        self._write_moderation_journal(revision, staged_ids)
                    for replay_id in sorted(removed):
                        for path in paths.get(replay_id, []):
                            os.replace(path, self._moderation_path(path))
                    if staged_ids:
                        self._sync_replay_dir()
            except BaseException:
                # SQLite has rolled back. Restore staged archives before releasing
                # the lock; an interrupted restoration is retried on startup.
                self._recover_moderation()
                raise
            try:
                self._recover_moderation()
            except OSError:
                # Committed deletion stays invisible even if disk cleanup fails.
                # The durable journal retries cleanup on restart/next moderation.
                logging.getLogger(__name__).warning("Moderation committed; replay cleanup pending.")
            return {"deleted_id": submission_id, "removed_replays": sorted(removed), "moderation_revision": revision}

    def _sync_replay_dir(self):
        # Native Windows cannot open a directory for POSIX fsync. Journal file
        # writes are still flushed; production Linux containers use fsync below.
        if os.name == 'nt':
            return
        descriptor = os.open(self.replay_dir, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _moderation_path(path):
        return path.with_suffix('.moderating') if path.suffix == '.json' else path.with_suffix('.tmp.moderating')

    def _write_moderation_journal(self, revision, replay_ids):
        journal = self.replay_dir / '.moderation-journal'
        temporary = self.replay_dir / '.moderation-journal-writing'
        temporary.unlink(missing_ok=True)
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump({'revision': revision, 'replay_ids': replay_ids}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, journal)
        self._sync_replay_dir()

    def _recover_moderation(self):
        """SQLite's committed revision decides whether to restore or purge files.

        A synced journal precedes renames; synced renames precede DB commit.
        No replay payload or private submission data is copied into the journal.
        The service supports one process, as does Tournament's worker lock.
        """
        with self.lock:
            journal = self.replay_dir / '.moderation-journal'
            if not journal.exists() and not journal.is_symlink():
                return
            if journal.is_symlink() or not journal.is_file():
                raise ValueError("Invalid moderation journal")
            data = self._moderation_json(journal.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or set(data) != {'revision', 'replay_ids'}
                    or type(data['revision']) is not int or data['revision'] < 1
                    or not isinstance(data['replay_ids'], list)
                    or any(not self.valid_id(key) for key in data['replay_ids'])
                    or len(set(data['replay_ids'])) != len(data['replay_ids'])):
                raise ValueError("Invalid moderation journal")
            committed = self.get('moderation_revision', 0) >= data['revision']
            targets = [self.replay_dir / f'{key}{suffix}' for key in data['replay_ids'] for suffix in ('.json', '.tmp')]
            pairs = [(target, self._moderation_path(target)) for target in targets]
            # Preflight the entire journal before restoring/unlinking any path.
            for target, staged in pairs:
                if target.is_symlink() or staged.is_symlink():
                    raise ValueError("Invalid moderation recovery path")
                if staged.exists() and (not staged.is_file() or target.exists()):
                    raise ValueError("Conflicting moderation recovery files")
            for target, staged in pairs:
                if staged.exists():
                    if committed:
                        staged.unlink()
                    else:
                        os.replace(staged, target)
            self._sync_replay_dir()
            journal.unlink()
            self._sync_replay_dir()

    @staticmethod
    def _moderation_json(text):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate stored JSON key")
                result[key] = value
            return result

        def nonfinite(_):
            raise ValueError("Non-finite stored JSON")

        return json.loads(text, object_pairs_hook=unique_object, parse_constant=nonfinite)

    @staticmethod
    def _validate_moderation_replay(replay, replay_id):
        if not isinstance(replay, dict) or replay.get('id', replay_id) != replay_id:
            raise ValueError("Invalid replay")
        for key in ('entries', 'results', 'frames'):
            rows = replay.get(key)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Invalid replay rows")
        for row in replay['entries'] + replay['results']:
            if not isinstance(row.get('id'), str) or not isinstance(row.get('alias'), str):
                raise ValueError("Invalid replay pilot")
        for frame in replay['frames']:
            if not isinstance(frame.get('pods'), list) or any(not isinstance(pod, dict) for pod in frame['pods']):
                raise ValueError("Invalid replay frame")
            if any(not isinstance(pod.get('id'), str) or not isinstance(pod.get('alias'), str) for pod in frame['pods']):
                raise ValueError("Invalid replay pod")

    @staticmethod
    def _replay_mentions(value, submission_id, alias_key):
        if isinstance(value, dict):
            if value.get('id') == submission_id or value.get('winner_id') == submission_id:
                return True
            return any(Store._replay_mentions(item, submission_id, alias_key) for item in value.values())
        if isinstance(value, list):
            return any(Store._replay_mentions(item, submission_id, alias_key) for item in value)
        return False

    def claimed_submission(self, alias, claim_token):
        """Return a private submission only when its student ownership token matches."""
        with self.lock, self.connection() as db:
            row = db.execute("SELECT * FROM submissions WHERE alias_key=?", (alias.casefold(),)).fetchone()
            if not row or not claim_token or not secrets.compare_digest(
                row["claim_token"].encode("utf-8"), claim_token.encode("utf-8", errors="replace")
            ):
                raise PermissionError("The private claim token does not match this pilot.")
            return dict(row)

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
            db.execute("DELETE FROM config WHERE key NOT IN ('admin_token', 'moderation_revision')")
            self._set(db, "session", self.initial_session())
            self._set(db, "job", self.initial_job())
            for path in self.replay_dir.glob("*.json"):
                path.unlink(missing_ok=True)
            for path in self.replay_dir.glob("*.tmp"):
                path.unlink(missing_ok=True)
