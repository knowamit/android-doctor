#!/usr/bin/env python3
"""
android-doctor — Find out why your Android phone is slow. Then fix it.

Usage:
    android-doctor diagnose         Full diagnostic scan
    android-doctor fix [--level]    Fix issues (safe|moderate|aggressive)
    android-doctor autofix          Iterative optimization loop
    android-doctor report           Diagnose + export HTML report
    android-doctor rollback         Undo all fixes
    android-doctor bloatware        Scan bloatware only
    android-doctor battery          Battery drain analysis
    android-doctor info             Show device info only
"""

import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adb.connection import (
    detect_device,
    find_adb,
    ADBError,
    NoDeviceError,
    MultipleDevicesError,
)
from adb import commands as cmd
from adb.parsers import (
    parse_battery,
    parse_memory,
    parse_cpu,
    parse_thermal,
    parse_storage_health,
)
from diagnosis.battery import diagnose_battery
from diagnosis.storage import diagnose_storage
from diagnosis.memory import diagnose_memory
from diagnosis.cpu import diagnose_cpu
from diagnosis.bloatware import diagnose_bloatware
from diagnosis.verdict import compute_verdict
from report.terminal import (
    print_full_report,
    print_device_info,
    print_bloatware,
    _c,
    C,
)


VERSION = "0.2.0"


def _spinner(msg: str):
    """Simple inline status message."""
    sys.stdout.write(f"\r  ⏳ {msg}...")
    sys.stdout.flush()


def _done(msg: str = "done"):
    sys.stdout.write(f" {msg}\n")
    sys.stdout.flush()


def _header():
    print()
    print(_c(C.BOLD + C.CYAN, f"  android-doctor v{VERSION}"))
    print(_c(C.DIM, "  Find out why your Android phone is slow. Then fix it."))
    print()


def _connect():
    """Find ADB and connect to device. Returns (adb_path, device)."""
    _spinner("Looking for ADB")
    try:
        adb_path = find_adb()
    except ADBError as e:
        _done("FAILED")
        print(f"\n  {_c(C.RED, str(e))}")
        sys.exit(1)
    _done("found")

    _spinner("Connecting to device")
    try:
        device = detect_device(adb_path)
    except (NoDeviceError, MultipleDevicesError) as e:
        _done("FAILED")
        print(f"\n  {_c(C.RED, str(e))}")
        sys.exit(1)
    _done(f"{device.brand} {device.model}")

    return adb_path, device


def _collect_diagnostics(adb_path, device):
    """Collect all diagnostic data. Returns all diagnosis objects."""
    _spinner("Reading battery health")
    battery_dump = cmd.dumpsys_battery(adb_path)
    battery_sysfs = cmd.battery_sysfs(adb_path)
    battery_data = parse_battery(battery_dump, battery_sysfs)
    _done()

    _spinner("Reading thermal sensors")
    thermal_raw = cmd.thermal_zones(adb_path)
    thermal_data = parse_thermal(thermal_raw)
    _done(f"{len(thermal_data)} zones")

    _spinner("Analyzing memory")
    meminfo_raw = cmd.proc_meminfo(adb_path)
    mem_data = parse_memory(meminfo_raw)
    _done(f"{mem_data.total_mb} MB total")

    _spinner("Analyzing CPU load")
    cpu_raw = cmd.dumpsys_cpuinfo(adb_path)
    loadavg = cmd.get_loadavg(adb_path)
    cpu_data = parse_cpu(cpu_raw, loadavg)
    _done()

    _spinner("Checking storage health")
    df_raw = cmd.df_storage(adb_path)
    emmc_data = cmd.emmc_health(adb_path)
    ufs_data = cmd.ufs_health(adb_path)
    storage_data = parse_storage_health(device.storage_type, emmc_data, ufs_data, df_raw)
    _done()

    _spinner("Scanning packages")
    system_pkgs = cmd.list_packages_system(adb_path)
    disabled_pkgs = cmd.list_packages_disabled(adb_path)
    _done(f"{len(system_pkgs)} system packages")

    _spinner("Running diagnosis")
    battery_diag = diagnose_battery(battery_data, thermal_data)
    storage_diag = diagnose_storage(storage_data)
    memory_diag = diagnose_memory(mem_data)
    cpu_diag = diagnose_cpu(cpu_data, thermal_data)
    bloatware_diag = diagnose_bloatware(system_pkgs, disabled_pkgs, device.brand)
    verdict = compute_verdict(battery_diag, storage_diag, memory_diag, cpu_diag, bloatware_diag)
    _done()

    return {
        "device": device,
        "battery": battery_diag,
        "storage": storage_diag,
        "memory": memory_diag,
        "cpu": cpu_diag,
        "bloatware": bloatware_diag,
        "verdict": verdict,
    }


