"""Request-local English/German API copy; never translate user data or protocol keys."""
from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import parse_qs


MESSAGES = {
    "Teacher token required.": "Der Lehrkraft-Schlüssel ist erforderlich.",
    "Replay not found.": "Die Rennaufzeichnung wurde nicht gefunden.",
    "Submission not found.": "Die Einreichung wurde nicht gefunden.",
    "Demo requires an empty waiting classroom. Reset first.": "Die Demo benötigt einen leeren, noch nicht gestarteten Kurs. Bitte zuerst zurücksetzen.",
    "Six demo example files are not installed.": "Die sechs Demo-Beispieldateien sind nicht installiert.",
    "Six genuine example bots inserted. Start qualification to race them; no results have been fabricated.": "Sechs echte Beispiel-Bots wurden hinzugefügt. Starte die Qualifikation, um sie fahren zu lassen; Ergebnisse werden nicht erfunden.",
    "Type RESET to confirm clearing the classroom.": "Gib RESET ein, um das Löschen der Kursdaten zu bestätigen.",
    "Classroom frontend is not installed.": "Die Kurs-Webseite ist nicht installiert.",
    "Request exceeds the 64 KiB limit.": "Die Anfrage überschreitet die Grenze von 64 KiB.",
    "Send a JSON request with Content-Type: application/json.": "Sende eine JSON-Anfrage mit Content-Type: application/json.",
    "Alias must contain 1–24 letters, digits, spaces, underscores or hyphens.": "Der Alias muss 1–24 Buchstaben, Ziffern, Leerzeichen, Unterstriche oder Bindestriche enthalten.",
    "Python source must contain valid Unicode text.": "Der Python-Code muss gültigen Unicode-Text enthalten.",
    "Python code must be at most 32 KiB.": "Der Python-Code darf höchstens 32 KiB groß sein.",
    "Python source could not be parsed safely.": "Der Python-Code konnte nicht sicher geprüft werden.",
    "A competition job is already running.": "Es läuft bereits ein Wettbewerb.",
    "Competition is frozen. Reset before starting a new session.": "Die Einreichungen für den Wettbewerb sind eingefroren. Setze den Kurs vor einer neuen Programmierphase zurück.",
    "Competition is already frozen.": "Die Einreichungen für den Wettbewerb sind bereits eingefroren.",
    "Submissions are closed or frozen.": "Die Einreichungsphase ist geschlossen oder die Einreichungen sind eingefroren.",
    "The private claim token does not match this pilot.": "Der private Schlüssel stimmt nicht mit diesem Bot überein.",
    "Practice run interrupted. Check the Docker sandbox and try again.": "Das Testrennen wurde unterbrochen. Prüfe die Docker-Sandbox und versuche es erneut.",
    "This alias is already claimed. Use its original claim token to update it.": "Dieser Alias ist bereits vergeben. Zum Aktualisieren benötigst du seinen ursprünglichen privaten Schlüssel.",
    "The classroom already has 60 submissions.": "Für diesen Kurs gibt es bereits 60 Einreichungen.",
    "Qualifications have already been started. Reset for a new competition.": "Die Qualifikation wurde bereits gestartet. Setze den Kurs für einen neuen Wettbewerb zurück.",
    "Submit at least one bot before qualifying.": "Vor der Qualifikation muss mindestens ein Bot eingereicht werden.",
    "Docker sandbox unavailable; no code was executed and submissions were not frozen.": "Die Docker-Sandbox ist nicht verfügbar. Es wurde kein Code ausgeführt und die Einreichungen wurden nicht eingefroren.",
    "Running qualification on three common tracks.": "Die Qualifikation läuft auf drei gemeinsamen Strecken.",
    "Complete qualifications before starting the final.": "Schließe die Qualifikation ab, bevor du das Finale startest.",
    "The final needs at least two eligible bots.": "Für das Finale werden mindestens zwei zugelassene Bots benötigt.",
    "Docker sandbox unavailable; the final was not started.": "Die Docker-Sandbox ist nicht verfügbar. Das Finale wurde nicht gestartet.",
    "Unable to start the competition worker.": "Der Wettbewerbsprozess konnte nicht gestartet werden.",
    "Worker startup failed.": "Der Start des Wettbewerbsprozesses ist fehlgeschlagen.",
    "Competition interrupted. Check the Docker sandbox and retry or reset.": "Der Wettbewerb wurde unterbrochen. Prüfe die Docker-Sandbox und versuche es erneut oder setze den Kurs zurück.",
    "Competition worker failed.": "Der Wettbewerbsprozess ist fehlgeschlagen.",
    "Qualification complete.": "Die Qualifikation ist abgeschlossen.",
    "Final complete.": "Das Finale ist abgeschlossen.",
    "Final complete; no bot finished, so no champion was crowned.": "Das Finale ist abgeschlossen. Kein Bot hat das Ziel erreicht, deshalb gibt es keinen Sieger.",
    "Job interrupted by server restart.": "Der Wettbewerb wurde durch einen Server-Neustart unterbrochen.",
    "Server restarted; reset or retry the competition.": "Der Server wurde neu gestartet. Setze den Kurs zurück oder starte den Wettbewerb erneut.",
    "Docker is not installed or not on PATH.": "Docker ist nicht installiert oder nicht im PATH verfügbar.",
    "Docker daemon is unavailable. Start Docker Desktop.": "Docker ist nicht erreichbar. Starte Docker Desktop.",
    "Sandbox image is missing; build sandbox/Dockerfile first.": "Das Sandbox-Image fehlt. Baue zuerst sandbox/Dockerfile.",
    "Restricted Docker sandbox ready.": "Die eingeschränkte Docker-Sandbox ist bereit.",
    "Docker availability check failed or timed out.": "Die Docker-Prüfung ist fehlgeschlagen oder hat zu lange gedauert.",
    "Docker sandbox is unavailable. Start Docker and build the bot image.": "Die Docker-Sandbox ist nicht verfügbar. Starte Docker und baue das Bot-Image.",
    "Bot exceeded its time limit.": "Der Bot hat sein Zeitlimit überschritten.",
    "Bot returned an invalid command.": "Der Bot hat einen ungültigen Befehl ausgegeben.",
    "Bot exceeded its output limit.": "Der Bot hat sein Ausgabelimit überschritten.",
    "Bot process crashed.": "Das Bot-Programm ist abgestürzt.",
    "Bot disqualified.": "Der Bot wurde disqualifiziert.",
    "Classroom one-pod racing": "Pod-Rennen für den Programmierkurs",
    "integer 0–100, BOOST once per race, or SHIELD": "ganze Zahl von 0 bis 100, BOOST einmal pro Rennen oder SHIELD",
    "Nearest other pod, including in the simultaneous final.": "Der nächstgelegene andere Pod, auch im gemeinsamen Finale.",
    "Flush stdout after every command; no bootstrap input.": "Leere stdout nach jedem Befehl mit flush=True; es gibt keine zusätzliche Start-Eingabe.",
    "Same three tracks and starting positions against a reference ghost; collisions disabled.": "Alle Bots fahren dieselben drei Strecken von denselben Startpositionen gegen einen Referenz-Bot; Kollisionen sind ausgeschaltet.",
    "Disqualified entries last; completed tracks descending, total turns ascending (DNF costs 700), aggregate checkpoint progress descending, case-folded alias then UUID.": "Disqualifizierte Bots stehen am Ende. Danach zählen absolvierte Strecken absteigend, benötigte Spielzüge aufsteigend (nicht beendet zählt als 700), Checkpoint-Fortschritt absteigend und zuletzt Alias ohne Beachtung der Großschreibung sowie UUID.",
    "Up to five eligible snapshot bots race simultaneously with collisions. At least two needed. Only a valid finisher can become champion.": "Bis zu fünf zugelassene Bots fahren mit ihrem eingefrorenen Code gleichzeitig mit Kollisionen. Mindestens zwei sind erforderlich. Nur ein Bot, der das Ziel gültig erreicht, kann gewinnen.",
    "Classroom variant, not the official CodinGame engine: width 16000, height 9000, checkpoint radius 600, pod radius 400, rotation 18 degrees/turn, friction 0.85, BOOST 650. SHIELD lasts three turns with no thrust and heavier mass.": "Kurs-Variante, nicht die offizielle CodinGame-Engine: Breite 16000, Höhe 9000, Checkpoint-Radius 600, Pod-Radius 400, Drehung 18 Grad pro Spielzug, Reibungsfaktor 0,85, BOOST 650. SHIELD wirkt drei Spielzüge lang ohne Schub und mit größerer Masse.",
    "Python syntax checked without execution; bot execution only in restricted Docker.": "Die Python-Syntax wird ohne Ausführung geprüft; Bots laufen ausschließlich in eingeschränkten Docker-Containern.",
}
COURSES = {"Wide Circuit": "Breiter Rundkurs", "Five Corners": "Fünf Kurven", "Switchback": "Zickzackstrecke"}


