import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signUp,startFixture,useTab} from './support.mjs';

test('F6 scenes, swap exhaustion/reset, constraints and read-only behavior',async()=>{
 const server=process.env.F6_PREVIEW_URL?{url:process.env.F6_PREVIEW_URL,stop:async()=>{}}:await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser);const page=await openPage(context,server.url);
  const api=makeApi(server.url),username='f6_'+Date.now().toString(36),password='F6-preview-fixture-12';
  await signUp(page,username,password);const token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const r=await api.call(token,path,method,body,key);assert.ok(r.status<300,JSON.stringify(r));return r.data;};
  const egg=await call('/ingredients','POST',{name:'鸡蛋',unit:'piece'});
  for(let i=0;i<5;i++)await call('/recipes','POST',{name:'场景菜'+i,servings:1,minutes:25,equipment:['煮锅'],source:'F6 fixture',steps:['煮熟'],ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'}]});
  await call('/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:45});
  const before=await call('/inventory');const recipesBefore=await call('/recipes');
  await useTab(page,'我的菜谱');const panel=page.locator('.recommendation-panel');
  await page.getByLabel('本次用时上限（分钟）').fill('35');
  for(const [scene,minutes,weights] of [['default',45,[60,40,10]],['clear_fridge',45,[40,80,10]],['quick',20,[60,40,10]],['less_shopping',45,[100,20,10]],['variety',45,[60,40,30]]]){
   await page.getByLabel('推荐场景').selectOption(scene);
   assert.equal(await page.getByLabel('本次用时上限（分钟）').inputValue(),String(minutes));
   const response=page.waitForResponse(r=>r.url().endsWith('/recommendations')&&r.request().method()==='POST');
   await panel.getByRole('button',{name:'生成本餐推荐',exact:true}).click();const data=await (await response).json();
   assert.equal(data.constraints.max_minutes,minutes);
   if(scene==='quick'){await panel.getByText('超出用时上限：5道').waitFor();await panel.getByRole('button',{name:'发现菜谱',exact:true}).waitFor();}
   else{assert.deepEqual(Object.values(data.candidates[0].score_weights),[...weights,0]);await panel.locator('.recommendation-card').first().waitFor();}
  }
  // A custom baseline survives quick -> another scene.
  await page.getByLabel('本次用时上限（分钟）').fill('32');
  assert.equal(await page.getByLabel('推荐场景').inputValue(),'custom');
  await page.getByLabel('推荐场景').selectOption('quick');assert.equal(await page.getByLabel('本次用时上限（分钟）').inputValue(),'20');
  await page.getByLabel('推荐场景').selectOption('clear_fridge');assert.equal(await page.getByLabel('本次用时上限（分钟）').inputValue(),'32');
  await panel.getByRole('button',{name:'生成本餐推荐',exact:true}).click();await panel.locator('.recommendation-card').first().waitFor();
  assert.match(await panel.innerText(),/价格未知 \/ 估价不完整/);assert.doesNotMatch(await panel.innerText(),/¥0/);
  let reads=0;page.on('request',r=>{if(r.url().endsWith('/recommendations'))reads++;});
  const skipped=new Set();
  while(await panel.locator('.recommendation-card').count()){
   const card=panel.locator('.recommendation-card').first(),name=await card.getByRole('heading').innerText();assert.ok(!skipped.has(name));skipped.add(name);
   await card.getByRole('button',{name:'换一道',exact:true}).click();
  }
  assert.equal(skipped.size,5);assert.equal(reads,0);await panel.getByText('本次候选已看完',{exact:true}).waitFor();
  await useTab(page,'食材库存');await useTab(page,'我的菜谱');await panel.getByText('本次候选已看完',{exact:true}).waitFor();
  await panel.getByRole('button',{name:'重置本次候选'}).click();assert.equal(await panel.locator('.recommendation-card').count(),3);
  await panel.locator('.recommendation-card').first().getByRole('button',{name:'换一道',exact:true}).click();
  await panel.getByRole('button',{name:'重新推荐',exact:true}).click();await panel.locator('.recommendation-card').first().waitFor();
  assert.equal(await panel.locator('.recommendation-card').count(),3);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  if(process.env.F6_PREVIEW_URL){await page.screenshot({path:'.tmp-e2e/f6-mobile.png',fullPage:true});await page.setViewportSize({width:1280,height:900});await page.screenshot({path:'.tmp-e2e/f6-desktop.png',fullPage:true});}
  assert.deepEqual(await call('/inventory'),before);assert.deepEqual(await call('/recipes'),recipesBefore);assert.deepEqual(await call('/cooking'),[]);
  assert.equal((await call('/me/preferences')).max_minutes,45);assert.deepEqual(page.problems,[]);
  await panel.locator('.recommendation-card').first().getByRole('button',{name:'保存这餐方案',exact:true}).click();await page.getByText('已保存方案，可在下方确认或更新',{exact:true}).waitFor();
  const plans=await call('/plans');assert.equal(plans.length,1);assert.equal(plans[0].snapshot.request.scenario,'clear_fridge');assert.equal(plans[0].snapshot.request.max_minutes,32);
  await page.getByLabel('本次用时上限（分钟）').fill('1');await panel.getByRole('button',{name:'生成本餐推荐',exact:true}).click();await panel.getByText('超出用时上限：5道').waitFor();await panel.getByRole('button',{name:'发现菜谱',exact:true}).click();await page.getByRole('heading',{name:'发现新菜，先核对再加'}).waitFor();
  await context.close();
 }finally{await browser?.close();await server.stop();}
});
