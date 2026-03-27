"""Battery optimization fixes via ADB."""

from __future__ import annotations
import sys
from adb.connection import shell, ADBError
from fix.rollback import ChangeRecord


def get_battery_drain_stats(adb_path: str | None = None) -> list[dict]:
    """Get top battery draining apps from batterystats."""
    try:
        raw = shell("dumpsys batterystats --charged 2>/dev/null | grep 'Uid '", adb_path=adb_path, timeout=30)
        entries = []
        for line in raw.splitlines():
            line = line.strip()
            if "Uid" in line and ":" in line:
                try:
                    parts = line.split(":")
                    uid_part = parts[0].strip()
                    rest = ":".join(parts[1:]).strip()
                    entries.append({"uid": uid_part, "detail": rest})
                except (IndexError, ValueError):
                    continue
        return entries
    except ADBError:
        return []


def get_wakelock_hogs(adb_path: str | None = None) -> list[dict]:
    """Identify apps holding excessive wakelocks (battery drainers)."""
    try:
        raw = shell(
            "dumpsys power 2>/dev/null | grep -A1 'Wake Lock'",
            adb_path=adb_path,
            timeout=15,
        )
        wakelocks = []
        for line in raw.splitlines():
            line = line.strip()
            if "Wake Lock" in line or "PARTIAL_WAKE_LOCK" in line:
                wakelocks.append({"detail": line})
        return wakelocks
    except ADBError:
        return []


def restrict_background_data(package: str, adb_path: str | None = None) -> ChangeRecord | None:
    """Restrict background data usage for a package (reduces battery drain from syncing)."""
    try:
        # Check current state
        current = shell(f"cmd netpolicy get restrict-background-whitelist {package} 2>/dev/null", adb_path=adb_path).strip()
        shell(f"cmd appops set {package} RUN_IN_BACKGROUND deny", adb_path=adb_path)
        return ChangeRecord(
            action="restrict_background",
            target=package,
            original_value="allowed",
            new_value="denied",
        )
    except ADBError:
        return None


def unrestrict_background(package: str, adb_path: str | None = None) -> bool:
    """Restore background activity for a package."""
    try:
        shell(f"cmd appops set {package} RUN_IN_BACKGROUND allow", adb_path=adb_path)
        return True
    except ADBError:
        return False


def set_battery_saver_mode(enabled: bool, adb_path: str | None = None) -> ChangeRecord | None:
    """Toggle battery saver mode."""
    try:
        current = shell("settings get global low_power", adb_path=adb_path).strip()
        new_val = "1" if enabled else "0"
        shell(f"settings put global low_power {new_val}", adb_path=adb_path)
        return ChangeRecord(
            action="set_setting",
            target="global:low_power",
            original_value=current,
            new_value=new_val,
        )
    except ADBError:
        return None


def optimize_doze(adb_path: str | None = None) -> list[ChangeRecord]:
    """Optimize Doze mode for aggressive battery saving."""
    records = []
    settings_to_optimize = [
        # Reduce screen timeout to 30s
        ("system:screen_off_timeout", "30000"),
        # Disable adaptive brightness processing (saves CPU)
        ("system:screen_brightness_mode", "0"),
    ]
    for target, new_val in settings_to_optimize:
        try:
            namespace, key = target.split(":", 1)
            original = shell(f"settings get {namespace} {key}", adb_path=adb_path).strip()
            shell(f"settings put {namespace} {key} {new_val}", adb_path=adb_path)
            records.append(ChangeRecord(
                action="set_setting",
                target=target,
                original_value=original,
                new_value=new_val,
            ))
        except (ADBError, ValueError):
            continue
    return records


def disable_location_for_package(package: str, adb_path: str | None = None) -> ChangeRecord | None:
    """Revoke location permission for a non-essential package."""
    try:
        shell(f"pm revoke {package} android.permission.ACCESS_FINE_LOCATION 2>/dev/null", adb_path=adb_path)
        shell(f"pm revoke {package} android.permission.ACCESS_COARSE_LOCATION 2>/dev/null", adb_path=adb_path)
        return ChangeRecord(
            action="revoke_location",
            target=package,
            original_value="granted",
            new_value="revoked",
        )
    except ADBError:
        return None


def grant_location_for_package(package: str, adb_path: str | None = None) -> bool:
    """Restore location permissions."""
    try:
        shell(f"pm grant {package} android.permission.ACCESS_FINE_LOCATION 2>/dev/null", adb_path=adb_path)
        shell(f"pm grant {package} android.permission.ACCESS_COARSE_LOCATION 2>/dev/null", adb_path=adb_path)
        return True
    except ADBError:
        return False


def get_top_battery_drainers(adb_path: str | None = None) -> list[tuple[str, float]]:
    """Get top battery-draining packages with estimated drain percentage.

    Parses dumpsys batterystats for per-app power consumption.
    """
    try:
        raw = shell(
            "dumpsys batterystats --charged 2>/dev/null",
            adb_path=adb_path,
            timeout=60,
        )
        drainers = []
        in_estimated = False
        for line in raw.splitlines():
            stripped = line.strip()
            if "Estimated power use" in stripped:
                in_estimated = True
                continue
            if in_estimated:
                if not stripped or stripped.startswith("---"):
                    break
                # Format: "Uid u0a123: 45.2 ( cpu=30.1 wifi=10.2 ... ) Pkg com.example.app"
                if "Uid" in stripped and "Pkg" in stripped:
                    try:
                        power_str = stripped.split(":")[1].strip().split("(")[0].strip()
                        power = float(power_str)
                        pkg = stripped.split("Pkg")[1].strip().split()[0]
                        drainers.append((pkg, power))
                    except (IndexError, ValueError):
                        continue
                # Simpler format: "Uid u0a123: 45.2"
                elif "Uid" in stripped:
                    try:
                        power_str = stripped.split(":")[1].strip().split()[0]
                        power = float(power_str)
                        # No package name in this format
                        uid = stripped.split(":")[0].strip()
                        drainers.append((uid, power))
                    except (IndexError, ValueError):
                        continue

        drainers.sort(key=lambda x: -x[1])
        return drainers[:15]
    except ADBError:
        return []
