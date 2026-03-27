"""Snapshot and rollback system for all changes made by android-doctor."""

from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field, asdict


SNAPSHOT_DIR = os.path.expanduser("~/.android-doctor")
SNAPSHOT_FILE = os.path.join(SNAPSHOT_DIR, "rollback_snapshot.json")


@dataclass
class ChangeRecord:
    action: str  # "disable_package" | "set_setting" | "restrict_background" | "force_stop"
    target: str  # package name or setting key
    original_value: str  # value before change
    new_value: str  # value after change
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class Snapshot:
    device_serial: str
    device_model: str
    created_at: float
    changes: list[ChangeRecord] = field(default_factory=list)


def _ensure_dir():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def save_snapshot(snapshot: Snapshot):
    """Save snapshot to disk."""
    _ensure_dir()
    data = {
        "device_serial": snapshot.device_serial,
        "device_model": snapshot.device_model,
        "created_at": snapshot.created_at,
        "changes": [asdict(c) for c in snapshot.changes],
    }
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_snapshot() -> Snapshot | None:
    """Load existing snapshot from disk."""
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    with open(SNAPSHOT_FILE) as f:
        data = json.load(f)
    return Snapshot(
        device_serial=data["device_serial"],
        device_model=data["device_model"],
        created_at=data["created_at"],
        changes=[ChangeRecord(**c) for c in data["changes"]],
    )


def delete_snapshot():
    """Remove snapshot file after successful rollback."""
    if os.path.exists(SNAPSHOT_FILE):
        os.remove(SNAPSHOT_FILE)


def has_snapshot() -> bool:
    return os.path.exists(SNAPSHOT_FILE)
