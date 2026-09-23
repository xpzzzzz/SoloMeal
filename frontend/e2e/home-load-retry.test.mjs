import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signUp,startFixture,waitText} from './support.mjs';

test('首次首页请求失败后可重试并恢复四栏',async()=>{
 const server=process.env.F8_PREVIEW_URL?{url:process.env.F8_PREVIEW_URL,stop:async()=>{}}:await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser),page=await openPage(context,server.url);
  const requests=[];
  page.on('request',r=>{if(new URL(r.url()).pathname==='/api/v1/home')requests.push(r.method());});
  await page.route('**/api/v1/home',route=>route.abort('failed'),{times:1});
  const username='f8retry_'+Date.now().toString(36),password='F8-retry-fixture-123';
  await signUp(page,username,password);
  await page.getByRole('button',{name:'重试首页',exact:true}).waitFor();
  assert.equal(await page.locator('.home-section').filter({hasText:'首页读取失败，请重试首页。'}).count(),4);
  const recovered=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/home'&&r.status()===200);
  await page.getByRole('button',{name:'重试首页',exact:true}).click();
  await recovered;
  await waitText(page,/今天的数据已更新。/);
  await page.getByRole('button',{name:'刷新今天',exact:true}).waitFor();
  assert.equal(await page.locator('.home-section').filter({hasText:'正在读取…'}).count(),0);
  assert.equal(await page.locator('.home-section').filter({hasText:'首页读取失败'}).count(),0);
  assert.equal(await page.locator('.home-section').count(),4);
  assert.match(await page.locator('.home-recommendations').innerText(),/生成本餐推荐/);
  assert.deepEqual(requests,['GET','GET'],'恢复只需重新读取聚合');
  const api=makeApi(server.url),token=await api.signIn(username,password);
  assert.deepEqual((await api.call(token,'/inventory')).data,[],'恢复没有写入库存');
  assert.deepEqual((await api.call(token,'/cooking')).data,[],'恢复没有写入用餐记录');
  assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{await browser?.close();await server.stop();}
});
