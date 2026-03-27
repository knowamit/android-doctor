"""High-level ADB command wrappers that return raw text output."""

from __future__ import annotations
from adb.connection import shell, ADBError


def dumpsys_battery(adb_path: str | None = None) -> str:
    return shell("dumpsys battery", adb_path=adb_path)


def battery_sysfs(adb_path: str | None = None) -> dict[str, str]:
    """Read battery sysfs files. Some may fail without root."""
    files = [
        "charge_full", "charge_full_design", "cycle_count",
        "temp", "health", "status", "current_now", "voltage_now",
        "capacity", "technology",
    ]
    result = {}
    for f in files:
        try:
            val = shell(
                f"cat /sys/class/power_supply/battery/{f} 2>/dev/null",
                adb_path=adb_path,
            ).strip()
            if val and "Permission denied" not in val:
                result[f] = val
        except ADBError:
            continue
    return result


def dumpsys_meminfo_summary(adb_path: str | None = None) -> str:
    return shell("dumpsys meminfo", adb_path=adb_path, timeout=60)


def proc_meminfo(adb_path: str | None = None) -> str:
    return shell("cat /proc/meminfo", adb_path=adb_path)


def dumpsys_cpuinfo(adb_path: str | None = None) -> str:
    return shell("dumpsys cpuinfo", adb_path=adb_path)


def top_snapshot(adb_path: str | None = None) -> str:
    return shell("top -n 1 -b -s cpu 2>/dev/null || top -n 1 -b", adb_path=adb_path, timeout=15)


def thermal_zones(adb_path: str | None = None) -> str:
    """Read all thermal zone temps and types. Falls back to thermalservice."""
    # Method 1: sysfs thermal zones (works on most devices)
    try:
        script = (
            "for zone in /sys/class/thermal/thermal_zone*; do "
            "type=$(cat $zone/type 2>/dev/null); "
            "temp=$(cat $zone/temp 2>/dev/null); "
            "[ -n \"$type\" ] && [ -n \"$temp\" ] && echo \"$type:$temp\"; "
            "done"
        )
        result = shell(script, adb_path=adb_path).strip()
        if result and ":" in result and "*" not in result:
            return result
    except ADBError:
        pass

    # Method 2: dumpsys thermalservice (Pixel, newer Android)
    try:
        raw = shell("dumpsys thermalservice 2>/dev/null", adb_path=adb_path)
        return _parse_thermal_service_to_zones(raw)
    except ADBError:
        pass

    # Method 3: HW thermal HAL (some Qualcomm devices)
    try:
        raw = shell("dumpsys android.hardware.thermal@2.0::IThermal/default 2>/dev/null", adb_path=adb_path)
        if raw.strip():
            return _parse_thermal_hal_to_zones(raw)
    except ADBError:
        pass

    return ""


def _parse_thermal_service_to_zones(raw: str) -> str:
    """Extract temperature readings from dumpsys thermalservice output."""
    lines = []
    in_temps = False
    for line in raw.splitlines():
        line = line.strip()
        # Look for temperature entries like: "skin : 35.2" or "Temperature{mValue=35.2, mName=skin"
        if "Temperature" in line and "mValue" in line and "mName" in line:
            try:
                name = ""
                temp = ""
                for part in line.split(","):
                    part = part.strip()
                    if "mName=" in part:
                        name = part.split("mName=")[1].strip().rstrip("}")
                    elif "mValue=" in part:
                        temp_val = part.split("mValue=")[1].strip()
                        temp = str(int(float(temp_val) * 1000))  # convert to millidegrees
                if name and temp:
                    lines.append(f"{name}:{temp}")
            except (ValueError, IndexError):
                continue
        # Simpler format: "Current temperatures from HAL:" followed by "name : value"
        if "Current temperatures" in line:
            in_temps = True
            continue
        if in_temps and ":" in line and not line.startswith("Current") and not line.startswith("---"):
            parts = line.split(":")
            if len(parts) == 2:
                name = parts[0].strip()
                try:
                    temp_c = float(parts[1].strip())
                    if 0 < temp_c < 150:
                        lines.append(f"{name}:{int(temp_c * 1000)}")
                except ValueError:
                    continue
    return "\n".join(lines)