def run_diagnose():
    """Run full diagnostic scan."""
    _header()
    adb_path, device = _connect()
    diag = _collect_diagnostics(adb_path, device)
    print()
    print_full_report(**diag)
    return diag


def run_fix(level: str = "safe"):
    """Run fix command: debloat + settings + battery optimization."""
    from fix.engine import FixEngine

    _header()
    adb_path, device = _connect()
    diag = _collect_diagnostics(adb_path, device)
    print()

    # Show diagnosis summary first
    print_full_report(**diag)

    # Confirm with user
    print(_c(C.BOLD + C.YELLOW, f"  Ready to apply fixes ({level} mode)."))
    print(f"  All changes are reversible via `android-doctor rollback`.")
    print()
    response = input(f"  Proceed? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        print("  Cancelled.")
        return

    print()
    engine = FixEngine(device, adb_path)
    stats = engine.run_all(diag["bloatware"], level)

    # Run diagnosis again to show improvement
    print(_c(C.BOLD, "  ═══ POST-FIX DIAGNOSIS ═══"))
    print()
    post_diag = _collect_diagnostics(adb_path, device)
    print()

    # Show before/after
    before_score = diag["verdict"].overall_score
    after_score = post_diag["verdict"].overall_score
    delta = after_score - before_score

    print(_c(C.BOLD, "  BEFORE → AFTER"))
    print(f"  Overall score: {before_score} → {after_score} ", end="")
    if delta > 0:
        print(_c(C.GREEN, f"(+{delta} improvement)"))
    elif delta < 0:
        print(_c(C.YELLOW, f"({delta})"))
    else:
        print(_c(C.DIM, "(no change yet — improvements may take a few minutes)"))
    print()


def run_autofix():
    """Run iterative optimization."""
    from fix.autofix import run_autofix as _run_autofix

    _header()
    adb_path, device = _connect()

    # Quick bloatware scan for experiment planning
    _spinner("Scanning packages")
    system_pkgs = cmd.list_packages_system(adb_path)
    disabled_pkgs = cmd.list_packages_disabled(adb_path)
    _done(f"{len(system_pkgs)} system packages")

    bloatware_diag = diagnose_bloatware(system_pkgs, disabled_pkgs, device.brand)
    print()

    print(_c(C.BOLD + C.YELLOW, "  Autofix will try optimizations one at a time,"))
    print(_c(C.BOLD + C.YELLOW, "  measure the impact, and keep only what helps."))
    print(f"  All changes are reversible via `android-doctor rollback`.")
    print()
    response = input(f"  Start autofix loop? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        print("  Cancelled.")
        return

    print()
    _run_autofix(device, bloatware_diag, adb_path)


def run_rollback():
    """Undo all fixes."""
    from fix.engine import run_rollback as _run_rollback

    _header()
    _spinner("Looking for ADB")
    adb_path = find_adb()
    _done("found")

    _spinner("Connecting to device")
    device = detect_device(adb_path)
    _done(f"{device.brand} {device.model}")
    print()

    _run_rollback(adb_path)


def run_report():
    """Run diagnosis and export HTML report."""
    from report.html import save_html_report

    diag = run_diagnose()
    if not diag:
        return

    print(_c(C.BOLD, "  Generating HTML report..."))
    path = save_html_report(**diag)
    print(f"  ✓ Report saved: {_c(C.CYAN, path)}")
    print()

    # Try to open in browser
    try:
        import webbrowser
        webbrowser.open(f"file://{path}")
        print(f"  Opened in browser.")
    except Exception:
        pass
    print()


def run_battery():
    """Battery-specific analysis."""
    from fix.battery import get_top_battery_drainers

    _header()
    adb_path, device = _connect()

    _spinner("Reading battery health")
    battery_dump = cmd.dumpsys_battery(adb_path)
    battery_sysfs = cmd.battery_sysfs(adb_path)
    battery_data = parse_battery(battery_dump, battery_sysfs)
    _done()

    _spinner("Reading thermal sensors")
    thermal_raw = cmd.thermal_zones(adb_path)
    thermal_data = parse_thermal(thermal_raw)
    _done(f"{len(thermal_data)} zones")

    _spinner("Analyzing battery drain")
    drainers = get_top_battery_drainers(adb_path)
    _done()

    print()
    battery_diag = diagnose_battery(battery_data, thermal_data)

    from report.terminal import print_battery
    print_battery(battery_diag)

    if drainers:
        print(_c(C.BOLD, "  TOP BATTERY DRAINERS (estimated power use)"))
        print(_c(C.DIM, "  " + "─" * 50))
        for pkg_or_uid, power in drainers[:10]:
            bar_len = min(30, int(power / 2))
            bar = "█" * bar_len
            print(f"  {_c(C.YELLOW, bar)} {power:.1f} mAh  {pkg_or_uid}")
        print()
    else:
        print(_c(C.DIM, "  Battery drain stats unavailable (may need full charge cycle)"))
        print()


def run_benchmark():
    """Run performance benchmark with app launch times."""
    from diagnosis.benchmark import run_benchmark as _run_bench, print_benchmark_comparison
    from diagnosis.history import save_benchmark, load_history

    _header()
    adb_path, device = _connect()

    history = load_history()
    label = "baseline" if not history else f"run-{len(history) + 1}"

    # Check if user wants before/after
    for arg in sys.argv[2:]:
        if arg.lower().strip("-") in ("before", "pre"):
            label = "before"
        elif arg.lower().strip("-") in ("after", "post"):
            label = "after"

    print()
    print(_c(C.BOLD, f"  Running benchmark ({label})..."))
    print(_c(C.DIM, "  This takes ~30-60 seconds. Apps will briefly open and close."))
    print()

    result = _run_bench(label=label, adb_path=adb_path)
    save_benchmark(result)

    # Print results
    print()
    print(_c(C.BOLD, "  BENCHMARK RESULTS"))
    print("  " + "─" * 50)
    print(f"  RAM free:     {result.ram_available_mb} MB")
    print(f"  Swap used:    {result.swap_used_mb} MB")
    print(f"  CPU load:     {result.cpu_load_1:.1f}")
    print(f"  Processes:    {result.running_process_count}")
    if result.io_seq_read_mbps > 0:
        print(f"  I/O read:     {result.io_seq_read_mbps:.0f} MB/s")
        print(f"  I/O write:    {result.io_seq_write_mbps:.0f} MB/s")
    print()

    ok_launches = [a for a in result.app_launches if a.status == "ok"]
    if ok_launches:
        print(_c(C.BOLD, "  APP LAUNCH TIMES (cold start)"))
        print("  " + "─" * 50)
        for launch in sorted(ok_launches, key=lambda l: l.total_time_ms, reverse=True):
            app_name = launch.package.split(".")[-1]
            ms = launch.total_time_ms
            bar_len = min(30, ms // 100)
            bar = "█" * max(1, bar_len)
            color = C.RED if ms > 2000 else (C.YELLOW if ms > 1000 else C.GREEN)
            print(f"  {_c(color, bar)} {ms}ms  {app_name}")
        avg_ms = sum(l.total_time_ms for l in ok_launches) / len(ok_launches)
        print(f"\n  Average: {avg_ms:.0f}ms across {len(ok_launches)} apps")
    print()

    # If there's a "before" in history, auto-compare
    if label == "after":
        before_entries = [e for e in history if e.get("label") == "before"]
        if before_entries:
            # Reconstruct BenchmarkResult from history entry
            from diagnosis.benchmark import AppLaunchResult as ALR
            be = before_entries[-1]
            before_result = type(result)(
                timestamp=be["timestamp"],
                app_launches=tuple(
                    ALR(package=a["package"], activity="", total_time_ms=a["total_time_ms"], status=a["status"])
                    for a in be.get("app_launches", [])
                ),
                ram_available_mb=be["ram_available_mb"],
                ram_used_pct=be["ram_used_pct"],
                swap_used_mb=be["swap_used_mb"],
                cpu_load_1=be["cpu_load_1"],
                io_seq_read_mbps=be["io_seq_read_mbps"],
                io_seq_write_mbps=be["io_seq_write_mbps"],
                running_process_count=be["running_process_count"],
                label="before",
            )
            print_benchmark_comparison(before_result, result)

    print(_c(C.DIM, f"  Saved to history. Run `android-doctor history` to see trends."))
    print()


def run_history():
    """Show benchmark history and trends."""
    from diagnosis.history import print_history

    _header()
    print_history()


def run_clean():
    """Clear app caches system-wide to free storage and improve I/O."""
    from fix.debloat import trim_all_caches

    _header()
    adb_path, device = _connect()

    # Show storage before
    _spinner("Checking storage")
    df_before = cmd.df_storage(adb_path)
    from adb.parsers import parse_df
    parts_before = parse_df(df_before)
    data_before = None
    for p in parts_before:
        if p.mount in ("/data", "/data/media", "/storage/emulated") or p.total_mb > 10000:
            data_before = p
            break
    if data_before:
        _done(f"{data_before.available_mb // 1024:.0f} GB free")
    else:
        _done()

    print()
    print(_c(C.BOLD, "  ═══ CACHE CLEANUP ═══"))
    print(f"  This clears app caches system-wide.")
    print(f"  Your app data, photos, messages are NOT touched.")
    print()

    _spinner("Trimming all app caches")
    result = trim_all_caches(adb_path)
    if result:
        _done("done")
    else:
        _done("failed (may need different Android version)")

    # Show storage after
    _spinner("Checking storage")
    df_after = cmd.df_storage(adb_path)
    parts_after = parse_df(df_after)
    data_after = None
    for p in parts_after:
        if p.mount in ("/data", "/data/media", "/storage/emulated") or p.total_mb > 10000:
            data_after = p
            break
    if data_after:
        _done(f"{data_after.available_mb // 1024:.0f} GB free")
    else:
        _done()

    print()
    if data_before and data_after:
        freed_mb = data_after.available_mb - data_before.available_mb
        if freed_mb > 0:
            if freed_mb > 1024:
                print(_c(C.GREEN, f"  ✓ Freed {freed_mb / 1024:.1f} GB of cache"))
            else:
                print(_c(C.GREEN, f"  ✓ Freed {freed_mb} MB of cache"))
        else:
            print(f"  Caches were already minimal ({data_after.available_mb // 1024:.0f} GB free)")
    print()


def run_info():
    """Show device info only."""
    adb_path = find_adb()
    device = detect_device(adb_path)
    print()
    print_device_info(device)


def run_bloatware():
    """Run bloatware scan only."""
    print()
    print(_c(C.BOLD + C.CYAN, "  android-doctor — Bloatware Scan"))
    print()

    adb_path = find_adb()

    _spinner("Connecting to device")
    device = detect_device(adb_path)
    _done(f"{device.brand} {device.model}")

    _spinner("Scanning packages")
    system_pkgs = cmd.list_packages_system(adb_path)
    disabled_pkgs = cmd.list_packages_disabled(adb_path)
    _done(f"{len(system_pkgs)} system packages")

    print()
    bloatware_diag = diagnose_bloatware(system_pkgs, disabled_pkgs, device.brand)
    print_bloatware(bloatware_diag)


def print_usage():
    print()
    print(_c(C.BOLD + C.CYAN, "  android-doctor") + " — Find out why your Android phone is slow. Then fix it.")
    print()
    print("  DIAGNOSE")
    print(f"    android-doctor {_c(C.BOLD, 'diagnose')}              Full diagnostic scan")
    print(f"    android-doctor {_c(C.BOLD, 'benchmark')}             Measure app launch times + I/O speed")
    print(f"    android-doctor {_c(C.BOLD, 'benchmark --before')}    Benchmark before fixing")
    print(f"    android-doctor {_c(C.BOLD, 'benchmark --after')}     Benchmark after fixing (auto-compares)")
    print(f"    android-doctor {_c(C.BOLD, 'history')}               Show performance trends over time")
    print(f"    android-doctor {_c(C.BOLD, 'report')}                Diagnose + export HTML report")
    print(f"    android-doctor {_c(C.BOLD, 'bloatware')}             Scan bloatware only")
    print(f"    android-doctor {_c(C.BOLD, 'battery')}               Battery drain analysis")
    print(f"    android-doctor {_c(C.BOLD, 'info')}                  Show device info only")
    print()
    print("  FIX")
    print(f"    android-doctor {_c(C.BOLD, 'fix')}                   Safe fixes (high-impact bloatware only)")
    print(f"    android-doctor {_c(C.BOLD, 'fix --moderate')}        + medium-impact bloatware")
    print(f"    android-doctor {_c(C.BOLD, 'fix --aggressive')}      All removable bloatware")
    print(f"    android-doctor {_c(C.BOLD, 'autofix')}               Iterative optimize loop (try → measure → keep/revert)")
    print(f"    android-doctor {_c(C.BOLD, 'clean')}                 Clear all app caches (safe, frees storage)")
    print(f"    android-doctor {_c(C.BOLD, 'rollback')}              Undo all fixes")
    print()
    print("  Requirements:")
    print("    • Android phone connected via USB")
    print("    • USB debugging enabled on the phone")
    print("    • ADB installed on this computer")
    print()


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    command = sys.argv[1].lower().strip("-")

    # Parse level flag for fix command
    level = "safe"
    for arg in sys.argv[2:]:
        arg_clean = arg.lower().strip("-")
        if arg_clean in ("moderate", "med"):
            level = "moderate"
        elif arg_clean in ("aggressive", "agg", "all"):
            level = "aggressive"

    try:
        if command in ("diagnose", "scan", "check", "run"):
            run_diagnose()
        elif command == "fix":
            run_fix(level)
        elif command == "autofix":
            run_autofix()
        elif command == "rollback":
            run_rollback()
        elif command in ("benchmark", "bench", "perf"):
            run_benchmark()
        elif command in ("history", "trend", "trends"):
            run_history()
        elif command in ("clean", "clear", "cache"):
            run_clean()
        elif command == "report":
            run_report()
        elif command == "battery":
            run_battery()
        elif command in ("info", "device"):
            run_info()
        elif command in ("bloatware", "bloat", "debloat"):
            run_bloatware()
        elif command in ("help", "h"):
            print_usage()
        elif command == "version":
            print(f"android-doctor v{VERSION}")
        else:
            print(f"\n  Unknown command: {command}")
            print_usage()
            sys.exit(1)
    except ADBError as e:
        print(f"\n  {_c(C.RED, 'Error:')} {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n\n  {_c(C.DIM, 'Interrupted.')}")
        sys.exit(130)


if __name__ == "__main__":
    main()
