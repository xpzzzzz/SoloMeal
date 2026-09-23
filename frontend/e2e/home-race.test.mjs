import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,signUp,startFixture,useTab,waitText} from './support.mjs';

// 刷新今天 re-reads the three list blocks only, so a scenario the user switched to keeps its
// own conditions and results instead of falling back to the aggregate's default scene.
test('今天首页刷新不覆盖已改的推荐场景，其余三块重读服务端',async()=>{
 const server=process.env.F8_PREVIEW_URL?{url:process.env.F8_PREVIEW_URL,stop:async()=>{}}:await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser),page=await openPage(context,server.url),api=makeApi(server.url);
  const requests=[];
  page.on('request',r=>{const p=new URL(r.url()).pathname;if(p.startsWith('/api/v1'))requests.push(r.method()+' '+p.slice(7));});
  const username='f8refresh_'+Date.now().toString(36),password='F8-race-fixture-120';
  await signUp(page,username,password);const token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const r=await api.call(token,path,method,body,key);assert.ok(r.status<300,JSON.stringify(r));return r.data;};
  await call('/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30,personal_time_enabled:true,personalization_enabled:true});
  const egg=await call('/ingredients','POST',{name:'鸡蛋',unit:'piece'});
  const noodle=await call('/ingredients','POST',{name:'挂面',unit:'g'});
  await call('/recipes','POST',{name:'场景保留菜',servings:1,minutes:15,equipment:['煮锅'],source:'F8 race',steps:['煮熟'],ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'}]});
  await call('/inventory','POST',{ingredient_id:egg.id,quantity:'5',unit:'piece',expires_on:new Date(Date.now()+2*864e5).toISOString().slice(0,10),expiry_source:'user',location:'冷藏'},'f8race-egg-0001');

  // The aggregate is read when the panel mounts, so leave and come back to see the seeded kitchen.
  await useTab(page,'我的菜谱');
  await useTab(page,'今天');
  await page.getByRole('heading',{name:'今天做点什么',exact:true}).waitFor();
  await waitText(page,/本次推荐依据/);
  assert.ok(await page.locator('.recommendation-card').count()>0,'首页聚合直接带出前三条');
  assert.deepEqual(requests.filter(r=>r.startsWith('POST /recommendations')||r.startsWith('POST /agent')),[],'首页不自动发起推荐，更不调用模型');
  assert.equal(await page.getByLabel('推荐场景').inputValue(),'default');

  await page.getByLabel('推荐场景').selectOption('quick');
  assert.equal(await page.locator('.recommendation-card').count(),0,'换场景即清空上次结果');
  await call('/inventory','POST',{ingredient_id:noodle.id,quantity:'150',unit:'g',expires_on:new Date(Date.now()+864e5).toISOString().slice(0,10),expiry_source:'user',location:'常温'},'f8race-noodle-01');
  const before=requests.length;
  await page.getByRole('button',{name:'刷新今天',exact:true}).click();
  await waitText(page,/今天的数据已更新，推荐条件保持不变。/);
  assert.equal(await page.getByLabel('推荐场景').inputValue(),'quick','刷新不覆盖用户已选场景');
  assert.equal(await page.locator('.recommendation-card').count(),0,'刷新不把默认场景的结果塞回来');
  assert.match(await page.evaluate(()=>document.body.innerText),/共 2 项需要处理：已过期 0 项，三天内到期 2 项。/,'优先处理按服务端聚合重读');
  assert.match(await page.evaluate(()=>document.body.innerText),/挂面 · 150(\.0+)? 克/);
  assert.deepEqual(requests.slice(before).filter(r=>!r.startsWith('GET /home')),[],'刷新今天只走聚合读取');

  const pending=page.waitForResponse(r=>r.url().endsWith('/recommendations')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'生成本餐推荐',exact:true}).click();
  const sent=(await pending).request().postDataJSON();
  assert.equal(sent.scenario,'quick');assert.equal(sent.max_minutes,20,'快速做仍按20分钟上限');
  await page.getByRole('button',{name:'刷新今天',exact:true}).click();
  await waitText(page,/今天的数据已更新，推荐条件保持不变。/);
  assert.equal(await page.getByLabel('推荐场景').inputValue(),'quick');
  assert.ok(await page.locator('.recommendation-card').count()>0,'已生成的结果留在原处');
  assert.deepEqual(await call('/cooking'),[],'浏览与刷新今天不产生用餐记录');
  assert.equal(Number((await call('/inventory')).find(row=>row.ingredient_id===egg.id).quantity),5,'浏览与刷新今天不扣库存');
  assert.deepEqual(page.problems,[],'页面不应出现未捕获异常');
  await context.close();
 }finally{await browser?.close();await server.stop();}
});
