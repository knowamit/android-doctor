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


def _build_uid_to_package_map(adb_path: str | None = None) -> dict[str, str]:
    """Build mapping from UID strings like 'u0a207' to package names."""
    uid_map: dict[str, str] = {}
    try:
        raw = shell("dumpsys package --uid 2>/dev/null || pm list packages -U 2>/dev/null", adb_path=adb_path, timeout=15)
        for line in raw.splitlines():
            line = line.strip()
            # Format: "package:com.example.app uid:10207"
            if "uid:" in line.lower() and "package:" in line.lower():
                try:
                    pkg = line.split("package:")[1].split()[0]
                    uid_num = int(line.split("uid:")[1].split()[0])
                    # Android app UIDs are 10000 + app_id; "u0a207" = user 0, app 207 = uid 10207
                    app_id = uid_num - 10000 if uid_num >= 10000 else uid_num
                    uid_map[f"u0a{app_id}"] = pkg
                    uid_map[str(uid_num)] = pkg
                except (IndexError, ValueError):
                    continue
    except ADBError:
        pass

    # Fallback: parse pm list packages -U directly
    if not uid_map:
        try:
            raw = shell("pm list packages -U", adb_path=adb_path, timeout=15)
            for line in raw.splitlines():
                line = line.strip()
                # "package:com.example.app uid:10207"
                if line.startswith("package:") and "uid:" in line:
                    try:
                        pkg = line.split("package:")[1].split()[0]
                        uid_num = int(line.split("uid:")[1].strip())
                        app_id = uid_num - 10000 if uid_num >= 10000 else uid_num
                        uid_map[f"u0a{app_id}"] = pkg
                        uid_map[str(uid_num)] = pkg
                    except (IndexError, ValueError):
                        continue
        except ADBError:
            pass

    # Known system UIDs
    uid_map.update({
        "1000": "system (android.os)",
        "0": "root (kernel)",
        "1001": "radio (telephony)",
        "1010": "wifi",
        "1021": "media",
        "1036": "log",
        "1066": "nfc",
        "1073": "shell",
        "9999": "nobody",
    })
    return uid_map


def get_top_battery_drainers(adb_path: str | None = None) -> list[tuple[str, float]]:
    """Get top battery-draining packages with estimated drain in mAh.

    Parses the 'Estimated power use' section from dumpsys batterystats.
    Resolves UIDs to human-readable package names.
    """
    try:
        raw = shell(
            "dumpsys batterystats --charged 2>/dev/null",
            adb_path=adb_path,
            timeout=60,
        )
    except ADBError:
        return []

    # Build UID → package name map
    uid_map = _build_uid_to_package_map(adb_path)

    drainers: list[tuple[str, float]] = []
    in_estimated = False

    for line in raw.splitlines():
        stripped = line.strip()
        if "Estimated power use" in stripped:
            in_estimated = True
            continue
        if not in_estimated:
            continue
        # Stop at empty line or next section
        if not stripped:
            break

        # Skip non-UID lines (Global, Capacity, etc.)
        if not stripped.startswith("UID"):
            continue

        # Format: "UID u0a207: 16.0 fg: 0.157 fgs: 0.624 ( cpu=0.796 ... )"
        # Or:     "UID 1000: 71.8 fg: 0.0121 ..."
        try:
            # Extract UID and power
            after_uid = stripped[4:]  # skip "UID "
            uid_str, rest = after_uid.split(":", 1)
            uid_str = uid_str.strip()

            # Power is the first number after the colon
            power_str = rest.strip().split()[0]
            power = float(power_str)

            if power < 0.1:
                continue  # skip negligible entries

            # Resolve UID to package name
            name = uid_map.get(uid_str, uid_str)

            drainers.append((name, power))
        except (IndexError, ValueError):
            continue

    drainers.sort(key=lambda x: -x[1])
    return drainers[:15]
