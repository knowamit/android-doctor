"""Battery health diagnosis."""

from __future__ import annotations
from dataclasses import dataclass
from adb.parsers import BatteryData, ThermalZone


@dataclass(frozen=True)
class BatteryDiagnosis:
    severity: str  # "ok" | "warning" | "critical"
    health_pct: float
    cycle_count: int
    temperature_c: float
    is_throttling: bool
    findings: tuple[str, ...]
    score: int  # 0-100


def diagnose_battery(battery: BatteryData, thermals: tuple[ThermalZone, ...]) -> BatteryDiagnosis:
    """Analyze battery health and thermal throttling risk."""
    findings = []
    score = 100

    # Battery capacity health
    if battery.health_pct > 0:
        if battery.health_pct < 70:
            findings.append(f"Battery capacity severely degraded: {battery.health_pct}% of original")
            score -= 40
        elif battery.health_pct < 80:
            findings.append(f"Battery capacity degraded: {battery.health_pct}% of original")
            score -= 25
        elif battery.health_pct < 90:
            findings.append(f"Battery showing wear: {battery.health_pct}% of original capacity")
            score -= 10
        else:
            findings.append(f"Battery capacity healthy: {battery.health_pct}%")
    else:
        findings.append("Battery capacity data unavailable (may need root)")

    # Cycle count
    if battery.cycle_count >= 0:
        if battery.cycle_count > 800:
            findings.append(f"Very high cycle count: {battery.cycle_count} (expected degradation)")
            score -= 20
        elif battery.cycle_count > 500:
            findings.append(f"High cycle count: {battery.cycle_count} (battery aging)")
            score -= 10
        elif battery.cycle_count > 300:
            findings.append(f"Moderate cycle count: {battery.cycle_count}")
            score -= 5
        else:
            findings.append(f"Low cycle count: {battery.cycle_count}")

    # Temperature check
    is_throttling = False
    if battery.temperature_c > 0:
        if battery.temperature_c > 45:
            findings.append(f"Battery temperature CRITICAL: {battery.temperature_c}C — active throttling likely")
            is_throttling = True
            score -= 25
        elif battery.temperature_c > 40:
            findings.append(f"Battery temperature elevated: {battery.temperature_c}C — throttling possible")
            is_throttling = True
            score -= 15
        elif battery.temperature_c > 35:
            findings.append(f"Battery temperature warm: {battery.temperature_c}C")
            score -= 5
        else:
            findings.append(f"Battery temperature normal: {battery.temperature_c}C")

    # Check thermal zones for CPU/GPU throttling
    cpu_temps = [z for z in thermals if any(k in z.name.lower() for k in ["cpu", "soc", "little", "big"])]
    gpu_temps = [z for z in thermals if "gpu" in z.name.lower()]

    for zone in cpu_temps:
        if zone.temp_c > 80:
            findings.append(f"CPU thermal zone '{zone.name}' critical: {zone.temp_c}C")
            is_throttling = True
            score -= 15
        elif zone.temp_c > 70:
            findings.append(f"CPU thermal zone '{zone.name}' hot: {zone.temp_c}C")
            is_throttling = True
            score -= 10

    for zone in gpu_temps:
        if zone.temp_c > 75:
            findings.append(f"GPU thermal zone '{zone.name}' hot: {zone.temp_c}C")
            is_throttling = True
            score -= 10

    # Battery health status from system
    if battery.health not in ("good", "unknown"):
        # Some devices (Pixel 4a) report "failure" even with decent capacity
        # due to driver quirks at high cycle counts. Weight this contextually.
        if battery.health == "failure" and battery.health_pct > 85:
            findings.append(
                f"System reports battery health: {battery.health} "
                f"(likely driver false-positive — capacity is {battery.health_pct}%)"
            )
            score -= 5
        else:
            findings.append(f"System reports battery health: {battery.health}")
            score -= 20

    score = max(0, min(100, score))

    if score >= 70:
        severity = "ok"
    elif score >= 40:
        severity = "warning"
    else:
        severity = "critical"

    return BatteryDiagnosis(
        severity=severity,
        health_pct=battery.health_pct,
        cycle_count=battery.cycle_count,
        temperature_c=battery.temperature_c,
        is_throttling=is_throttling,
        findings=tuple(findings),
        score=score,
    )
