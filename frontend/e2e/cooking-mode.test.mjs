import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,horizontalOverflow,launchBrowser,makeApi,mobileContext,openPage,signIn,signUp,signOut,startFixture,useTab,waitText} from './support.mjs';
const PASSWORD='cooking-fixture-2026';

export async function cookingFlow(url,context,username,{clock=true}={}){
 const page=await openPage(context,url),api=makeApi(url);
 await signUp(page,username,PASSWORD);
 const token=await api.signIn(username,PASSWORD);
 const item=(await api.call(token,'/ingredients','POST',{name:'做饭测试米',unit:'g'})).data.id;
 await api.call(token,'/inventory','POST',{ingredient_id:item,quantity:'300',unit:'g'});
 const recipe=(await api.call(token,'/recipes','POST',{name:'F3步骤米饭',servings:1,minutes:20,equipment:['煮锅'],steps:['洗米','加水','煮熟'],source:'F3测试',ingredients:[{ingredient_id:item,quantity:'80',unit:'g'}]})).data;
 await page.getByRole('button',{name:'刷新库存',exact:true}).click();
 await useTab(page,'我的菜谱');
 await page.locator('.recipe').filter({hasText:'F3步骤米饭'}).getByRole('button',{name:'开始做饭',exact:true}).click();
 if(clock){await page.clock.install();await page.clock.pauseAt(new Date(Date.now()+1000));}
 await page.getByRole('button',{name:'开始步骤与计时'}).click();
 if(clock)await page.clock.runFor(120000);
 await page.getByRole('button',{name:'暂停计时',exact:true}).click();
 if(clock){await page.clock.runFor(300000);assert.match(await page.getByLabel('总计时').innerText(),/^2 分/);}
 await page.getByLabel('当前步骤已完成').check();await page.getByRole('button',{name:'下一步',exact:true}).click();
 assert.equal((await api.call(token,'/cooking')).data.length,0);
 assert.equal((await api.call(token,'/inventory')).data[0].quantity,'300.000');
 await page.reload({waitUntil:'domcontentloaded'});await signIn(page,username,PASSWORD);
 await page.getByRole('button',{name:'继续未完成做饭',exact:true}).click();
 assert.match(await page.getByLabel('总计时').innerText(),/已暂停/);
 await waitText(page,/已完成 1 \/ 3 步/);
 await page.getByRole('button',{name:'继续计时',exact:true}).click();
 if(clock)await page.clock.runFor(180000);
 await page.getByRole('button',{name:'结束并确认做饭',exact:true}).click();
 if(clock)assert.equal(await page.getByLabel('实际耗时（分钟）',{exact:true}).inputValue(),'5');
 // Simulate a lost success response. The second request must replay the same operation.
 let dropped=false;const sent=[];
 await page.route('**/api/v1/cooking',async route=>{
  if(route.request().method()!=='POST')return route.continue();
  sent.push({body:route.request().postDataJSON(),key:route.request().headers()['idempotency-key']});
  if(!dropped){dropped=true;await route.fetch();return route.abort('failed');}
  return route.continue();
 });
 await page.getByRole('button',{name:'确认做饭并扣库存',exact:true}).click();
 await waitText(page,/无法连接服务器/);
 await page.getByRole('button',{name:'重试同一次确认',exact:true}).click();
 await waitText(page,/修改用时/);
 assert.equal(sent.length,2);assert.deepEqual(sent[0],sent[1]);
 let rows=(await api.call(token,'/cooking')).data;assert.equal(rows.length,1);assert.equal(rows[0].duration_source,'timer');
 assert.equal((await api.call(token,'/inventory')).data[0].quantity,'220.000');
 await page.getByRole('button',{name:'修改用时',exact:true}).click();
 await page.getByLabel('实际耗时（分钟，留空清除）').fill('12');
 await page.getByRole('button',{name:'保存用时',exact:true}).click();await waitText(page,/用时已保存/);
 rows=(await api.call(token,'/cooking')).data;assert.equal(rows[0].actual_minutes,12);assert.equal(rows[0].duration_source,'manual');
 assert.equal((await api.call(token,'/inventory')).data[0].quantity,'220.000');
 await page.getByRole('button',{name:'撤销并恢复食材'}).click();await waitText(page,/已撤销/);
 assert.equal((await api.call(token,'/inventory')).data[0].quantity,'300.000');
 assert.equal(await page.getByRole('button',{name:'修改用时',exact:true}).count(),0);
 // Logout clears unfinished timer storage, while reload above did not.
 await useTab(page,'我的菜谱');await page.locator('.recipe').filter({hasText:'F3步骤米饭'}).getByRole('button',{name:'开始做饭',exact:true}).click();await page.getByRole('button',{name:'开始步骤与计时'}).click();
 assert.ok((await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('solomeal:cooking:')))).length);
 await signOut(page);assert.equal((await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('solomeal:cooking:')))).length,0);
 await signIn(page,username,PASSWORD);assert.equal(await page.getByText('发现未完成计时',{exact:true}).count(),0);
 assert.deepEqual(page.problems,[]);return {page,recipe,token};
}

