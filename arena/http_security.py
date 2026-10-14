"""Defense-in-depth HTTP controls; not a substitute for access control."""
import ipaddress
import math
import os
import re
import threading
import time
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from .locale_api import language_for, translate
from .base_path import application_path


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}


def normalized_hostname(value):
    if not value or len(value) > 253:
        return None
    value = value.lower()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        return value if all(re.fullmatch(label, part) for part in value.split(".")) else None


def normalized_origin(value):
    """Accept a serialized HTTP(S) origin, never a URL path or wildcard."""
    try:
        parsed = urlsplit(value)
        host = normalized_hostname(parsed.hostname)
        if (parsed.scheme not in {"http", "https"} or not host or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)):
            return None
        if ":" in host:
            ipaddress.IPv6Address(host)
            host = f"[{host}]"
        elif not re.fullmatch(r"[a-z0-9.-]+", host):
            return None
        port = parsed.port
        default_port = 443 if parsed.scheme == "https" else 80
        suffix = f":{port}" if port is not None and port != default_port else ""
        return f"{parsed.scheme}://{host}{suffix}"
    except (ValueError, TypeError):
        return None


def configured_origins():
    values = os.environ.get("POD_PUBLIC_ORIGINS", "")
    if not values.strip():
        return frozenset()
    origins = [normalized_origin(value.strip()) for value in values.split(",")]
    if any(origin is None for origin in origins):
        raise ValueError("POD_PUBLIC_ORIGINS must contain exact HTTP(S) origins without paths or credentials.")
    return frozenset(origins)


def configured_hosts():
    values = os.environ.get("POD_ALLOWED_HOSTS", "")
    if not values.strip():
        return frozenset()
    hosts = [normalized_hostname(value.strip()) for value in values.split(",")]
    if any(host is None for host in hosts):
        raise ValueError("POD_ALLOWED_HOSTS must contain exact hostnames or IP addresses without ports.")
    return frozenset(hosts)


def configured_request_limits():
    rules = {"/api/submissions": ("POD_SUBMISSIONS_PER_MINUTE", 240),
             "/api/practice": ("POD_PRACTICE_PER_MINUTE", 60)}
    limits = {}
    for path, (name, default) in rules.items():
        value = os.environ.get(name, str(default))
        if not re.fullmatch(r"[1-9][0-9]{0,4}", value) or int(value) > 10000:
            raise ValueError(f"{name} must be an integer between 1 and 10000.")
        limits[path] = int(value)
    return limits


class RequestBudget:
    """Bounded, process-wide fixed windows; never key on client-controlled IPs."""
    def __init__(self, limits, clock=None):
        self.limits = dict(limits)
        self.clock = clock or time.monotonic
        self.windows = {}
        self.lock = threading.Lock()

    def retry_after(self, path):
        if path not in self.limits:
            return 0
        with self.lock:
            now = self.clock()
            end, count = self.windows.get(path, (now + 60, 0))
            if now >= end:
                end, count = now + 60, 0
            if count >= self.limits[path]:
                return max(1, math.ceil(end - now))
            self.windows[path] = (end, count + 1)
            return 0


class HTTPSecurityMiddleware:
    def __init__(self, app, public_origins=(), allowed_hosts=(), request_budget=None):
        self.app = app
        self.public_origins = frozenset(public_origins)
        self.allowed_hosts = frozenset(allowed_hosts)
        self.request_budget = request_budget

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(SECURITY_HEADERS)
                if application_path(scope).startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        request = Request(scope)
        hosts = request.headers.getlist("host")
        target = normalized_origin(f"{scope['scheme']}://{hosts[0]}") if len(hosts) == 1 else None
        hostname = normalized_hostname(urlsplit(target).hostname) if target else None
        if not target or (self.allowed_hosts and hostname not in self.allowed_hosts):
            language = language_for(request)
            response = JSONResponse({"detail": translate("Request hostname is not allowed.", language)},
                                    status_code=400, headers={"Content-Language": language,
                                                             "Vary": "Accept-Language"})
            return await response(scope, receive, secured_send)
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origins = request.headers.getlist("origin")
            allowed = self.public_origins | {target}
            denied = len(origins) > 1 or request.headers.get("sec-fetch-site", "").lower() == "cross-site"
            if origins:
                denied = denied or normalized_origin(origins[0]) not in allowed
            elif "referer" in request.headers:
                try:
                    referrer = urlsplit(request.headers["referer"])
                    source = normalized_origin(f"{referrer.scheme}://{referrer.netloc}")
                except ValueError:
                    source = None
                denied = denied or source not in allowed
            if denied:
                language = language_for(request)
                response = JSONResponse({"detail": translate("Request origin is not allowed.", language)},
                                        status_code=403, headers={"Content-Language": language,
                                                                 "Vary": "Accept-Language"})
                return await response(scope, receive, secured_send)
        if scope["method"] == "POST" and self.request_budget is not None:
            retry = self.request_budget.retry_after(application_path(scope))
            if retry:
                language = language_for(request)
                response = JSONResponse({"detail": translate("Too many requests. Wait and try again.", language)},
                                        status_code=429, headers={"Retry-After": str(retry),
                                                                 "Content-Language": language,
                                                                 "Vary": "Accept-Language"})
                return await response(scope, receive, secured_send)
        await self.app(scope, receive, secured_send)
