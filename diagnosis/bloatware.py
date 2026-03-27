"""Bloatware detection and analysis."""

from __future__ import annotations
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BloatwareEntry:
    package: str
    name: str
    category: str  # "telemetry" | "ads" | "assistant" | "media" | "social" | "carrier" | "duplicate" | "other"
    impact: str  # "high" | "medium" | "low"
    description: str


@dataclass(frozen=True)
class BloatwareDiagnosis:
    severity: str
    total_system_packages: int
    bloatware_found: int
    high_impact_count: int
    removable: tuple[BloatwareEntry, ...]
    already_disabled: tuple[str, ...]
    findings: tuple[str, ...]
    score: int


def _load_bloatware_db() -> dict:
    """Load the bloatware database."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bloatware_db.json")
    with open(db_path) as f:
        return json.load(f)


def _detect_oem(system_packages: list[str]) -> str:
    """Detect phone manufacturer from package names."""
    oem_prefixes = {
        "samsung": ["com.samsung.", "com.sec."],
        "xiaomi": ["com.miui.", "com.xiaomi."],
        "oppo": ["com.coloros.", "com.nearme.", "com.oplus.", "com.heytap."],
        "vivo": ["com.vivo.", "com.bbk."],
        "oneplus": ["com.oneplus."],
        "huawei": ["com.huawei."],
        "realme": ["com.realme."],
        "google": ["com.google."],
    }
    counts: dict[str, int] = {}
    for pkg in system_packages:
        for oem, prefixes in oem_prefixes.items():
            if any(pkg.startswith(p) for p in prefixes):
                counts[oem] = counts.get(oem, 0) + 1

    # Google is always present, ignore unless it dominates (Pixel)
    google_count = counts.get("google", 0)
    non_google = {k: v for k, v in counts.items() if k != "google"}

    if non_google:
        return max(non_google, key=lambda k: non_google[k])
    if google_count > 20:
        return "google"
    return "unknown"


def diagnose_bloatware(
    system_packages: list[str],
    disabled_packages: list[str],
    brand: str = "",
) -> BloatwareDiagnosis:
    """Scan for removable bloatware."""
    db = _load_bloatware_db()
    findings = []

    oem = brand.lower() if brand else _detect_oem(system_packages)
    findings.append(f"Detected OEM: {oem}")
    findings.append(f"Total system packages: {len(system_packages)}")

    # Build lookup of all known bloatware
    all_bloat: dict[str, dict] = {}
    for section in ["google", oem]:
        if section in db:
            for entry in db[section]:
                all_bloat[entry["package"]] = entry
    # Also check "common" section
    if "common" in db:
        for entry in db["common"]:
            all_bloat[entry["package"]] = entry

    # Match against installed system packages
    found: list[BloatwareEntry] = []
    already_disabled_found: list[str] = []
    disabled_set = set(disabled_packages)

    for pkg in system_packages:
        if pkg in all_bloat:
            entry_data = all_bloat[pkg]
            if pkg in disabled_set:
                already_disabled_found.append(pkg)
            else:
                found.append(BloatwareEntry(
                    package=pkg,
                    name=entry_data.get("name", pkg),
                    category=entry_data.get("category", "other"),
                    impact=entry_data.get("impact", "low"),
                    description=entry_data.get("description", ""),
                ))

    # Sort by impact
    impact_order = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda e: impact_order.get(e.impact, 3))

    high_count = sum(1 for e in found if e.impact == "high")
    med_count = sum(1 for e in found if e.impact == "medium")

    if found:
        findings.append(f"Removable bloatware: {len(found)} packages ({high_count} high-impact, {med_count} medium)")
    else:
        findings.append("No known bloatware detected — clean install!")

    if already_disabled_found:
        findings.append(f"Already disabled: {len(already_disabled_found)} packages (good)")

    # Categorize findings
    categories: dict[str, int] = {}
    for entry in found:
        categories[entry.category] = categories.get(entry.category, 0) + 1
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        findings.append(f"  {cat}: {count} packages")

    # Score
    score = 100
    score -= high_count * 8
    score -= med_count * 4
    score -= max(0, (len(found) - 10)) * 2  # penalty for sheer volume
    score = max(0, min(100, score))

    severity = "ok" if score >= 70 else ("warning" if score >= 40 else "critical")

    return BloatwareDiagnosis(
        severity=severity,
        total_system_packages=len(system_packages),
        bloatware_found=len(found),
        high_impact_count=high_count,
        removable=tuple(found),
        already_disabled=tuple(already_disabled_found),
        findings=tuple(findings),
        score=score,
    )
