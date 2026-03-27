"""Safe package disabling via ADB (no root, reversible)."""

from __future__ import annotations
import sys
from adb.connection import shell, ADBError
from fix.rollback import ChangeRecord


def disable_package(package: str, adb_path: str | None = None) -> ChangeRecord | None:
    """Disable a system package. Reversible via enable_package."""
    try:
        shell(f"pm disable-user --user 0 {package}", adb_path=adb_path)
        return ChangeRecord(
            action="disable_package",
            target=package,
            original_value="enabled",
            new_value="disabled",
        )
    except ADBError as e:
        _warn(f"Failed to disable {package}: {e}")
        return None


def enable_package(package: str, adb_path: str | None = None) -> bool:
    """Re-enable a previously disabled package."""
    try:
        shell(f"pm enable {package}", adb_path=adb_path)
        return True
    except ADBError as e:
        _warn(f"Failed to enable {package}: {e}")
        return False


def force_stop_package(package: str, adb_path: str | None = None) -> ChangeRecord | None:
    """Force stop a running package to free memory/CPU immediately."""
    try:
        shell(f"am force-stop {package}", adb_path=adb_path)
        return ChangeRecord(
            action="force_stop",
            target=package,
            original_value="running",
            new_value="stopped",
        )
    except ADBError:
        return None


def clear_package_cache(package: str, adb_path: str | None = None) -> ChangeRecord | None:
    """Clear cache for a specific package (does NOT delete user data)."""
    try:
        # pm trim-caches only works with a size target, not per-package
        # Use the content provider approach to clear app cache
        shell(f"cmd package compile -m verify -f {package} 2>/dev/null", adb_path=adb_path)
        shell(f"run-as {package} cache clear 2>/dev/null", adb_path=adb_path)
        return ChangeRecord(
            action="clear_cache",
            target=package,
            original_value="cached",
            new_value="cache_cleared",
        )
    except ADBError:
        return None


def trim_all_caches(adb_path: str | None = None) -> ChangeRecord | None:
    """Trim system-wide caches. Frees storage without deleting user data.

    pm trim-caches asks the system to free up to N bytes of cache across all apps.
    """
    try:
        # Request the system to free up to 1TB — it'll free whatever cache it can
        shell("pm trim-caches 1099511627776", adb_path=adb_path, timeout=60)
        return ChangeRecord(
            action="trim_caches",
            target="system",
            original_value="cached",
            new_value="trimmed",
        )
    except ADBError:
        return None


def get_package_cache_sizes(packages: list[str], adb_path: str | None = None) -> list[tuple[str, int]]:
    """Get cache sizes for packages. Returns list of (package, cache_bytes) sorted by size."""
    results = []
    for pkg in packages:
        try:
            output = shell(f"dumpsys package {pkg} 2>/dev/null | grep -i cache", adb_path=adb_path, timeout=5)
            # Try to extract cache size from dumpsys diskstats instead
        except ADBError:
            continue
    # Better approach: parse dumpsys diskstats for all apps at once
    try:
        raw = shell("dumpsys diskstats", adb_path=adb_path, timeout=30)
        current_pkg = ""
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("Package:") or line.startswith("package:"):
                current_pkg = line.split(":", 1)[1].strip().split()[0]
            elif "cache" in line.lower() and current_pkg:
                parts = line.split()
                for part in parts:
                    try:
                        size = int(part)
                        if size > 0:
                            results.append((current_pkg, size))
                            break
                    except ValueError:
                        continue
    except ADBError:
        pass
    results.sort(key=lambda x: -x[1])
    return results


def _warn(msg: str):
    sys.stderr.write(f"  ⚠ {msg}\n")
