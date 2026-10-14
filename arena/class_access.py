"""Persistent invitation and opaque participant cookies; separate from bot ownership."""
import hashlib
import math
import os
import re
import secrets
import time

from fastapi import HTTPException

COOKIE = 'pod_participant'


def settings():
    flags = {}
    for name, default in [('POD_CLASS_ACCESS_REQUIRED', '0'), ('POD_CLASS_COOKIE_SECURE', '1')]:
        value = os.environ.get(name, default)
        if value not in ('0', '1'):
            raise ValueError(f'{name} must be 0 or 1.')
        flags[name] = value == '1'
    limits = {}
    for name, default in [('POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE', 30),
                          ('POD_PARTICIPANT_PRACTICE_PER_MINUTE', 6), ('POD_JOIN_PER_MINUTE', 120)]:
        value = os.environ.get(name, str(default))
        if not re.fullmatch(r'[1-9][0-9]{0,4}', value) or int(value) > 10000:
            raise ValueError(f'{name} must be an integer between 1 and 10000.')
        limits[name] = int(value)
    return flags, limits


def digest(value):
    return hashlib.sha256(value.encode('utf-8', errors='replace')).hexdigest()


class ClassAccess:
    def __init__(self, store):
        self.store = store

    def snapshot(self):
        return self.store.get('class_access', {'generation': 0, 'expires_at': 0, 'code_hash': '', 'sessions': {}})

    def valid(self, token):
        if not token or len(token) > 128:
            return None
        with self.store.lock:
            state = self.snapshot()
            session = state['sessions'].get(digest(token))
            if (state['code_hash'] and state['expires_at'] > time.time() and session
                    and session['generation'] == state['generation'] and session['expires_at'] > time.time()):
                return digest(token)
        return None

    def consume(self, token, path, limit):
        # Only two fixed paths on at most 60 server-authenticated session records.
        with self.store.lock:
            key = self.valid(token)
            if not key:
                raise HTTPException(401, 'Classroom access required.')
            state = self.snapshot()
            budgets = state['sessions'][key].setdefault('budgets', {})
            now = time.time()
            end, count = budgets.get(path, (now + 60, 0))
            if now >= end:
                end, count = now + 60, 0
            if count >= limit:
                raise HTTPException(429, 'Too many requests. Wait and try again.',
                                    headers={'Retry-After': str(max(1, math.ceil(end - now)))})
            budgets[path] = [end, count + 1]
            self.store.update(class_access=state)

    def status(self):
        with self.store.lock:
            state = self.snapshot()
            return {'active': bool(state['code_hash'] and state['expires_at'] > time.time()),
                    'generation': state['generation'], 'expires_at': state['expires_at']}

    def rotate(self, duration):
        with self.store.lock:
            code = secrets.token_urlsafe(32)
            state = {'generation': self.snapshot()['generation'] + 1,
                     'expires_at': time.time() + duration, 'code_hash': digest(code), 'sessions': {}}
            self.store.update(class_access=state)
            return {**self.status(), 'code': code}

    def revoke(self):
        with self.store.lock:
            self.store.update(class_access={'generation': self.snapshot()['generation'] + 1,
                                            'expires_at': 0, 'code_hash': '', 'sessions': {}})
            return self.status()

    def join(self, code, existing):
        with self.store.lock:
            state = self.snapshot()
            if not secrets.compare_digest(digest(code), state['code_hash']) or state['expires_at'] <= time.time():
                raise HTTPException(401, 'Invitation is invalid or expired.')
            state['sessions'] = {key: session for key, session in state['sessions'].items()
                                 if session['expires_at'] > time.time() and session['generation'] == state['generation']}
            valid_existing = self.valid(existing)
            if not valid_existing and len(state['sessions']) >= 60:
                self.store.update(class_access=state)
                raise HTTPException(429, 'Classroom participant capacity reached.', headers={'Retry-After': '60'})
            token = existing if valid_existing else secrets.token_urlsafe(32)
            state['sessions'].setdefault(digest(token), {'generation': state['generation'], 'expires_at': state['expires_at']})
            self.store.update(class_access=state)
            return token, state['expires_at']
