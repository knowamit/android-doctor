"""Generate shareable HTML diagnosis report."""

from __future__ import annotations
import html
import os
import time

from adb.connection import DeviceInfo
from diagnosis.battery import BatteryDiagnosis
from diagnosis.storage import StorageDiagnosis
from diagnosis.memory import MemoryDiagnosis
from diagnosis.cpu import CpuDiagnosis
from diagnosis.bloatware import BloatwareDiagnosis
from diagnosis.verdict import Verdict


def _severity_color(severity: str) -> str:
    return {
        "ok": "#22c55e", "healthy": "#22c55e",
        "warning": "#eab308", "degraded": "#eab308",
        "critical": "#ef4444", "unhealthy": "#f97316",
    }.get(severity, "#94a3b8")


def _score_gradient(score: int) -> str:
    if score >= 70:
        return "#22c55e"
    if score >= 40:
        return "#eab308"
    return "#ef4444"


def _findings_html(findings: tuple[str, ...]) -> str:
    items = []
    for f in findings:
        escaped = html.escape(f)
        if any(w in f.lower() for w in ["critical", "severely", "very high", "extremely"]):
            items.append(f'<li class="finding critical">{escaped}</li>')
        elif any(w in f.lower() for w in ["degraded", "elevated", "high", "hot", "warning", "heavy"]):
            items.append(f'<li class="finding warning">{escaped}</li>')
        else:
            items.append(f'<li class="finding ok">{escaped}</li>')
    return "\n".join(items)


