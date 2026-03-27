"""Memory/RAM diagnosis."""

from __future__ import annotations
from dataclasses import dataclass
from adb.parsers import MemoryData


@dataclass(frozen=True)
class MemoryDiagnosis:
    severity: str
    total_mb: int
    available_mb: int
    used_pct: float
    swap_used_mb: int
    findings: tuple[str, ...]
    score: int


def diagnose_memory(mem: MemoryData) -> MemoryDiagnosis:
    """Analyze RAM usage and pressure."""
    findings = []
    score = 100

    # Total RAM assessment
    if mem.total_mb < 2048:
        findings.append(f"Total RAM: {mem.total_mb} MB — severely insufficient for modern Android")
        score -= 30
    elif mem.total_mb < 3072:
        findings.append(f"Total RAM: {mem.total_mb} MB — low for modern apps")
        score -= 20
    elif mem.total_mb < 4096:
        findings.append(f"Total RAM: {mem.total_mb} MB — adequate but tight")
        score -= 10
    elif mem.total_mb < 6144:
        findings.append(f"Total RAM: {mem.total_mb} MB — decent")
    else:
        findings.append(f"Total RAM: {mem.total_mb} MB — plenty")

    # RAM pressure
    if mem.used_pct > 90:
        findings.append(f"RAM usage CRITICAL: {mem.used_pct}% used ({mem.available_mb} MB free)")
        score -= 30
    elif mem.used_pct > 80:
        findings.append(f"RAM usage high: {mem.used_pct}% used ({mem.available_mb} MB free)")
        score -= 20
    elif mem.used_pct > 70:
        findings.append(f"RAM usage moderate: {mem.used_pct}% ({mem.available_mb} MB free)")
        score -= 10
    else:
        findings.append(f"RAM usage healthy: {mem.used_pct}% ({mem.available_mb} MB free)")

    # Swap usage (indicates RAM pressure)
    swap_used = mem.swap_total_mb - mem.swap_free_mb
    if swap_used > 0:
        if swap_used > 1024:
            findings.append(f"Heavy swap usage: {swap_used} MB — severe RAM pressure, causes I/O thrashing")
            score -= 25
        elif swap_used > 512:
            findings.append(f"Moderate swap usage: {swap_used} MB — RAM pressure causing slowdowns")
            score -= 15
        elif swap_used > 100:
            findings.append(f"Light swap usage: {swap_used} MB")
            score -= 5
    else:
        if mem.swap_total_mb > 0:
            findings.append("No swap in use — good")

    # Low available memory warning
    if mem.available_mb < 300 and mem.total_mb > 0:
        findings.append(f"CRITICALLY low free memory: {mem.available_mb} MB — app reloads and jank expected")
        score -= 15

    score = max(0, min(100, score))
    severity = "ok" if score >= 70 else ("warning" if score >= 40 else "critical")

    return MemoryDiagnosis(
        severity=severity,
        total_mb=mem.total_mb,
        available_mb=mem.available_mb,
        used_pct=mem.used_pct,
        swap_used_mb=swap_used,
        findings=tuple(findings),
        score=score,
    )
