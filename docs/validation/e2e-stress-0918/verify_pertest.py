# Per-test maximum duration across the 9 stress rounds, so the claim that the two race
# regressions (preferences-race, quotes-race) never failed and never approached the 30s
# navigation cap can be checked by name rather than by memory.
import collections
import pathlib
import re

ARCH = pathlib.Path(__file__).resolve().parent  # the archive itself; the temp dir it came from is volatile
LINE = re.compile(r"^([\u2714\u2716])\s+(.*?)\s+\(([\d.]+)ms\)\s*$")

worst = collections.defaultdict(float)
verdict = collections.defaultdict(set)
for round_no in range(1, 10):
    text = (ARCH / f"round-{round_no}.log").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        match = LINE.match(line.strip())
        if not match:
            continue
        name, seconds = match.group(2).strip(), float(match.group(3))
        # the failing-tests section repeats each failure, so keep one row per round
        key = (round_no, name)
        worst[key] = seconds
        verdict[name].add(match.group(1))

per_test = collections.defaultdict(float)
for (round_no, name), seconds in worst.items():
    per_test[name] = max(per_test[name], seconds)

print("== slowest per test across 9 rounds ==")
for name, seconds in sorted(per_test.items(), key=lambda kv: -kv[1])[:6]:
    marks = "".join(sorted(verdict[name]))
    print(f"  {seconds:8.0f}ms  marks={marks}  {name[:44]}")

print("\n== any test that ever failed ==")
for name, marks in sorted(verdict.items()):
    if "\u2716" in marks:
        print(f"  {marks}  {name[:60]}")

print(f"\ntotal scenario-runs counted: {len(worst)} (expect 180)")
print(f"distinct test names: {len(verdict)} (expect 20)")
