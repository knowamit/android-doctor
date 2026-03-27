"""Parse raw ADB output into structured data."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BatteryData:
    level: int = 0
    temperature_c: float = 0.0
    voltage_mv: int = 0
    health: str = "unknown"
    status: str = "unknown"
    technology: str = "unknown"
    cycle_count: int = -1  # -1 = unavailable
    charge_full_uah: int = -1
    charge_full_design_uah: int = -1
    health_pct: float = -1.0  # calculated


@dataclass(frozen=True)
class MemoryData:
    total_mb: int = 0
    available_mb: int = 0
    free_mb: int = 0
    cached_mb: int = 0
    swap_total_mb: int = 0
    swap_free_mb: int = 0
    used_pct: float = 0.0


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    cpu_pct: float
    mem_kb: int = 0


@dataclass(frozen=True)
class CpuData:
    total_load_pct: float = 0.0
    top_processes: tuple[ProcessInfo, ...] = ()
    load_avg_1: float = 0.0
    load_avg_5: float = 0.0
    load_avg_15: float = 0.0


@dataclass(frozen=True)
class ThermalZone:
    name: str
    temp_c: float


@dataclass(frozen=True)
class StoragePartition:
    mount: str
    total_mb: int
    used_mb: int
    available_mb: int
    use_pct: float


@dataclass(frozen=True)
class StorageHealthData:
    storage_type: str = "unknown"  # emmc | ufs | unknown
    life_used_pct: float = -1.0  # -1 = unavailable
    pre_eol: str = "unknown"  # normal | warning | urgent | unknown
    partitions: tuple[StoragePartition, ...] = ()


def parse_battery(dumpsys_output: str, sysfs: dict[str, str]) -> BatteryData:
    """Parse battery data from dumpsys + sysfs."""
    props: dict[str, str] = {}
    for line in dumpsys_output.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            props[key.strip().lower()] = val.strip()

    level = int(props.get("level", "0"))
    raw_temp = int(props.get("temperature", "0"))
    temperature_c = raw_temp / 10.0
    voltage_mv = int(props.get("voltage", "0"))
    health_str = props.get("health", "unknown").lower()
    health_map = {"2": "good", "3": "overheat", "4": "dead", "5": "over-voltage", "6": "failure", "7": "cold"}
    health = health_map.get(health_str, health_str)
    status_str = props.get("status", "unknown").lower()
    status_map = {"2": "charging", "3": "discharging", "5": "full", "4": "not charging"}
    status = status_map.get(status_str, status_str)
    technology = props.get("technology", sysfs.get("technology", "unknown"))

    cycle_count = int(sysfs["cycle_count"]) if "cycle_count" in sysfs else -1
    charge_full = int(sysfs["charge_full"]) if "charge_full" in sysfs else -1
    charge_full_design = int(sysfs["charge_full_design"]) if "charge_full_design" in sysfs else -1

    health_pct = -1.0
    if charge_full > 0 and charge_full_design > 0:
        health_pct = round((charge_full / charge_full_design) * 100, 1)

    return BatteryData(
        level=level,
        temperature_c=temperature_c,
        voltage_mv=voltage_mv,
        health=health,
        status=status,
        technology=technology,
        cycle_count=cycle_count,
        charge_full_uah=charge_full,
        charge_full_design_uah=charge_full_design,
        health_pct=health_pct,
    )


def parse_memory(proc_meminfo_output: str) -> MemoryData:
    """Parse /proc/meminfo."""
    vals: dict[str, int] = {}
    for line in proc_meminfo_output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            key = parts[0].rstrip(":")
            try:
                vals[key] = int(parts[1])
            except ValueError:
                continue

    total_kb = vals.get("MemTotal", 0)
    available_kb = vals.get("MemAvailable", 0)
    free_kb = vals.get("MemFree", 0)
    cached_kb = vals.get("Cached", 0)
    swap_total_kb = vals.get("SwapTotal", 0)
    swap_free_kb = vals.get("SwapFree", 0)

    total_mb = total_kb // 1024
    used_pct = ((total_kb - available_kb) / total_kb * 100) if total_kb > 0 else 0

    return MemoryData(
        total_mb=total_mb,
        available_mb=available_kb // 1024,
        free_mb=free_kb // 1024,
        cached_mb=cached_kb // 1024,
        swap_total_mb=swap_total_kb // 1024,
        swap_free_mb=swap_free_kb // 1024,
        used_pct=round(used_pct, 1),
    )


def parse_cpu(dumpsys_output: str, loadavg: str) -> CpuData:
    """Parse CPU info from dumpsys cpuinfo.

    CPU percentages in dumpsys are per-core, so a single process can show >100%
    on multi-core devices. We normalize total to 0-100 range using core count.
    """
    processes = []
    total_load = 0.0
    load1 = load5 = load15 = 0.0
    num_cores = 0

    for line in dumpsys_output.splitlines():
        line = line.strip()
        if not line:
            continue

        # "Load: 40.21 / 37.55 / 18.26"
        if line.startswith("Load:"):
            parts = line.replace("Load:", "").strip().split("/")
            if len(parts) >= 3:
                try:
                    load1 = float(parts[0].strip())
                    load5 = float(parts[1].strip())
                    load15 = float(parts[2].strip())
                except ValueError:
                    pass
            continue

        if line.startswith("CPU usage"):
            continue

        # Lines like: "105% 2008/system_server: 67% user + 37% kernel / faults: ..."
        if "%" in line and "/" in line:
            try:
                pct_str = line.split("%")[0].strip()
                cpu_pct = float(pct_str)
                total_load += cpu_pct
                after_pct = line.split("%", 1)[1].strip()
                pid_name = after_pct.split(":")[0].strip()
                if "/" in pid_name:
                    pid_str, name = pid_name.split("/", 1)
                    pid = int(pid_str.strip())
                    processes.append(ProcessInfo(pid=pid, name=name.strip(), cpu_pct=cpu_pct))
            except (ValueError, IndexError):
                continue

    # Fallback: parse /proc/loadavg if dumpsys didn't have Load: line
    if load1 == 0 and loadavg:
        parts = loadavg.split()
        if len(parts) >= 3:
            try:
                load1 = float(parts[0])
                load5 = float(parts[1])
                load15 = float(parts[2])
            except ValueError:
                pass

    # Estimate core count from total load ceiling (if total >100, multi-core)
    if total_load > 100:
        # Rough core estimate: round up total/100
        num_cores = max(1, int(total_load / 100) + 1)
        # Normalize to 0-100% of total CPU capacity
        normalized_load = round(total_load / num_cores, 1)
    else:
        normalized_load = round(total_load, 1)

    top_procs = tuple(sorted(processes, key=lambda p: p.cpu_pct, reverse=True)[:10])
    return CpuData(
        total_load_pct=normalized_load,
        top_processes=top_procs,
        load_avg_1=load1,
        load_avg_5=load5,
        load_avg_15=load15,
    )


def parse_thermal(thermal_output: str) -> tuple[ThermalZone, ...]:
    """Parse thermal zone readings."""
    zones = []
    for line in thermal_output.splitlines():
        line = line.strip()
        if ":" in line:
            name, _, temp_str = line.partition(":")
            name = name.strip()
            temp_str = temp_str.strip()
            if temp_str and name:
                try:
                    raw_temp = int(temp_str)
                    # Temps are in millidegrees
                    temp_c = raw_temp / 1000.0 if raw_temp > 200 else float(raw_temp)
                    if 0 < temp_c < 150:  # sanity check
                        zones.append(ThermalZone(name=name, temp_c=round(temp_c, 1)))
                except ValueError:
                    continue
    return tuple(zones)


def parse_df(df_output: str) -> tuple[StoragePartition, ...]:
    """Parse df output into partition info."""
    partitions = []
    for line in df_output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        # Skip header
        if parts[0] == "Filesystem":
            continue
        try:
            mount = parts[-1] if not parts[-1].endswith("%") else parts[0]
            # df on android outputs in 1K blocks or bytes — varies by device
            # Try to find numeric columns
            nums = [p for p in parts[1:] if p.replace("%", "").isdigit()]
            if len(nums) >= 3:
                total = int(nums[0])
                used = int(nums[1])
                available = int(nums[2])
                # Convert from KB to MB
                total_mb = total // 1024
                used_mb = used // 1024
                avail_mb = available // 1024
                use_pct = (used / total * 100) if total > 0 else 0
                if total_mb > 0:
                    partitions.append(StoragePartition(
                        mount=mount,
                        total_mb=total_mb,
                        used_mb=used_mb,
                        available_mb=avail_mb,
                        use_pct=round(use_pct, 1),
                    ))
        except (ValueError, IndexError):
            continue
    return tuple(partitions)


def parse_storage_health(
    storage_type: str,
    emmc_data: dict[str, str],
    ufs_data: dict[str, str],
    df_output: str,
) -> StorageHealthData:
    """Parse storage health from eMMC/UFS sysfs + df."""
    partitions = parse_df(df_output)
    life_used_pct = -1.0
    pre_eol = "unknown"

    if storage_type == "emmc" and emmc_data:
        # life_time: "0x03 0x03" — hex values, each in 10% increments
        if "life_time" in emmc_data:
            parts = emmc_data["life_time"].split()
            if parts:
                try:
                    hex_val = int(parts[0], 16)
                    life_used_pct = hex_val * 10.0  # 0x03 = 30%
                except ValueError:
                    pass
        if "pre_eol_info" in emmc_data:
            raw = emmc_data["pre_eol_info"].strip()
            try:
                eol_val = int(raw, 16) if raw.startswith("0x") else int(raw)
                pre_eol = {1: "normal", 2: "warning", 3: "urgent"}.get(eol_val, "unknown")
            except ValueError:
                pass
    elif storage_type == "ufs" and ufs_data:
        for key in ["life_time_estimation_a", "life_time_estimation_b"]:
            if key in ufs_data:
                try:
                    raw = ufs_data[key].strip()
                    hex_val = int(raw, 16) if raw.startswith("0x") else int(raw)
                    life_used_pct = hex_val * 10.0
                    break
                except ValueError:
                    continue

    return StorageHealthData(
        storage_type=storage_type,
        life_used_pct=life_used_pct,
        pre_eol=pre_eol,
        partitions=partitions,
    )
