import assert from 'node:assert/strict';
import test from 'node:test';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,signUp,startFixture,useTab} from './support.mjs';

for(const failedStep of ['accept','plan'])test(`主动提醒${failedStep}响应丢失后重新打开浏览器继续且只创建一份方案`,async()=>{
 const server=await startFixture(0,{proactivityDemo:true});let browser,context;
 try{
  browser=await launchBrowser();context=await desktopContext(browser);let page=await openPage(context,server.url);
  const username='recover_'+failedStep+'_'+Date.now().toString(36),password='Proactive-test-123';
  await signUp(page,username,password);
  const api=makeApi(server.url),token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const response=await api.call(token,path,method,body,key);assert.ok(response.status<300,JSON.stringify(response));return response.data;};
  const user=await call('/me');
  const ingredient=await call('/ingredients','POST',{name:'菠菜',unit:'g'});
  await call('/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30,personal_time_enabled:true,personalization_enabled:true});
  await call('/recipes','POST',{name:'恢复菠菜饭',servings:1,minutes:10,equipment:['煮锅'],source:'fixture',steps:['煮'],ingredients:[{ingredient_id:ingredient.id,quantity:'100',unit:'g'}]});
  const tomorrow=new Date(Date.now()+86400000).toISOString().slice(0,10);
  await call('/inventory','POST',{ingredient_id:ingredient.id,quantity:'300',unit:'g',expires_on:tomorrow,expiry_source:'user'},'recover-stock-001');
  const tick=await fetch(server.url+'/internal/tick',{method:'POST',headers:{'Content-Type':'application/json','X-Internal-Token':'fixture-proactivity-token'},body:JSON.stringify({user_id:user.id})});
  assert.equal(tick.status,200);assert.equal((await tick.json()).created,1);
  await page.reload({waitUntil:'domcontentloaded'});await signIn(page,username,password);
  const card=page.locator('.proactive-card');await card.getByRole('heading',{name:/菠菜.*明天到期/}).waitFor();
  const pattern=failedStep==='accept'?'**/proactivity/items/*/accept':'**/api/v1/plans*';
  await page.route(pattern,async route=>{
   if(route.request().method()!=='POST')return route.continue();
   const response=await route.fetch();assert.ok(response.status()===200||response.status()===201);await route.abort('failed');
  });
  await card.getByRole('button',{name:/就做这个|继续处理/}).click();
  await page.getByRole('alert').last().waitFor();
  await context.close();context=await desktopContext(browser);page=await openPage(context,server.url);
  await signIn(page,username,password);
  const resumed=page.locator('.proactive-card');await resumed.getByRole('heading',{name:/菠菜/}).waitFor({timeout:6000});
  await resumed.getByRole('button',{name:/就做这个|继续处理/}).click();
  const saved=page.locator('#saved-plans .history-row').filter({hasText:'恢复菠菜饭'});
  await saved.waitFor();assert.equal((await call('/plans')).length,1);
  assert.equal(Number((await call('/inventory'))[0].quantity),300);
  await saved.getByRole('button',{name:'确认做完'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'确认做完'}).click();
  await page.getByText('已记录，库存同步更新').waitFor();
  assert.equal(Number((await call('/inventory'))[0].quantity),200);
 }finally{await context?.close();await browser?.close();await server.stop();}
});

test('没有提醒时首页不渲染提醒容器',async()=>{
 const server=await startFixture(0);let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser),page=await openPage(context,server.url);
  const loaded=page.waitForResponse(response=>response.url().endsWith('/proactivity/inbox'));
  await signUp(page,'empty_'+Date.now().toString(36),'Proactive-test-123');
  assert.equal((await loaded).status(),200);
  assert.equal(await page.locator('.proactive-inbox').count(),0);
  await context.close();
 }finally{await browser?.close();await server.stop();}
});

test('演示推进后连续忽略三次，显示采购提醒的抑制期限',async()=>{
 const server=await startFixture(0,{proactivityDemo:true});let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser),page=await openPage(context,server.url);
  const username='snooze_'+Date.now().toString(36),password='Proactive-test-123';
  await signUp(page,username,password);
  const api=makeApi(server.url),token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const result=await api.call(token,path,method,body,key);assert.ok(result.status<300,JSON.stringify(result));return result.data;};
  await call('/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30,personal_time_enabled:true,personalization_enabled:true});
  const ingredient=await call('/ingredients','POST',{name:'番茄',unit:'g'});
  const recipe=await call('/recipes','POST',{name:'番茄饭',servings:1,minutes:10,equipment:['煮锅'],source:'fixture',steps:['煮'],ingredients:[{ingredient_id:ingredient.id,quantity:'100',unit:'g'}]});
  const plan=await call('/plans','POST',{recipe_id:recipe.id,constraints:{}},'demo-plan-001');
  await call('/shopping','POST',{plan_id:plan.id,expected_version:plan.version},'demo-shop-001');
  const advance=page.getByRole('button',{name:'⏩ 推进 1 天'});
  for(let day=0;day<4&&!await page.locator('.proactive-card').count();day++){
   const response=page.waitForResponse(r=>r.url().endsWith('/proactivity/simulate'));
   await advance.click();assert.equal((await response).status(),200);
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent?.includes('推进 1 天')&&!b.disabled));
  }
  for(let n=0;n<3;n++){
   const card=page.locator('.proactive-card');await card.getByRole('heading',{name:/番茄饭/}).waitFor();
   const response=page.waitForResponse(r=>r.url().includes('/dismiss')&&r.request().method()==='POST');
   await card.getByRole('button',{name:'不是这个'}).click();assert.equal((await response).status(),200);
   if(n<2){const tick=page.waitForResponse(r=>r.url().endsWith('/proactivity/simulate'));
    await advance.click();assert.equal((await tick).status(),200);}
  }
  await page.getByText(/采购草稿提醒已暂停至 \d{4}-\d{2}-\d{2}/).waitFor();
  const inbox=await call('/proactivity/inbox');assert.deepEqual(inbox.meta.suppressed_kinds,['shopping_stale']);
  assert.deepEqual(page.problems,[]);await context.close();
 }finally{await browser?.close();await server.stop();}
});

