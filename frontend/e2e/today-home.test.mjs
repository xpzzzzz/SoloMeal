import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,signOut,signUp,startFixture,testDate,useTab,visibleButtons,waitText} from './support.mjs';

// One operable home page over the already reviewed services: the aggregate is read, so nothing
// on this page may move stock until 确认做饭并扣库存 says so.
test('F8 今天首页聚合、收藏、做饭、改用时与切换账号',async()=>{
 const server=process.env.F8_PREVIEW_URL?{url:process.env.F8_PREVIEW_URL,stop:async()=>{}}:await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();const context=await desktopContext(browser);const page=await openPage(context,server.url);
  const requests=[];
  page.on('request',r=>{const p=new URL(r.url()).pathname;if(p.startsWith('/api/v1'))requests.push(r.method()+' '+p.slice(7));});
  const api=makeApi(server.url),username='f8_'+Date.now().toString(36),password='F8-preview-fixture-12';
  await signUp(page,username,password);const token=await api.signIn(username,password);
  const call=async(path,method='GET',body,key)=>{const r=await api.call(token,path,method,body,key);assert.ok(r.status<300,JSON.stringify(r));return r.data;};
  const egg=await call('/ingredients','POST',{name:'鸡蛋',unit:'piece'});
  const tomato=await call('/ingredients','POST',{name:'番茄',unit:'piece'});
  const boil=await call('/recipes','POST',{name:'首页煮蛋',servings:1,minutes:10,equipment:['煮锅'],source:'F8 fixture',steps:['煮熟'],ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'}]});
  const stew=await call('/recipes','POST',{name:'首页番茄蛋',servings:1,minutes:15,equipment:['煮锅'],source:'F8 fixture',steps:['煮番茄'],ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'},{ingredient_id:tomato.id,quantity:'2',unit:'piece'}]});
  await call('/me/preferences','PUT',{equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30,personal_time_enabled:true,personalization_enabled:true});
  await call('/inventory','POST',{ingredient_id:egg.id,quantity:'5',unit:'piece',expires_on:testDate(2),expiry_source:'user',location:'冷藏'},'f8-stock-0000001');
  const plan=await call('/plans','POST',{recipe_id:stew.id,constraints:{}},'f8-plan-0000001');
  await call('/shopping','POST',{plan_id:plan.id,expected_version:plan.version},'f8-draft-000001');
  requests.length=0;
  await page.reload({waitUntil:'domcontentloaded'});
  await signIn(page,username,password);

  await page.getByRole('heading',{name:'今天做点什么',exact:true}).waitFor();
  assert.equal(await page.locator('.home').count(),1,'登录后应停在今天首页');
  await waitText(page,/鸡蛋 · 5(\.0+)? 个 · \d{4}-\d{2}-\d{2}[^\n]*\n三天内到期/);
  assert.match(await page.evaluate(()=>document.body.innerText),/共 1 项需要处理：已过期 0 项，三天内到期 1 项。/);
  await waitText(page,/首页番茄蛋 · 待买 1 项 · 共 1 项/);
  assert.match(await page.evaluate(()=>document.body.innerText),/还没有完成的用餐记录。/,'没有记录时不能凭空出现历史');
  assert.deepEqual(requests.filter(r=>r.startsWith('POST /recommendations')||r.startsWith('POST /agent')),[],'首页加载不得自动发起推荐或助手请求');

  await page.getByRole('button',{name:'生成本餐推荐',exact:true}).click();
  await page.getByRole('heading',{name:'本次推荐依据',exact:true}).waitFor();
  const eggCard=page.locator('.recommendation-card').filter({hasText:'首页煮蛋'});
  assert.match(await eggCard.innerText(),/现有库存足够，无需采购/);
  const favorited=page.waitForResponse(r=>r.url().endsWith('/recipes/'+boil.id+'/feedback')&&r.request().method()==='PUT');
  await eggCard.getByRole('button',{name:'收藏',exact:true}).click();
  assert.equal((await favorited).status(),200);
  await eggCard.getByRole('button',{name:'已收藏',exact:true}).waitFor();
  await useTab(page,'我的菜谱');
  await page.locator('.recipe').filter({hasText:'首页煮蛋'}).getByRole('button',{name:'已收藏',exact:true}).waitFor();
  await useTab(page,'今天');
  await page.locator('.recommendation-card').filter({hasText:'首页番茄蛋'}).getByRole('button',{name:'换一道'}).click();
  assert.equal(await page.locator('.recommendation-card').filter({hasText:'首页番茄蛋'}).count(),0);
  await page.locator('.recommendation-card').filter({hasText:'首页煮蛋'}).getByRole('button',{name:'开始做饭',exact:true}).click();

  await page.getByRole('heading',{name:'开始做饭 · 首页煮蛋',exact:true}).waitFor();
  await page.getByRole('button',{name:'开始步骤与计时',exact:true}).click();
  await page.getByRole('button',{name:'结束并确认做饭',exact:true}).click();
  await page.getByLabel('实际耗时（分钟）',{exact:true}).fill('12');
  await page.getByRole('button',{name:'确认做饭并扣库存',exact:true}).click();
  await page.getByRole('heading',{name:'每一餐都有记录',exact:true}).waitFor();
  const records=await call('/cooking');
  assert.equal(records.length,1,'确认做饭才新增记录');
  assert.equal(records[0].actual_minutes,12);
  assert.equal(Number((await call('/inventory'))[0].quantity),4,'只有确认做饭才扣库存');
  assert.equal((await call('/shopping'))[0].status,'draft','做饭不应改动采购清单');

  await useTab(page,'今天');
  await waitText(page,/首页煮蛋 · \d{4}-\d{2}-\d{2} · 1 人份 · 12 分钟/);
  await page.locator('.home-recent button').first().click();
  await page.getByRole('heading',{name:'每一餐都有记录',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.activeElement?.id),'meal-'+records[0].id,'点击最近做过应聚焦那条记录');
  const row=page.locator('#meal-'+records[0].id);
  await row.getByRole('button',{name:'修改用时',exact:true}).click();
  await row.getByLabel('实际耗时（分钟，留空清除）').fill('9');
  await row.getByRole('button',{name:'保存用时',exact:true}).click();
  await waitText(page,/用时已保存，库存未改变/);
  assert.equal((await call('/cooking'))[0].actual_minutes,9);
  assert.equal(Number((await call('/inventory'))[0].quantity),4,'修改用时不碰库存');

  await useTab(page,'今天');
  await waitText(page,/首页煮蛋 · \d{4}-\d{2}-\d{2} · 1 人份 · 9 分钟/,'刷新前保留已读内容');
  const before=requests.length;
  await page.getByRole('button',{name:'刷新今天',exact:true}).click();
  await waitText(page,/今天的数据已更新，推荐条件保持不变。/);
  assert.deepEqual(requests.slice(before).filter(r=>r.startsWith('POST /recommendations')),[],'刷新今天不重跑推荐');
  if(process.env.F8_PREVIEW_URL)await page.screenshot({path:'.tmp-e2e/f8-desktop.png',fullPage:true});

  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'今天首页在 390px 不应横向溢出');
  const small=(await visibleButtons(page)).filter(b=>b.height<40);
  assert.deepEqual(small,[],`今天首页按钮在窄屏过小：${JSON.stringify(small)}`);
  if(process.env.F8_PREVIEW_URL)await page.screenshot({path:'.tmp-e2e/f8-mobile.png',fullPage:true});
  await page.setViewportSize({width:1280,height:900});

  await signOut(page);
  const second='f8b_'+Date.now().toString(36);
  await signUp(page,second,password);
  await page.getByRole('heading',{name:'今天做点什么',exact:true}).waitFor();
  const fresh=await api.signIn(second,password);
  assert.deepEqual(await api.call(fresh,'/inventory').then(r=>r.data),[],'新账号看不到上一个账号的库存');
  assert.match(await page.evaluate(()=>document.body.innerText),/三天内没有需要处理的食材。/);
  assert.match(await page.evaluate(()=>document.body.innerText),/没有待办采购清单。/);
  await waitText(page,/先把厨房装起来/);
  if(process.env.F8_PREVIEW_URL)await page.screenshot({path:'.tmp-e2e/f8-empty-start.png',fullPage:true});
  const added=page.locator('.home-start').getByRole('button',{name:'导入示例菜谱',exact:true});
  assert.equal(await page.locator('table tbody tr').count(),0,'示例内容只在显式点击后写入');
  await added.click();
  await waitText(page,/示例菜谱已就绪/);
  assert.equal((await api.call(fresh,'/recipes')).data.length,3,'导入示例只添加菜谱');
  assert.deepEqual(await api.call(fresh,'/inventory').then(r=>r.data),[],'导入示例不增加库存');
  assert.deepEqual(await api.call(fresh,'/cooking').then(r=>r.data),[],'导入示例不伪造用餐记录');
  assert.deepEqual(await api.call(fresh,'/shopping').then(r=>r.data),[],'导入示例不生成采购清单');
  assert.match(await page.evaluate(()=>document.body.innerText),/还没有完成的用餐记录。/);
  assert.equal((await call('/inventory'))[0].name,'鸡蛋','上一个账号的数据仍在');
  assert.deepEqual(page.problems,[],'页面不应出现未捕获异常');
  await context.close();
 }finally{await browser?.close();await server.stop();}
});
