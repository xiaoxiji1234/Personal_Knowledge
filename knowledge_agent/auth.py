from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets


@dataclass
class AuthUser:
    username: str
    display_name: str
    password_salt: str
    password_hash: str
    created_at: str


@dataclass
class AuthSession:
    token: str
    username: str
    created_at: str
    expires_at: str


class AuthStore:
    """Persist lightweight local users and sessions for the web console."""

    def __init__(self, file_path: Path) -> None:
        """Store the JSON file path used for local auth persistence."""
        self.file_path = file_path

    def register_user(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        remember_me: bool = False,
    ) -> dict[str, object]:
        """Create a new local user and immediately issue one session token."""
        normalized_username = self._normalize_username(username)
        normalized_display_name = self._normalize_display_name(display_name or username)
        normalized_password = self._validate_password(password)
        payload = self._load_payload()
        users = payload["users"]
        if normalized_username in users:
            raise ValueError("用户名已存在")

        password_salt = secrets.token_hex(16)
        user = AuthUser(
            username=normalized_username,
            display_name=normalized_display_name,
            password_salt=password_salt,
            password_hash=self._hash_password(normalized_password, password_salt),
            created_at=_now(),
        )
        users[normalized_username] = asdict(user)
        session = self._issue_session(payload, normalized_username, remember_me=remember_me)
        self._save_payload(payload)
        return {"token": session.token, "user": self._public_user(user), "expiresAt": session.expires_at}

    def authenticate_user(self, username: str, password: str, remember_me: bool = False) -> dict[str, object]:
        """Validate one username/password pair and return a fresh session token."""
        normalized_username = self._normalize_username(username)
        normalized_password = self._validate_password(password)
        payload = self._load_payload()
        user_data = payload["users"].get(normalized_username)
        if not user_data:
            raise LookupError("用户名或密码错误")

        user = AuthUser(**user_data)
        expected_hash = self._hash_password(normalized_password, user.password_salt)
        if not hmac.compare_digest(expected_hash, user.password_hash):
            raise LookupError("用户名或密码错误")

        session = self._issue_session(payload, normalized_username, remember_me=remember_me)
        self._save_payload(payload)
        return {"token": session.token, "user": self._public_user(user), "expiresAt": session.expires_at}

    def get_user_by_token(self, token: str | None) -> dict[str, str] | None:
        """Resolve one session token back to the public user profile."""
        normalized_token = (token or "").strip()
        if not normalized_token:
            return None
        payload = self._load_payload()
        session_data = payload["sessions"].get(normalized_token)
        if not session_data:
            return None
        if self._is_session_expired(session_data):
            payload["sessions"].pop(normalized_token, None)
            self._save_payload(payload)
            return None
        username = str(session_data.get("username") or "").strip().lower()
        user_data = payload["users"].get(username)
        if not user_data:
            return None
        return self._public_user(AuthUser(**user_data))

    def revoke_token(self, token: str | None) -> bool:
        """Delete one stored session token during logout."""
        normalized_token = (token or "").strip()
        if not normalized_token:
            return False
        payload = self._load_payload()
        deleted = payload["sessions"].pop(normalized_token, None) is not None
        if deleted:
            self._save_payload(payload)
        return deleted

    def _issue_session(self, payload: dict[str, dict[str, object]], username: str, remember_me: bool = False) -> AuthSession:
        """Create and persist one opaque session token for a known user."""
        created_at = _now_datetime()
        expires_at = created_at + timedelta(days=7 if remember_me else 1)
        session = AuthSession(
            token=secrets.token_urlsafe(32),
            username=username,
            created_at=created_at.isoformat(),
            expires_at=expires_at.isoformat(),
        )
        payload["sessions"][session.token] = asdict(session)
        return session

    def _is_session_expired(self, session_data: dict[str, object]) -> bool:
        """Check whether one stored session has passed its expiration time."""
        expires_at = str(session_data.get("expires_at") or "").strip()
        if not expires_at:
            return True
        try:
            return datetime.fromisoformat(expires_at) <= _now_datetime()
        except ValueError:
            return True

    def _load_payload(self) -> dict[str, dict[str, object]]:
        """Read the auth JSON file and normalize its top-level containers."""
        if not self.file_path.exists():
            return {"users": {}, "sessions": {}}
        raw_text = self.file_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return {"users": {}, "sessions": {}}
        payload = json.loads(raw_text)
        users = payload.get("users", {}) if isinstance(payload, dict) else {}
        sessions = payload.get("sessions", {}) if isinstance(payload, dict) else {}
        return {
            "users": users if isinstance(users, dict) else {},
            "sessions": sessions if isinstance(sessions, dict) else {},
        }

    def _save_payload(self, payload: dict[str, dict[str, object]]) -> None:
        """Write the complete auth payload back to disk atomically enough for local use."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize_username(self, username: str | None) -> str:
        """Normalize usernames to a case-insensitive short identifier."""
        compact = " ".join((username or "").split()).strip().lower()
        if len(compact) < 3:
            raise ValueError("用户名至少需要 3 个字符")
        if len(compact) > 40:
            raise ValueError("用户名不能超过 40 个字符")
        return compact

    def _normalize_display_name(self, display_name: str | None) -> str:
        """Normalize the display name shown inside the frontend shell."""
        compact = " ".join((display_name or "").split()).strip()
        if len(compact) < 2:
            raise ValueError("昵称至少需要 2 个字符")
        if len(compact) > 40:
            raise ValueError("昵称不能超过 40 个字符")
        return compact

    def _validate_password(self, password: str | None) -> str:
        """Validate password length so the local demo auth is not trivially weak."""
        value = password or ""
        if len(value) < 6:
            raise ValueError("密码至少需要 6 个字符")
        if len(value) > 128:
            raise ValueError("密码不能超过 128 个字符")
        return value

    def _hash_password(self, password: str, password_salt: str) -> str:
        """Derive a stable PBKDF2 hash used for password verification."""
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            password_salt.encode("utf-8"),
            120_000,
        ).hex()

    def _public_user(self, user: AuthUser) -> dict[str, str]:
        """Return the frontend-safe subset of one stored auth user."""
        return {
            "username": user.username,
            "displayName": user.display_name,
        }


def _now() -> str:
    """Return one UTC timestamp string for user and session creation records."""
    return _now_datetime().isoformat()


def _now_datetime() -> datetime:
    """Return one timezone-aware UTC datetime used for session calculations."""
    return datetime.now(timezone.utc)
