// Repo-external diagnostic probe #2; nothing here is committed.
// Probe #1 showed the fixture answers GET / (and both assets) with 200 while page.goto stalls.
// This one splits the stall: Chrome's own navigation timing (network vs main thread), and for
// navigations killed at the 30s cap it keeps waiting to learn the true stall length.
import {desktopContext, launchBrowser, startFixture} from 'file:///D:/Code/meal-manager/frontend/e2e/support.mjs';

const iterations = Number(process.argv[2] ?? 150);

const NAV_READ = `(() => { const e = performance.getEntriesByType('navigation')[0];
  if (!e) return null;
  const r = (v) => Math.round(v);
  return {responseStart: r(e.responseStart), responseEnd: r(e.responseEnd),
    dcl: r(e.domContentLoadedEventStart), loadEnd: r(e.loadEventEnd),
    connect: r(e.connectEnd - e.connectStart), ttfb: r(e.responseStart - e.requestStart),
    transfer: r(e.responseEnd - e.responseStart), afterResponse: r(e.domContentLoadedEventStart - e.responseEnd)};
})()`;

const rows = [];
for (let i = 1; i <= iterations; i += 1) {
  const row = {i, at: new Date().toISOString().slice(11, 19)};
  const server = await startFixture(0);   // 12 of 13 real e2e files use model-delay 0
  try {
    const browser = await launchBrowser();
    const context = await desktopContext(browser);
    const page = await context.newPage();
    const start = Date.now();
    let navError = null;
    try {
      await page.goto(server.url, {waitUntil: 'domcontentloaded'});
    } catch (error) {
      navError = error.message.split('\n')[0];
    }
    row.goto = Date.now() - start;
    if (navError) row.navError = navError;
    const t = Date.now();
    try {
      const res = await fetch(`${server.url}/`, {signal: AbortSignal.timeout(8000)});
      row.nodeRoot = Date.now() - t;
      row.rootStatus = res.status;
    } catch (error) { row.nodeRoot = Date.now() - t; row.rootStatus = `ERR:${error.name}`; }
    if (navError) {
      // Keep waiting past the cap to measure the real length of the stall.
      const wait = Date.now();
      try {
        await page.waitForFunction('document.readyState !== "loading"', {timeout: 90_000});
        row.trueDclAfterCap = Date.now() - wait;
        row.realNavLength = Date.now() - start;
      } catch { row.trueDclAfterCap = 'still-loading-after-90s'; }
    }
    try { row.nav = await page.evaluate(NAV_READ); } catch (error) { row.navReadError = error.message.split('\n')[0]; }
    row.fixtureAnswered = /"GET \/ HTTP\/1\.1" 200 OK/.test(server.log());
    await context.close();
    await browser.close();
  } finally {
    await server.stop();
  }
  rows.push(row);
  console.log(JSON.stringify(row));
}

const numeric = rows.filter((r) => typeof r.goto === 'number').sort((a, b) => b.goto - a.goto);
console.log(JSON.stringify({kind: 'summary', samples: numeric.length}));
console.log(JSON.stringify({kind: 'worst10', rows: numeric.slice(0, 10).map((r) => ({
  i: r.i, goto: r.goto, nodeRoot: r.nodeRoot, nav: r.nav, trueDcl: r.trueDclAfterCap,
}))}));
