"""System settings optimization via ADB."""

from __future__ import annotations
from adb.connection import shell, ADBError
from fix.rollback import ChangeRecord


def set_animation_scale(scale: str, adb_path: str | None = None) -> list[ChangeRecord]:
    """Set all animation scales. '0.5' = snappier, '0' = instant."""
    records = []
    settings = [
        "window_animation_scale",
        "transition_animation_scale",
        "animator_duration_scale",
    ]
    for setting in settings:
        try:
            original = shell(f"settings get global {setting}", adb_path=adb_path).strip()
            shell(f"settings put global {setting} {scale}", adb_path=adb_path)
            records.append(ChangeRecord(
                action="set_setting",
                target=f"global:{setting}",
                original_value=original,
                new_value=scale,
            ))
        except ADBError:
            continue
    return records


def set_background_process_limit(limit: int, adb_path: str | None = None) -> ChangeRecord | None:
    """Limit background processes. 0=no bg, 1-4=limited, -1=default (no limit)."""
    try:
        original = shell("settings get global background_process_limit", adb_path=adb_path).strip()
        if original == "null":
            original = "-1"
        shell(f"settings put global background_process_limit {limit}", adb_path=adb_path)
        return ChangeRecord(
            action="set_setting",
            target="global:background_process_limit",
            original_value=original,
            new_value=str(limit),
        )
    except ADBError:
        return None


def set_always_finish_activities(enabled: bool, adb_path: str | None = None) -> ChangeRecord | None:
    """When enabled, finishes activities as soon as user leaves them (frees RAM faster)."""
    try:
        original = shell("settings get global always_finish_activities", adb_path=adb_path).strip()
        new_val = "1" if enabled else "0"
        shell(f"settings put global always_finish_activities {new_val}", adb_path=adb_path)
        return ChangeRecord(
            action="set_setting",
            target="global:always_finish_activities",
            original_value=original,
            new_value=new_val,
        )
    except ADBError:
        return None


def disable_hw_overlays(adb_path: str | None = None) -> ChangeRecord | None:
    """Disable HW overlays — forces GPU rendering for consistent performance."""
    try:
        original = shell("settings get global disable_hw_overlays 2>/dev/null || echo 0", adb_path=adb_path).strip()
        shell("settings put global disable_hw_overlays 1", adb_path=adb_path)
        return ChangeRecord(
            action="set_setting",
            target="global:disable_hw_overlays",
            original_value=original,
            new_value="1",
        )
    except ADBError:
        return None


def restore_setting(target: str, value: str, adb_path: str | None = None) -> bool:
    """Restore a setting to its original value."""
    try:
        namespace, key = target.split(":", 1)
        if value in ("-1", "null"):
            shell(f"settings delete {namespace} {key}", adb_path=adb_path)
        else:
            shell(f"settings put {namespace} {key} {value}", adb_path=adb_path)
        return True
    except (ADBError, ValueError):
        return False