if(!process.env.F3_PREVIEW_IMPORT)test('F3 desktop timer recovery, lost response replay, duration edit and undo',async()=>{
 const server=await startFixture(0);let browser;
 try{browser=await launchBrowser();const context=await desktopContext(browser);await cookingFlow(server.url,context,'f3_desktop');}finally{await browser?.close();await server.stop();}
});
if(!process.env.F3_PREVIEW_IMPORT)test('F3 narrow screen pause and confirmation remain operable',async()=>{
 const server=await startFixture(0);let browser;
 try{browser=await launchBrowser();const context=await mobileContext(browser);const {page}=await cookingFlow(server.url,context,'f3_mobile',{clock:false});assert.ok(await horizontalOverflow(page)<=1);}finally{await browser?.close();await server.stop();}
});
if(!process.env.F3_PREVIEW_IMPORT)test('F3 running refresh and stock/version recovery preserve the draft',async()=>{
 const server=await startFixture(0);let browser;
 try{
 browser=await launchBrowser();const context=await desktopContext(browser),page=await openPage(context,server.url),api=makeApi(server.url);
 await signUp(page,'f3_recovery',PASSWORD);const token=await api.signIn('f3_recovery',PASSWORD);
 const item=(await api.call(token,'/ingredients','POST',{name:'测试面',unit:'g'})).data.id;
 const body={name:'版本恢复面',servings:1,minutes:10,equipment:['煮锅'],steps:['煮面','装盘'],source:'F3测试',ingredients:[{ingredient_id:item,quantity:'80',unit:'g'}]};
 const r=(await api.call(token,'/recipes','POST',body)).data;
 await page.getByRole('button',{name:'刷新库存',exact:true}).click();await useTab(page,'我的菜谱');
 await page.getByRole('button',{name:'开始做饭',exact:true}).click();await page.clock.install();await page.clock.pauseAt(new Date(Date.now()+1000));
 await page.getByRole('button',{name:'开始步骤与计时'}).click();await page.getByLabel('当前步骤已完成').check();await page.clock.runFor(60000);
 await page.reload({waitUntil:'domcontentloaded'});await signIn(page,'f3_recovery',PASSWORD);await page.clock.runFor(60000);
 await page.getByRole('button',{name:'继续未完成做饭',exact:true}).click();assert.match(await page.getByLabel('总计时').innerText(),/^2 分/);
 await page.getByRole('button',{name:'结束并确认做饭',exact:true}).click();await page.getByRole('button',{name:'不记录用时',exact:true}).click();
 await page.getByRole('button',{name:'确认做饭并扣库存',exact:true}).click();await waitText(page,/可用食材不足/);
 assert.equal((await api.call(token,'/cooking')).data.length,0);assert.equal(await page.getByLabel('当前步骤已完成').isChecked(),true);
 await api.call(token,'/inventory','POST',{ingredient_id:item,quantity:'300',unit:'g'});
 await api.call(token,'/recipes/'+r.id,'PUT',{...body,steps:['新版煮面','装盘'],expected_version:r.version});
 await page.getByRole('button',{name:'确认做饭并扣库存',exact:true}).click();await waitText(page,/记录已变化/);
 await page.getByRole('button',{name:'读取最新版菜谱供核对'}).click();await page.getByRole('button',{name:'已核对，使用新版继续（保留计时，重置步骤）'}).click();
 assert.match(await page.getByLabel('总计时').innerText(),/^2 分/);
 await page.getByRole('button',{name:'确认做饭并扣库存',exact:true}).click();await waitText(page,/填写用时/);
 const rows=(await api.call(token,'/cooking')).data;assert.equal(rows.length,1);assert.equal(rows[0].recipe.version,2);assert.equal(rows[0].actual_minutes,null);
 assert.equal((await api.call(token,'/inventory')).data[0].quantity,'220.000');assert.deepEqual(page.problems,[]);
 }finally{await browser?.close();await server.stop();}
});
