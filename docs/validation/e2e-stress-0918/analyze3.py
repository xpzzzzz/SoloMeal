# Repo-external analysis of probe3.jsonl; nothing here is committed.
# Three-way attribution table: data: (no socket, no bundle) vs http: (fixture document) in the
# same browser and same instant, plus a Node fetch of the same URL as the server-side control.
import json
import statistics
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "probe3.jsonl"
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def pct(values, q):
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))
    return ordered[index]


def stats(label, values):
    if not values:
        print(f"{label:8} n=0")
        return
    print(f"{label:8} n={len(values):4} p50={pct(values,50):7.0f} p90={pct(values,90):7.0f} "
          f"p99={pct(values,99):7.0f} max={max(values):7.0f} mean={statistics.mean(values):7.0f}")


print(f"iterations={len(rows)}")
for key in ("data", "http", "data2", "nodeRoot"):
    stats(key, [r[key] for r in rows if key in r])

print("\n-- killed at Playwright's 30s cap --")
for key in ("data", "http", "data2"):
    killed = [r for r in rows if r.get(f"{key}Error")]
    print(f"{key}: {len(killed)}" + "".join(f"  i={r['i']} at={r['at']}" for r in killed))

print("\n-- slow rows (>4000ms on any navigation) --")
slow = [r for r in rows if r.get("slow")]
print(f"count={len(slow)}")
for r in slow:
    print(f"i={r['i']:3} at={r['at']} data={r['data']:6} http={r['http']:6} data2={r['data2']:6} "
          f"node={r['nodeRoot']:5}"
          + (f" err={r.get('httpError') or r.get('dataError') or r.get('data2Error')}" if any(
              r.get(f"{k}Error") for k in ("data", "http", "data2")) else ""))

print("\n-- conditional: http fast (<2000) vs http slow (>=2000), median of the bracketing data: navs --")
fast = [r for r in rows if r.get("http", 9e9) < 2000]
bad = [r for r in rows if r.get("http", 0) >= 2000]
for label, group in (("http<2s", fast), ("http>=2s", bad)):
    if group:
        print(f"{label:9} n={len(group):4} median data={statistics.median(g['data'] for g in group):7.0f} "
              f"median data2={statistics.median(g['data2'] for g in group):7.0f} "
              f"median node={statistics.median(g['nodeRoot'] for g in group):6.0f}")

print("\n-- verdict helper --")
# data: slow alongside http: slow  => browser process/ main thread globally busy.
# data: fast while http: slow     => the stall lives in the network/document-load path, not the process.
both = [r for r in rows if r.get("http", 0) >= 4000 and max(r["data"], r["data2"]) >= 4000]
net_only = [r for r in rows if r.get("http", 0) >= 4000 and max(r["data"], r["data2"]) < 4000]
print(f"http>=4s with data>=4s (process-level): {len(both)}")
print(f"http>=4s with data<4s  (load-path only): {len(net_only)}")
print(f"http>=4s with nodeRoot>=4s (server-side): {len([r for r in rows if r.get('http',0)>=4000 and r.get('nodeRoot',0)>=4000])}")
if both:
    print("process-level rows: " + ", ".join(f"i={r['i']}@{r['at']}" for r in both))
if net_only:
    print("load-path rows:     " + ", ".join(f"i={r['i']}@{r['at']}" for r in net_only))
