# android-doctor

### Find out why your Android phone is slow. Then fix it.

Your 2-year-old Android phone didn't get slow by accident. The storage chips are physically degrading. Samsung pre-installed 47 apps you never asked for. Google Play Services is eating 400MB of your RAM. Your battery is causing the CPU to throttle itself by 30-50%.

A factory reset won't fix hardware wear. "Cleaner" apps on the Play Store are scams that show fake scans and display ads. **android-doctor** connects to your phone via USB, runs real hardware diagnostics, identifies the actual root cause, fixes what it can, and proves it with before/after benchmarks.

Zero dependencies. No root. No ads. No cloud. Fully reversible.

---

## 21% faster app launches — measured, not promised

Real results from a Pixel 4a after running `android-doctor fix` + `android-doctor clean`:

```
  BENCHMARK: BEFORE vs AFTER

  SYSTEM METRICS
  ───────────────────────────────────────────────
  RAM free:       2021 MB →   2311 MB  +290 MB
  RAM used:       63.9%  →   58.7%    -5%
  Swap used:       629 MB →    624 MB  -5 MB

  APP LAUNCH TIMES (cold start)
  ───────────────────────────────────────────────
  settings
    Before: ██████████████████████████████ 842ms
    After:  ████████████ 346ms  ▼ 496ms faster (59%)
  dialer
    Before: ██████████████████████████████ 1144ms
    After:  █████████████ 510ms  ▼ 634ms faster (55%)
  whatsapp
    Before: ██████████████████████████████ 990ms
    After:  █████████████████ 575ms  ▼ 415ms faster (42%)
  photos
    Before: ██████████████████████████████ 794ms
    After:  ██████████████████████ 593ms  ▼ 201ms faster (25%)

  AVERAGE
  Apps launch 21% faster on average (218ms saved)
```

These numbers come from `am start -W` cold launch measurements on a real device. The tool measures, then optimizes, then measures again. You see exactly what changed.

---

## Quick start

```bash
git clone https://github.com/Ammroid/android-doctor.git
cd android-doctor

# Connect your Android phone via USB (USB debugging must be enabled)
./android-doctor diagnose
```

That's it. Python 3.9+ and ADB are the only requirements. No `pip install`.

### Install ADB if you don't have it

```bash
# macOS
brew install android-platform-tools

# Linux (Debian/Ubuntu)
sudo apt install adb

# Windows
choco install adb
```

### Enable USB debugging on your phone

Settings → About Phone → tap "Build Number" 7 times → back to Settings → Developer Options → enable "USB Debugging" → connect via USB → tap "Allow" on the prompt

---

## What it does

### Diagnose — what's actually wrong

```bash
./android-doctor diagnose
```

```
  ╔═══════════════════════════════════════════════════╗
  ║       ANDROID DOCTOR — Diagnosis Report          ║
  ╚═══════════════════════════════════════════════════╝

  DEVICE
  Model:     samsung SM-A525F | Android 13 | 4GB RAM | eMMC

  🟡 BATTERY & THERMAL                    50/100
    ⚠ Battery capacity degraded: 78% of original
    ⚠ High cycle count: 512
    ⚡ THERMAL THROTTLING DETECTED

  🟢 STORAGE HEALTH                       75/100
    ⚠ Storage type: eMMC (degrades faster than UFS)
    • NAND flash moderate wear: 30% consumed

  🟡 MEMORY (RAM)                         55/100
    ⚠ RAM usage high: 85% (570 MB free)
    ⚠ Moderate swap: 648 MB

  🔴 BLOATWARE SCAN                        0/100
    • 29 removable packages (9 high-impact)
    • Bixby, Samsung Pay, Facebook Services...

  ╔═══════════════════════════════════════════════════╗
  ║ 🟠 Overall Health: 52/100 (UNHEALTHY)            ║
  ╚═══════════════════════════════════════════════════╝

  ROOT CAUSE BREAKDOWN
  Hardware (storage/RAM):  ██████            21%
  Software (bloat/apps):   ███████████████   53%
  Thermal (battery/heat):  ███████           26%
```

It reads real hardware data — NAND flash wear levels, battery charge cycles, thermal zone temperatures, per-process CPU/RAM usage — and attributes your slowdown to hardware, software, or thermal causes with percentages.

### Benchmark — measure what you can feel

```bash
./android-doctor benchmark --before     # measure app launch times
# ... make changes ...
./android-doctor benchmark --after      # auto-compares with "before"
./android-doctor history                # track trends over time
```

Measures cold app launch times (via `am start -W`), storage I/O speed, RAM pressure, swap usage, and process count. The `--after` flag automatically generates a before/after comparison.

### Fix — debloat + optimize + battery

```bash
./android-doctor fix                    # safe: high-impact bloatware only
./android-doctor fix --moderate         # + medium-impact
./android-doctor fix --aggressive       # everything removable
```

