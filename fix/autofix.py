"""Autofix: scientific iterative optimization loop.

Each optimization is tried individually, measured, and only kept if
it produces a measurable improvement. No guesswork — pure data.

  1. Take a baseline measurement
  2. Try one optimization
  3. Measure again
  4. Keep if improved, revert if not
  5. Repeat
"""

from __future__ import annotations
import sys
import time
from dataclasses import dataclass

from adb.connection import DeviceInfo, shell, ADBError
from adb import commands as cmd
from adb.parsers import parse_memory, parse_cpu
from fix.rollback import Snapshot, ChangeRecord, save_snapshot
from fix.debloat import disable_package, enable_package, force_stop_package
from fix.settings import (
    set_animation_scale,
    set_background_process_limit,
    restore_setting,
)
from fix.battery import restrict_background_data, unrestrict_background
from diagnosis.bloatware import BloatwareDiagnosis


@dataclass(frozen=True)
class Metrics:
    """Snapshot of current device performance."""
    ram_available_mb: int
    ram_used_pct: float
    swap_used_mb: int
    cpu_load_1: float
    timestamp: float


@dataclass
class ExperimentResult:
    """Result of a single optimization experiment."""
    name: str
    action: str
    target: str
    kept: bool
    ram_freed_mb: int
    cpu_delta: float
    swap_freed_mb: int
    change: ChangeRecord | None


def _print(msg: str):
    sys.stdout.write(f"  {msg}\n")
    sys.stdout.flush()


def measure(adb_path: str | None = None) -> Metrics:
    """Take a performance measurement snapshot."""
    meminfo_raw = cmd.proc_meminfo(adb_path)
    mem = parse_memory(meminfo_raw)
    loadavg = cmd.get_loadavg(adb_path)

    load1 = 0.0
    if loadavg:
        parts = loadavg.split()
        if parts:
            try:
                load1 = float(parts[0])
            except ValueError:
                pass

    return Metrics(
        ram_available_mb=mem.available_mb,
        ram_used_pct=mem.used_pct,
        swap_used_mb=mem.swap_total_mb - mem.swap_free_mb,
        cpu_load_1=load1,
        timestamp=time.time(),
    )


def _improved(before: Metrics, after: Metrics) -> bool:
    """Did the optimization measurably improve things?"""
    ram_freed = after.ram_available_mb - before.ram_available_mb
    swap_freed = before.swap_used_mb - after.swap_used_mb
    cpu_improved = before.cpu_load_1 - after.cpu_load_1

    # Any of these count as improvement:
    if ram_freed >= 20:   # freed 20MB+ RAM
        return True
    if swap_freed >= 50:  # freed 50MB+ swap
        return True
    if cpu_improved >= 0.5:  # reduced load by 0.5+
        return True
    # Combined small improvements also count
    if ram_freed > 0 and (swap_freed > 0 or cpu_improved > 0):
        return True
    return False


def _build_experiments(
    bloatware: BloatwareDiagnosis,
    adb_path: str | None = None,
) -> list[dict]:
    """Build ordered list of experiments to try."""
    experiments = []

    # Experiment: disable each bloatware package (high impact first)
    for entry in bloatware.removable:
        experiments.append({
            "name": f"Disable {entry.name}",
            "type": "disable_package",
            "target": entry.package,
            "display": entry.name,
            "impact": entry.impact,
        })

    # Experiment: animation scale optimizations
    experiments.append({
        "name": "Set animations to 0.5x",
        "type": "set_animation_scale",
        "target": "0.5",
        "display": "Animation scale → 0.5x",
        "impact": "medium",
    })

    # Experiment: background process limit
    experiments.append({
        "name": "Limit background processes to 4",
        "type": "set_bg_limit",
        "target": "4",
        "display": "Background limit → 4 processes",
        "impact": "medium",
    })

    # Experiment: restrict background for high-drain apps
    for entry in bloatware.removable:
        if entry.impact == "high":
            experiments.append({
                "name": f"Restrict background: {entry.name}",
                "type": "restrict_background",
                "target": entry.package,
                "display": entry.name,
                "impact": "medium",
            })

    # Sort: high impact first
    impact_order = {"high": 0, "medium": 1, "low": 2}
    experiments.sort(key=lambda e: impact_order.get(e.get("impact", "low"), 3))

    return experiments


