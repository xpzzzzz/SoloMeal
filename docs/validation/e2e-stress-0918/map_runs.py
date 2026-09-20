# Maps every slow (>=20s) and failing scenario-run in the 9 stress rounds back to the
# e2e test file that declares it, so the "stalls landed in N different test files" claim
# can be checked against the sources instead of asserted.
import pathlib
import re

ARCH = pathlib.Path(__file__).resolve().parent  # the archive itself; the temp dir it came from is volatile
# This script originally lived in frontend/e2e/, so __file__.parent WAS the source dir. From
# docs/validation/e2e-stress-0918/ the repo root is parents[3]. Without this the title map is
# silently empty and every run prints '??' instead of a filename.
E2E = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "e2e"

PASS, FAIL = "\u2714", "\u2716"

title2file = {}
for path in sorted(E2E.glob("*.test.mjs")):
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"""(?:test|it)\(\s*(['"`])((?:(?!\1).)*)\1""", text, re.S):
        title2file[match.group(2).strip()] = path.name
print(f"titles mapped: {len(title2file)} across {len(list(E2E.glob('*.test.mjs')))} test files")

slow, fails, unmapped, passing = [], [], set(), 0
for round_no in range(1, 10):
    text = (ARCH / f"round-{round_no}.log").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        match = re.match(rf"^([{PASS}{FAIL}])\s+(.*?)\s+\(([\d.]+)ms\)$", line.strip())
        if not match:
            continue
        mark, name, seconds = match.group(1), match.group(2).strip(), float(match.group(3)) / 1000
        source = title2file.get(name)
        if source is None:
            unmapped.add(name)
            source = "??"
        if mark == PASS:
            passing += 1
        if mark == FAIL:
            fails.append((round_no, name, seconds, source))
        elif seconds >= 20:
            slow.append((round_no, name, seconds, source))

print(f"unmapped titles: {unmapped or '(none)'}")

print(f"\n== failing runs: {len(fails)} raw lines, {len({(r, n) for r, n, *_ in fails})} distinct round+name (node --test prints each failure twice, see report §4.4) ==")
for round_no, name, seconds, source in fails:
    print(f"  round-{round_no} {seconds:5.1f}s  {source:34} {name[:36]}")
print(f"  distinct files ({len({s for *_, s in fails})}): {sorted({s for *_, s in fails})}")

print(f"\n== passing runs >=20s: {len(slow)} of {passing} ==")
for round_no, name, seconds, source in sorted(slow, key=lambda row: -row[2]):
    print(f"  round-{round_no} {seconds:5.1f}s  {source:34} {name[:36]}")
print(f"  distinct files ({len({s for *_, s in slow})}): {sorted({s for *_, s in slow})}")
print(f"  distinct rounds: {sorted({r for r, *_ in slow})}")
print(f"  >=25s: {len([r for r in slow if r[2] >= 25])}")

union = {s for *_, s in slow + fails}
print(f"\n== union of slow+failing runs: {len(union)} distinct files ==")
print(f"  {sorted(union)}")
