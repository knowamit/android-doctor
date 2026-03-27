"""Persist diagnostic and benchmark results for trend tracking."""

from __future__ import annotations
import json
import os
import time
from dataclasses import asdict

from diagnosis.benchmark import BenchmarkResult, AppLaunchResult


HISTORY_DIR = os.path.expanduser("~/.android-doctor")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.json")


def _ensure_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def save_benchmark(result: BenchmarkResult):
    """Append a benchmark result to history."""
    _ensure_dir()
    history = load_history()

    entry = {
        "timestamp": result.timestamp,
        "label": result.label,
        "ram_available_mb": result.ram_available_mb,
        "ram_used_pct": result.ram_used_pct,
        "swap_used_mb": result.swap_used_mb,
        "cpu_load_1": result.cpu_load_1,
        "io_seq_read_mbps": result.io_seq_read_mbps,
        "io_seq_write_mbps": result.io_seq_write_mbps,
        "io_rand_read_iops": result.io_rand_read_iops,
        "io_rand_write_iops": result.io_rand_write_iops,
        "running_process_count": result.running_process_count,
        "app_launches": [
            {
                "package": a.package,
                "total_time_ms": a.total_time_ms,
                "status": a.status,
            }
            for a in result.app_launches
        ],
    }
    history.append(entry)

    # Keep last 100 entries
    if len(history) > 100:
        history = history[-100:]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def load_history() -> list[dict]:
    """Load benchmark history."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE) as f:
        return json.load(f)


def print_history():
    """Print benchmark history as a trend table."""
    history = load_history()
    if not history:
        print("  No benchmark history yet. Run `android-doctor benchmark` to start tracking.")
        return

    G = "\033[92m"
    R = "\033[91m"
    B = "\033[1m"
    D = "\033[2m"
    C = "\033[96m"
    X = "\033[0m"

    print()
    print(f"  {B}PERFORMANCE HISTORY{X}")
    print(f"  {'─' * 70}")
    print(f"  {D}{'Date':<20} {'Label':<10} {'RAM free':>9} {'Swap':>7} {'Load':>6} {'Procs':>6} {'I/O R':>7}{X}")
    print(f"  {'─' * 70}")

    prev = None
    for entry in history[-20:]:  # show last 20
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["timestamp"]))
        label = entry.get("label", "")[:10]
        ram = entry["ram_available_mb"]
        swap = entry["swap_used_mb"]
        load = entry["cpu_load_1"]
        procs = entry["running_process_count"]
        io_r = entry["io_seq_read_mbps"]

        # Color based on trend vs previous
        if prev:
            ram_c = G if ram > prev["ram_available_mb"] else (R if ram < prev["ram_available_mb"] else D)
            swap_c = G if swap < prev["swap_used_mb"] else (R if swap > prev["swap_used_mb"] else D)
            load_c = G if load < prev["cpu_load_1"] else (R if load > prev["cpu_load_1"] else D)
        else:
            ram_c = swap_c = load_c = ""

        io_str = f"{io_r:.0f} MB/s" if io_r > 0 else "n/a"
        print(f"  {ts:<20} {C}{label:<10}{X} {ram_c}{ram:>7} MB{X} {swap_c}{swap:>5} MB{X} {load_c}{load:>5.1f}{X} {procs:>6} {io_str:>7}")
        prev = entry

    # Show app launch trend for the most common app
    all_pkgs: dict[str, list[int]] = {}
    for entry in history:
        for launch in entry.get("app_launches", []):
            if launch["status"] == "ok" and launch["total_time_ms"] > 0:
                pkg = launch["package"]
                all_pkgs.setdefault(pkg, []).append(launch["total_time_ms"])

    if all_pkgs:
        # Pick app with most data points
        best_pkg = max(all_pkgs, key=lambda k: len(all_pkgs[k]))
        times = all_pkgs[best_pkg]
        if len(times) >= 2:
            app_name = best_pkg.split(".")[-1]
            first = times[0]
            last = times[-1]
            delta_pct = ((last - first) / first) * 100 if first > 0 else 0
            print()
            print(f"  {B}APP LAUNCH TREND: {app_name}{X}")
            print(f"  {'─' * 40}")

            # Mini sparkline
            max_t = max(times)
            min_t = min(times)
            for i, t in enumerate(times):
                bar_len = int((t / max_t) * 25) if max_t > 0 else 1
                bar = "█" * max(1, bar_len)
                color = G if t <= min_t * 1.1 else (R if t >= max_t * 0.9 else "")
                print(f"  {color}{bar} {t}ms{X}")

            if delta_pct < -10:
                print(f"  {G}↓ {abs(delta_pct):.0f}% faster since first benchmark{X}")
            elif delta_pct > 10:
                print(f"  {R}↑ {delta_pct:.0f}% slower since first benchmark{X}")
            else:
                print(f"  {D}≈ Stable performance{X}")

    print()
