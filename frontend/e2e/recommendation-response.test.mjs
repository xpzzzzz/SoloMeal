import test from 'node:test';
import assert from 'node:assert/strict';
import {startFixture,launchBrowser,desktopContext,openPage,signUp,signIn,
 useTab,waitText,shot,makeApi} from './support.mjs';

test('缺料推荐由工具结果展示，错误模型建议不显示，重登可恢复',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  const username='response_0916',password='response-fixture-1';
  await signUp(page,username,password);
  await useTab(page,'一人食助手');
  await page.getByLabel('想安排怎样的一餐？').fill('测试推荐三人餐');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await waitText(page,/当前不能生成做饭预览/);
  let text=await page.evaluate(()=>document.body.innerText);
  assert.match(text,/缺鸡蛋 3(?:\.0+)?个/);
  assert.doesNotMatch(text,/错误夹具回答/);
  const api=makeApi(server.url),token=await api.signIn(username,password);
  const runs=(await api.call(token,'/agent/runs')).data;
  const run=(await api.call(token,'/agent/runs/'+runs[0].id)).data;
  assert.equal(run.result.next_actions[0].prepare_cooking.enabled,false);
  assert.match(run.result.model_message,/错误夹具回答/);
  assert.deepEqual((await api.call(token,'/inventory')).data,[]);
  await page.reload();
  await signIn(page,username,password);
  await useTab(page,'一人食助手');
  await page.getByRole('button',{name:'测试推荐三人餐 · 1 次运行',exact:true}).click();
  await waitText(page,/当前不能生成做饭预览/);
  text=await page.evaluate(()=>document.body.innerText);
  assert.doesNotMatch(text,/错误夹具回答/);
  assert.deepEqual(page.problems,[]);
  await shot(page,'recommendation-response-0916.png');
 }finally{await browser?.close();await server.stop();}
});
