import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,openPage,signUp,startFixture,useTab} from './support.mjs';

let server,browser;
const PASSWORD='pref-race-1';

before(async()=>{
 server=await startFixture(0);
 browser=await launchBrowser();
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

// The panel's mount GET used to overwrite whatever was typed while it was in flight.
test('慢响应落地不会清掉用户已输入的厨具',async()=>{
 const context=await desktopContext(browser);
 const page=await openPage(context,server.url);
 await signUp(page,'ui_pref_race_0918',PASSWORD);
 let resolved;
 const landed=new Promise(r=>{resolved=r;});
 await page.route('**/api/v1/me/preferences',async route=>{
  if(route.request().method()!=='GET'){await route.continue();return;}
  const response=await route.fetch();
  await new Promise(r=>setTimeout(r,1_500));
  await route.fulfill({status:response.status(),contentType:'application/json',body:await response.text()});
  resolved();
 });
 await useTab(page,'厨房偏好');
 await page.getByLabel('现有厨具（逗号分隔）').fill('煮锅');
 await landed;
 assert.equal(await page.getByLabel('现有厨具（逗号分隔）').inputValue(),'煮锅','挂载响应晚到 1.5 秒也不得覆盖已输入内容');
 const put=page.waitForResponse(r=>r.url().endsWith('/api/v1/me/preferences')&&r.request().method()==='PUT');
 await page.getByRole('button',{name:'保存偏好'}).click();
 const saved=await (await put).json();
 assert.deepEqual(saved.equipment,['煮锅'],'保存的必须是用户输入的厨具');
 await context.close();
});
