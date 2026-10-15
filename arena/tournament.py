"""One durable competition at a time; student code is only passed to the engine."""
from __future__ import annotations

from functools import partial
import math
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
            result = race_fn([entry, reference], track, laps=2, max_turns=700, collisions=False)
        except Exception as exc:
            raise CompetitionError(503, "Practice run interrupted. Check the Docker sandbox and try again.") from exc
        raw_frames = result.get("frames", [])
        if len(raw_frames) > 701 or any(len(frame.get("pods", [])) > 5 for frame in raw_frames):
            raise CompetitionError(503, "Practice run interrupted. Check the Docker sandbox and try again.")
        result_fields = ("id", "alias", "place", "finished", "disqualified", "turns", "passed", "distance_to_checkpoint")
        results = [{**{key: row[key] for key in result_fields if key in row}, "error": public_error(row.get("error"))}
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
            tracks = self._tracks()
            job = {"status": "running", "phase": "qualification", "completed": 0, "total": len(snapshot) * len(tracks), "message": "Running qualification on three common tracks."}
            self.store.update(snapshot=snapshot, tracks=tracks, session={**session, "status": "qualifying"}, job=job,
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
            job = {"status": "running", "phase": "final", "completed": 0, "total": 1, "message": f"Racing {len(entries)} finalists simultaneously."}
            finalists = [{"id": e["id"], "alias": e["alias"]} for e in entries]
            self.store.update(session={**self.session(), "status": "final"}, job=job, finalists=finalists, champion=None, active_replay_id=None)
            self._launch(self._final, entries, self.store.get("tracks")[0])
            return job

    def _tracks(self):
        if self.tracks_fn:
            return self.tracks_fn(seed=2026, count=3)
        from .engine import make_tracks
        return make_tracks(seed=2026, count=3)

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

    def _race(self, entries, track, kind, title, collisions):
        replay_id = str(uuid.uuid4())
        replay = {"id": replay_id, "track": track, "laps": 2, "max_turns": 700, "collisions": collisions,
                  "input_protocol": self.input_protocol,
                  "status": "running", "winner_id": None, "entries": [{"id": e["id"], "alias": e["alias"]} for e in entries], "frames": [], "results": []}
        self.store.add_replay(replay_id, title, kind)
        self.store.write_replay(replay_id, replay)
        self.store.update(active_replay_id=replay_id)
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
        result = race_fn(entries, track, laps=2, max_turns=700, collisions=collisions, on_frame=on_frame)
        raw_frames = result.get("frames", [])
        if len(raw_frames) > 701 or any(len(frame["pods"]) > 5 for frame in raw_frames):
            raise ValueError("Engine exceeded replay bounds")
        replay["frames"] = [self._safe_frame(frame) for frame in raw_frames]
        result_fields = ("id", "alias", "place", "finished", "disqualified", "turns", "passed", "distance_to_checkpoint")
        replay["results"] = [{**{k: row[k] for k in result_fields if k in row}, "error": public_error(row.get("error"))} for row in result["results"]]
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
                replay = self._race([entry, baseline], track, "qualification", f"{entry['alias']} · {track['name']}", False)
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

    def _final(self, entries, track):
        replay = self._race(entries, track, "final", f"Final · {len(entries)} pods", True)
        winner = next((row for row in replay["results"] if row["id"] == replay["winner_id"]), None)
        champion = {"id": winner["id"], "alias": winner["alias"]} if winner else None
        with self.lock:
            job = self.store.get("job")
            self.store.update(champion=champion, session={**self.session(), "status": "finished"}, job={**job, "status": "finished", "completed": 1, "message": "Final complete." if champion else "Final complete; no bot finished, so no champion was crowned."})

    def reset(self):
        with self.lock:
            self.require_idle()
            self.store.reset()
            return self.session()
