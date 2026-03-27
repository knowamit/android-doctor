"""Fix engine: orchestrates all optimization steps with rollback support."""

from __future__ import annotations
import sys
import time

from adb.connection import DeviceInfo, shell, ADBError
from diagnosis.bloatware import BloatwareDiagnosis, BloatwareEntry
from fix.rollback import Snapshot, ChangeRecord, save_snapshot, load_snapshot, has_snapshot
from fix.debloat import disable_package, force_stop_package
from fix.settings import (
    set_animation_scale,
    set_background_process_limit,
    set_always_finish_activities,
)
from fix.battery import (
    restrict_background_data,
    optimize_doze,
    get_top_battery_drainers,
)


class FixEngine:
    """Orchestrates safe, reversible phone optimizations."""

    def __init__(self, device: DeviceInfo, adb_path: str | None = None):
        self.device = device
        self.adb_path = adb_path
        self.snapshot = Snapshot(
            device_serial=device.serial,
            device_model=device.model,
            created_at=time.time(),
        )
        self.stats = {
            "packages_disabled": 0,
            "packages_stopped": 0,
            "settings_changed": 0,
            "battery_optimized": 0,
        }

    def _record(self, change: ChangeRecord | None):
        if change:
            self.snapshot.changes.append(change)

    def _records(self, changes: list[ChangeRecord]):
        self.snapshot.changes.extend(changes)

    def _print(self, msg: str):
        sys.stdout.write(f"  {msg}\n")
        sys.stdout.flush()

    def run_debloat(self, bloatware: BloatwareDiagnosis, level: str = "safe") -> int:
        """Disable bloatware packages.

        Levels:
          "safe"       — only HIGH impact packages
          "moderate"   — HIGH + MEDIUM impact
          "aggressive" — all removable packages
        """
        targets: list[BloatwareEntry] = []
        for entry in bloatware.removable:
            if level == "safe" and entry.impact != "high":
                continue
            if level == "moderate" and entry.impact == "low":
                continue
            targets.append(entry)

        if not targets:
            self._print("No packages to disable at this level.")
            return 0

        self._print(f"Disabling {len(targets)} packages ({level} mode)...")
        disabled = 0
        for entry in targets:
            self._print(f"  → {entry.name} ({entry.package})")
            # Force stop first to free resources immediately
            self._record(force_stop_package(entry.package, self.adb_path))
            change = disable_package(entry.package, self.adb_path)
            self._record(change)
            if change:
                disabled += 1
                self.stats["packages_disabled"] += 1

        self._print(f"  ✓ Disabled {disabled}/{len(targets)} packages")
        return disabled

    def run_settings_optimization(self) -> int:
        """Apply performance-improving settings."""
        count = 0

        self._print("Optimizing animation scales (0.5x)...")
        changes = set_animation_scale("0.5", self.adb_path)
        self._records(changes)
        count += len(changes)

        self._print("Setting background process limit (4)...")
        change = set_background_process_limit(4, self.adb_path)
        self._record(change)
        if change:
            count += 1

        self.stats["settings_changed"] = count
        self._print(f"  ✓ {count} settings optimized")
        return count

    def run_battery_optimization(self, bloatware: BloatwareDiagnosis) -> int:
        """Apply battery-saving optimizations."""
        count = 0

        # Restrict background for high-impact bloatware that's still enabled
        self._print("Restricting background activity for battery drainers...")
        for entry in bloatware.removable:
            if entry.impact == "high":
                change = restrict_background_data(entry.package, self.adb_path)
                self._record(change)
                if change:
                    count += 1
                    self._print(f"  → Restricted: {entry.name}")

        # Optimize doze/screen settings
        self._print("Optimizing power settings...")
        doze_changes = optimize_doze(self.adb_path)
        self._records(doze_changes)
        count += len(doze_changes)

        self.stats["battery_optimized"] = count
        self._print(f"  ✓ {count} battery optimizations applied")
        return count

    def run_all(self, bloatware: BloatwareDiagnosis, level: str = "safe") -> dict:
        """Run all optimization phases."""
        self._print("")
        self._print("═══ PHASE 1: Debloating ═══")
        self.run_debloat(bloatware, level)

        self._print("")
        self._print("═══ PHASE 2: Settings Optimization ═══")
        self.run_settings_optimization()

        self._print("")
        self._print("═══ PHASE 3: Battery Optimization ═══")
        self.run_battery_optimization(bloatware)

        # Save rollback snapshot
        save_snapshot(self.snapshot)
        total = len(self.snapshot.changes)
        self._print("")
        self._print(f"═══ COMPLETE: {total} changes applied ═══")
        self._print(f"  Rollback saved. Run `android-doctor rollback` to undo all changes.")
        self._print("")

        return self.stats


def run_rollback(adb_path: str | None = None) -> int:
    """Undo all changes from the last fix run."""
    from fix.debloat import enable_package
    from fix.settings import restore_setting
    from fix.battery import unrestrict_background, grant_location_for_package
    from fix.rollback import delete_snapshot

    snapshot = load_snapshot()
    if not snapshot:
        print("  No rollback snapshot found. Nothing to undo.")
        return 0

    print(f"  Rolling back {len(snapshot.changes)} changes from {snapshot.device_model}...")
    restored = 0

    # Reverse in opposite order
    for change in reversed(snapshot.changes):
        try:
            if change.action == "disable_package":
                if enable_package(change.target, adb_path):
                    print(f"  ✓ Re-enabled: {change.target}")
                    restored += 1
            elif change.action == "set_setting":
                if restore_setting(change.target, change.original_value, adb_path):
                    print(f"  ✓ Restored: {change.target} = {change.original_value}")
                    restored += 1
            elif change.action == "restrict_background":
                if unrestrict_background(change.target, adb_path):
                    print(f"  ✓ Unrestricted: {change.target}")
                    restored += 1
            elif change.action == "revoke_location":
                if grant_location_for_package(change.target, adb_path):
                    print(f"  ✓ Restored location: {change.target}")
                    restored += 1
            elif change.action in ("force_stop", "clear_cache"):
                # Not reversible, skip
                continue
        except Exception as e:
            print(f"  ⚠ Failed to rollback {change.target}: {e}")

    delete_snapshot()
    print(f"\n  Rollback complete: {restored}/{len(snapshot.changes)} changes restored.")
    return restored
