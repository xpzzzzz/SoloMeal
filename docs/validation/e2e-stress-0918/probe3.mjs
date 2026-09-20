// Repo-external diagnostic probe #3; nothing here is committed.
// Same browser, same instant: does a data: navigation (no socket, no bundle) stall like the
// fixture navigation?  data: slow  => browser process globally starved/busy.
//                         data: fast => the stall is specific to loading this document.
import {desktopContext, launchBrowser, startFixture} from 'file:///D:/Code/meal-manager/frontend/e2e/support.mjs';

const iterations = Number(process.argv[2] ?? 150);
const CONTROL = 'data:text/html,<h1>control</h1>';

for (let i = 1; i <= iterations; i += 1) {
  const row = {i, at: new Date().toISOString().slice(11, 19)};
  const server = await startFixture(0);
  try {
    const browser = await launchBrowser();
    const context = await desktopContext(browser);
    const page = await context.newPage();
    for (const [label, url, wait] of [['data', CONTROL, null], ['http', server.url, null], ['data2', CONTROL, null]]) {
      const t = Date.now();
      let err = null;
      try { await page.goto(url, {waitUntil: 'domcontentloaded'}); } catch (e) { err = e.message.split('\n')[0]; }
      row[label] = Date.now() - t;
      if (err) row[`${label}Error`] = err;
    }
    const t = Date.now();
    try { await fetch(`${server.url}/`, {signal: AbortSignal.timeout(8000)}); row.nodeRoot = Date.now() - t; }
    catch { row.nodeRoot = Date.now() - t; }
    row.slow = row.data > 4000 || row.http > 4000 || row.data2 > 4000;
    await context.close();
    await browser.close();
  } finally { await server.stop(); }
  console.log(JSON.stringify(row));
}
