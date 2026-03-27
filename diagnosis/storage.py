"""Storage health diagnosis."""

from __future__ import annotations
from dataclasses import dataclass
from adb.parsers import StorageHealthData


@dataclass(frozen=True)
class StorageDiagnosis:
    severity: str  # "ok" | "warning" | "critical"
    storage_type: str
    life_remaining_pct: float  # -1 if unknown
    space_used_pct: float
    total_gb: float
    available_gb: float
    findings: tuple[str, ...]
    score: int


def diagnose_storage(health: StorageHealthData) -> StorageDiagnosis:
    """Analyze storage health: wear level, space, type."""
    findings = []
    score = 100

    # Storage type assessment
    stype = health.storage_type
    if stype == "emmc":
        findings.append("Storage type: eMMC (slower, degrades faster than UFS)")
        score -= 10
    elif stype == "ufs":
        findings.append("Storage type: UFS (fast, good longevity)")
    else:
        findings.append("Storage type: could not detect (eMMC/UFS unknown)")

    # NAND wear level
    life_remaining = -1.0
    if health.life_used_pct >= 0:
        life_remaining = max(0, 100 - health.life_used_pct)
        if health.life_used_pct >= 80:
            findings.append(f"NAND flash wear CRITICAL: {health.life_used_pct:.0f}% life consumed, {life_remaining:.0f}% remaining")
            score -= 40
        elif health.life_used_pct >= 50:
            findings.append(f"NAND flash showing wear: {health.life_used_pct:.0f}% life consumed, {life_remaining:.0f}% remaining")
            score -= 20
        elif health.life_used_pct >= 30:
            findings.append(f"NAND flash moderate wear: {health.life_used_pct:.0f}% consumed")
            score -= 10
        else:
            findings.append(f"NAND flash healthy: only {health.life_used_pct:.0f}% consumed")
    else:
        findings.append("NAND wear data unavailable (may need root or older kernel)")

    # Pre-EOL status
    if health.pre_eol == "urgent":
        findings.append("Storage pre-EOL status: URGENT — nearing end of life")
        score -= 30
    elif health.pre_eol == "warning":
        findings.append("Storage pre-EOL status: WARNING — significant wear")
        score -= 15
    elif health.pre_eol == "normal":
        findings.append("Storage pre-EOL status: normal")

    # Disk space — find /data partition
    data_part = None
    total_gb = 0.0
    available_gb = 0.0
    space_used_pct = 0.0

    for p in health.partitions:
        if p.mount in ("/data", "/data/media", "/storage/emulated"):
            data_part = p
            break
    if not data_part:
        # Fallback: largest partition
        candidates = [p for p in health.partitions if p.total_mb > 1000]
        if candidates:
            data_part = max(candidates, key=lambda p: p.total_mb)

    if data_part:
        total_gb = data_part.total_mb / 1024
        available_gb = data_part.available_mb / 1024
        space_used_pct = data_part.use_pct

        if space_used_pct > 95:
            findings.append(f"Storage almost full: {space_used_pct:.0f}% used ({available_gb:.1f} GB free of {total_gb:.0f} GB)")
            score -= 25
        elif space_used_pct > 85:
            findings.append(f"Storage getting full: {space_used_pct:.0f}% used ({available_gb:.1f} GB free)")
            score -= 15
        elif space_used_pct > 70:
            findings.append(f"Storage usage moderate: {space_used_pct:.0f}% used ({available_gb:.1f} GB free)")
            score -= 5
        else:
            findings.append(f"Storage space healthy: {space_used_pct:.0f}% used ({available_gb:.1f} GB free)")

    score = max(0, min(100, score))
    severity = "ok" if score >= 70 else ("warning" if score >= 40 else "critical")

    return StorageDiagnosis(
        severity=severity,
        storage_type=stype,
        life_remaining_pct=life_remaining,
        space_used_pct=space_used_pct,
        total_gb=total_gb,
        available_gb=available_gb,
        findings=tuple(findings),
        score=score,
    )
