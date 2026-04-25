"""Local FinMind API key failover management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Callable

from twadvisor.constants import TAIWAN_TIMEZONE

DEFAULT_ROTATE_STATUS_CODES = {402}
DEFAULT_COOLDOWN_HOURS = 24
MAX_FINMIND_KEYS = 10


@dataclass(frozen=True)
class FinMindApiKey:
    """A configured FinMind API key."""

    index: int
    name: str
    token: str


class FinMindKeyRotator:
    """Track the active FinMind API key and rotate away from quota errors."""

    def __init__(
        self,
        keys: list[FinMindApiKey],
        state_path: str | Path,
        rotate_on_status: set[int] | None = None,
        cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        """Create a key rotator backed by a local state file."""

        if not keys:
            raise ValueError("At least one enabled FinMind API key is required")
        self.keys = keys[:MAX_FINMIND_KEYS]
        self.state_path = Path(state_path)
        self.rotate_on_status = rotate_on_status or set(DEFAULT_ROTATE_STATUS_CODES)
        self.cooldown_hours = cooldown_hours
        self._now_func = now_func

    @classmethod
    def from_file(cls, config_path: str | Path, state_path: str | Path) -> "FinMindKeyRotator | None":
        """Load a rotator from a local JSON config file when it exists."""

        path = Path(config_path)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid FinMind key config JSON: {path}") from exc

        records = raw.get("keys", [])
        if not isinstance(records, list):
            raise ValueError("FinMind key config field 'keys' must be a list")

        keys: list[FinMindApiKey] = []
        for index, record in enumerate(records[:MAX_FINMIND_KEYS]):
            parsed = _parse_key_record(index, record)
            if parsed is not None:
                keys.append(parsed)
        if not keys:
            return None
        keys = [FinMindApiKey(index=index, name=key.name, token=key.token) for index, key in enumerate(keys)]

        rotate_on_status = _parse_status_codes(raw.get("rotate_on_status"), DEFAULT_ROTATE_STATUS_CODES)
        cooldown_hours = _parse_positive_int(raw.get("cooldown_hours"), DEFAULT_COOLDOWN_HOURS)
        return cls(
            keys=keys,
            state_path=state_path,
            rotate_on_status=rotate_on_status,
            cooldown_hours=cooldown_hours,
        )

    def should_rotate(self, status_code: int) -> bool:
        """Return whether the status code should retire the active key temporarily."""

        return status_code in self.rotate_on_status

    def iter_available_keys(self) -> list[FinMindApiKey]:
        """Return keys in retry order, starting from the persisted active key."""

        state = self._load_state()
        changed = self._clear_expired_exhausted_keys(state)
        current_index = self._state_current_index(state)
        ordered = self.keys[current_index:] + self.keys[:current_index]
        available = [key for key in ordered if not self._is_exhausted(key, state)]
        if changed:
            self._save_state(state)
        return available

    def mark_success(self, key: FinMindApiKey) -> None:
        """Persist the active key after a successful request."""

        state = self._load_state()
        exhausted = state.setdefault("exhausted", {})
        if isinstance(exhausted, dict):
            exhausted.pop(key.name, None)
        state["current_index"] = key.index
        state["current_name"] = key.name
        state["updated_at"] = self._now().isoformat()
        self._save_state(state)

    def mark_exhausted(self, key: FinMindApiKey, status_code: int) -> None:
        """Mark a key as temporarily exhausted and advance the active pointer."""

        now = self._now()
        cooldown_until = now + timedelta(hours=self.cooldown_hours)
        state = self._load_state()
        exhausted = state.setdefault("exhausted", {})
        if not isinstance(exhausted, dict):
            exhausted = {}
            state["exhausted"] = exhausted
        exhausted[key.name] = {
            "status_code": status_code,
            "exhausted_at": now.isoformat(),
            "cooldown_until": cooldown_until.isoformat(),
        }
        state["current_index"] = self._next_index_after(key)
        state["current_name"] = self.keys[state["current_index"]].name
        state["updated_at"] = now.isoformat()
        self._save_state(state)

    def _now(self) -> datetime:
        if self._now_func is not None:
            return self._now_func()
        return datetime.now(TAIWAN_TIMEZONE)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return state if isinstance(state, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        temp_path = self.state_path.with_name(f"{self.state_path.name}.tmp")
        temp_path.write_text(f"{payload}\n", encoding="utf-8")
        temp_path.replace(self.state_path)

    def _state_current_index(self, state: dict[str, Any]) -> int:
        raw_index = state.get("current_index", 0)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return 0
        if index < 0 or index >= len(self.keys):
            return 0
        return index

    def _next_index_after(self, key: FinMindApiKey) -> int:
        if not self.keys:
            return 0
        return (key.index + 1) % len(self.keys)

    def _is_exhausted(self, key: FinMindApiKey, state: dict[str, Any]) -> bool:
        exhausted = state.get("exhausted", {})
        if not isinstance(exhausted, dict):
            return False
        record = exhausted.get(key.name)
        if not isinstance(record, dict):
            return False
        cooldown_until = _parse_datetime(record.get("cooldown_until"))
        return cooldown_until is not None and cooldown_until > self._now()

    def _clear_expired_exhausted_keys(self, state: dict[str, Any]) -> bool:
        exhausted = state.get("exhausted", {})
        if not isinstance(exhausted, dict):
            return False
        expired = []
        for name, record in exhausted.items():
            if not isinstance(record, dict):
                expired.append(name)
                continue
            cooldown_until = _parse_datetime(record.get("cooldown_until"))
            if cooldown_until is None or cooldown_until <= self._now():
                expired.append(name)
        for name in expired:
            exhausted.pop(name, None)
        return bool(expired)


def _parse_key_record(index: int, record: object) -> FinMindApiKey | None:
    if isinstance(record, str):
        token = record.strip()
        name = f"finmind_{index + 1}"
        enabled = True
    elif isinstance(record, dict):
        enabled = bool(record.get("enabled", True))
        token = str(record.get("token", "")).strip()
        name = str(record.get("name") or f"finmind_{index + 1}").strip()
    else:
        return None

    if not enabled or not token or token == "paste_your_key_here":
        return None
    return FinMindApiKey(index=index, name=name or f"finmind_{index + 1}", token=token)


def _parse_status_codes(value: object, default: set[int]) -> set[int]:
    if not isinstance(value, list):
        return set(default)
    status_codes: set[int] = set()
    for item in value:
        try:
            status_codes.add(int(item))
        except (TypeError, ValueError):
            continue
    return status_codes or set(default)


def _parse_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TAIWAN_TIMEZONE)
    return parsed