def run_autofix(
    device: DeviceInfo,
    bloatware: BloatwareDiagnosis,
    adb_path: str | None = None,
    max_iterations: int = 30,
) -> list[ExperimentResult]:
    """Run the experiment-driven-style optimization loop."""

    _print("╔═══════════════════════════════════════════════════╗")
    _print("║       AUTOFIX — Iterative Optimization Loop      ║")
    _print("╚═══════════════════════════════════════════════════╝")
    _print("")

    experiments = _build_experiments(bloatware, adb_path)
    if not experiments:
        _print("No experiments to run.")
        return []

    _print(f"Planned: {len(experiments)} experiments (max {max_iterations} iterations)")
    _print("")

    # Take initial baseline
    _print("Taking baseline measurement...")
    baseline = measure(adb_path)
    _print(f"  RAM free: {baseline.ram_available_mb} MB | "
           f"Swap used: {baseline.swap_used_mb} MB | "
           f"Load: {baseline.cpu_load_1:.1f}")
    _print("")

    snapshot = Snapshot(
        device_serial=device.serial,
        device_model=device.model,
        created_at=time.time(),
    )

    results: list[ExperimentResult] = []
    kept_count = 0
    total_ram_freed = 0
    total_swap_freed = 0

    for i, exp in enumerate(experiments[:max_iterations], 1):
        _print(f"Iteration {i}/{min(len(experiments), max_iterations)}: {exp['name']}")

        # Measure before
        before = measure(adb_path)
        time.sleep(0.5)  # Let system settle

        # Apply experiment
        change = _apply_experiment(exp, adb_path)

        # Wait for effect to propagate
        time.sleep(1.5)

        # Measure after
        after = measure(adb_path)

        ram_freed = after.ram_available_mb - before.ram_available_mb
        swap_freed = before.swap_used_mb - after.swap_used_mb
        cpu_delta = before.cpu_load_1 - after.cpu_load_1

        if _improved(before, after):
            kept = True
            kept_count += 1
            total_ram_freed += max(0, ram_freed)
            total_swap_freed += max(0, swap_freed)
            if change:
                snapshot.changes.append(change)
            status = "\033[92m✅ KEEPING\033[0m"
            details = []
            if ram_freed > 0:
                details.append(f"RAM +{ram_freed} MB")
            if swap_freed > 0:
                details.append(f"Swap -{swap_freed} MB")
            if cpu_delta > 0:
                details.append(f"Load -{cpu_delta:.1f}")
            detail_str = " | ".join(details) if details else "measurable improvement"
        else:
            kept = False
            _revert_experiment(exp, change, adb_path)
            status = "\033[93m↩ REVERTED\033[0m"
            detail_str = "no measurable improvement"

        _print(f"  → {status} ({detail_str})")

        results.append(ExperimentResult(
            name=exp["name"],
            action=exp["type"],
            target=exp["target"],
            kept=kept,
            ram_freed_mb=max(0, ram_freed) if kept else 0,
            cpu_delta=cpu_delta if kept else 0,
            swap_freed_mb=max(0, swap_freed) if kept else 0,
            change=change if kept else None,
        ))

    # Save snapshot
    save_snapshot(snapshot)

    # Final measurement
    _print("")
    _print("Taking final measurement...")
    final = measure(adb_path)

    _print("")
    _print("╔═══════════════════════════════════════════════════╗")
    _print("║              AUTOFIX RESULTS                     ║")
    _print("╚═══════════════════════════════════════════════════╝")
    _print("")
    _print(f"  Experiments run:  {len(results)}")
    _print(f"  Changes kept:     {kept_count}")
    _print(f"  Changes reverted: {len(results) - kept_count}")
    _print("")
    _print(f"  BEFORE → AFTER:")
    _print(f"  RAM free:   {baseline.ram_available_mb} MB → {final.ram_available_mb} MB "
           f"(\033[92m+{final.ram_available_mb - baseline.ram_available_mb} MB\033[0m)")
    _print(f"  Swap used:  {baseline.swap_used_mb} MB → {final.swap_used_mb} MB "
           f"(\033[92m-{baseline.swap_used_mb - final.swap_used_mb} MB\033[0m)")
    _print(f"  CPU load:   {baseline.cpu_load_1:.1f} → {final.cpu_load_1:.1f} "
           f"(\033[92m-{baseline.cpu_load_1 - final.cpu_load_1:.1f}\033[0m)")
    _print("")
    _print(f"  All changes are reversible: `android-doctor rollback`")
    _print("")

    return results


def _apply_experiment(exp: dict, adb_path: str | None = None) -> ChangeRecord | None:
    """Apply a single experiment. Returns the change record."""
    exp_type = exp["type"]
    target = exp["target"]

    if exp_type == "disable_package":
        force_stop_package(target, adb_path)
        return disable_package(target, adb_path)

    elif exp_type == "set_animation_scale":
        changes = set_animation_scale(target, adb_path)
        return changes[0] if changes else None

    elif exp_type == "set_bg_limit":
        return set_background_process_limit(int(target), adb_path)

    elif exp_type == "restrict_background":
        return restrict_background_data(target, adb_path)

    return None


def _revert_experiment(exp: dict, change: ChangeRecord | None, adb_path: str | None = None):
    """Revert a single experiment."""
    if not change:
        return

    exp_type = exp["type"]

    if exp_type == "disable_package":
        enable_package(change.target, adb_path)

    elif exp_type in ("set_animation_scale", "set_bg_limit"):
        restore_setting(change.target, change.original_value, adb_path)

    elif exp_type == "restrict_background":
        unrestrict_background(change.target, adb_path)
