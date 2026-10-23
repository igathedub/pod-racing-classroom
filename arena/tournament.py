"""One durable competition at a time; student code is only passed to the engine."""
from __future__ import annotations

from functools import partial
import math
import sqlite3
import threading
import time
import uuid

from .protocol import configured_input_protocol


class CompetitionError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message
        super().__init__(message)


def public_error(error):
    if not error:
        return None
    # Do not publish student exception text, source lines, or runner tracebacks.
    text = str(error).lower()
    for marker, message in (("timeout", "Bot exceeded its time limit."), ("malformed", "Bot returned an invalid command."), ("output", "Bot exceeded its output limit."), ("crash", "Bot process crashed.")):
        if marker in text:
            return message
    return "Bot disqualified."


def rank_results(snapshot, race_results, max_turns=700):
    """Invalid entries last; completed tracks, turns, DNF progress, alias then ID."""
    rows = []
    for entry in snapshot:
        results = race_results.get(entry["id"], [])
        completed = sum(bool(r.get("finished")) and not r.get("disqualified", False) for r in results)
        invalid = any(r.get("disqualified", False) for r in results)
        turns = sum(int(r.get("turns", max_turns)) if r.get("finished") and not r.get("disqualified") else max_turns for r in results)
        progress = 0.0
        for result in results:
            distance = float(result.get("distance_to_checkpoint", 20000))
            if not math.isfinite(distance):
                distance = 20000
            progress += max(0, int(result.get("passed", 0))) + max(0.0, 1.0 - min(20000.0, max(0.0, distance)) / 20000.0)
        errors = [public_error(r.get("error")) for r in results if r.get("error")]
        rows.append({"id": entry["id"], "alias": entry["alias"], "completed_tracks": completed,
                     "total_turns": turns, "progress": round(progress, 6), "disqualified": invalid,
                     **({"error": errors[0]} if errors else {})})
    rows.sort(key=lambda r: (r["disqualified"], -r["completed_tracks"], r["total_turns"], -r["progress"], r["alias"].casefold(), r["id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def valid_finish_time(result):
    """A simulated finish is numeric, finite and positive; no ceiling fallback."""
    value = result.get("finish_time")
    if not result.get("finished") or result.get("disqualified") or type(value) not in (int, float):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def rank_final_results(snapshot, race_results):
    """Rank only this series: three complete simulated times, never qualifiers."""
    rows = []
    for entry in snapshot:
        results = race_results.get(entry["id"], [])
        times = [valid_finish_time(result) for result in results]
        times += [None] * (3 - len(times))
        completed = sum(value is not None for value in times)
        invalid = any(result.get("disqualified", False) for result in results)
        total = sum(times) if completed == 3 and not invalid else None
        if total is not None and not math.isfinite(total):
            total = None
        errors = [public_error(result.get("error")) for result in results if result.get("error")]
        rows.append({"id": entry["id"], "alias": entry["alias"], "completed_tracks": completed,
                     "disqualified": invalid, "race_times": times, "total_time": total,
                     **({"error": errors[0]} if errors else {})})
    rows.sort(key=lambda row: (row["total_time"] is None, row["total_time"] or 0,
                               row["disqualified"], -row["completed_tracks"], row["alias"].casefold(), row["id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


class Tournament:
    def __init__(self, store, *, race_fn=None, tracks_fn=None, sandbox_fn=None, input_protocol=None):
        self.store = store
        self.input_protocol = configured_input_protocol(input_protocol)
        self.lock = threading.RLock()
        self.race_fn = race_fn
        self.tracks_fn = tracks_fn
        self.sandbox_fn = sandbox_fn
        self.worker = None
        self._practice_active = False
        self._sandbox_lock = threading.Lock()
        self._sandbox_cache = None
        self._sandbox_checked = 0.0

    def sandbox_status(self, *, refresh=False):
        # Polling browsers share a short cache; a job start forces fresh preflight.
        with self._sandbox_lock:
            if not refresh and self._sandbox_cache is not None and time.monotonic() - self._sandbox_checked < 5:
                return dict(self._sandbox_cache)
            result = self._probe_sandbox()
            self._sandbox_cache = result
            self._sandbox_checked = time.monotonic()
            return dict(result)

    def _probe_sandbox(self):
        try:
            if self.sandbox_fn:
                result = self.sandbox_fn()
            else:
                from .bots import sandbox_status
                result = sandbox_status()
            return {"available": bool(result["available"]), "detail": str(result["detail"]), "image": str(result["image"])}
        except Exception:
            return {"available": False, "detail": "Docker sandbox is unavailable. Start Docker and build the bot image.", "image": "pod-classroom-bot:local"}

    def session(self):
        session = self.store.get("session", self.store.initial_session())
        if session["status"] == "open" and session["deadline"] is not None and time.time() >= session["deadline"]:
            session = {**session, "status": "closed"}
        return session

    def busy(self):
        return self._practice_active or self.store.get("job", self.store.initial_job())["status"] == "running"

    def require_idle(self):
        if self.busy():
            raise CompetitionError(409, "A competition job is already running.")

    def start_session(self, duration):
        with self.lock:
            self.require_idle()
            if self.store.get("snapshot") is not None or self.session()["status"] not in ("waiting", "open", "closed"):
                raise CompetitionError(409, "Competition is frozen. Reset before starting a new session.")
            session = {"status": "open", "deadline": time.time() + duration, "duration_seconds": duration}
            self.store.update(session=session)
            return session

    def close_session(self):
        with self.lock:
            self.require_idle()
            session = self.session()
            if session["status"] not in ("waiting", "open", "closed"):
                raise CompetitionError(409, "Competition is already frozen.")
            session["status"] = "closed"
            self.store.update(session=session)
            return session

    def submit(self, alias, code, token):
        with self.lock:
            self.require_idle()
            if self.session()["status"] != "open" or self.store.get("snapshot") is not None:
                raise CompetitionError(409, "Submissions are closed or frozen.")
            try:
                return self.store.submit(alias, code, token)
            except PermissionError as exc:
                raise CompetitionError(409, str(exc)) from exc
            except OverflowError as exc:
                raise CompetitionError(409, str(exc)) from exc

    def delete_submission(self, submission_id):
        with self.lock:
            self.require_idle()
            if not self.store.valid_id(submission_id):
                raise CompetitionError(422, "Invalid submission ID.")
            try:
                return self.store.delete_submission(submission_id)
            except LookupError as exc:
                raise CompetitionError(404, "Submission not found.") from exc
            except (ValueError, OSError, sqlite3.Error, RecursionError) as exc:
                raise CompetitionError(409, "Submission could not be deleted safely. Check stored competition data and retry.") from exc

    def practice(self, alias, claim_token):
        """Run a student's saved bot against the reference ghost without publishing it."""
        with self.lock:
            self.require_idle()
            if self.session()["status"] != "open" or self.store.get("snapshot") is not None:
                raise CompetitionError(409, "Submissions are closed or frozen.")
            if not self.sandbox_status(refresh=True)["available"]:
                raise CompetitionError(503, "Docker sandbox unavailable; no code was executed and submissions were not frozen.")
            try:
                entry = self.store.claimed_submission(alias, claim_token)
            except PermissionError as exc:
                raise CompetitionError(409, str(exc)) from exc
            self._practice_active = True
        try:
            return self._practice_race({key: entry[key] for key in ("id", "alias", "code", "version")})
        finally:
            with self.lock:
                self._practice_active = False

    def _practice_race(self, entry):
        track = self._tracks()[0]
        reference = {"id": str(uuid.uuid4()), "alias": "Reference ghost", "code": "", "kind": "reference"}
        race_fn = self.race_fn
        if race_fn is None:
            from .engine import run_race
            race_fn = partial(run_race, input_protocol=self.input_protocol)
        try:
            result = race_fn([entry, reference], track, laps=2, max_turns=700)
        except Exception as exc:
            raise CompetitionError(503, "Practice run interrupted. Check the Docker sandbox and try again.") from exc
        raw_frames = result.get("frames", [])
        if len(raw_frames) > 701 or any(len(frame.get("pods", [])) > 5 for frame in raw_frames):
            raise CompetitionError(503, "Practice run interrupted. Check the Docker sandbox and try again.")
        result_fields = ("id", "alias", "place", "finished", "disqualified", "turns", "finish_time", "passed", "distance_to_checkpoint")
        results = [{**{key: row[key] for key in result_fields if key in row}, "finish_time": valid_finish_time(row), "error": public_error(row.get("error"))}
                   for row in result.get("results", [])]
        winner = next((row for row in results if row.get("id") == result.get("winner_id") and row.get("finished") and not row.get("disqualified")), None)
        return {"id": str(uuid.uuid4()), "kind": "practice", "title": f"Practice · {entry['alias']}", "track": track,
                "laps": 2, "max_turns": 700, "collisions": False, "status": "finished",
                "input_protocol": self.input_protocol,
                "winner_id": winner["id"] if winner else None,
                "entries": [{"id": item["id"], "alias": item["alias"]} for item in (entry, reference)],
                "frames": [self._safe_frame(frame) for frame in raw_frames], "results": results}

    def start_qualification(self):
        with self.lock:
            self.require_idle()
            session = self.session()
            job = self.store.get("job", self.store.initial_job())
            # A failed/interrupted qualification can restart only its immutable snapshot.
            existing = self.store.get("snapshot")
            if existing is not None and not (job["status"] == "failed" and job["phase"] == "qualification"):
                raise CompetitionError(409, "Qualifications have already been started. Reset for a new competition.")
            snapshot = existing if existing is not None else [{k: row[k] for k in ("id", "alias", "code", "version")} for row in self.store.submissions(private=True)]
            if not snapshot:
                raise CompetitionError(409, "Submit at least one bot before qualifying.")
            if not self.sandbox_status(refresh=True)["available"]:
                raise CompetitionError(503, "Docker sandbox unavailable; no code was executed and submissions were not frozen.")
            tracks = self.store.get("tracks") if existing is not None else None
            final_tracks = self.store.get("final_tracks") if existing is not None else None
            if tracks is None or final_tracks is None:
                collection = self._tracks(count=6)
                tracks = tracks if tracks is not None else collection[:3]
                final_tracks = final_tracks if final_tracks is not None else collection[3:6]
            job = {"status": "running", "phase": "qualification", "completed": 0, "total": len(snapshot) * len(tracks), "message": "Running qualification on three common tracks."}
            self.store.update(snapshot=snapshot, tracks=tracks, final_tracks=final_tracks, final_format="three-track-total-time-v1",
                              final_replay_ids=[], final_leaderboard=[], session={**session, "status": "qualifying"}, job=job,
                              leaderboard=[], finalists=[], champion=None, active_replay_id=None)
            self._launch(self._qualify, snapshot, tracks)
            return job

    def start_final(self):
        with self.lock:
            self.require_idle()
            job = self.store.get("job", self.store.initial_job())
            if self.session()["status"] != "qualified" and not (job["status"] == "failed" and job["phase"] == "final"):
                raise CompetitionError(409, "Complete qualifications before starting the final.")
            board = self.store.get("leaderboard", [])
            ids = [row["id"] for row in board if not row["disqualified"]][:5]
            by_id = {entry["id"]: entry for entry in self.store.get("snapshot", [])}
            entries = [by_id[entry_id] for entry_id in ids]
            if len(entries) < 2:
                raise CompetitionError(409, "The final needs at least two eligible bots.")
            if not self.sandbox_status(refresh=True)["available"]:
                raise CompetitionError(503, "Docker sandbox unavailable; the final was not started.")
            tracks = self.store.get("final_tracks")
            if tracks is None:
                # Upgrade only on an explicit final start; historical archives and
                # their qualification courses remain untouched.
                tracks = self._tracks(count=6)[3:6]
            qualifiers = self.store.get("tracks", [])
            try:
                collection = qualifiers + tracks
                distinct = (len(qualifiers) == len(tracks) == 3
                            and len({track["id"] for track in collection}) == 6
                            and len({tuple(map(tuple, track["checkpoints"])) for track in collection}) == 6)
            except (TypeError, KeyError):
                distinct = False
            if not distinct:
                raise CompetitionError(409, "The final needs three distinct tracks different from qualification.")
            job = {"status": "running", "phase": "final", "completed": 0, "total": 3, "message": f"Racing {len(entries)} finalists over three different tracks."}
            finalists = [{"id": e["id"], "alias": e["alias"]} for e in entries]
            self.store.update(session={**self.session(), "status": "final"}, job=job, finalists=finalists,
                              final_tracks=tracks, final_format="three-track-total-time-v1",
                              final_replay_ids=[], final_leaderboard=[], champion=None, active_replay_id=None)
            self._launch(self._final, entries, tracks)
            return job

    def _tracks(self, count=3):
        if self.tracks_fn:
            return self.tracks_fn(seed=2026, count=count)
        from .engine import make_tracks
        return make_tracks(seed=2026, count=count)

    def _launch(self, target, *args):
        self.worker = threading.Thread(target=self._guard, args=(target, args), daemon=True, name="classroom-tournament")
        try:
            self.worker.start()
        except Exception:
            job = self.store.get("job")
            self.store.update(job={**job, "status": "failed", "message": "Unable to start the competition worker.", "error": "Worker startup failed."})
            raise CompetitionError(503, "Unable to start the competition worker.")

    def _guard(self, target, args):
        try:
            target(*args)
        except Exception:
            # Full exception details may include submitted source or sandbox internals.
            with self.lock:
                job = self.store.get("job")
                self.store.update(job={**job, "status": "failed", "message": "Competition interrupted. Check the Docker sandbox and retry or reset.", "error": "Competition worker failed."})
                active = self.store.get("active_replay_id")
                if active:
                    replay = self.store.read_replay(active)
                    if replay and replay.get("status") == "running":
                        replay["status"] = "failed"
                        self.store.write_replay(active, replay)

    @staticmethod
    def _safe_frame(frame):
        fields = ("id", "alias", "x", "y", "angle", "vx", "vy", "next_checkpoint", "passed", "finished", "disqualified", "boost_available")
        return {"turn": frame["turn"], "pods": [{**{k: pod[k] for k in fields if k in pod}, "error": public_error(pod.get("error"))} for pod in frame["pods"]]}

    def _race(self, entries, track, kind, title, *, series_index=None):
        replay_id = str(uuid.uuid4())
        replay = {"id": replay_id, "track": track, "laps": 2, "max_turns": 700, "collisions": False,
                  "input_protocol": self.input_protocol,
                  "status": "running", "winner_id": None, "entries": [{"id": e["id"], "alias": e["alias"]} for e in entries], "frames": [], "results": []}
        if series_index is not None:
            replay.update(series_index=series_index, series_total=3, title=title)
        self.store.add_replay(replay_id, title, kind)
        # Current/live references must only identify an already-readable archive.
        try:
            self.store.write_replay(replay_id, replay)
        except Exception:
            # Retain an empty failed attempt if storage recovers, but still fail
            # the job and never publish this attempt as the current/live race.
            replay["status"] = "failed"
            self.store.write_replay(replay_id, replay)
            raise
        with self.lock:
            self.store.update(active_replay_id=replay_id,
                              **({"final_replay_ids": self.store.get("final_replay_ids", []) + [replay_id]}
                                 if series_index is not None else {}))
        last_write = time.monotonic()

        def on_frame(frame):
            nonlocal last_write
            if len(replay["frames"]) >= 701 or len(frame["pods"]) > 5:
                raise ValueError("Engine exceeded replay bounds")
            replay["frames"].append(self._safe_frame(frame))
            now = time.monotonic()
            if now - last_write >= 0.25:
                self.store.write_replay(replay_id, replay)
                last_write = now

        race_fn = self.race_fn
        if race_fn is None:
            from .engine import run_race
            race_fn = partial(run_race, input_protocol=self.input_protocol)
        result = race_fn(entries, track, laps=2, max_turns=700, on_frame=on_frame)
        raw_frames = result.get("frames", [])
        if len(raw_frames) > 701 or any(len(frame["pods"]) > 5 for frame in raw_frames):
            raise ValueError("Engine exceeded replay bounds")
        replay["frames"] = [self._safe_frame(frame) for frame in raw_frames]
        result_fields = ("id", "alias", "place", "finished", "disqualified", "turns", "finish_time", "passed", "distance_to_checkpoint")
        replay["results"] = [{**{k: row[k] for k in result_fields if k in row}, "finish_time": valid_finish_time(row), "error": public_error(row.get("error"))} for row in result["results"]]
        eligible_winner = next((r for r in replay["results"] if r["id"] == result.get("winner_id") and r.get("finished") and not r.get("disqualified")), None)
        replay.update(status="finished", winner_id=eligible_winner["id"] if eligible_winner else None)
        self.store.write_replay(replay_id, replay)
        self.store.finish_replay(replay_id, eligible_winner["alias"] if eligible_winner else None)
        return replay

    def _qualify(self, snapshot, tracks):
        results = {entry["id"]: [] for entry in snapshot}
        baseline = {"id": str(uuid.uuid4()), "alias": "Reference ghost", "code": "", "kind": "reference"}
        completed = 0
        for entry in snapshot:
            for track in tracks:
                replay = self._race([entry, baseline], track, "qualification", f"{entry['alias']} · {track['name']}")
                row = next(r for r in replay["results"] if r["id"] == entry["id"])
                results[entry["id"]].append(row)
                completed += 1
                with self.lock:
                    job = self.store.get("job")
                    self.store.update(job={**job, "completed": completed, "message": f"Qualified {completed} of {job['total']} races."})
        board = rank_results(snapshot, results)
        eligible = [{"id": row["id"], "alias": row["alias"]} for row in board if not row["disqualified"]][:5]
        with self.lock:
            job = self.store.get("job")
            self.store.update(leaderboard=board, finalists=eligible, job={**job, "status": "finished", "message": "Qualification complete."}, session={**self.session(), "status": "qualified"})

    def _final(self, entries, tracks):
        results = {entry["id"]: [] for entry in entries}
        for index, track in enumerate(tracks, 1):
            replay = self._race(entries, track, "final", f"Final {index}/3 · {track['name']} · {len(entries)} pods", series_index=index)
            for entry in entries:
                results[entry["id"]].append(next((row for row in replay["results"] if row["id"] == entry["id"]), {}))
            board = rank_final_results(entries, results)
            with self.lock:
                job = self.store.get("job")
                self.store.update(final_leaderboard=board, job={**job, "completed": index, "message": f"Final {index} of 3 complete."})
        winner = next((row for row in board if row["total_time"] is not None), None)
        champion = {"id": winner["id"], "alias": winner["alias"]} if winner else None
        with self.lock:
            job = self.store.get("job")
            self.store.update(champion=champion, session={**self.session(), "status": "finished"}, job={**job, "status": "finished", "completed": 3, "message": "Three-track final complete." if champion else "Three-track final complete; no bot finished all three tracks, so no champion was crowned."})

    def reset(self):
        with self.lock:
            self.require_idle()
            self.store.reset()
            return self.session()
