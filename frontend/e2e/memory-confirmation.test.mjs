import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,openPage,signUp,startFixture,useTab} from './support.mjs';

test('建议确认绑定运行，删除后页面不再显示旧保存状态',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  await signUp(page,'memory_ui_owner','memory-ui-fixture-1');
  const suggestion={category:'cooking_method',target:'stir_fry',polarity:1};
  const runId='3fb410ad-7926-4bd5-b354-9fb1383c69aa';
  const result={id:runId,session_id:runId,latest_run_id:runId,session_version:1,
   status:'completed',steps:1,event_seq:1,constraints:{},context_summary:{},result:{},pending:{},
   messages:[{role:'user',content:'以后喜欢清炒'}],
   events:[{step:1,tool:'suggest_memory',result:{memory_suggestion:suggestion},elapsed_ms:1}]};
  let saved=false,retired=false;
  const confirmed=[];
  await page.route('**/api/v1/agent/runs',async route=>{
   if(route.request().method()==='POST')return route.fulfill({json:result});
   return route.fulfill({json:[]});
  });
  await page.route('**/api/v1/agent/sessions',route=>route.fulfill({json:[]}));
  await page.route('**/api/v1/me/memories/confirm',async route=>{
   confirmed.push(route.request().postDataJSON());
   if(retired)return route.fulfill({status:409,json:{error:{code:'MEMORY_RETIRED'}}});
   saved=true;return route.fulfill({json:{saved:true}});
  });
  await page.route('**/api/v1/me/memories',route=>route.fulfill({json:saved?[{id:'memory-1',...suggestion}]:[]}));
  await page.route('**/api/v1/me/memories/memory-1',route=>{
   assert.equal(route.request().method(),'DELETE');saved=false;retired=true;
   return route.fulfill({json:{deleted:true}});
  });
  await useTab(page,'一人食助手');
  await page.getByLabel('想安排怎样的一餐？').fill('以后喜欢清炒');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await page.getByRole('button',{name:'确认保存偏好'}).click();
  await page.getByText('已确认保存这条长期偏好。').waitFor();
  assert.deepEqual(confirmed[0],{run_id:runId,step:1,...suggestion});
  const manager=page.locator('details').filter({hasText:'管理长期偏好记忆'});
  await manager.locator('summary').click();
  await manager.getByRole('button',{name:'读取记忆'}).click();
  await manager.getByRole('button',{name:'删除',exact:true}).click();
  await page.getByRole('button',{name:'确认保存偏好'}).waitFor();
  assert.equal(await page.getByText('已确认保存这条长期偏好。').count(),0);
  await page.getByRole('button',{name:'确认保存偏好'}).click();
  await page.getByText('保存结果未确认；请读取记忆并检查服务状态，勿重复创建。').waitFor();
  assert.equal(await page.getByText('已确认保存这条长期偏好。').count(),0);
 }finally{if(browser)await browser.close();await server.stop();}
});
