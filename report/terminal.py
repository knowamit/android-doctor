"""Rich terminal output for diagnosis reports."""

from __future__ import annotations
import sys
from adb.connection import DeviceInfo
from diagnosis.battery import BatteryDiagnosis
from diagnosis.storage import StorageDiagnosis
from diagnosis.memory import MemoryDiagnosis
from diagnosis.cpu import CpuDiagnosis
from diagnosis.bloatware import BloatwareDiagnosis, BloatwareEntry
from diagnosis.verdict import Verdict


# ANSI color codes
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _supports_color():
        return text
    return f"{code}{text}{C.RESET}"


def _severity_icon(severity: str) -> str:
    icons = {"ok": "🟢", "warning": "🟡", "critical": "🔴", "healthy": "🟢", "degraded": "🟡", "unhealthy": "🟠", "critical": "🔴"}
    return icons.get(severity, "⚪")


def _score_bar(score: int, width: int = 20) -> str:
    filled = int(score / 100 * width)
    empty = width - filled
    if score >= 70:
        color = C.GREEN
    elif score >= 40:
        color = C.YELLOW
    else:
        color = C.RED
    bar = _c(color, "█" * filled) + _c(C.DIM, "░" * empty)
    return f"{bar} {score}/100"


def _hr(char: str = "─", width: int = 60) -> str:
    return _c(C.DIM, char * width)


def print_header():
    print()
    print(_c(C.BOLD + C.CYAN, "  ╔═══════════════════════════════════════════════════╗"))
    print(_c(C.BOLD + C.CYAN, "  ║") + _c(C.BOLD + C.WHITE, "       ANDROID DOCTOR — Diagnosis Report        ") + _c(C.BOLD + C.CYAN, "║"))
    print(_c(C.BOLD + C.CYAN, "  ╚═══════════════════════════════════════════════════╝"))
    print()


def print_device_info(device: DeviceInfo):
    print(_c(C.BOLD, "  DEVICE"))
    print(_hr())
    print(f"  Model:     {_c(C.WHITE + C.BOLD, f'{device.brand} {device.model}')}")
    print(f"  Android:   {device.android_version} (SDK {device.sdk_version})")
    print(f"  Chipset:   {device.chipset or 'unknown'}")
    print(f"  RAM:       {device.total_ram_mb} MB")
    print(f"  Storage:   {device.storage_type.upper()}")
    print(f"  Build:     {device.build_display}")
    print()


def print_battery(diag: BatteryDiagnosis):
    icon = _severity_icon(diag.severity)
    print(f"  {icon} {_c(C.BOLD, 'BATTERY & THERMAL')}  {_score_bar(diag.score)}")
    print(_hr())
    for finding in diag.findings:
        prefix = "  ⚠ " if any(w in finding.lower() for w in ["critical", "degraded", "elevated", "high"]) else "  • "
        if "critical" in finding.lower() or "severely" in finding.lower():
            print(_c(C.RED, f"{prefix}{finding}"))
        elif any(w in finding.lower() for w in ["degraded", "elevated", "high", "hot"]):
            print(_c(C.YELLOW, f"{prefix}{finding}"))
        else:
            print(f"{prefix}{finding}")
    if diag.is_throttling:
        print(_c(C.RED + C.BOLD, "  ⚡ THERMAL THROTTLING DETECTED — CPU speed is being reduced"))
    print()


def print_storage(diag: StorageDiagnosis):
    icon = _severity_icon(diag.severity)
    print(f"  {icon} {_c(C.BOLD, 'STORAGE HEALTH')}  {_score_bar(diag.score)}")
    print(_hr())
    for finding in diag.findings:
        prefix = "  ⚠ " if any(w in finding.lower() for w in ["critical", "warning", "full", "emmc"]) else "  • "
        if "critical" in finding.lower() or "urgent" in finding.lower():
            print(_c(C.RED, f"{prefix}{finding}"))
        elif any(w in finding.lower() for w in ["warning", "full", "emmc", "wear"]):
            print(_c(C.YELLOW, f"{prefix}{finding}"))
        else:
            print(f"{prefix}{finding}")
    print()


def print_memory(diag: MemoryDiagnosis):
    icon = _severity_icon(diag.severity)
    print(f"  {icon} {_c(C.BOLD, 'MEMORY (RAM)')}  {_score_bar(diag.score)}")
    print(_hr())
    for finding in diag.findings:
        if "critical" in finding.lower() or "severely" in finding.lower():
            print(_c(C.RED, f"  ⚠ {finding}"))
        elif any(w in finding.lower() for w in ["high", "heavy", "low", "insufficient"]):
            print(_c(C.YELLOW, f"  ⚠ {finding}"))
        else:
            print(f"  • {finding}")
    print()


