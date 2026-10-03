"""Local password login for JARVIS Cyber. Stdlib only, no extra dependencies.

Design goals, matching app.py's existing style:
  - No external auth provider (no "ChatGPT login", no OAuth, no network calls).
    Everything needed to log in lives on this machine, in the same sqlite DB
    the app already uses for memories.
  - Password is hashed with salted PBKDF2-SHA256 (hashlib, stdlib) — nothing
    to pip install.
  - Sessions are random opaque tokens stored server-side with an expiry, sent
    to the browser as an HttpOnly cookie. The browser never sees the password
    hash, and a stolen cookie can be revoked server-side (unlike a JWT).
  - Login attempts are rate-limited to slow down local brute forcing.

First run: no password is set yet, so app.py sends the browser to /setup.
After a password exists, app.py sends unauthenticated requests to /login.
"""
import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path

# PBKDF2 iteration count — OWASP's 2023 minimum recommendation for PBKDF2-SHA256.
# Safe to raise later; existing hashes keep working since the count isn't stored
# per-row here (single user). If you ever raise it, existing users must reset
# their password, so bump this only when you're also comfortable with that.
PBKDF2_ITERATIONS = 310_000

SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # session cookie lasts 2 weeks
MAX_ATTEMPTS = 5                         # failed logins before a lockout
LOCKOUT_SECONDS = 60 * 5                 # lockout length once MAX_ATTEMPTS is hit


class AuthError(Exception):
    """Raised for any user-facing auth problem (bad password, locked out, ...)."""


class Auth:
    """Password storage + session issuing/verification.

    Backed by the same sqlite file app.py already opens for `memories`, so
    there's no second database file to manage or back up separately.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute(
                'CREATE TABLE IF NOT EXISTS auth_password ('
                '  id INTEGER PRIMARY KEY CHECK (id = 1),'  # single row: one local user
                '  salt BLOB NOT NULL,'
                '  hash BLOB NOT NULL,'
                '  created_at TEXT DEFAULT CURRENT_TIMESTAMP'
                ')'
            )
            conn.execute(
                'CREATE TABLE IF NOT EXISTS auth_session ('
                '  token TEXT PRIMARY KEY,'
                '  expires_at REAL NOT NULL'
                ')'
            )
            conn.execute(
                'CREATE TABLE IF NOT EXISTS auth_attempt ('
                '  id INTEGER PRIMARY KEY CHECK (id = 1),'
                '  failures INTEGER NOT NULL DEFAULT 0,'
                '  locked_until REAL NOT NULL DEFAULT 0'
                ')'
            )

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- password lifecycle -------------------------------------------------

    def has_password(self) -> bool:
        with self._connect() as conn:
            row = conn.execute('SELECT 1 FROM auth_password WHERE id = 1').fetchone()
        return row is not None

    def set_password(self, password: str):
        """Used once, from /setup, to create the local password. Also used
        later if you add a "change password" screen — it overwrites the row
        and drops every existing session, so other logged-in tabs are kicked
        out and have to log in again with the new password."""
        if not isinstance(password, str) or not (8 <= len(password) <= 200):
            raise AuthError('비밀번호는 8~200자로 입력하세요.')
        salt = secrets.token_bytes(16)
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
        with self._connect() as conn:
            conn.execute('DELETE FROM auth_password')
            conn.execute('INSERT INTO auth_password (id, salt, hash) VALUES (1, ?, ?)', (salt, pw_hash))
            conn.execute('DELETE FROM auth_session')
            conn.execute('DELETE FROM auth_attempt')

    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str) or len(password) > 200:
            return False
        now = time.time()
        with self._connect() as conn:
            attempt = conn.execute('SELECT failures, locked_until FROM auth_attempt WHERE id = 1').fetchone()
            if attempt and attempt['locked_until'] > now:
                raise AuthError(f'너무 많이 틀렸어요. {int(attempt["locked_until"] - now)}초 후 다시 시도하세요.')
            pw_row = conn.execute('SELECT salt, hash FROM auth_password WHERE id = 1').fetchone()
            if pw_row is None:
                raise AuthError('비밀번호가 아직 설정되지 않았습니다.')
            candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), pw_row['salt'], PBKDF2_ITERATIONS)
            # constant-time compare: a timing difference here would leak how
            # many leading bytes of the hash were correct.
            ok = hmac.compare_digest(candidate, pw_row['hash'])
            if ok:
                conn.execute('DELETE FROM auth_attempt WHERE id = 1')
            else:
                failures = (attempt['failures'] if attempt and not attempt['locked_until'] else 0) + 1
                locked_until = now + LOCKOUT_SECONDS if failures >= MAX_ATTEMPTS else 0
                conn.execute(
                    'INSERT INTO auth_attempt (id, failures, locked_until) VALUES (1, ?, ?) '
                    'ON CONFLICT(id) DO UPDATE SET failures = excluded.failures, locked_until = excluded.locked_until',
                    (failures, locked_until),
                )
            return ok

    # ---- sessions -------------------------------------------------------------

    def issue_session(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            conn.execute('DELETE FROM auth_session WHERE expires_at < ?', (time.time(),))
            conn.execute(
                'INSERT INTO auth_session (token, expires_at) VALUES (?, ?)',
                (token, time.time() + SESSION_TTL_SECONDS),
            )
        return token

    def verify_session(self, token) -> bool:
        if not token:
            return False
        with self._connect() as conn:
            row = conn.execute('SELECT expires_at FROM auth_session WHERE token = ?', (token,)).fetchone()
        return row is not None and row['expires_at'] > time.time()

    def revoke_session(self, token):
        if not token:
            return
        with self._connect() as conn:
            conn.execute('DELETE FROM auth_session WHERE token = ?', (token,))


def read_cookie(cookie_header, name):
    """Pull one cookie value out of a raw Cookie: header. Returns None if
    absent. Deliberately dumb (no quoting/escaping support) because this app
    only ever sets cookies it reads back itself."""
    if not cookie_header:
        return None
    for part in cookie_header.split(';'):
        part = part.strip()
        if part.startswith(name + '='):
            return part[len(name) + 1:]
    return None


def session_cookie_header(token, max_age=SESSION_TTL_SECONDS):
    """Build the Set-Cookie value for a fresh login. SameSite=Strict blocks
    the cookie from being sent on cross-site requests (CSRF-ish defense in
    depth on top of the existing X-Jarvis-Token check). No `Secure` flag:
    the app only ever listens on http://127.0.0.1, so there's no TLS to
    require, and `Secure` on a non-HTTPS origin just makes browsers drop the
    cookie entirely."""
    return f'jarvis_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}'


def cleared_session_cookie_header():
    return 'jarvis_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
