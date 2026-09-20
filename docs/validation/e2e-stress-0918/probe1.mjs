// Repo-external diagnostic probe; nothing here is committed.
// Question: when the suite's first page.goto('/') stalls past Playwright's 30s cap,
// is the fixture server also failing to answer, or only the browser?
import {launchBrowser, desktopContext, startFixture} from 'file:///D:/Code/meal-manager/frontend/e2e/support.mjs';

const iterations = Number(process.argv[2] ?? 100);
const slowMs = 6000;
const rows = [];

async function timed(label, fn) {
  const start = Date.now();
  const value = await fn();
  return {label, ms: Date.now() - start, value};
}

for (let i = 1; i <= iterations; i += 1) {
  const row = {i, at: new Date().toISOString().slice(11, 19)};
  const boot = Date.now();
  let server;
  try {
    server = await startFixture(3);
  } catch (error) {
    console.log(JSON.stringify({i, bootError: String(error.message).slice(0, 200)}));
    continue;
  }
  row.boot = Date.now() - boot;
  try {
    const browser = await launchBrowser();
    const context = await desktopContext(browser);
    const page = await context.newPage();
    let navError = null;
    const nav = await timed('goto', async () => {
      try {
        await page.goto(server.url, {waitUntil: 'domcontentloaded'});
        return 'ok';
      } catch (error) {
        navError = error.message.split('\n')[0];
        return 'failed';
      }
    });
    row.goto = nav.ms;
    if (navError) row.navError = navError;
    // Same server, same instant, different client: the discriminator.
    const root = await timed('nodeRoot', () => fetch(`${server.url}/`, {signal: AbortSignal.timeout(8000)})
      .then((r) => r.status).catch((e) => `ERR:${e.name}`));
    row.nodeRoot = root.ms;
    const health = await timed('nodeHealth', () => fetch(`${server.url}/health/live`, {signal: AbortSignal.timeout(8000)})
      .then((r) => r.status).catch((e) => `ERR:${e.name}`));
    row.nodeHealth = health.ms;
    row.rootStatus = root.value;
    row.healthStatus = health.value;
    if (row.goto > slowMs) {
      row.fixtureLog = server.log().slice(-1600);
    }
    await context.close();
    await browser.close();
  } finally {
    await server.stop();
  }
  rows.push(row);
  console.log(JSON.stringify(row));
}

const gotos = rows.map((r) => r.goto).filter((v) => typeof v === 'number').sort((a, b) => a - b);
const pick = (q) => gotos[Math.min(gotos.length - 1, Math.floor(gotos.length * q))];
console.log(JSON.stringify({
  kind: 'summary',
  samples: gotos.length,
  p50: pick(0.5), p90: pick(0.9), p99: pick(0.99), max: gotos[gotos.length - 1],
  overSlowMs: gotos.filter((v) => v > slowMs).length,
}));
