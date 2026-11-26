"""Optional frame profiler. Does nothing unless the PIXABY_PROFILE environment variable is set.

    Windows (cmd):   set PIXABY_PROFILE=40
                     python <your usual launcher>
    PowerShell:      $env:PIXABY_PROFILE=40
    Linux / macOS:   PIXABY_PROFILE=40 python <your usual launcher>

Start a level, play normally (move around, fight, shoot arrows, the busy parts!). After the
given number of seconds it prints a report and saves it to profile_report.txt (plus
profile.prof, which `pip install snakeviz` + `snakeviz profile.prof` can draw).

It runs in two halves, because cProfile slows the game down and would distort the timings:
  1st half  plain timers around each part of the frame  -> where the frame time really goes
  2nd half  cProfile                                    -> which functions inside those parts

The hooks live in game.py's main loop (search for `_fp.`). With the variable unset each hook
is one `if` and costs nothing you could measure.
"""
import os
import time
import cProfile
import pstats
import io
from collections import defaultdict

try:
    _TOTAL = float(os.environ.get("PIXABY_PROFILE", "") or 0)
except ValueError:
    _TOTAL = 0.0
ON = _TOTAL > 0

IDLE = "idle (FPS cap wait)"
_clock = time.perf_counter

_laps = defaultdict(float)        # name -> total seconds (phase 1)
_lap_worst = defaultdict(float)   # name -> longest single lap (seconds)
_frame_ms = []                    # work time per frame, FPS-cap wait excluded (phase 1)
_s = {"t0": None, "last": 0.0, "work": 0.0, "phase": 1, "done": False, "prof": None}


def frame_start():
    """Call once at the top of each frame."""
    if not ON or _s["done"]:
        return
    now = _clock()
    if _s["t0"] is None:
        _s["t0"] = now
        print(f"[profiler] timing for {_TOTAL / 2:.0f}s, then cProfile for {_TOTAL / 2:.0f}s "
              f"- play the busy parts of a level")
    elif _s["phase"] == 1:
        _frame_ms.append(_s["work"] * 1000.0)
    _s["work"] = 0.0
    _s["last"] = now

    elapsed = now - _s["t0"]
    if elapsed >= _TOTAL:
        finish()
    elif _s["phase"] == 1 and elapsed >= _TOTAL / 2:
        _s["phase"] = 2
        _s["prof"] = cProfile.Profile()
        _s["prof"].enable()


def lap(name):
    """Attribute the time since the previous lap()/frame_start() to `name`."""
    if not ON or _s["phase"] != 1 or _s["t0"] is None or _s["done"]:
        return
    now = _clock()
    dt = now - _s["last"]
    _s["last"] = now
    _laps[name] += dt
    if dt > _lap_worst[name]:
        _lap_worst[name] = dt
    if name != IDLE:
        _s["work"] += dt


def _percentile(values, p):
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(len(v) * p))]


def _timer_report():
    n = len(_frame_ms)
    if n == 0:
        return "no frames were timed (did a level start before the time ran out?)\n"
    avg = sum(_frame_ms) / n
    out = io.StringIO()
    out.write(f"FRAME TIMES  ({n} frames, FPS-cap wait not counted)\n")
    out.write(f"  average {avg:6.2f} ms   95th percentile {_percentile(_frame_ms, 0.95):6.2f} ms   "
              f"worst {max(_frame_ms):6.2f} ms\n")
    out.write(f"  budget: 33.3 ms at 30 FPS, 16.7 ms at 60 FPS  ->  "
              f"you are using {avg / 33.3 * 100:3.0f}% of a 30 FPS frame\n\n")
    out.write(f"  {'part of the frame':26} {'avg ms':>8} {'% of work':>10} {'worst ms':>9}\n")
    work_total = sum(v for k, v in _laps.items() if k != IDLE) or 1.0
    for name, total in sorted(_laps.items(), key=lambda kv: -kv[1]):
        if name == IDLE:
            out.write(f"  {name:26} {total / n * 1000:8.2f} {'-':>10} {_lap_worst[name] * 1000:9.2f}\n")
        else:
            out.write(f"  {name:26} {total / n * 1000:8.2f} {total / work_total * 100:9.1f}% "
                      f"{_lap_worst[name] * 1000:9.2f}\n")
    return out.getvalue()


def _function_report(pr):
    out = io.StringIO()
    stats = pstats.Stats(pr)

    # how much of the time is the physics code?
    phys_total, phys_rows = 0.0, []
    for (fname, line, func), (cc, nc, tt, ct, _callers) in stats.stats.items():
        if fname.endswith("physics.py") or "_fast" in fname:
            phys_total += tt
            phys_rows.append((tt, nc, func))
    all_tt = sum(v[2] for v in stats.stats.values()) or 1.0
    out.write("PHYSICS (scripts/physics.py)\n")
    out.write(f"  {phys_total:.2f}s of {all_tt:.2f}s profiled = {phys_total / all_tt * 100:.1f}% of all Python time\n")
    for tt, nc, func in sorted(phys_rows, reverse=True)[:6]:
        out.write(f"    {func:28} {tt:7.3f}s  {nc:8d} calls\n")
    out.write("  (if you built _fast, time spent inside it shows up under its caller, not here)\n\n")

    stats.strip_dirs()
    s = io.StringIO()
    stats.stream = s
    stats.sort_stats("tottime").print_stats(22)
    out.write("TOP 22 FUNCTIONS BY OWN TIME (tottime)  - this is what to optimise first\n")
    out.write(_trim(s.getvalue()))

    s = io.StringIO()
    stats.stream = s
    stats.sort_stats("cumulative").print_stats(30)
    out.write("\nTOP 30 BY CUMULATIVE TIME (function + everything it calls)\n")
    out.write(_trim(s.getvalue()))
    return out.getvalue()


def _trim(text):
    """Keep pstats' table, drop its banner lines."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("ncalls"):
            return "\n".join(lines[i:]).rstrip() + "\n"
    return text


def finish():
    """Print + save the report. Safe to call more than once."""
    if not ON or _s["done"] or _s["t0"] is None:
        return
    _s["done"] = True
    pr = _s["prof"]
    if pr is not None:
        pr.disable()

    text = "=" * 78 + "\nPIXEL ABYSS FRAME PROFILE\n" + "=" * 78 + "\n\n" + _timer_report()
    if pr is not None:
        text += "\n" + "-" * 78 + "\n" + _function_report(pr)
    else:
        text += "\n(the second, cProfile half never started: the run was shorter than half the time)\n"
    print(text)
    try:
        with open("profile_report.txt", "w", encoding="utf-8") as fh:
            fh.write(text)
        if pr is not None:
            pr.dump_stats("profile.prof")
        print("[profiler] saved profile_report.txt" + (" and profile.prof" if pr is not None else ""))
    except OSError as ex:
        print("[profiler] could not save the report:", ex)