def _parse_thermal_hal_to_zones(raw: str) -> str:
    """Extract temperature from thermal HAL dump."""
    lines = []
    for line in raw.splitlines():
        # Format varies: "Name: skin, Temperature: 35.2" etc.
        if "Temperature" in line and ("Name" in line or "name" in line):
            try:
                name = ""
                temp = ""
                parts = line.split(",")
                for part in parts:
                    part = part.strip()
                    if "Name" in part or "name" in part:
                        name = part.split(":")[1].strip() if ":" in part else ""
                    if "Temperature" in part or "temperature" in part:
                        temp_str = part.split(":")[1].strip() if ":" in part else ""
                        temp = str(int(float(temp_str) * 1000))
                if name and temp:
                    lines.append(f"{name}:{temp}")
            except (ValueError, IndexError):
                continue
    return "\n".join(lines)


def df_storage(adb_path: str | None = None) -> str:
    return shell("df", adb_path=adb_path)


def dumpsys_diskstats(adb_path: str | None = None) -> str:
    return shell("dumpsys diskstats", adb_path=adb_path, timeout=60)


def storage_benchmark(adb_path: str | None = None) -> str:
    """Run built-in storage benchmark. Can take a while."""
    try:
        return shell("sm benchmark", adb_path=adb_path, timeout=120)
    except ADBError:
        return ""


def emmc_health(adb_path: str | None = None) -> dict[str, str]:
    """Read eMMC health from sysfs."""
    result = {}
    paths = {
        "life_time": "cat /sys/class/mmc_host/mmc0/mmc0:*/life_time 2>/dev/null",
        "pre_eol_info": "cat /sys/class/mmc_host/mmc0/mmc0:*/pre_eol_info 2>/dev/null",
    }
    for key, cmd in paths.items():
        try:
            val = shell(cmd, adb_path=adb_path).strip()
            if val and "Permission denied" not in val and "No such file" not in val:
                result[key] = val
        except ADBError:
            continue
    return result


def ufs_health(adb_path: str | None = None) -> dict[str, str]:
    """Read UFS health descriptors."""
    result = {}
    for key in ["life_time_estimation_a", "life_time_estimation_b"]:
        try:
            val = shell(
                f"cat /sys/devices/platform/*/health_descriptor/{key} 2>/dev/null",
                adb_path=adb_path,
            ).strip()
            if val and "Permission denied" not in val and "No such file" not in val:
                result[key] = val
        except ADBError:
            continue
    return result


def dumpsys_storaged(adb_path: str | None = None) -> str:
    try:
        return shell("dumpsys storaged 2>/dev/null", adb_path=adb_path, timeout=30)
    except ADBError:
        return ""


def block_device_stats(adb_path: str | None = None) -> str:
    try:
        return shell("cat /sys/block/*/stat 2>/dev/null", adb_path=adb_path)
    except ADBError:
        return ""


def list_packages_system(adb_path: str | None = None) -> list[str]:
    """List all system (pre-installed) packages."""
    output = shell("pm list packages -s", adb_path=adb_path)
    return [
        line.replace("package:", "").strip()
        for line in output.splitlines()
        if line.startswith("package:")
    ]


def list_packages_third_party(adb_path: str | None = None) -> list[str]:
    """List user-installed packages."""
    output = shell("pm list packages -3", adb_path=adb_path)
    return [
        line.replace("package:", "").strip()
        for line in output.splitlines()
        if line.startswith("package:")
    ]


def list_packages_disabled(adb_path: str | None = None) -> list[str]:
    """List already-disabled packages."""
    output = shell("pm list packages -d", adb_path=adb_path)
    return [
        line.replace("package:", "").strip()
        for line in output.splitlines()
        if line.startswith("package:")
    ]


def list_packages_all(adb_path: str | None = None) -> list[str]:
    """List all packages."""
    output = shell("pm list packages", adb_path=adb_path)
    return [
        line.replace("package:", "").strip()
        for line in output.splitlines()
        if line.startswith("package:")
    ]


def get_running_services(adb_path: str | None = None) -> str:
    return shell("dumpsys activity services", adb_path=adb_path, timeout=30)


def get_animation_scales(adb_path: str | None = None) -> dict[str, str]:
    """Get current animation scale settings."""
    scales = {}
    for setting in ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"]:
        try:
            val = shell(f"settings get global {setting}", adb_path=adb_path).strip()
            scales[setting] = val
        except ADBError:
            scales[setting] = "unknown"
    return scales


def get_background_process_limit(adb_path: str | None = None) -> str:
    try:
        return shell("settings get global background_process_limit 2>/dev/null", adb_path=adb_path).strip()
    except ADBError:
        return "unknown"


def get_loadavg(adb_path: str | None = None) -> str:
    try:
        return shell("cat /proc/loadavg", adb_path=adb_path).strip()
    except ADBError:
        return ""
