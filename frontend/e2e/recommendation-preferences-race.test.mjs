import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signUp,startFixture,useTab} from './support.mjs';

test('quick scene uses saved limit during a slow preferences GET and preserves manual edits',async()=>{
 const server=process.env.F6_PREVIEW_URL?{url:process.env.F6_PREVIEW_URL,stop:async()=>{}}:await startFixture(0);
 let browser,release;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser),page=await openPage(context,server.url),api=makeApi(server.url);
  const username='f6race_'+Date.now().toString(36),password='F6-race-fixture-120';
  await signUp(page,username,password);const token=await api.signIn(username,password);
  const call=async(path,method='GET',body)=>{const r=await api.call(token,path,method,body);assert.ok(r.status<300,JSON.stringify(r));return r.data;};
  await call('/me/preferences','PUT',{equipment:['煮锅'],default_servings:1,max_minutes:10,excluded_ingredients:[]});
  const egg=await call('/ingredients','POST',{name:'鸡蛋',unit:'piece'});
  await call('/recipes','POST',{name:'十五分钟回归菜',servings:1,minutes:15,equipment:['煮锅'],source:'F6 regression',steps:['煮熟'],ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'}]});
  let gate=new Promise(r=>{release=r;});
  await page.route('**/api/v1/me/preferences',async route=>{if(route.request().method()==='GET')await gate;await route.continue();});
  const submit=async()=>{
   const pending=page.waitForResponse(r=>r.url().endsWith('/recommendations')&&r.request().method()==='POST');
   await page.getByRole('button',{name:'生成本餐推荐',exact:true}).click();
   const r=await pending;return {request:r.request().postDataJSON(),data:await r.json()};
  };
  await useTab(page,'我的菜谱');await page.getByLabel('推荐场景').selectOption('quick');
  const first=await submit();
  assert.equal(first.request.max_minutes,null,'unloaded preferences must not be replaced with 20');
  assert.equal(first.data.constraints.max_minutes,10);assert.equal(first.data.candidates.length,0);
  await page.getByText('超出用时上限：1道').waitFor();
  release();await page.waitForFunction(()=>document.querySelector('.recommendation-controls input[type=number]')?.value==='10');
  assert.equal(await page.locator('.recommendation-card').count(),0);
  const again=await submit();assert.equal(again.request.max_minutes,10);assert.equal(again.data.candidates.length,0);
  // A late preference response must not replace an explicit manual baseline.
  await useTab(page,'食材库存');gate=new Promise(r=>{release=r;});await useTab(page,'我的菜谱');
  await page.getByLabel('本次用时上限（分钟）').fill('35');await page.getByLabel('推荐场景').selectOption('quick');
  const manual=await submit();assert.equal(manual.request.max_minutes,20);assert.equal(manual.data.candidates.length,1);
  const loaded=page.waitForResponse(r=>r.url().endsWith('/me/preferences')&&r.request().method()==='GET');release();await loaded;
  assert.equal(await page.getByLabel('本次用时上限（分钟）').inputValue(),'20');
  await page.getByLabel('推荐场景').selectOption('clear_fridge');assert.equal(await page.getByLabel('本次用时上限（分钟）').inputValue(),'35');
  await page.getByLabel('推荐场景').selectOption('default');assert.equal(await page.getByLabel('本次用时上限（分钟）').inputValue(),'10');
  assert.equal((await call('/me/preferences')).max_minutes,10);assert.deepEqual(await call('/inventory'),[]);assert.deepEqual(await call('/cooking'),[]);assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{release?.();await browser?.close();await server.stop();}
});
