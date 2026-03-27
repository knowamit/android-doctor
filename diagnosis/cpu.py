"""CPU load and thermal throttling diagnosis."""

from __future__ import annotations
from dataclasses import dataclass
from adb.parsers import CpuData, ThermalZone


@dataclass(frozen=True)
class CpuDiagnosis:
    severity: str
    total_load_pct: float
    load_avg_1: float
    is_throttling: bool
    max_temp_c: float
    top_hogs: tuple[tuple[str, float], ...]  # (name, cpu_pct)
    findings: tuple[str, ...]
    score: int


def diagnose_cpu(cpu: CpuData, thermals: tuple[ThermalZone, ...]) -> CpuDiagnosis:
    """Analyze CPU load, thermal state, and top consumers."""
    findings = []
    score = 100

    # Load average assessment
    if cpu.load_avg_1 > 4.0:
        findings.append(f"Load average extremely high: {cpu.load_avg_1:.1f} / {cpu.load_avg_5:.1f} / {cpu.load_avg_15:.1f}")
        score -= 25
    elif cpu.load_avg_1 > 2.0:
        findings.append(f"Load average elevated: {cpu.load_avg_1:.1f} / {cpu.load_avg_5:.1f} / {cpu.load_avg_15:.1f}")
        score -= 15
    elif cpu.load_avg_1 > 1.0:
        findings.append(f"Load average moderate: {cpu.load_avg_1:.1f} / {cpu.load_avg_5:.1f} / {cpu.load_avg_15:.1f}")
        score -= 5
    else:
        findings.append(f"Load average normal: {cpu.load_avg_1:.1f} / {cpu.load_avg_5:.1f} / {cpu.load_avg_15:.1f}")

    # Total CPU usage
    if cpu.total_load_pct > 80:
        findings.append(f"CPU utilization very high: {cpu.total_load_pct}%")
        score -= 20
    elif cpu.total_load_pct > 50:
        findings.append(f"CPU utilization elevated: {cpu.total_load_pct}%")
        score -= 10

    # Top CPU hogs
    hogs = []
    for proc in cpu.top_processes[:5]:
        if proc.cpu_pct > 10:
            findings.append(f"High CPU process: {proc.name} ({proc.cpu_pct}%)")
            hogs.append((proc.name, proc.cpu_pct))
            score -= 5

    # Thermal throttling detection
    is_throttling = False
    max_temp = 0.0
    cpu_zones = [z for z in thermals if any(k in z.name.lower() for k in ["cpu", "soc", "big", "little", "cluster"])]

    for zone in cpu_zones:
        if zone.temp_c > max_temp:
            max_temp = zone.temp_c
        if zone.temp_c > 80:
            findings.append(f"CPU thermal throttling active: {zone.name} at {zone.temp_c}C")
            is_throttling = True
            score -= 20
        elif zone.temp_c > 70:
            findings.append(f"CPU running hot: {zone.name} at {zone.temp_c}C — may throttle under load")
            is_throttling = True
            score -= 10

    if not cpu_zones and thermals:
        max_temp = max(z.temp_c for z in thermals)
        if max_temp > 50:
            findings.append(f"Highest thermal reading: {max_temp}C")

    if not findings:
        findings.append("CPU load appears normal")

    score = max(0, min(100, score))
    severity = "ok" if score >= 70 else ("warning" if score >= 40 else "critical")

    return CpuDiagnosis(
        severity=severity,
        total_load_pct=cpu.total_load_pct,
        load_avg_1=cpu.load_avg_1,
        is_throttling=is_throttling,
        max_temp_c=max_temp,
        top_hogs=tuple(hogs),
        findings=tuple(findings),
        score=score,
    )
