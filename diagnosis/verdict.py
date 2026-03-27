"""Final verdict: combine all diagnoses into root cause attribution."""

from __future__ import annotations
from dataclasses import dataclass
from diagnosis.battery import BatteryDiagnosis
from diagnosis.storage import StorageDiagnosis
from diagnosis.memory import MemoryDiagnosis
from diagnosis.cpu import CpuDiagnosis
from diagnosis.bloatware import BloatwareDiagnosis


@dataclass(frozen=True)
class Verdict:
    overall_score: int  # 0-100
    overall_severity: str  # "healthy" | "degraded" | "unhealthy" | "critical"
    hardware_pct: int  # % of slowdown attributed to hardware
    software_pct: int  # % attributed to software/bloat
    thermal_pct: int  # % attributed to thermal/battery
    top_issues: tuple[str, ...]  # ranked list of top problems
    recommendation: str  # primary recommendation


def compute_verdict(
    battery: BatteryDiagnosis,
    storage: StorageDiagnosis,
    memory: MemoryDiagnosis,
    cpu: CpuDiagnosis,
    bloatware: BloatwareDiagnosis,
) -> Verdict:
    """Compute final diagnosis verdict with root cause attribution."""

    # Weighted overall score
    weights = {
        "battery": 0.20,
        "storage": 0.25,
        "memory": 0.25,
        "cpu": 0.15,
        "bloatware": 0.15,
    }
    overall = int(
        battery.score * weights["battery"]
        + storage.score * weights["storage"]
        + memory.score * weights["memory"]
        + cpu.score * weights["cpu"]
        + bloatware.score * weights["bloatware"]
    )

    # Root cause attribution
    # Hardware = storage wear + low RAM (can't fix with software)
    # Thermal = battery degradation + throttling
    # Software = bloatware + high CPU from apps + RAM pressure from apps

    hw_penalty = max(0, 100 - storage.score) + max(0, min(30, 100 - memory.score) if memory.total_mb < 4096 else 0)
    thermal_penalty = max(0, 100 - battery.score) + (20 if cpu.is_throttling else 0)
    sw_penalty = max(0, 100 - bloatware.score) + max(0, 100 - cpu.score)

    total_penalty = hw_penalty + thermal_penalty + sw_penalty
    if total_penalty > 0:
        hardware_pct = int(hw_penalty / total_penalty * 100)
        thermal_pct = int(thermal_penalty / total_penalty * 100)
        software_pct = 100 - hardware_pct - thermal_pct
    else:
        hardware_pct = 0
        thermal_pct = 0
        software_pct = 0

    # Collect and rank top issues
    issues = []

    if storage.score < 50:
        issues.append(("Storage degradation (NAND wear + I/O slowdown)", 100 - storage.score))
    if memory.score < 50:
        issues.append(("RAM pressure (insufficient memory, swap thrashing)", 100 - memory.score))
    if battery.score < 50:
        issues.append(("Battery degradation causing thermal throttling", 100 - battery.score))
    if bloatware.score < 70:
        issues.append((f"Bloatware ({bloatware.bloatware_found} removable packages)", 100 - bloatware.score))
    if cpu.score < 60:
        issues.append(("High CPU usage from background processes", 100 - cpu.score))

    if storage.score < 80 and storage.score >= 50:
        issues.append(("Moderate storage wear", 100 - storage.score))
    if memory.score < 80 and memory.score >= 50:
        issues.append(("Elevated RAM usage", 100 - memory.score))
    if battery.score < 80 and battery.score >= 50:
        issues.append(("Battery showing age", 100 - battery.score))

    issues.sort(key=lambda x: -x[1])
    top_issues = tuple(issue[0] for issue in issues[:5])

    # Primary recommendation
    if not issues:
        recommendation = "Your phone looks healthy! No major issues detected."
    else:
        worst = issues[0][0].lower()
        if "storage" in worst:
            recommendation = (
                "Primary bottleneck is storage degradation. "
                "Run `android-doctor fix` to remove bloatware and reduce I/O pressure. "
                "Consider a phone with UFS storage for your next device."
            )
        elif "ram" in worst:
            recommendation = (
                "Primary bottleneck is RAM pressure. "
                "Run `android-doctor fix` to disable bloatware and free memory. "
                "Avoid keeping many apps open simultaneously."
            )
        elif "battery" in worst or "thermal" in worst:
            recommendation = (
                "Battery degradation is causing thermal throttling. "
                "Run `android-doctor fix` to reduce CPU load from bloatware. "
                "Consider battery replacement (~$30-50 at a repair shop)."
            )
        elif "bloatware" in worst:
            recommendation = (
                "Manufacturer bloatware is the primary issue. "
                "Run `android-doctor fix` to safely disable unnecessary packages. "
                "This is the most impactful fix available."
            )
        else:
            recommendation = (
                "Multiple factors contributing to slowdown. "
                "Run `android-doctor fix` for software optimizations."
            )

    if overall >= 80:
        severity = "healthy"
    elif overall >= 60:
        severity = "degraded"
    elif overall >= 40:
        severity = "unhealthy"
    else:
        severity = "critical"

    return Verdict(
        overall_score=overall,
        overall_severity=severity,
        hardware_pct=hardware_pct,
        software_pct=software_pct,
        thermal_pct=thermal_pct,
        top_issues=top_issues,
        recommendation=recommendation,
    )
