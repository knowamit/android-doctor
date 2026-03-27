"""Benchmark: measure real-world performance metrics that users can feel."""

from __future__ import annotations
import time
import re
from dataclasses import dataclass
from adb.connection import shell, ADBError


@dataclass(frozen=True)
class AppLaunchResult:
    package: str
    activity: str
    total_time_ms: int  # -1 if failed
    status: str  # "ok" | "not_installed" | "error"


@dataclass(frozen=True)
class BenchmarkResult:
    timestamp: float
    app_launches: tuple[AppLaunchResult, ...]
    ram_available_mb: int
    ram_used_pct: float
    swap_used_mb: int
    cpu_load_1: float
    io_seq_read_mbps: float  # -1 if unavailable
    io_seq_write_mbps: float
    io_rand_read_iops: float  # -1 if unavailable
    io_rand_write_iops: float
    running_process_count: int
    label: str  # "before" | "after" | "baseline" | custom


# Apps to benchmark — common apps most people have installed
BENCHMARK_APPS = [
    ("com.google.android.gm", "com.google.android.gm/.ConversationListActivityGmail"),
    ("com.google.android.apps.photos", "com.google.android.apps.photos/.home.HomeActivity"),
    ("com.android.settings", "com.android.settings/.Settings"),
    ("com.google.android.youtube", "com.google.android.youtube/.HomeActivity"),
    ("com.google.android.apps.maps", "com.google.android.apps.maps/.MapsActivity"),
    ("com.whatsapp", "com.whatsapp/.Main"),
    ("com.whatsapp.w4b", "com.whatsapp.w4b/.Main"),
    ("com.instagram.android", "com.instagram.android/.activity.MainTabActivity"),
    ("com.google.android.dialer", "com.google.android.dialer/.extensions.GoogleDialtactsActivity"),
    ("com.android.chrome", "com.android.chrome/com.google.android.apps.chrome.Main"),
]


def measure_app_launch(package: str, activity: str, adb_path: str | None = None) -> AppLaunchResult:
    """Measure cold launch time for an app using `am start -W`.

    Force-stops the app first to ensure cold start measurement.
    """
    # Check if installed
    try:
        check = shell(f"pm path {package} 2>/dev/null", adb_path=adb_path).strip()
        if not check:
            return AppLaunchResult(package=package, activity=activity, total_time_ms=-1, status="not_installed")
    except ADBError:
        return AppLaunchResult(package=package, activity=activity, total_time_ms=-1, status="not_installed")

    try:
        # Force stop for cold launch
        shell(f"am force-stop {package}", adb_path=adb_path)
        time.sleep(0.5)

        # Launch with timing
        output = shell(f"am start -W -n {activity} 2>&1", adb_path=adb_path, timeout=15)

        # Parse TotalTime from output: "TotalTime: 1234"
        match = re.search(r"TotalTime:\s*(\d+)", output)
        if match:
            total_ms = int(match.group(1))
            # Force stop again to clean up
            shell(f"am force-stop {package}", adb_path=adb_path)
            return AppLaunchResult(package=package, activity=activity, total_time_ms=total_ms, status="ok")

        return AppLaunchResult(package=package, activity=activity, total_time_ms=-1, status="error")
    except ADBError:
        return AppLaunchResult(package=package, activity=activity, total_time_ms=-1, status="error")