def select_language(query: str | None = None, accept: str = "") -> str:
    if query in ("en", "de"):
        return query
    preferences = []
    for order, item in enumerate(accept.split(",")):
        parts = item.strip().lower().split(";")
        language = parts[0].split("-")[0]
        quality = 1.0
        try:
            for parameter in parts[1:]:
                if parameter.strip().startswith("q="):
                    quality = float(parameter.strip()[2:])
        except ValueError:
            continue
        if language in ("en", "de") and 0 < quality <= 1:
            preferences.append((quality, -order, language))
    return max(preferences)[2] if preferences else "en"


def language_for(request) -> str:
    return select_language(request.query_params.get("lang"), request.headers.get("accept-language", ""))


def translate(message, language: str):
    if language != "de" or not isinstance(message, str):
        return message
    if message in MESSAGES:
        return MESSAGES[message]
    if message.startswith("Value error, "):
        return translate(message[len("Value error, "):], language)
    match = re.fullmatch(r"Python syntax error at line (\d+|None): (.*)", message)
    if match:
        reason = {"invalid syntax": "ungültige Syntax", "expected ':'": "Doppelpunkt erwartet", "unexpected indent": "unerwartete Einrückung", "unterminated string literal": "nicht abgeschlossene Zeichenkette"}.get(match[2], match[2])
        return f"Python-Syntaxfehler in Zeile {match[1]}: {reason}"
    match = re.fullmatch(r"Qualified (\d+) of (\d+) races\.", message)
    if match:
        return f"{match[1]} von {match[2]} Qualifikationsrennen abgeschlossen."
    match = re.fullmatch(r"Racing (\d+) finalists simultaneously\.", message)
    if match:
        return f"{match[1]} Finalisten fahren gleichzeitig."
    if message.startswith("String should have at least "):
        return "Der Text ist zu kurz."
    if message.startswith("String should have at most "):
        return "Der Text ist zu lang."
    return {"Field required": "Dieses Feld ist erforderlich.", "Input should be a valid string": "Hier ist ein Text erforderlich.", "Input should be a valid integer": "Hier ist eine ganze Zahl erforderlich.", "Extra inputs are not permitted": "Zusätzliche Felder sind nicht erlaubt."}.get(message, message)