def generate_html_report(
    device: DeviceInfo,
    battery: BatteryDiagnosis,
    storage: StorageDiagnosis,
    memory: MemoryDiagnosis,
    cpu: CpuDiagnosis,
    bloatware: BloatwareDiagnosis,
    verdict: Verdict,
) -> str:
    """Generate a complete HTML report string."""

    bloat_rows = ""
    for entry in bloatware.removable[:20]:
        impact_class = entry.impact
        bloat_rows += f"""
        <tr>
          <td><span class="impact {impact_class}">{entry.impact.upper()}</span></td>
          <td>{html.escape(entry.name)}</td>
          <td class="mono">{html.escape(entry.package)}</td>
          <td>{html.escape(entry.description)}</td>
        </tr>"""

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Android Doctor — {html.escape(device.brand)} {html.escape(device.model)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
    background: #09090b;
    color: #e4e4e7;
    padding: 2rem;
    max-width: 900px;
    margin: 0 auto;
    line-height: 1.6;
  }}
  h1 {{
    font-size: 1.5rem;
    letter-spacing: -0.03em;
    border-bottom: 1px solid #27272a;
    padding-bottom: 0.75rem;
    margin-bottom: 1.5rem;
  }}
  h1 span {{ color: #c2703e; }}
  .meta {{
    color: #71717a;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 1.5rem;
  }}
  .device-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 2rem;
    margin-bottom: 2rem;
    padding: 1rem;
    border: 1px solid #27272a;
    border-radius: 4px;
  }}
  .device-grid dt {{ color: #71717a; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .device-grid dd {{ color: #e4e4e7; font-weight: 600; margin-bottom: 0.5rem; }}
  .section {{
    margin-bottom: 2rem;
    border: 1px solid #27272a;
    border-radius: 4px;
    overflow: hidden;
  }}
  .section-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #27272a;
    background: #18181b;
  }}
  .section-title {{ font-weight: 600; font-size: 0.9rem; }}
  .score {{
    font-size: 0.85rem;
    font-weight: 700;
    padding: 0.15rem 0.6rem;
    border-radius: 3px;
  }}
  .section-body {{ padding: 1rem; }}
  .score-bar {{
    height: 6px;
    background: #27272a;
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 1rem;
  }}
  .score-bar-fill {{ height: 100%; border-radius: 3px; }}
  ul.findings {{ list-style: none; }}
  li.finding {{ padding: 0.3rem 0; font-size: 0.85rem; }}
  li.finding.critical::before {{ content: "🔴 "; }}
  li.finding.warning::before {{ content: "🟡 "; }}
  li.finding.ok::before {{ content: "🟢 "; }}
  .verdict {{
    border: 2px solid {_severity_color(verdict.overall_severity)};
    border-radius: 4px;
    padding: 1.5rem;
    margin-bottom: 2rem;
    text-align: center;
  }}
  .verdict-score {{
    font-size: 3rem;
    font-weight: 800;
    letter-spacing: -0.05em;
    color: {_score_gradient(verdict.overall_score)};
  }}
  .verdict-label {{
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: {_severity_color(verdict.overall_severity)};
    margin-top: 0.25rem;
  }}
  .breakdown {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1rem;
    margin: 1.5rem 0;
  }}
  .breakdown-item {{ text-align: center; }}
  .breakdown-pct {{
    font-size: 1.5rem;
    font-weight: 700;
  }}
  .breakdown-label {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #71717a;
  }}
  .issues ol {{
    padding-left: 1.5rem;
    margin: 0.5rem 0;
  }}
  .issues li {{ font-size: 0.85rem; padding: 0.2rem 0; }}
  .recommendation {{
    background: #14532d;
    border: 1px solid #166534;
    border-radius: 4px;
    padding: 1rem;
    font-size: 0.85rem;
    margin-top: 1rem;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }}
  th {{
    text-align: left;
    padding: 0.5rem;
    border-bottom: 1px solid #27272a;
    color: #71717a;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  td {{ padding: 0.4rem 0.5rem; border-bottom: 1px solid #18181b; }}
  .mono {{ font-size: 0.75rem; color: #71717a; }}
  .impact {{
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.1rem 0.4rem;
    border-radius: 2px;
    text-transform: uppercase;
  }}
  .impact.high {{ background: #7f1d1d; color: #fca5a5; }}
  .impact.medium {{ background: #713f12; color: #fde68a; }}
  .impact.low {{ background: #1c1917; color: #78716c; }}
  .footer {{
    text-align: center;
    color: #52525b;
    font-size: 0.7rem;
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid #18181b;
  }}
  .footer a {{ color: #c2703e; text-decoration: none; }}
</style>
</head>
<body>
  <h1><span>android-doctor</span> — Diagnosis Report</h1>
  <p class="meta">Generated {timestamp}</p>

  <dl class="device-grid">
    <dt>Model</dt><dd>{html.escape(device.brand)} {html.escape(device.model)}</dd>
    <dt>Android</dt><dd>{html.escape(device.android_version)} (SDK {html.escape(device.sdk_version)})</dd>
    <dt>Chipset</dt><dd>{html.escape(device.chipset or 'unknown')}</dd>
    <dt>RAM</dt><dd>{device.total_ram_mb} MB</dd>
    <dt>Storage</dt><dd>{device.storage_type.upper()}</dd>
    <dt>Build</dt><dd>{html.escape(device.build_display)}</dd>
  </dl>

  <div class="verdict">
    <div class="verdict-score">{verdict.overall_score}</div>
    <div class="verdict-label">{verdict.overall_severity}</div>
  </div>

  <div class="breakdown">
    <div class="breakdown-item">
      <div class="breakdown-pct" style="color:#ef4444">{verdict.hardware_pct}%</div>
      <div class="breakdown-label">Hardware</div>
    </div>
    <div class="breakdown-item">
      <div class="breakdown-pct" style="color:#eab308">{verdict.software_pct}%</div>
      <div class="breakdown-label">Software</div>
    </div>
    <div class="breakdown-item">
      <div class="breakdown-pct" style="color:#3b82f6">{verdict.thermal_pct}%</div>
      <div class="breakdown-label">Thermal</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Battery & Thermal</span>
      <span class="score" style="background:{_score_gradient(battery.score)}20;color:{_score_gradient(battery.score)}">{battery.score}/100</span>
    </div>
    <div class="section-body">
      <div class="score-bar"><div class="score-bar-fill" style="width:{battery.score}%;background:{_score_gradient(battery.score)}"></div></div>
      <ul class="findings">{_findings_html(battery.findings)}</ul>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Storage Health</span>
      <span class="score" style="background:{_score_gradient(storage.score)}20;color:{_score_gradient(storage.score)}">{storage.score}/100</span>
    </div>
    <div class="section-body">
      <div class="score-bar"><div class="score-bar-fill" style="width:{storage.score}%;background:{_score_gradient(storage.score)}"></div></div>
      <ul class="findings">{_findings_html(storage.findings)}</ul>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Memory (RAM)</span>
      <span class="score" style="background:{_score_gradient(memory.score)}20;color:{_score_gradient(memory.score)}">{memory.score}/100</span>
    </div>
    <div class="section-body">
      <div class="score-bar"><div class="score-bar-fill" style="width:{memory.score}%;background:{_score_gradient(memory.score)}"></div></div>
      <ul class="findings">{_findings_html(memory.findings)}</ul>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">CPU & Processes</span>
      <span class="score" style="background:{_score_gradient(cpu.score)}20;color:{_score_gradient(cpu.score)}">{cpu.score}/100</span>
    </div>
    <div class="section-body">
      <div class="score-bar"><div class="score-bar-fill" style="width:{cpu.score}%;background:{_score_gradient(cpu.score)}"></div></div>
      <ul class="findings">{_findings_html(cpu.findings)}</ul>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Bloatware Scan</span>
      <span class="score" style="background:{_score_gradient(bloatware.score)}20;color:{_score_gradient(bloatware.score)}">{bloatware.score}/100</span>
    </div>
    <div class="section-body">
      <div class="score-bar"><div class="score-bar-fill" style="width:{bloatware.score}%;background:{_score_gradient(bloatware.score)}"></div></div>
      <p style="font-size:0.85rem;margin-bottom:0.75rem">
        {bloatware.bloatware_found} removable packages ({bloatware.high_impact_count} high-impact)
      </p>
      <table>
        <thead><tr><th>Impact</th><th>Name</th><th>Package</th><th>Description</th></tr></thead>
        <tbody>{bloat_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="issues">
    <h3 style="font-size:0.9rem;margin-bottom:0.5rem">Top Issues</h3>
    <ol>
      {"".join(f"<li>{html.escape(issue)}</li>" for issue in verdict.top_issues)}
    </ol>
  </div>

  <div class="recommendation">
    {html.escape(verdict.recommendation)}
  </div>

  <div class="footer">
    Generated by <a href="https://github.com/Ammroid/android-doctor">android-doctor</a> v0.1.0
  </div>
</body>
</html>"""


def save_html_report(
    device: DeviceInfo,
    battery: BatteryDiagnosis,
    storage: StorageDiagnosis,
    memory: MemoryDiagnosis,
    cpu: CpuDiagnosis,
    bloatware: BloatwareDiagnosis,
    verdict: Verdict,
    output_path: str | None = None,
) -> str:
    """Generate and save HTML report to file. Returns file path."""
    report_html = generate_html_report(
        device, battery, storage, memory, cpu, bloatware, verdict
    )
    if not output_path:
        safe_model = device.model.replace(" ", "_").replace("/", "_")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"android-doctor-report_{safe_model}_{timestamp}.html"
        # Save to Desktop, fallback to home, fallback to temp
        for directory in [
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~"),
            "/tmp",
        ]:
            if os.path.isdir(directory) and os.access(directory, os.W_OK):
                output_path = os.path.join(directory, filename)
                break
        else:
            output_path = os.path.join("/tmp", filename)

    with open(output_path, "w") as f:
        f.write(report_html)

    return os.path.abspath(output_path)
