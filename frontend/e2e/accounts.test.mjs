// P6-04: two kitchens in one browser. The scripted fixture seeds each account separately,
// so this also proves the test double itself is not leaking one user into another.
import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {
 addKindAndBatch,desktopContext,waitForRows,launchBrowser,makeApi,openPage,shot,signIn,signOut,signUp,startFixture,useTab,waitText,
} from './support.mjs';

let server,browser,api;
const PASSWORD='accounts-fixture-1';
const A='ui_acct_a_0908',B='ui_acct_b_0908';

before(async()=>{
 server=await startFixture(0);
 browser=await launchBrowser();
 api=makeApi(server.url);
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

async function assistantStockIn(page,text){
 await useTab(page,'一人食助手');
 await page.getByLabel('想安排怎样的一餐？').fill(text);
 await page.getByRole('button',{name:'发送'}).click();
 await waitText(page,/确认入库/);
 await page.getByRole('button',{name:'确认入库'}).click();
 await waitText(page,/操作已确认/);
}

test('第二个账号看不到第一个账号的厨房，换账号后页面缓存也会清空',async()=>{
 const context=await desktopContext(browser);
 const pageA=await openPage(context,server.url);
 await signUp(pageA,A,PASSWORD);
 await addKindAndBatch(pageA,{name:'牛奶',quantity:'5',location:'冷藏'});
 await assistantStockIn(pageA,'测试入库甲账号');
 await useTab(pageA,'食材库存');
 // The scripted model stocks the account's first ingredient, which for 甲 is the 牛奶 just added.
 await waitForRows(pageA,2);
 assert.equal((await pageA.locator('table tbody tr').count()),2,'甲账号应有手工牛奶与脚本入库两批');

 const contextB=await desktopContext(browser);
 const pageB=await openPage(contextB,server.url);
 await signUp(pageB,B,PASSWORD);
 await useTab(pageB,'食材库存');
 await waitText(pageB,/暂无未归档的库存批次/);
 assert.doesNotMatch(await pageB.evaluate(()=>document.body.innerText),/牛奶/,'乙账号不应看到甲账号的食材');
 await useTab(pageB,'报价与采购');
 assert.match(await pageB.evaluate(()=>document.body.innerText),/还没有采购清单/);
 assert.doesNotMatch(await pageB.evaluate(()=>document.body.innerText),/牛奶/,'报价与采购也不应看到甲账号的数据');
 await shot(pageB,'accounts-second-user.png');

 await assistantStockIn(pageB,'测试入库乙账号');
 const tokenB=await api.signIn(B,PASSWORD),tokenA=await api.signIn(A,PASSWORD);
 const batchesB=(await api.call(tokenB,'/inventory')).data;
 const batchesA=(await api.call(tokenA,'/inventory')).data;
 assert.equal(batchesB.length,1,'乙账号只应有脚本入库的一批');
 assert.equal(Number(batchesB[0].quantity),2);
 assert.equal(batchesA.length,2,'乙账号的入库不应改动甲账号');
 assert.deepEqual((await api.call(tokenB,'/agent/sessions')).data.map(s=>s.runs.length),[1]);
 assert.deepEqual((await api.call(tokenA,'/agent/sessions')).data.map(s=>s.runs.length),[1]);

 // Switch accounts in the same tab: the previous kitchen must disappear from the page state.
 await signOut(pageB);
 await signIn(pageB,A,PASSWORD);
 await useTab(pageB,'一人食助手');
 await waitText(pageB,new RegExp('测试入库甲账号 · 1 次运行'));
 assert.doesNotMatch(await pageB.evaluate(()=>document.body.innerText),/测试入库乙账号/,'换账号后不应残留上一个账号的对话');
 await useTab(pageB,'食材库存');
 await waitText(pageB,/牛奶/);
 await waitForRows(pageB,2);
 assert.equal(pageB.problems.length,0,`页面不应出现未捕获异常：${pageB.problems.join('; ')}`);
 await context.close();
 await contextB.close();
});