Disables bloatware via `pm disable-user` (no root needed), optimizes animation scales, limits background processes, restricts battery-draining background activity, and tunes power settings. Every change is recorded.

### Autofix — scientific optimization loop

```bash
./android-doctor autofix
```

```
  Iteration 1: Disable Bixby Voice
    → RAM freed: 87 MB | CPU idle improved: 3.2%
    ✅ KEEPING (measurable improvement)

  Iteration 2: Disable AR Zone
    → RAM freed: 12 MB | CPU idle improved: 0.1%
    ↩ REVERTED (no measurable improvement)

  Iteration 3: Set animation scale 0.5x
    → UI responsiveness improved
    ✅ KEEPING

  ... 12 more iterations ...

  TOTAL: 5 kept, 10 reverted
  All changes are reversible: android-doctor rollback
```

Tries each optimization individually, measures the impact on RAM/CPU/swap, keeps only what helps, reverts what doesn't. Data-driven, not guesswork.

### Clean — free gigabytes of cache

```bash
./android-doctor clean
```

```
  ⏳ Checking storage... 77 GB free
  ⏳ Trimming all app caches... done
  ⏳ Checking storage... 80 GB free

  ✓ Freed 3.3 GB of cache
```

Clears all app caches system-wide using `pm trim-caches`. Your photos, messages, app data — untouched. Just cached files that will be recreated as needed.

### Rollback — undo everything

```bash
./android-doctor rollback
```

```
  Rolling back 6 changes from Pixel 4a...
  ✓ Re-enabled: com.google.android.apps.docs
  ✓ Restored: global:background_process_limit = -1
  ✓ Restored: global:window_animation_scale = 1.0
  Rollback complete: 6/6 changes restored.
```

Every change is snapshotted before it's made. One command restores everything.

---

## All commands

| Command | What it does |
|---------|-------------|
| `./android-doctor diagnose` | Full diagnostic: battery, storage, RAM, CPU, thermal, bloatware |
| `./android-doctor benchmark --before` | Measure app launch times, I/O speed, RAM before fixes |
| `./android-doctor benchmark --after` | Measure again, auto-compare with before |
| `./android-doctor history` | Show performance trends across all benchmark runs |
| `./android-doctor fix` | Safe debloat + settings + battery optimization |
| `./android-doctor fix --aggressive` | Remove all identified bloatware |
| `./android-doctor autofix` | Scientific optimization loop with before/after proof |
| `./android-doctor clean` | Clear all app caches (freed 3.3 GB on test device) |
| `./android-doctor battery` | Battery health, cycle count, thermal throttling, drain analysis |
| `./android-doctor report` | Export diagnosis as shareable HTML file |
| `./android-doctor rollback` | Undo every change made by fix/autofix |
| `./android-doctor info` | Device info only |
| `./android-doctor bloatware` | Bloatware scan only |

---

## What it checks

| Category | Metrics | How |
|----------|---------|-----|
| **Battery** | Capacity %, charge cycles, temperature, thermal throttling state | `/sys/class/power_supply/battery/*` + `dumpsys battery` + `dumpsys thermalservice` |
| **Storage** | NAND wear level (eMMC/UFS), pre-EOL status, disk space, storage type | `/sys/class/mmc_host/*/life_time` + UFS health descriptors + `df` |
| **Memory** | Total/used/available RAM, swap pressure, per-process breakdown | `/proc/meminfo` + `dumpsys meminfo` |
| **CPU** | Load average, per-process CPU%, thermal zone temperatures | `dumpsys cpuinfo` + `/sys/class/thermal/thermal_zone*` |
| **Bloatware** | OEM-specific bloat across 8 manufacturers, 113 packages with impact ratings | `pm list packages` matched against curated database |
| **Performance** | Cold app launch times, sequential I/O speed, process count | `am start -W` + `dd` benchmarks |

---

## Supported manufacturers

The bloatware database covers packages from:

- **Samsung** — 30 packages (Bixby suite, Samsung Pay, AR suite, Samsung Free, telemetry)
- **Xiaomi / MIUI** — 25 packages (MSA ads, analytics, Mi apps, Joyose telemetry)
- **Oppo / ColorOS** — 14 packages (HeyTap suite, boot telemetry, ROM statistics)
- **Vivo / FunTouch** — 10 packages
- **OnePlus / OxygenOS** — 5 packages
- **Huawei / EMUI** — 11 packages (AppGallery, HiVoice, Petal Search)
- **Google / Pixel** — 8 packages (Digital Wellbeing, ARCore, Google TV)
- **Common pre-installs** — 10 packages (Facebook Services, LinkedIn, OneDrive)

The database includes impact ratings (high/medium/low) and categories (telemetry, ads, duplicate, assistant, media) so you know exactly what each package does and why it's safe to disable.

---

## Why existing tools aren't enough

