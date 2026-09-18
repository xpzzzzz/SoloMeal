// P6-04: the quote and purchase pages under broken networks. The purchase confirm is the one
// click in the app that writes several batches at once, so a lost response must not turn into a
// double restock, and a stale draft must be refused rather than silently overwritten.
import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {
 testDate,desktopContext,launchBrowser,makeApi,openPage,shot,signIn,startFixture,useTab,waitText,
} from './support.mjs';

let server,browser,api;
const PASSWORD='shopping-fixture-1';

before(async()=>{
 server=await startFixture(0);
 browser=await launchBrowser();
 api=makeApi(server.url);
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

// Build a pending plan and its purchase draft through the service, then argue with it in the page.
async function prepareDraft(user){
 await api.call(null,'/auth/register','POST',{username:user,password:PASSWORD});
 const token=await api.signIn(user,PASSWORD);
 const ingredient=(await api.call(token,'/ingredients','POST',{name:'鸡蛋',unit:'piece'})).data;
 await api.call(token,'/recipes','POST',{name:'测试煮鸡蛋',servings:1,minutes:10,equipment:['煮锅'],
  steps:['烧水煮蛋'],source:'E2E 采购用例',
  ingredients:[{ingredient_id:ingredient.id,quantity:'2',unit:'piece'}]});
 await api.call(token,'/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30});
 await api.call(token,'/quotes','POST',{ingredient_id:ingredient.id,package_quantity:'6',
  package_price:'5.50',source:'楼下超市',observed_on:testDate(),currency:'CNY',expected_version:0});
 assert.equal((await api.call(token,'/quotes')).data.length,1,'包装报价应已保存');
 const recommended=(await api.call(token,'/recommendations','POST',{include_optional:false})).data;
 const candidate=recommended.candidates[0];
 assert.ok(candidate.shopping.length,'用例菜谱应缺料，才能生成采购清单');
 const plan=(await api.call(token,'/plans','POST',{recipe_id:candidate.recipe.id,
  constraints:{include_optional:candidate.include_optional,score_weights:candidate.score_weights}})).data;
 const list=(await api.call(token,'/shopping','POST',{plan_id:plan.id,expected_version:plan.version})).data;
 return {token,ingredient,list};
}

test('保存回复丢失时页面可重试，同一次采购只入库一批',async()=>{
 const user='ui_shop_lost_0908';
 const {token,list}=await prepareDraft(user);
 const context=await desktopContext(browser);
 const page=await openPage(context,server.url);
 await signIn(page,user,PASSWORD);
 await useTab(page,'报价与采购');
 await waitText(page,new RegExp(`采购版本 ${list.version}`));

 // The browser never learns the outcome, but the server has already committed the whole order.
 const confirmPath=`${server.url}/api/v1/shopping/${list.id}/confirm`;
 await page.route(confirmPath,async route=>{await route.fetch();await route.abort('failed');});
 const editor=page.locator('section.panel').filter({hasText:'采购版本'});
 await editor.getByRole('button',{name:'核对并入库'}).click();
 await editor.getByRole('button',{name:'确认已购买并整单入库'}).click();
 await waitText(page,/无法连接服务器|浏览器已离线/);
 const lost=(await api.call(token,'/shopping')).data[0];
 assert.equal(lost.status,'completed','请求已经到达服务端，采购应确实完成');
 let batches=(await api.call(token,'/inventory')).data;
 assert.equal(batches.length,1,'一次确认只应新增一批库存');
 assert.equal(Number(batches[0].quantity),6);
 await shot(page,'shopping-lost-response.png');

 // The page still offers the action; the same logical retry must reuse its idempotency key.
 await page.unroute(confirmPath);
 await editor.getByRole('button',{name:'核对并入库'}).click();
 await editor.getByRole('button',{name:'确认已购买并整单入库'}).click();
 await waitText(page,/整单已入库/,30_000).catch(async()=>{
  const text=await page.evaluate(()=>document.body.innerText);
  assert.fail(`重试后应能收敛：${text.slice(0,1500)}`);
 });
 batches=(await api.call(token,'/inventory')).data;
 assert.equal(batches.length,1,'重试不得再次入库');
 assert.equal(Number(batches[0].quantity),6);
 assert.equal((await api.call(token,'/shopping')).data[0].version,lost.version,'重试不推进清单版本');
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await context.close();
});

test('离线时报价与采购按钮给出可读原因，恢复后同样的修改可以保存',async()=>{
 const user='ui_shop_offline_0908';
 const {token,list}=await prepareDraft(user);
 const context=await desktopContext(browser);
 const page=await openPage(context,server.url);
 await signIn(page,user,PASSWORD);
 await useTab(page,'报价与采购');
 await waitText(page,new RegExp(`采购版本 ${list.version}`));

 await context.setOffline(true);
 await waitText(page,/浏览器已离线/);
 const editor=page.locator('section.panel').filter({hasText:'采购版本'});
 await editor.locator('input[type="number"]').first().fill('8');
 await page.getByRole('button',{name:'保存采购修改'}).click();
 await waitText(page,/浏览器已离线，恢复网络后可重试/);
 assert.equal((await api.call(token,'/shopping')).data[0].version,list.version,'离线保存不应改动草稿');

 await context.setOffline(false);
 await waitText(page,/采购版本/);
 await page.getByRole('button',{name:'保存采购修改'}).click();
 await waitText(page,/草稿已保存/);
 const saved=(await api.call(token,'/shopping')).data[0];
 assert.equal(saved.version,list.version+1,'恢复后同一份修改应保存成功');
 assert.equal(Number(saved.items[0].quantity),8);
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await shot(page,'shopping-offline-edit.png');
 await context.close();
});
