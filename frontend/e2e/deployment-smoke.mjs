// Explicitly targets a disposable deployed environment; not part of the fixture CI suite.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {launchBrowser,mobileContext,openPage,signIn,useTab,waitText,horizontalOverflow} from './support.mjs';

const [url,evidence,output]=process.argv.slice(2);
assert.ok(url&&evidence&&output,'Usage: node e2e/deployment-smoke.mjs URL PRIVATE_DEMO_DIR OUTPUT_PREFIX');
assert.ok(['127.0.0.1','localhost'].includes(new URL(url).hostname));
const credentials=JSON.parse(await readFile(path.join(evidence,'credentials.json'),'utf8'));
const browser=await launchBrowser();
try{
 const context=await mobileContext(browser);
 const page=await openPage(context,url);
 await signIn(page,credentials.username,credentials.password);
 await useTab(page,'食材库存');
 await waitText(page,/演示大米/);
 await waitText(page,/演示鸡蛋/);
 assert.equal(await horizontalOverflow(page),0);
 await page.screenshot({path:output+'-inventory.png',fullPage:true});
 await useTab(page,'用餐记录');
 await waitText(page,/演示白米饭/);
 await waitText(page,/已撤销/);
 await useTab(page,'小票录入');
 await waitText(page,/小票/);
 await page.screenshot({path:output+'-receipts.png',fullPage:true});
 await useTab(page,'一人食助手');
 await page.getByRole('button',{name:'查库存 · 1 次运行',exact:true}).click();
 await waitText(page,/尚未配置模型/);
 assert.equal(await horizontalOverflow(page),0);
 assert.deepEqual(page.problems,[]);
 await page.screenshot({path:output+'-agent-disabled.png',fullPage:true});
 await writeFile(output+'-checks.json',JSON.stringify({passed:true,viewport:'390x844',
  scope:'headless Chromium mobile emulation, not an Android physical device',pages:['inventory','cooking','receipts','agent-disabled']},null,2));
 console.log('Deployed UI smoke passed (mobile emulation; not a real Android device)');
}finally{await browser.close();}