| | Play Store "cleaners" | UAD-ng | Battery Historian | android-doctor |
|--|--|--|--|--|
| Reads NAND flash wear | No | No | No | Yes |
| Reads battery cycles | No | No | Yes | Yes |
| Detects thermal throttling | No | No | No | Yes |
| Identifies root cause | No | No | No | Yes (hardware vs software vs thermal %) |
| Removes bloatware | No (they ARE bloatware) | Yes | No | Yes |
| Before/after benchmarks | No | No | No | Yes (app launch times, I/O, RAM) |
| Tracks trends over time | No | No | No | Yes |
| Battery optimization | No | No | No | Yes |
| Cache clearing | Fake scans | No | No | Yes (freed 3.3 GB on test device) |
| Fully reversible | N/A | Partial | N/A | Yes (one-command rollback) |
| Requires root | Often | No | No | No |
| Shows ads | Yes | No | No | No |
| Open source | No | Yes | Yes | Yes |

---

## Why Android phones slow down — the real reasons

1. **NAND flash degradation** — Your storage chips physically wear out. Each write cycle damages the oxide layer. After 1,000-3,000 cycles (TLC NAND), read/write speeds degrade 30-50%. A factory reset doesn't repair silicon.

2. **Battery-driven thermal throttling** — After 300-500 charge cycles, your battery's internal resistance rises. It generates more heat under load. The CPU throttles itself by 30-50% to prevent overheating. Your phone is literally running at half speed.

3. **Manufacturer bloatware** — Samsung ships ~47 pre-installed apps. Xiaomi's MSA ad framework runs constantly. Facebook Services is pre-installed on most phones. These consume RAM, CPU, and battery even when you never open them.

4. **Software inflation** — The apps you re-install after a factory reset are the 2024 versions, not the 2021 versions your phone shipped with. Google Play Services alone uses 400MB+ of RAM on a 4GB phone.

5. **eMMC storage** — Budget phones use eMMC (half-duplex, ~300 MB/s) instead of UFS (full-duplex, ~2,100 MB/s). eMMC degrades 2-3x faster. A budget phone from 2021 is running on dying storage by 2024.

6. **Proven corporate negligence** — Samsung's Game Optimizing Service throttled 10,000+ apps while exempting benchmark apps ($58M settlement, 2026). Apple's Batterygate throttled iPhones without disclosure ($500M settlement, 2020). Italy fined both companies for updates that "significantly reduced performance to accelerate phone substitution."

---

## Project structure

```
android-doctor/
├── android-doctor          # CLI entry point (just run this)
├── doctor.py               # Command router
├── adb/
│   ├── connection.py       # Device detection, ADB runner
│   ├── commands.py         # 25+ ADB command wrappers
│   └── parsers.py          # Structured data from raw output
├── diagnosis/
│   ├── battery.py          # Battery health + thermal throttling
│   ├── storage.py          # NAND wear + eMMC/UFS + disk space
│   ├── memory.py           # RAM pressure + swap analysis
│   ├── cpu.py              # CPU load + process hogs + thermals
│   ├── bloatware.py        # OEM bloatware detection
│   ├── benchmark.py        # App launch times + I/O speed
│   ├── history.py          # Persistent trend tracking
│   └── verdict.py          # Root cause attribution engine
├── fix/
│   ├── debloat.py          # Package disable/enable + cache trim
│   ├── settings.py         # Animation, background limits
│   ├── battery.py          # Background restrict, doze, drain analysis
│   ├── autofix.py          # Scientific optimization loop
│   ├── engine.py           # Fix orchestrator
│   └── rollback.py         # Snapshot + restore system
├── report/
│   ├── terminal.py         # Colored terminal output
│   └── html.py             # Shareable HTML export
├── data/
│   └── bloatware_db.json   # 113 packages across 8 OEMs
└── tests/
```

Zero pip dependencies. Pure Python 3.9+ standard library + ADB.

---

## Roadmap

- [x] Diagnostic engine (battery, storage, RAM, CPU, thermal, bloatware)
- [x] Fix command with safe debloating, settings optimization, battery tuning
- [x] Autofix loop — try each optimization, measure, keep only what helps
- [x] App launch time benchmarks with before/after comparison
- [x] Performance history and trend tracking
- [x] Cache clearing (system-wide)
- [x] HTML report export
- [x] Full rollback system
- [ ] Storage I/O benchmark (sequential + random 4K)
- [ ] Per-app battery drain ranking
- [ ] Shizuku-based Android companion app (no PC needed)
- [ ] Custom bloatware lists via YAML config

---

## Contributing

The bloatware database (`data/bloatware_db.json`) is the easiest way to contribute. If you have a phone from a manufacturer not fully covered, submit a PR adding packages with their impact ratings.

Run the diagnostic on your phone and share your results — especially if you have a Samsung, Xiaomi, or Oppo device with heavy bloatware. The before/after benchmarks from `android-doctor benchmark` make great evidence.

---

## License

MIT — do whatever you want with it.