def _parse_dd_speed(output: str) -> float:
    """Parse speed from dd output. Handles multiple formats:
    - '871 M/s'  '1.2 G/s'  '500 K/s'
    - '104857600 bytes/sec'  '104857600 B/s'
    - '100 MB/s'
    - '10485760 bytes (10 M) copied, 0.011 s, 871 M/s'
    """
    # Format: "X.X G/s"
    match = re.search(r"(\d+(?:\.\d+)?)\s*G/s", output)
    if match:
        return float(match.group(1)) * 1024

    # Format: "X.X M/s" or "X MB/s"
    match = re.search(r"(\d+(?:\.\d+)?)\s*M(?:B)?/s", output)
    if match:
        return float(match.group(1))

    # Format: "X K/s" or "X KB/s"
    match = re.search(r"(\d+(?:\.\d+)?)\s*K(?:B)?/s", output)
    if match:
        return float(match.group(1)) / 1024

    # Format: "X bytes/sec" or "X B/s"
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:bytes/sec|B/s)", output)
    if match:
        return float(match.group(1)) / (1024 * 1024)

    # Fallback: parse "X bytes ... copied, Y s" and compute
    match = re.search(r"(\d+)\s*bytes.*copied.*?(\d+(?:\.\d+)?)\s*s", output)
    if match:
        nbytes = float(match.group(1))
        secs = float(match.group(2))
        if secs > 0:
            return nbytes / secs / (1024 * 1024)

    return -1.0


def measure_io_speed(adb_path: str | None = None) -> tuple[float, float, float, float]:
    """Measure I/O speed. Returns (seq_read, seq_write, rand_read_iops, rand_write_iops)."""
    seq_read = -1.0
    seq_write = -1.0
    rand_read_iops = -1.0
    rand_write_iops = -1.0
    bench_path = "/data/local/tmp/ad_bench"

    try:
        # Sequential write: 50MB
        write_out = shell(
            f"dd if=/dev/zero of={bench_path} bs=1048576 count=50 conv=fsync 2>&1",
            adb_path=adb_path,
            timeout=60,
        )
        seq_write = _parse_dd_speed(write_out)

        # Sequential read: read back 50MB
        shell("sync 2>/dev/null", adb_path=adb_path)
        read_out = shell(
            f"dd if={bench_path} of=/dev/null bs=1048576 2>&1",
            adb_path=adb_path,
            timeout=60,
        )
        seq_read = _parse_dd_speed(read_out)

        # Random 4K write: 1000 blocks of 4K (4MB total, random pattern)
        rand_write_out = shell(
            f"dd if=/dev/urandom of={bench_path}_rnd bs=4096 count=1000 conv=fsync 2>&1",
            adb_path=adb_path,
            timeout=60,
        )
        rw_speed = _parse_dd_speed(rand_write_out)
        if rw_speed > 0:
            # Convert MB/s to IOPS (each op is 4KB)
            rand_write_iops = round(rw_speed * 1024 / 4, 0)

        # Random 4K read: read back
        rand_read_out = shell(
            f"dd if={bench_path}_rnd of=/dev/null bs=4096 2>&1",
            adb_path=adb_path,
            timeout=60,
        )
        rr_speed = _parse_dd_speed(rand_read_out)
        if rr_speed > 0:
            rand_read_iops = round(rr_speed * 1024 / 4, 0)

        # Cleanup
        shell(f"rm -f {bench_path} {bench_path}_rnd", adb_path=adb_path)
    except ADBError:
        # Cleanup on failure too
        try:
            shell(f"rm -f {bench_path} {bench_path}_rnd", adb_path=adb_path)
        except ADBError:
            pass

    return (round(seq_read, 1), round(seq_write, 1), rand_read_iops, rand_write_iops)


def count_running_processes(adb_path: str | None = None) -> int:
    """Count running processes."""
    try:
        output = shell("ps -e 2>/dev/null | wc -l", adb_path=adb_path)
        return max(0, int(output.strip()) - 1)  # subtract header
    except (ADBError, ValueError):
        return 0


