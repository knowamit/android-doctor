"""ADB device detection and connection management."""

from __future__ import annotations
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    model: str
    brand: str
    manufacturer: str
    android_version: str
    sdk_version: str
    chipset: str
    total_ram_mb: int
    storage_type: str  # "emmc" | "ufs" | "unknown"
    build_display: str


class ADBError(Exception):
    pass


class NoDeviceError(ADBError):
    pass


class MultipleDevicesError(ADBError):
    pass


def find_adb() -> str:
    """Find ADB binary on the system."""
    path = shutil.which("adb")
    if path:
        return path
    common_paths = [
        "/Users/macbookpro/Library/Android/sdk/platform-tools/adb",
        "/usr/local/bin/adb",
        "/opt/homebrew/bin/adb",
    ]
    for p in common_paths:
        try:
            result = subprocess.run(
                [p, "version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise ADBError(
        "ADB not found. Install Android SDK Platform Tools:\n"
        "  macOS:   brew install android-platform-tools\n"
        "  Linux:   sudo apt install adb\n"
        "  Windows: choco install adb"
    )


def run_adb(args: list[str], adb_path: str | None = None, timeout: int = 30) -> str:
    """Run an ADB command and return stdout."""
    adb = adb_path or find_adb()
    try:
        result = subprocess.run(
            [adb] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ADBError(f"ADB command timed out: adb {' '.join(args)}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "no devices" in stderr or "device not found" in stderr:
            raise NoDeviceError(
                "No Android device found. Make sure:\n"
                "  1. USB debugging is enabled on your phone\n"
                "  2. Phone is connected via USB\n"
                "  3. You accepted the USB debugging prompt on the phone"
            )
        if "more than one device" in stderr:
            raise MultipleDevicesError(
                "Multiple devices connected. Disconnect extras or specify device serial."
            )
        raise ADBError(f"ADB error: {stderr}")
    return result.stdout


def shell(cmd: str, adb_path: str | None = None, timeout: int = 30) -> str:
    """Run a shell command on the connected device."""
    return run_adb(["shell", cmd], adb_path=adb_path, timeout=timeout)


def get_prop(prop: str, adb_path: str | None = None) -> str:
    """Get a single system property."""
    return shell(f"getprop {prop}", adb_path=adb_path).strip()


def _detect_storage_type(adb_path: str | None = None) -> str:
    """Detect whether device uses eMMC or UFS storage."""
    try:
        # Method 1: UFS block devices (sda, sdb, etc.) — most reliable
        # UFS exposes multiple scsi-like block devices; eMMC uses mmcblk0
        block_devs = shell("ls /sys/block/ 2>/dev/null", adb_path=adb_path).strip()
        if block_devs:
            devs = block_devs.split()
            has_sda = any(d.startswith("sd") for d in devs)
            has_mmcblk = any(d.startswith("mmcblk") for d in devs)
            if has_sda and not has_mmcblk:
                return "ufs"
            if has_mmcblk and not has_sda:
                return "emmc"

        # Method 2: UFS health descriptor path
        ufs_health = shell(
            "ls /sys/devices/platform/*/health_descriptor/ 2>/dev/null | head -1",
            adb_path=adb_path,
        )
        if ufs_health.strip():
            return "ufs"

        # Method 3: eMMC sysfs
        emmc_check = shell(
            "ls /sys/class/mmc_host/mmc0/ 2>/dev/null | head -1",
            adb_path=adb_path,
        )
        if emmc_check.strip():
            return "emmc"
    except ADBError:
        pass
    return "unknown"


def _get_total_ram(adb_path: str | None = None) -> int:
    """Get total RAM in MB."""
    try:
        meminfo = shell("cat /proc/meminfo", adb_path=adb_path)
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return kb // 1024
    except (ADBError, ValueError, IndexError):
        pass
    return 0


def detect_device(adb_path: str | None = None) -> DeviceInfo:
    """Detect connected device and gather basic info."""
    adb = adb_path or find_adb()

    # Verify device is connected
    devices_output = run_adb(["devices"], adb_path=adb)
    connected = [
        line.split("\t")
        for line in devices_output.strip().splitlines()[1:]
        if "\tdevice" in line
    ]
    if not connected:
        raise NoDeviceError(
            "No Android device found. Make sure:\n"
            "  1. USB debugging is enabled on your phone\n"
            "  2. Phone is connected via USB\n"
            "  3. You accepted the USB debugging prompt on the phone"
        )
    if len(connected) > 1:
        raise MultipleDevicesError(
            "Multiple devices connected. Disconnect extras or specify device serial."
        )

    serial = connected[0][0]

    return DeviceInfo(
        serial=serial,
        model=get_prop("ro.product.model", adb),
        brand=get_prop("ro.product.brand", adb),
        manufacturer=get_prop("ro.product.manufacturer", adb),
        android_version=get_prop("ro.build.version.release", adb),
        sdk_version=get_prop("ro.build.version.sdk", adb),
        chipset=get_prop("ro.hardware.chipname", adb) or get_prop("ro.hardware", adb),
        total_ram_mb=_get_total_ram(adb),
        storage_type=_detect_storage_type(adb),
        build_display=get_prop("ro.build.display.id", adb),
    )
