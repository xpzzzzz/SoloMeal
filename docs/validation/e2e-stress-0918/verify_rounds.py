# Recomputes the suite-round and host-attribution numbers quoted by the §99 report
# from round-*.log and sampler-masked.csv.  Run from the archive directory: python3 verify_rounds.py
# Result lines are read from the runner's own per-test output: "✔ <name> (<ms>ms)" /
# "✖ <name> (<ms>ms)".  Failures are re-listed at the bottom of each log with their stack.
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent  # the archive itself; the temp dir it came from is volatile
LINE = re.compile(r"^([✔✖]) (.+?) \((\d+(?:\.\d+)?)ms\)", re.M)

print("== per-round outcome, from round-*.log ==")
all_pass_ms = []
slow_pass = []
by_round = {}
for p in sorted(HERE.glob("round-*.log"), key=lambda x: int(x.stem.split("-")[1])):
    txt = p.read_text(encoding="utf-8", errors="replace")
    # Keep only the results block, not the "failing tests" re-listing at the bottom.
    head = txt.split("✖ failing tests")[0]
    rows = [(m.group(1), m.group(2), float(m.group(3))) for m in LINE.finditer(head)]
    npass = sum(1 for r in rows if r[0] == "✔")
    nfail = sum(1 for r in rows if r[0] == "✖")
    dur = re.search(r"duration_ms ([\d.]+)", txt)
    print(f"{p.name}: tests={len(rows)} pass={npass} fail={nfail} "
          f"runner_duration={float(dur.group(1))/1000 if dur else float('nan'):.1f}s")
    by_round[p.stem] = rows
    for mark, name, ms in rows:
        if mark == "✔":
            all_pass_ms.append((p.stem, name, ms))
            if ms >= 20000:
                slow_pass.append((p.stem, name, ms))

print("\n== passing runs >=20s (the sub-cap tail) ==")
print(f"count={len(slow_pass)} of {len(all_pass_ms)} passing runs across 9 rounds")
for r, n, ms in sorted(slow_pass, key=lambda x: -x[2]):
    print(f"  {r} {ms/1000:6.1f}s  {n[:44]}")
print(f"  >=25s: {len([x for x in slow_pass if x[2] >= 25000])}")
print("  by round: " + str(Counter(r for r, _, _ in slow_pass)))

print("\n== failures (kept, not overwritten by later green rounds) ==")
fails = [(r, n, ms) for r, rows in by_round.items() for m, n, ms in rows if m == "✖"]
for r, n, ms in sorted(fails, key=lambda x: (x[0], -x[2])):
    print(f"  {r} {ms/1000:6.1f}s  {n[:44]}")
print(f"  total {len(fails)} failing scenario-runs over 180; "
      f"distinct test names={len({n for _, n, _ in fails})}")

print("\n== slowest passing run per round (how close to the cap without failing) ==")
for r in sorted(by_round, key=lambda x: int(x.split('-')[1])):
    best = max(((ms, n) for m, n, ms in by_round[r] if m == "✔"), default=None)
    if best:
        print(f"  {r}: {best[0]/1000:6.1f}s  {best[1][:44]}")

print("\n== sampler-masked.csv: stall window vs control ==")
# sampler.ps1 asks for Sleep 1500ms but enumerating every process costs ~500ms more, so the
# real tick interval is p50 2.00s (min 1.00s, max 2.00s). The CPU column is a delta of
# Get-Process.CPU in milliseconds PER TICK, not per second: divide by ~2.0 to get cores.
# The name column here is the masked one: role_* tags stand for the processes this report
# reasons about by name, proc_NN for the rest. See report section 2 "脱敏副本口径".
print("tick interval is ~2.0s and the CPU column is ms/tick, NOT ms/s (see report §7-3)")
lines = (HERE / "sampler-masked.csv").read_text(encoding="utf-8").splitlines()[1:]
recs = []
for ln in lines:
    parts = ln.split(",")
    if len(parts) != 4 or not parts[3].isdigit():
        continue
    h, m, s = (int(x) for x in parts[0].split(":"))
    recs.append((h * 3600 + m * 60 + s, parts[1], parts[2], int(parts[3])))
names = sorted({r[2] for r in recs})
print(f"rows={len(recs)} distinct names={len(names)}: {', '.join(names)}")


def window(lo, hi, label):
    # sampler.ps1 keys on $p.Id, so each tick's 8 rows are the top-8 PIDs, NOT the top-8 distinct
    # process names: one name can occupy several slots (role_browser_under_test does in 13 ticks). Aggregate by name
    # and keep the two apart -- "appears" counts ticks, "rows" counts CSV lines.
    sub = [r for r in recs if lo <= r[0] <= hi]
    ticks = len({r[0] for r in sub})
    print(f"\n{label}: ticks-with-data={ticks} rows={len(sub)}")
    if not ticks:
        print("    (no samples -- this window is outside the sampler's coverage)")
        return
    per = {}
    for st, _, nm, cpu in sub:
        per.setdefault(nm, []).append((st, cpu))
    ranked = sorted(per, key=lambda n: -sum(c for _, c in per[n]))
    for nm in dict.fromkeys(ranked[:8] + REPORT_NAMES):
        v = per.get(nm)
        if not v:
            print(f"    {nm:22} absent from this window")
            continue
        tot = sum(c for _, c in v)
        bytick = Counter()
        for st, c in v:
            bytick[st] += c
        print(f"    {nm:22} sum={tot/1000:7.1f}s  mean={round(tot/ticks):5}ms/tick  "
              f"appears={len(bytick):3}/{ticks} ticks  rows={len(v):3}  "
              f"peak={max(bytick.values()):5}ms/tick (largest single pid {max(c for _, c in v)})")


REPORT_NAMES = ["role_ambient_heavy_1", "role_ambient_heavy_3", "role_ambient_heavy_2",
                "role_browser_under_test", "role_test_runner", "role_fixture_server"]


# probe1b cap-kills were logged at 13:51:50Z / 13:52:31Z / 13:53:08Z; sampler stamps are local (UTC+8).
def L(h, m, s=0):
    return h * 3600 + m * 60 + s


first = min(r[0] for r in recs)
last = max(r[0] for r in recs)
print(f"\nsampler covers {first//3600:02d}:{first%3600//60:02d}:{first%60:02d} to "
      f"{last//3600:02d}:{last%3600//60:02d}:{last%60:02d} local")

# The three windows the report quotes in §3.5. All three sit INSIDE the sampler's coverage, which
# is the point: the earlier draft of this script used 21:20-21:40 and 22:05-22:16 as "controls"
# and both contain zero samples (report §7-4). Those are kept at the end only to show they are empty.
window(first, L(21, 51, 29), "before-control  21:46:57-21:51:29")
window(L(21, 51, 30), L(21, 53, 35), "STALL WINDOW    21:51:30-21:53:35")
window(L(21, 53, 36), last, "after-control   21:53:36-22:00:56")

print("\n== the two invalid 'control' windows from the retracted draft (§7-4) ==")
window(L(21, 20), L(21, 40), "control A   21:20:00-21:40:00")
window(L(22, 5), L(22, 16), "control B   22:05:00-22:16:00")