def run_benchmark(label: str = "baseline", adb_path: str | None = None) -> BenchmarkResult:
    """Run a full benchmark suite."""
    import sys
    from adb import commands as cmd
    from adb.parsers import parse_memory

    def _status(msg: str):
        sys.stdout.write(f"\r  ⏳ {msg}...")
        sys.stdout.flush()

    def _ok(msg: str = "done"):
        sys.stdout.write(f" {msg}\n")
        sys.stdout.flush()

    # RAM/swap/CPU
    _status("Measuring RAM & CPU")
    meminfo = cmd.proc_meminfo(adb_path)
    mem = parse_memory(meminfo)
    loadavg = cmd.get_loadavg(adb_path)
    load1 = 0.0
    if loadavg:
        try:
            load1 = float(loadavg.split()[0])
        except (ValueError, IndexError):
            pass
    swap_used = mem.swap_total_mb - mem.swap_free_mb
    _ok()

    # Process count
    _status("Counting processes")
    proc_count = count_running_processes(adb_path)
    _ok(str(proc_count))

    # I/O speed
    _status("Benchmarking storage I/O (50MB)")
    read_mbps, write_mbps, rand_r_iops, rand_w_iops = measure_io_speed(adb_path)
    if read_mbps > 0:
        rand_info = f" | 4K R:{rand_r_iops:.0f} W:{rand_w_iops:.0f} IOPS" if rand_r_iops > 0 else ""
        _ok(f"Seq R:{read_mbps:.0f} W:{write_mbps:.0f} MB/s{rand_info}")
    else:
        _ok("skipped")

    # App launch times
    _status("Measuring app launch times")
    launches = []
    installed_count = 0
    for pkg, activity in BENCHMARK_APPS:
        result = measure_app_launch(pkg, activity, adb_path)
        if result.status == "ok":
            launches.append(result)
            installed_count += 1
        elif result.status == "not_installed":
            continue  # skip silently
        else:
            launches.append(result)
    _ok(f"{installed_count} apps tested")

    return BenchmarkResult(
        timestamp=time.time(),
        app_launches=tuple(launches),
        ram_available_mb=mem.available_mb,
        ram_used_pct=mem.used_pct,
        swap_used_mb=swap_used,
        cpu_load_1=load1,
        io_seq_read_mbps=read_mbps,
        io_seq_write_mbps=write_mbps,
        io_rand_read_iops=rand_r_iops,
        io_rand_write_iops=rand_w_iops,
        running_process_count=proc_count,
        label=label,
    )


