# Recomputes every number quoted by the §99 stress report from the raw jsonl/csv logs.
# Run from the archive directory: python3 verify_stats.py
# Percentile convention throughout: nearest-rank on the ascending-sorted list,
# index = clamp(round(q/100*(n-1))) 0-based. Cap-killed samples are NOT excluded, so a
# p99 of 30000ms means "clipped by Playwright's default 30s navigation timeout", not a
# measured duration.
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(name):
    out = []
    for line in (HERE / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("{"):
            rec = json.loads(line)
            if rec.get("kind") in ("summary", "worst10"):
                continue
            out.append(rec)
    return out


def pct(values, q):
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))
    return ordered[index]


def dist(label, values):
    n = len(values)
    print(f"{label:10} n={n:4} p50={pct(values,50):7.0f} p90={pct(values,90):7.0f} "
          f"p99={pct(values,99):7.0f} max={max(values):7.0f} mean={statistics.mean(values):7.0f}")


print("== suite rounds (round-*.log / summary.txt) ==")
# node --test prints its summary as "# tests N" / "# pass N" / "# fail N" lines, here rendered with
# the info marker; the English words "passed"/"failed" never occur, so grepping for them yields
# nothing and every round used to print "(no result line)".
for p in sorted(HERE.glob("round-*.log")):
    txt = p.read_text(encoding="utf-8", errors="replace")
    got = {}
    for ln in txt.splitlines():
        # Each summary line is "<marker> <key> <number>" where the marker is the single char
        # U+2139. It cannot be matched with [^\w] because Python classifies U+2139 as a letter.
        m = re.match(r"^.\s+(tests|pass|fail|cancelled|skipped|duration_ms)\s+([\d.]+)$",
                     ln.strip())
        if m:
            got[m.group(1)] = m.group(2)
    if not got:
        print(f"{p.name}: (no result line)")
        continue
    print(f"{p.name}: tests={got.get('tests')} pass={got.get('pass')} fail={got.get('fail')} "
          f"cancelled={got.get('cancelled')} skipped={got.get('skipped')} "
          f"duration_ms={got.get('duration_ms')}")

print("\n== probe1 (fixture --model-delay 3, 200 cold boots) ==")
r1 = rows("probe1.jsonl")
g1 = [r["goto"] for r in r1 if isinstance(r.get("goto"), (int, float))]
dist("goto", g1)
kills1 = [r for r in r1 if r.get("navError")]
print(f"over 6000ms: {len([v for v in g1 if v > 6000])}  cap-kills: {len(kills1)}")
for r in kills1:
    print(f"  kill i={r['i']} at={r['at']}Z goto={r['goto']} nodeRoot={r['nodeRoot']}ms "
          f"rootStatus={r.get('rootStatus')} err={r['navError']}")
print("  distinct navError texts: " + str({r["navError"] for r in kills1}))

print("\n== probe1b (same code path, re-run) ==")
r1b = rows("probe1b.jsonl")
g1b = [r["goto"] for r in r1b if isinstance(r.get("goto"), (int, float))]
dist("goto", g1b)
kills1b = [r for r in r1b if r.get("navError")]
print(f"over 6000ms: {len([v for v in g1b if v > 6000])}  cap-kills: {len(kills1b)}")
for r in kills1b:
    print(f"  kill i={r['i']} at={r['at']}Z goto={r['goto']} nodeRoot={r['nodeRoot']}ms "
          f"rootStatus={r.get('rootStatus')}")

print("\n== probe2 (fixture --model-delay 0, 150 boots, Chrome NavigationTiming) ==")
r2 = rows("probe2.jsonl")
g2 = [r["goto"] for r in r2 if isinstance(r.get("goto"), (int, float))]
dist("goto", g2)
nav = [r["nav"] for r in r2 if r.get("nav")]
print(f"nav-timing rows: {len(nav)}   fixtureAnswered true: "
      f"{len([r for r in r2 if r.get('fixtureAnswered')])}/{len(r2)}")
for key in ("connect", "ttfb", "transfer", "responseEnd", "afterResponse"):
    vals = [n[key] for n in nav if isinstance(n.get(key), (int, float))]
    dist(key, vals)
share = [n["nav"]["afterResponse"] / n["goto"] * 100 for n in r2
         if n.get("nav", {}).get("afterResponse") and isinstance(n.get("goto"), (int, float))]
print(f"afterResponse share of goto: p50={pct(share,50):.1f}% min={min(share):.1f}% "
      f"max={max(share):.1f}%")
print(f"cap-kills in probe2: {len([r for r in r2 if r.get('navError')])}, "
      f"goto>4000ms: {len([v for v in g2 if v > 4000])}")

print("\n== probe3 (same browser/instant: data: vs http: vs Node fetch, 150 boots) ==")
r3 = rows("probe3.jsonl")
for key in ("data", "http", "data2", "nodeRoot"):
    dist(key, [r[key] for r in r3 if isinstance(r.get(key), (int, float))])
print(f"slow(>4000ms any nav) rows: {len([r for r in r3 if r.get('slow')])}")
print(f"navError rows: {len([r for r in r3 if any(k.endswith('Error') for k in r)])}")
print(f"http>=4000ms rows: {len([r for r in r3 if r.get('http', 0) >= 4000])} "
      f"-> discriminator never fires if this is 0")

print("\n== sampler-masked.csv (top-8 processes per tick; tick is ~2.0s and values are ms/tick, NOT ms/s) ==")
# Name column is the masked one (role_* / proc_NN); stamps, PIDs and cpu_ms are the original values.
lines = (HERE / "sampler-masked.csv").read_text(encoding="utf-8").splitlines()
recs = [ln.split(",") for ln in lines[1:] if ln and not ln.startswith("sampler")]
by_name = {}
for stamp, pid, name, cpu in recs:
    by_name.setdefault(name, []).append(int(cpu))
print(f"ticks: {len({r[0] for r in recs})}, rows: {len(recs)}, distinct processes: {len(by_name)}")
for name, vals in sorted(by_name.items(), key=lambda kv: -sum(kv[1]))[:8]:
    print(f"  {name:16} peak={max(vals):7}ms/tick  sum={sum(vals):9}ms")
