import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signUp,startFixture,useTab} from './support.mjs';

test('F7 keeps the exact unresolved creation across navigation, then permits a new purchase',async()=>{
 const server=process.env.F7_PREVIEW_URL?{url:process.env.F7_PREVIEW_URL,stop:async()=>{}}:await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser);const page=await openPage(context,server.url);
  const api=makeApi(server.url),username='f7retry_'+Date.now().toString(36),password='F7-retry-fixture-12';
  await signUp(page,username,password);const token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const r=await api.call(token,path,method,body,key);assert.ok(r.status<300,JSON.stringify(r));return r.data;};
  const egg=await call('/ingredients','POST',{name:'重试鸡蛋',unit:'piece'});
  await call('/recipes','POST',{name:'重试蛋菜',servings:1,minutes:10,equipment:['煮锅'],source:'F7 retry test',steps:['煮熟'],ingredients:[{ingredient_id:egg.id,quantity:'2',unit:'piece'}]});
  await page.getByRole('button',{name:'刷新库存',exact:true}).click();
  const keys=[];
  for(const mode of ['direct','navigate','inflight']){
   await useTab(page,'我的菜谱');
   await page.locator('.recipe-grid').getByRole('button',{name:'加入采购组合'}).click();
   await page.getByLabel('组合预算（元，可留空）').fill('12.50');
   await page.getByRole('button',{name:'计算采购',exact:true}).click();await page.locator('.combined-preview').waitFor();
   let firstBody,firstKey,firstId,release,committed;
   const gate=new Promise(resolve=>{release=resolve;});const submitted=new Promise(resolve=>{committed=resolve;});
   await page.route('**/api/v1/shopping/combined',async route=>{
    firstKey=route.request().headers()['idempotency-key'];firstBody=route.request().postDataJSON();
    const result=await route.fetch();assert.equal(result.status(),201);firstId=(await result.json()).id;committed();
    if(mode==='inflight')await gate;
    await route.abort('failed');
   });
   await page.getByRole('button',{name:'保存组合采购清单',exact:true}).click();await submitted;
   if(mode==='inflight'){await useTab(page,'食材库存');await useTab(page,'我的菜谱');assert.equal(await page.getByRole('button',{name:'正在确认保存…'}).isDisabled(),true);release();}
   else await page.locator('.combination-panel').getByText('无法连接服务器，请检查网络后重试',{exact:true}).waitFor();
   await page.getByRole('button',{name:'重试保存组合清单',exact:true}).waitFor();
   const before=await call('/shopping');assert.equal(before.length,keys.length+1);
   await page.unroute('**/api/v1/shopping/combined');
   if(mode==='navigate'){await useTab(page,'食材库存');await useTab(page,'我的菜谱');}
   assert.equal(await page.locator('.combination-row').count(),1);
   assert.equal(await page.getByLabel('组合预算（元，可留空）').inputValue(),'12.50');
   assert.equal(await page.getByRole('button',{name:'计算采购',exact:true}).isDisabled(),true);
   // A gateway rate limit on retry does not resolve the earlier unknown outcome.
   if(mode==='navigate'){
    await page.route('**/api/v1/shopping/combined',route=>route.fulfill({status:429,contentType:'application/json',body:'{}'}));
    await page.getByRole('button',{name:'重试保存组合清单',exact:true}).click();
    await page.locator('.combination-panel').getByText(/请求较频繁/).waitFor();
    await page.unroute('**/api/v1/shopping/combined');
   }
   const response=page.waitForResponse(r=>r.url().endsWith('/shopping/combined'));
   await page.getByRole('button',{name:'重试保存组合清单',exact:true}).click();const recovered=await response;
   assert.equal(recovered.status(),201);assert.equal(recovered.request().headers()['idempotency-key'],firstKey);
   assert.deepEqual(recovered.request().postDataJSON(),firstBody);
   const after=await call('/shopping');assert.equal(after.length,before.length);
   assert.equal((await recovered.json()).id,firstId);
   assert.ok(!keys.includes(firstKey));keys.push(firstKey);
   await page.getByRole('heading',{name:'买好需要的，记入厨房',exact:true}).waitFor();
   assert.equal(await page.locator('.combination-row').count(),0);
   assert.equal(await page.getByRole('button',{name:'重试保存组合清单',exact:true}).count(),0);
  }
  // Explicit session change discards the old user's pending state.
  await useTab(page,'我的菜谱');await page.locator('.recipe-grid').getByRole('button',{name:'加入采购组合'}).click();
  await page.getByRole('button',{name:'计算采购',exact:true}).click();await page.locator('.combined-preview').waitFor();
  await page.route('**/api/v1/shopping/combined',route=>route.abort('failed'));
  await page.getByRole('button',{name:'保存组合采购清单',exact:true}).click();
  await page.locator('.combination-panel').getByText('无法连接服务器，请检查网络后重试',{exact:true}).waitFor();
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  await signUp(page,username+'_other',password);await useTab(page,'我的菜谱');
  assert.equal(await page.locator('.combination-row').count(),0);
  assert.equal(await page.getByRole('button',{name:'重试保存组合清单',exact:true}).count(),0);
  assert.deepEqual(await call('/inventory'),[]);assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{await browser?.close();await server.stop();}
});
