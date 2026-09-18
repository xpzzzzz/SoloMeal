// P6-04: real browser network failures. Every scenario cuts the network with Chromium's own
// offline emulation, so navigator.onLine, the online/offline events and in-flight fetches all
// behave as they do on a phone that loses signal. Scripted fixture model only, never a real one.
import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
 import {
 addKindAndBatch,desktopContext,launchBrowser,makeApi,openPage,shot,signIn,signUp,startFixture,useTab,
 waitText,visibleButtons,
 } from './support.mjs';

let server,browser,api;
const PASSWORD='offline-fixture-1';

before(async()=>{
 server=await startFixture(6);
 browser=await launchBrowser();
 api=makeApi(server.url);
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

test('一个运行中的助手请求遇到断网，只会在恢复后继续，不会重复执行工具',async()=>{
 const context=await desktopContext(browser);
 const page=await openPage(context,server.url);
 await signUp(page,'ui_off_run_0908',PASSWORD);
 await useTab(page,'一人食助手');
 await page.getByLabel('想安排怎样的一餐？').fill('测试查询断网恢复');
 await page.getByRole('button',{name:'发送'}).click();
 // steps already counts the in-flight model call, so the running status appears with 1 轮.
 await waitText(page,/运行中 · 已执行 1 轮/);

 await context.setOffline(true);
 await waitText(page,/浏览器已离线，恢复网络后页面会自动同步/);
 await waitText(page,/连接中断，正在自动重连|进度连接已停止/);
 const alerts=(await page.getByRole('alert').allInnerTexts()).join('\n');
 assert.match(alerts,/无法连接服务器|浏览器已离线/,`断网提示应当可读：${alerts}`);
 assert.doesNotMatch(alerts,/Failed to fetch|TypeError|fetch is not defined/);
 await shot(page,'offline-during-run.png');

 // The server finishes the step it already started; only the browser lost the answer.
 const token=await api.signIn('ui_off_run_0908',PASSWORD);
 const running=(await api.call(token,'/agent/runs')).data;
 assert.equal(running.length,1,'断网不应产生第二个运行');
 let run=(await api.call(token,'/agent/runs/'+running[0].id)).data;
 assert.equal(run.steps,1);

 await context.setOffline(false);
 await page.waitForFunction(()=>navigator.onLine===true);
 await waitText(page,/可继续 · 已执行 1 轮/);
 assert.ok((await visibleButtons(page)).some(b=>b.text==='继续执行'),'恢复后应可继续原运行');
 await page.getByRole('button',{name:'继续执行'}).click();
 await waitText(page,/已完成 · 已执行 2 轮/);
 await waitText(page,/脚本测试：已查询库存/);

 // The record list stays collapsed, so read textContent instead of rendered text.
 const records=page.locator('details').filter({hasText:'工具执行记录'});
 const toolRecords=await records.locator('h4').allTextContents();
 assert.equal(toolRecords.length,1,'get_inventory 只应执行一次');
 assert.match(toolRecords[0],/^1\. get_inventory · \d+ ms$/);
 run=(await api.call(token,'/agent/runs/'+running[0].id)).data;
 assert.equal(run.status,'completed');
 assert.equal(run.events.length,1);
 assert.deepEqual(run.events.map(e=>e.step),[1]);
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await context.close();
});

test('离线横幅即时出现，恢复网络后无需点击就同步服务端的新数据',async()=>{
 const context=await desktopContext(browser);
 const page=await openPage(context,server.url);
 await signUp(page,'ui_off_page_0908',PASSWORD);
 // addKindAndBatch waits for the row to render; going offline during that POST would really
 // cancel the write, which is a different (and much less interesting) story.
 await addKindAndBatch(page,{name:'酱油',quantity:'2',location:'常温'});

 await context.setOffline(true);
 await waitText(page,/浏览器已离线/);
 await page.getByRole('button',{name:'刷新库存'}).click();
 await waitText(page,/浏览器已离线，恢复网络后可重试/);
 assert.match(await page.locator('table').innerText(),/酱油/,'离线时已加载的批次仍然可见');
 await shot(page,'offline-stale-data.png');

 // Somebody else changes the kitchen while this browser is offline, and the page must catch up
 // on its own once the network returns.
 const token=await api.signIn('ui_off_page_0908',PASSWORD);
 const added=(await api.call(token,'/ingredients','POST',{name:'番茄',unit:'piece'})).data;
 assert.equal((await api.call(token,'/inventory','POST',{ingredient_id:added.id,quantity:'3',unit:'piece',
 location:'冷藏',expiry_source:'unknown'})).status,201);
 assert.doesNotMatch(await page.locator('table').innerText(),/番茄/,'离线期间页面不应看到新数据');

 await context.setOffline(false);
 await waitText(page,/番茄/,30_000);
 assert.equal((await page.locator('table tbody tr').count()),2,'恢复后应当看到两个批次');
 assert.equal(await page.locator('.offline-bar').count(),0,'横幅应随网络恢复消失');
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await context.close();
});

test('一个标签页离线时的取消不会生效，另一标签页确认后落后页面收敛',async()=>{
 const contextA=await desktopContext(browser),contextB=await desktopContext(browser);
 const pageA=await openPage(contextA,server.url);
 await signUp(pageA,'ui_off_tabs_0908',PASSWORD);
 await useTab(pageA,'一人食助手');
 await pageA.getByLabel('想安排怎样的一餐？').fill('测试入库双标签页');
 await pageA.getByRole('button',{name:'发送'}).click();
 await waitText(pageA,/确认入库/);

 const pageB=await openPage(contextB,server.url);
 await signIn(pageB,'ui_off_tabs_0908',PASSWORD);
 await useTab(pageB,'一人食助手');
 await waitText(pageB,/测试入库双标签页 · 1 次运行/);
 await pageB.getByText('测试入库双标签页 · 1 次运行').click();
 await waitText(pageB,/等待确认 · 已执行 1 轮/);

 await contextA.setOffline(true);
 await waitText(pageA,/浏览器已离线/);
 await pageA.getByRole('button',{name:'取消本次运行'}).click();
 await waitText(pageA,/无法连接服务器|浏览器已离线/);
 const token=await api.signIn('ui_off_tabs_0908',PASSWORD);
 let listed=(await api.call(token,'/agent/runs')).data;
 assert.equal(listed.length,1,'离线标签页的取消不应创建或改写运行');
 assert.equal(listed[0].status,'awaiting_confirmation');

 await pageB.getByRole('button',{name:'确认入库'}).click();
 await waitText(pageB,/操作已确认/);
 await waitText(pageB,/已入库/);

 await contextA.setOffline(false);
 await waitText(pageA,/操作已确认|等待确认/,30_000);
 await waitText(pageA,/已入库/);
 assert.equal(await pageA.getByRole('button',{name:'确认入库'}).count(),0,'已确认的运行不应再提供确认按钮');

 const batches=(await api.call(token,'/inventory')).data;
 assert.equal(batches.length,1,'一次确认只入库一批');
 assert.equal(Number(batches[0].quantity),2);
 assert.equal((await api.call(token,'/agent/sessions')).data[0].runs.length,1);
 assert.equal(pageA.problems.length,0,`页面不应出现未捕获异常：${pageA.problems.join('; ')}`);
 await shot(pageA,'offline-tab-converged.png');
 await contextA.close();await contextB.close();
});
