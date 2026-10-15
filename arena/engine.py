"""Original deterministic one-pod classroom referee (not the official engine).

Motion is solved chronologically within each turn: swept checkpoint crossings and
pod contacts share one event clock. Commands rotate at most 18 degrees (first
turn unrestricted), accelerate, then move; positions round half away from zero
and velocities truncate after 0.85 friction. BOOST is 650 once, then 100 on reuse.
SHIELD lasts its activation turn plus two more; mass 10 and no acceleration.
Checkpoint order starts at index 1 and a lap ends by passing index 0.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
import uuid

from arena.bots import BotError, BotMalformed, make_runner
from arena.protocol import configured_input_protocol

WIDTH = 16000
HEIGHT = 9000
CHECKPOINT_RADIUS = 600.0
POD_RADIUS = 400.0
FRICTION = 0.85
EPS = 1e-8


@dataclass
class Pod:
    id: str
    alias: str
    x: float
    y: float
    angle: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    next_checkpoint: int = 1
    passed: int = 0
    finished: bool = False
    disqualified: bool = False
    error: str | None = None
    boost_available: bool = True
    shield_turns: int = 0
    finish_time: float | None = None
    turns: int = 0

    @property
    def active(self) -> bool:
        return not self.finished and not self.disqualified

    @property
    def mass(self) -> float:
        return 10.0 if self.shield_turns else 1.0


def make_tracks(seed: int = 2026, count: int = 3) -> list[dict]:
    if not isinstance(count, int) or not 0 <= count <= 100:
        raise ValueError("count must be an integer from 0 to 100")
    rng = random.Random(seed)
    templates = [
        [(2600, 2300), (12900, 2100), (13400, 6900), (2900, 7100)],
        [(2400, 4500), (6500, 1500), (13200, 2300), (13000, 7000), (6300, 7400)],
        [(2200, 1800), (13800, 1800), (9300, 4400), (13500, 7300), (2300, 7100)],
    ]
    names = ["Wide Circuit", "Five Corners", "Switchback"]
    result = []
    for index in range(count):
        checkpoints = [[x + rng.randint(-300, 300), y + rng.randint(-250, 250)]
                       for x, y in templates[index % len(templates)]]
        result.append({"id": f"track-{seed}-{index + 1}", "name": names[index % 3],
                       "checkpoints": checkpoints})
    return result


def _relative(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def _round(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def parse_command(command: str) -> tuple[int, int, int | str]:
    if not isinstance(command, str) or len(command.encode("utf-8")) > 1024:
        raise BotMalformed("Command must be text of at most 1 KiB")
    # Labels are permitted after the third token, but not additional lines.
    if "\n" in command.strip() or "\r" in command.strip():
        raise BotMalformed("Expected exactly one command line")
    fields = command.split()
    if len(fields) < 3:
        raise BotMalformed("Expected target_x target_y thrust")
    try:
        x, y = int(fields[0]), int(fields[1])
        if abs(x) > 10_000_000 or abs(y) > 10_000_000:
            raise ValueError
        value = fields[2]
        thrust = value if value in {"BOOST", "SHIELD"} else max(0, min(100, int(value)))
    except (ValueError, OverflowError):
        raise BotMalformed("Targets must be bounded integers; thrust is an integer, BOOST or SHIELD") from None
    return x, y, thrust


def apply_command(pod: Pod, command: tuple[int, int, int | str], *, first: bool = False) -> None:
    tx, ty, thrust = command
    dx, dy = tx - pod.x, ty - pod.y
    desired = math.degrees(math.atan2(dy, dx)) % 360 if dx or dy else pod.angle
    change = _relative(desired - pod.angle)
    pod.angle = (pod.angle + (change if first else max(-18, min(18, change)))) % 360
    if thrust == "SHIELD":
        pod.shield_turns = 3
        return
    if pod.shield_turns:
        return
    if thrust == "BOOST":
        thrust = 650 if pod.boost_available else 100
        pod.boost_available = False
    radians = math.radians(pod.angle)
    pod.vx += math.cos(radians) * thrust
    pod.vy += math.sin(radians) * thrust


def _circle_time(dx: float, dy: float, vx: float, vy: float,
                 radius: float, remaining: float, *, contact: bool = False) -> float | None:
    c = dx * dx + dy * dy - radius * radius
    approach = dx * vx + dy * vy
    if c <= EPS:
        if not contact or approach < -EPS:
            return 0.0
        return None
    a = vx * vx + vy * vy
    if a <= EPS or approach >= 0:
        return None
    discriminant = approach * approach - a * c
    if discriminant < -EPS:
        return None
    t = (-approach - math.sqrt(max(0.0, discriminant))) / a
    if -EPS <= t <= remaining + EPS:
        return max(0.0, min(remaining, t))
    return None


def checkpoint_time(pod: Pod, checkpoint, remaining: float = 1.0) -> float | None:
    return _circle_time(pod.x - checkpoint[0], pod.y - checkpoint[1],
                        pod.vx, pod.vy, CHECKPOINT_RADIUS, remaining)


def collision_time(a: Pod, b: Pod, remaining: float = 1.0) -> float | None:
    return _circle_time(a.x - b.x, a.y - b.y, a.vx - b.vx, a.vy - b.vy,
                        2 * POD_RADIUS, remaining, contact=True)


def bounce(a: Pod, b: Pod) -> None:
    dx, dy = b.x - a.x, b.y - a.y
    distance = math.hypot(dx, dy)
    if distance < EPS:
        # Coincident pods need a stable normal, not division by zero.
        dx, dy = a.vx - b.vx, a.vy - b.vy
        distance = math.hypot(dx, dy)
        if distance < EPS:
            dx, dy, distance = 1.0, 0.0, 1.0
    nx, ny = dx / distance, dy / distance
    closing = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny
    if closing <= EPS:
        return
    impulse = closing / (1 / a.mass + 1 / b.mass)
    # Two half-impulses: the second has the beginner-rules minimum 120.
    impulse += max(120.0, impulse)
    a.vx -= impulse * nx / a.mass
    a.vy -= impulse * ny / a.mass
    b.vx += impulse * nx / b.mass
    b.vy += impulse * ny / b.mass


def advance_turn(pods: list[Pod], checkpoints: list, *, laps: int = 2,
                 collisions: bool = True, turn: int = 1) -> None:
    """Solve one turn continuously, then round/friction, without zero-time loops.

    Equal-time events use checkpoint-before-contact and stable entry order. The
    event budget is a deterministic degeneracy guard (e.g. coincident circles).
    """
    elapsed = 0.0
    event_budget = 256 + len(pods) * len(checkpoints) * laps
    for _ in range(event_budget):
        remaining = 1.0 - elapsed
        events = []
        for i, pod in enumerate(pods):
            if not pod.active:
                continue
            t = checkpoint_time(pod, checkpoints[pod.next_checkpoint], remaining)
            if t is not None:
                events.append((t, 0, i, -1))
            if collisions:
                for j in range(i + 1, len(pods)):
                    other = pods[j]
                    if other.active:
                        t = collision_time(pod, other, remaining)
                        if t is not None:
                            events.append((t, 1, i, j))
        if not events:
            for pod in pods:
                if pod.active:
                    pod.x += pod.vx * remaining
                    pod.y += pod.vy * remaining
            elapsed = 1.0
            break
        dt, kind, i, j = min(events)
        for pod in pods:
            if pod.active:
                pod.x += pod.vx * dt
                pod.y += pod.vy * dt
        elapsed += dt
        pod = pods[i]
        if kind == 0:
            pod.passed += 1
            pod.next_checkpoint = (pod.next_checkpoint + 1) % len(checkpoints)
            if pod.passed >= laps * len(checkpoints):
                pod.finished = True
                pod.finish_time = turn - 1 + elapsed
                pod.turns = turn
        else:
            bounce(pod, pods[j])
        if elapsed >= 1.0 - EPS:
            # Zero-duration checkpoint events at the end still matter; next
            # iterations process them, and separating collisions are excluded.
            elapsed = 1.0
    else:
        # Pathological contact piles cannot hang a classroom race. Finite,
        # deterministic fallback advances only the unprocessed residual time.
        for pod in pods:
            if pod.active:
                pod.x += pod.vx * (1.0 - elapsed)
                pod.y += pod.vy * (1.0 - elapsed)
    for pod in pods:
        if not pod.disqualified:
            pod.x, pod.y = _round(pod.x), _round(pod.y)
            pod.vx, pod.vy = math.trunc(pod.vx * FRICTION), math.trunc(pod.vy * FRICTION)
            pod.shield_turns = max(0, pod.shield_turns - 1)
            if not pod.finished:
                pod.turns = turn


def observation(pod: Pod, pods: list[Pod], checkpoints: list, *,
                input_protocol: str | None = None) -> str:
    input_protocol = configured_input_protocol(input_protocol)
    cx, cy = checkpoints[pod.next_checkpoint]
    dx, dy = cx - pod.x, cy - pod.y
    angle = _relative(math.degrees(math.atan2(dy, dx)) - pod.angle)
    checkpoint_line = (f"{_round(pod.x)} {_round(pod.y)} {_round(cx)} {_round(cy)} "
                       f"{_round(math.hypot(dx, dy))} {_round(angle)}\n")
    if input_protocol == "checkpoint-only":
        return checkpoint_line
    others = [other for other in pods if other is not pod and not other.disqualified]
    opponent = min(others, key=lambda p: ((p.x - pod.x) ** 2 + (p.y - pod.y) ** 2, p.id)) if others else pod
    return checkpoint_line + f"{_round(opponent.x)} {_round(opponent.y)}\n"


def _frame(pods: list[Pod], turn: int) -> dict:
    return {"turn": turn, "pods": [
        {"id": p.id, "alias": p.alias, "x": p.x, "y": p.y, "angle": p.angle,
         "vx": p.vx, "vy": p.vy, "next_checkpoint": p.next_checkpoint,
         "passed": p.passed, "finished": p.finished, "disqualified": p.disqualified,
         "error": p.error, "boost_available": p.boost_available} for p in pods
    ]}


def run_race(entries: list[dict], track: dict, *, laps: int = 2, max_turns: int = 700,
             collisions: bool = True, on_frame=None, runner_factory=None,
             input_protocol: str | None = None) -> dict:
    input_protocol = configured_input_protocol(input_protocol)
    if not 1 <= len(entries) <= 60:
        raise ValueError("A race needs 1 to 60 entries")
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Entry IDs must be unique")
    if not isinstance(laps, int) or not 1 <= laps <= 20:
        raise ValueError("laps must be from 1 to 20")
    if not isinstance(max_turns, int) or not 1 <= max_turns <= 5000:
        raise ValueError("max_turns must be from 1 to 5000")
    checkpoints = track.get("checkpoints", [])
    if not 2 <= len(checkpoints) <= 30:
        raise ValueError("A track needs 2 to 30 checkpoints")
    for point in checkpoints:
        if len(point) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                                  or abs(v) > 10_000_000 for v in point):
            raise ValueError("Checkpoint coordinates must be finite bounded numbers")
    cx, cy = checkpoints[0]
    dx, dy = checkpoints[1][0] - cx, checkpoints[1][1] - cy
    heading = math.atan2(dy, dx)
    pods = []
    for index, entry in enumerate(entries):
        lateral = (index - (len(entries) - 1) / 2) * 850
        pods.append(Pod(str(entry["id"]), str(entry["alias"]),
                        _round(cx - math.sin(heading) * lateral),
                        _round(cy + math.cos(heading) * lateral),
                        angle=math.degrees(heading) % 360))
    runners = [None] * len(entries)
    frames = []
    factory = runner_factory or make_runner

    def disqualify(pod: Pod, error: Exception):
        kind = error.kind if isinstance(error, BotError) else "crash"
        message = str(error) if isinstance(error, BotError) else "Bot runner failed"
        pod.disqualified, pod.error = True, f"{kind}: {message}"

    def emit(turn: int):
        frame = _frame(pods, turn)
        frames.append(frame)
        if on_frame is not None:
            on_frame(frame)

    try:
        for index, entry in enumerate(entries):
            try:
                runners[index] = factory(entry)
            except Exception as error:
                disqualify(pods[index], error)
        emit(0)
        for turn in range(1, max_turns + 1):
            if not any(p.active for p in pods):
                break
            # Freeze all observations before any commands/errors mutate state.
            inputs = [observation(pod, pods, checkpoints, input_protocol=input_protocol)
                      for pod in pods]
            for index, pod in enumerate(pods):
                if not pod.active:
                    continue
                try:
                    command = parse_command(runners[index].act(inputs[index], first=(turn == 1)))
                    apply_command(pod, command, first=(turn == 1))
                except Exception as error:
                    pod.turns = turn
                    disqualify(pod, error)
                    # Release a faulty bot promptly, not only at race end.
                    try:
                        runners[index].close()
                    except Exception:
                        pass
            advance_turn(pods, checkpoints, laps=laps, collisions=collisions, turn=turn)
            emit(turn)
    finally:
        for runner in runners:
            if runner is not None:
                try:
                    runner.close()
                except Exception:
                    pass
    def distance(pod):
        cx, cy = checkpoints[pod.next_checkpoint]
        return math.hypot(pod.x - cx, pod.y - cy)

    def rank(pod):
        tie = (pod.alias.casefold(), pod.id)
        if pod.disqualified:
            return (2, -pod.passed, distance(pod), *tie)
        if pod.finished:
            return (0, pod.finish_time, 0, *tie)
        return (1, -pod.passed, distance(pod), *tie)

    ordered = sorted(pods, key=rank)
    results = [{"id": p.id, "alias": p.alias, "place": index + 1,
                "finished": p.finished, "disqualified": p.disqualified, "error": p.error,
                "turns": p.turns, "passed": p.passed, "distance_to_checkpoint": distance(p)}
               for index, p in enumerate(ordered)]
    winner = next((p.id for p in ordered if p.finished and not p.disqualified), None)
    return {"id": str(uuid.uuid4()), "track": track, "laps": laps, "max_turns": max_turns,
            "input_protocol": input_protocol,
            "collisions": collisions, "status": "finished", "winner_id": winner,
            "entries": [{"id": p.id, "alias": p.alias} for p in pods],
            "frames": frames, "results": results}