def print_benchmark_comparison(before: BenchmarkResult, after: BenchmarkResult):
    """Print a before/after benchmark comparison."""
    import sys

    G = "\033[92m"  # green
    R = "\033[91m"  # red
    Y = "\033[93m"  # yellow
    B = "\033[1m"   # bold
    D = "\033[2m"   # dim
    X = "\033[0m"   # reset

    print()
    print(f"  {B}╔═══════════════════════════════════════════════════╗{X}")
    print(f"  {B}║         BENCHMARK: BEFORE vs AFTER               ║{X}")
    print(f"  {B}╚═══════════════════════════════════════════════════╝{X}")
    print()

    # System metrics
    print(f"  {B}SYSTEM METRICS{X}")
    print(f"  {'─' * 55}")

    def _delta(before_val, after_val, unit: str, lower_is_better: bool = False):
        delta = after_val - before_val
        if delta == 0:
            return f"{D}(no change){X}"
        if lower_is_better:
            color = G if delta < 0 else R
            sign = "" if delta < 0 else "+"
        else:
            color = G if delta > 0 else R
            sign = "+" if delta > 0 else ""
        return f"{color}{sign}{delta:.0f}{unit}{X}"

    print(f"  {'RAM free:':<22} {before.ram_available_mb:>6} MB → {after.ram_available_mb:>6} MB  {_delta(before.ram_available_mb, after.ram_available_mb, ' MB')}")
    print(f"  {'RAM used:':<22} {before.ram_used_pct:>5.1f}%  → {after.ram_used_pct:>5.1f}%   {_delta(before.ram_used_pct, after.ram_used_pct, '%', lower_is_better=True)}")
    print(f"  {'Swap used:':<22} {before.swap_used_mb:>6} MB → {after.swap_used_mb:>6} MB  {_delta(before.swap_used_mb, after.swap_used_mb, ' MB', lower_is_better=True)}")
    print(f"  {'CPU load:':<22} {before.cpu_load_1:>6.1f}    → {after.cpu_load_1:>6.1f}     {_delta(before.cpu_load_1, after.cpu_load_1, '', lower_is_better=True)}")
    print(f"  {'Processes:':<22} {before.running_process_count:>6}    → {after.running_process_count:>6}     {_delta(before.running_process_count, after.running_process_count, '', lower_is_better=True)}")

    if before.io_seq_read_mbps > 0 and after.io_seq_read_mbps > 0:
        print(f"  {'Seq read:':<22} {before.io_seq_read_mbps:>5.0f} MB/s → {after.io_seq_read_mbps:>5.0f} MB/s {_delta(before.io_seq_read_mbps, after.io_seq_read_mbps, ' MB/s')}")
        print(f"  {'Seq write:':<22} {before.io_seq_write_mbps:>5.0f} MB/s → {after.io_seq_write_mbps:>5.0f} MB/s {_delta(before.io_seq_write_mbps, after.io_seq_write_mbps, ' MB/s')}")
    if before.io_rand_read_iops > 0 and after.io_rand_read_iops > 0:
        print(f"  {'4K rand read:':<22} {before.io_rand_read_iops:>5.0f} IOPS → {after.io_rand_read_iops:>5.0f} IOPS {_delta(before.io_rand_read_iops, after.io_rand_read_iops, ' IOPS')}")
        print(f"  {'4K rand write:':<22} {before.io_rand_write_iops:>5.0f} IOPS → {after.io_rand_write_iops:>5.0f} IOPS {_delta(before.io_rand_write_iops, after.io_rand_write_iops, ' IOPS')}")
    print()

    # App launch times
    print(f"  {B}APP LAUNCH TIMES (cold start){X}")
    print(f"  {'─' * 55}")

    # Match apps from before and after
    before_map = {r.package: r for r in before.app_launches if r.status == "ok"}
    after_map = {r.package: r for r in after.app_launches if r.status == "ok"}

    total_before_ms = 0
    total_after_ms = 0
    app_count = 0

    for pkg in before_map:
        if pkg in after_map:
            b = before_map[pkg]
            a = after_map[pkg]
            if b.total_time_ms > 0 and a.total_time_ms > 0:
                delta_ms = a.total_time_ms - b.total_time_ms
                total_before_ms += b.total_time_ms
                total_after_ms += a.total_time_ms
                app_count += 1

                pct_change = (delta_ms / b.total_time_ms) * 100 if b.total_time_ms > 0 else 0
                app_name = pkg.split(".")[-1]
                if len(app_name) > 15:
                    app_name = app_name[:15]

                if delta_ms < -50:
                    color = G
                    indicator = f"▼ {abs(delta_ms)}ms faster ({abs(pct_change):.0f}%)"
                elif delta_ms > 50:
                    color = R
                    indicator = f"▲ {delta_ms}ms slower"
                else:
                    color = D
                    indicator = "≈ same"

                # Visual bar
                max_ms = max(b.total_time_ms, a.total_time_ms)
                bar_scale = 30 / max_ms if max_ms > 0 else 1
                bar_b = "█" * max(1, int(b.total_time_ms * bar_scale))
                bar_a = "█" * max(1, int(a.total_time_ms * bar_scale))

                print(f"  {app_name:<16}")
                print(f"    Before: {D}{bar_b}{X} {b.total_time_ms}ms")
                print(f"    After:  {color}{bar_a}{X} {a.total_time_ms}ms  {color}{indicator}{X}")

    if app_count > 0:
        avg_before = total_before_ms / app_count
        avg_after = total_after_ms / app_count
        avg_delta = avg_after - avg_before
        avg_pct = (avg_delta / avg_before) * 100 if avg_before > 0 else 0
        print()
        print(f"  {B}AVERAGE{X}")
        if avg_delta < 0:
            print(f"  {G}Apps launch {abs(avg_pct):.0f}% faster on average ({abs(avg_delta):.0f}ms saved){X}")
        elif avg_delta > 0:
            print(f"  {R}Apps launch {avg_pct:.0f}% slower on average{X}")
        else:
            print(f"  {D}No significant change in launch times{X}")
    elif not before_map:
        print(f"  {D}No app launch data in 'before' benchmark{X}")

    print()
