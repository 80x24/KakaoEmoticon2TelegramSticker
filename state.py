import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Set

STATE_PATH = Path(__file__).parent / "state.json"


def _load() -> dict:
    if not STATE_PATH.exists():
        return {"owner_id": None, "whitelist": []}
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save(state: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=STATE_PATH.parent, prefix=".state.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_PATH)


def get_owner() -> Optional[int]:
    return _load().get("owner_id")


def set_owner(user_id: int) -> bool:
    state = _load()
    if state.get("owner_id") is not None:
        return False
    state["owner_id"] = user_id
    _save(state)
    return True


def get_whitelist() -> Set[int]:
    return set(_load().get("whitelist", []))


def add_to_whitelist(user_id: int) -> bool:
    state = _load()
    wl = state.setdefault("whitelist", [])
    if user_id in wl:
        return False
    wl.append(user_id)
    _save(state)
    return True


def remove_from_whitelist(user_id: int) -> bool:
    state = _load()
    wl = state.setdefault("whitelist", [])
    if user_id not in wl:
        return False
    wl.remove(user_id)
    _save(state)
    return True


def is_authorized(user_id: int) -> bool:
    state = _load()
    owner = state.get("owner_id")
    if owner is None:
        return False
    if user_id == owner:
        return True
    return user_id in state.get("whitelist", [])