test('主动提醒显示、忽略失败回滚，并通过方案确认扣减库存',async()=>{
 const server=await startFixture(0,{proactivityDemo:true});let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser),page=await openPage(context,server.url);
  const username='proactive_'+Date.now().toString(36),password='Proactive-test-123';
  await signUp(page,username,password);
  const api=makeApi(server.url),token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const result=await api.call(token,path,method,body,key);assert.ok(result.status<300,JSON.stringify(result));return result.data;};
  const user=await call('/me');
  const ingredient=await call('/ingredients','POST',{name:'菠菜',unit:'g'});
  await call('/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30,personal_time_enabled:true,personalization_enabled:true});
  const recipe=await call('/recipes','POST',{name:'菠菜饭',servings:1,minutes:10,equipment:['煮锅'],source:'fixture',steps:['煮'],ingredients:[{ingredient_id:ingredient.id,quantity:'100',unit:'g'}]});
  const tomorrow=new Date(Date.now()+86400000).toISOString().slice(0,10);
  await call('/inventory','POST',{ingredient_id:ingredient.id,quantity:'300',unit:'g',expires_on:tomorrow,expiry_source:'user'},'proactive-stock-1');
  const tick=await fetch(server.url+'/internal/tick',{method:'POST',headers:{'Content-Type':'application/json','X-Internal-Token':'fixture-proactivity-token'},body:JSON.stringify({user_id:user.id})});
  assert.equal(tick.status,200);assert.equal((await tick.json()).created,1);
  await page.reload({waitUntil:'domcontentloaded'});await signIn(page,username,password);
  const card=page.locator('.proactive-card');await card.getByRole('heading',{name:/菠菜.*明天到期/}).waitFor();
  assert.match(await card.innerText(),/菠菜饭/);
  await card.locator('summary').click();assert.match(await card.innerText(),/1 道菜谱可用/);
  let finish;const gate=new Promise(resolve=>{finish=resolve;});
  await page.route('**/proactivity/items/*/dismiss',async route=>{await gate;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'TEST_FAILURE'}})});});
  await card.getByRole('button',{name:'不是这个'}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.proactive-card').length===0);
  finish();await page.getByRole('alert').filter({hasText:'操作没有完成'}).waitFor();
  await card.getByRole('heading',{name:/菠菜/}).waitFor();
  await page.unroute('**/proactivity/items/*/dismiss');
  await page.route('**/api/v1/plans*',async route=>{
   if(route.request().method()!=='POST')return route.continue();
   assert.equal((await route.fetch()).status(),201);await route.abort('failed');
  });
  await card.getByRole('button',{name:/就做这个|继续处理/}).click();
  await page.getByRole('alert').last().waitFor();
  await page.unroute('**/api/v1/plans*');
  await useTab(page,'食材库存');await useTab(page,'今天');
  await card.getByRole('heading',{name:/菠菜/}).waitFor();
  await page.route('**/api/v1/plans*',async route=>{
   if(route.request().method()==='GET')return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'TEST_FAILURE'}})});
   return route.continue();
  });
  await card.getByRole('button',{name:/就做这个|继续处理/}).click();
  await page.getByRole('alert').last().waitFor();
  await page.unroute('**/api/v1/plans*');
  await useTab(page,'食材库存');await useTab(page,'今天');
  await card.getByRole('heading',{name:/菠菜/}).waitFor();
  await card.getByRole('button',{name:/就做这个|继续处理/}).click();
  const saved=page.locator('#saved-plans .history-row').filter({hasText:'菠菜饭'});
  await saved.waitFor();assert.equal(Number((await call('/inventory'))[0].quantity),300);
  await saved.getByRole('button',{name:'确认做完'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'确认做完'}).click();
  await page.getByText('已记录，库存同步更新').waitFor();
  assert.equal(Number((await call('/inventory'))[0].quantity),200);
  assert.equal((await call('/cooking')).length,1);
  const plans=await call('/plans');assert.equal(plans.length,1,'丢响应后切页重试不得创建第二个方案');
  assert.equal(plans[0].snapshot.candidate.recipe.id,recipe.id);
  assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{await browser?.close();await server.stop();}
});