def print_cpu(diag: CpuDiagnosis):
    icon = _severity_icon(diag.severity)
    print(f"  {icon} {_c(C.BOLD, 'CPU & PROCESSES')}  {_score_bar(diag.score)}")
    print(_hr())
    for finding in diag.findings:
        if "throttling" in finding.lower() or "critical" in finding.lower():
            print(_c(C.RED, f"  ⚠ {finding}"))
        elif "high" in finding.lower() or "elevated" in finding.lower() or "hot" in finding.lower():
            print(_c(C.YELLOW, f"  ⚠ {finding}"))
        else:
            print(f"  • {finding}")
    print()


def print_bloatware(diag: BloatwareDiagnosis):
    icon = _severity_icon(diag.severity)
    print(f"  {icon} {_c(C.BOLD, 'BLOATWARE SCAN')}  {_score_bar(diag.score)}")
    print(_hr())
    for finding in diag.findings:
        print(f"  • {finding}")

    if diag.removable:
        print()
        print(_c(C.BOLD, "  Top removable packages:"))
        shown = 0
        for entry in diag.removable:
            if shown >= 15:
                remaining = len(diag.removable) - shown
                print(_c(C.DIM, f"  ... and {remaining} more"))
                break
            impact_color = C.RED if entry.impact == "high" else (C.YELLOW if entry.impact == "medium" else C.DIM)
            impact_label = _c(impact_color, f"[{entry.impact.upper()}]")
            print(f"    {impact_label} {entry.name} ({_c(C.DIM, entry.package)})")
            if entry.description:
                print(f"         {_c(C.DIM, entry.description)}")
            shown += 1
    print()


def print_verdict(verdict: Verdict):
    print(_c(C.BOLD + C.CYAN, "  ╔═══════════════════════════════════════════════════╗"))
    icon = _severity_icon(verdict.overall_severity)
    score_text = f"Overall Health: {verdict.overall_score}/100 ({verdict.overall_severity.upper()})"
    print(_c(C.BOLD + C.CYAN, "  ║") + f" {icon} {_c(C.BOLD + C.WHITE, score_text):<52}" + _c(C.BOLD + C.CYAN, "║"))
    print(_c(C.BOLD + C.CYAN, "  ╚═══════════════════════════════════════════════════╝"))
    print()

    # Root cause attribution
    print(_c(C.BOLD, "  ROOT CAUSE BREAKDOWN"))
    print(_hr())
    hw = verdict.hardware_pct
    sw = verdict.software_pct
    th = verdict.thermal_pct

    bar_width = 30
    hw_bar = "█" * int(hw / 100 * bar_width)
    sw_bar = "█" * int(sw / 100 * bar_width)
    th_bar = "█" * int(th / 100 * bar_width)

    print(f"  Hardware (storage/RAM):  {_c(C.RED, hw_bar):<{bar_width + 10}} {hw}%")
    print(f"  Software (bloat/apps):   {_c(C.YELLOW, sw_bar):<{bar_width + 10}} {sw}%")
    print(f"  Thermal (battery/heat):  {_c(C.CYAN, th_bar):<{bar_width + 10}} {th}%")
    print()

    # Top issues
    if verdict.top_issues:
        print(_c(C.BOLD, "  TOP ISSUES"))
        print(_hr())
        for i, issue in enumerate(verdict.top_issues, 1):
            print(f"  {i}. {issue}")
        print()

    # Recommendation
    print(_c(C.BOLD + C.GREEN, "  RECOMMENDATION"))
    print(_hr())
    # Wrap recommendation text
    words = verdict.recommendation.split()
    line = "  "
    for word in words:
        if len(line) + len(word) + 1 > 60:
            print(line)
            line = "  " + word
        else:
            line += " " + word if line.strip() else "  " + word
    if line.strip():
        print(line)
    print()


def print_full_report(
    device: DeviceInfo,
    battery: BatteryDiagnosis,
    storage: StorageDiagnosis,
    memory: MemoryDiagnosis,
    cpu: CpuDiagnosis,
    bloatware: BloatwareDiagnosis,
    verdict: Verdict,
):
    """Print the complete diagnosis report."""
    print_header()
    print_device_info(device)
    print_battery(battery)
    print_storage(storage)
    print_memory(memory)
    print_cpu(cpu)
    print_bloatware(bloatware)
    print_verdict(verdict)