def translate_detail(detail, language):
    if isinstance(detail, str):
        return translate(detail, language)
    if isinstance(detail, list):
        return [{**item, "message": translate(item["message"], language)} if isinstance(item, dict) and "message" in item else translate(item, language) for item in detail]
    return detail


def localize_rules(rules: dict, language: str) -> dict:
    if language == "en":
        return rules
    result = deepcopy(rules)
    for field in ("title", "qualification", "ranking", "final", "physics", "security"):
        result[field] = translate(result[field], language)
    for field in ("thrust", "opponent", "flush"):
        result["protocol"][field] = translate(result["protocol"][field], language)
    return result


def _replay_title(metadata, language):
    title = metadata.get("title", "")
    if language != "de":
        return title
    if metadata.get("kind") == "final":
        match = re.fullmatch(r"Final · (\d+) pods", title)
        return f"Finale · {match[1]} Pods" if match else title
    if metadata.get("kind") == "qualification":
        alias, separator, course = title.rpartition(" · ")
        return alias + separator + COURSES.get(course, course)
    return title


def localize_state(state: dict, language: str) -> dict:
    if language == "en":
        return state
    result = deepcopy(state)
    for key in ("message", "error"):
        if key in result["job"]:
            result["job"][key] = translate(result["job"][key], language)
    result["sandbox"]["detail"] = translate(result["sandbox"]["detail"], language)
    for row in result["leaderboard"]:
        if "error" in row:
            row["error"] = translate(row["error"], language)
    for metadata in result["replays"]:
        metadata["title"] = _replay_title(metadata, language)
    return result


def localize_replay(replay: dict, language: str) -> dict:
    if language == "en":
        return replay
    result = deepcopy(replay)
    if result["track"].get("id", "").startswith("track-2026-"):
        result["track"]["name"] = COURSES.get(result["track"]["name"], result["track"]["name"])
    for row in result.get("results", []):
        if "error" in row:
            row["error"] = translate(row["error"], language)
    for frame in result.get("frames", []):
        for pod in frame["pods"]:
            if "error" in pod:
                pod["error"] = translate(pod["error"], language)
    return result


class LanguageHeadersMiddleware:
    """Mark response language without buffering large replay or file responses."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
        language = select_language(query.get("lang", [None])[0], headers.get(b"accept-language", b"").decode("latin-1"))

        async def localized_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                output = list(message.get("headers", []))
                output.append((b"content-language", language.encode("ascii")))
                output.append((b"vary", b"Accept-Language"))
                message["headers"] = output
            await send(message)

        await self.app(scope, receive, localized_send)
