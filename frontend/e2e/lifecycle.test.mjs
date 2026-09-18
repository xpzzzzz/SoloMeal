import test from 'node:test';
import assert from 'node:assert/strict';
import {
 addKindAndBatch,desktopContext,launchBrowser,makeApi,openPage,shot,signIn,signUp,startFixture,useTab,waitText,
} from './support.mjs';

test('盘点归档恢复、菜谱编辑和方案版本取消在刷新后与服务端一致',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  const api=makeApi(server.url);
  await signUp(page,'ui_lifecycle_0914','lifecycle-fixture-1');
  await addKindAndBatch(page,{name:'鸡蛋',quantity:'6',location:'冷藏'});
  const token=await api.signIn('ui_lifecycle_0914','lifecycle-fixture-1');
  const inventory=async()=> (await api.call(token,'/inventory?include_archived=true')).data;
  const batch=(await inventory())[0];
  const editor=page.locator('details.panel').filter({hasText:'盘点、编辑与归档批次'});
  await editor.locator('summary').click();
  await editor.getByLabel('需要编辑的批次').selectOption(batch.id);
  await editor.getByLabel(/实际剩余数量/).fill('5');
  await editor.getByLabel('存放位置').fill('冰箱上层');
  await editor.getByRole('button',{name:'保存批次',exact:true}).click();
  await waitText(page,/批次已保存/);
  assert.equal(Number((await inventory())[0].quantity),5);
  await editor.getByLabel('需要编辑的批次').selectOption(batch.id);
  await editor.getByRole('button',{name:'归档批次',exact:true}).click();
  await waitText(page,/批次已归档/);
  assert.equal((await inventory())[0].archived,true);
  assert.deepEqual((await api.call(token,'/inventory')).data,[]);
  await page.reload();
  await signIn(page,'ui_lifecycle_0914','lifecycle-fixture-1');
  await waitText(page,/暂无未归档的库存批次/);
  await editor.locator('summary').click();
  await editor.getByRole('button',{name:'查看归档批次',exact:true}).click();
  await editor.getByRole('button',{name:'恢复批次',exact:true}).click();
  await waitText(page,/批次已恢复/);
  assert.deepEqual((await inventory()).map(b=>[Number(b.quantity),b.archived,b.location]),[[5,false,'冰箱上层']]);

  await useTab(page,'厨房偏好');
  await page.getByLabel('现有厨具（逗号分隔）').fill('煮锅');
  const saved=page.waitForResponse(r=>r.url().endsWith('/me/preferences')&&r.request().method()==='PUT');
  await page.getByRole('button',{name:'保存偏好'}).click();
  assert.equal((await saved).status(),200);
  await useTab(page,'我的菜谱');
  const recipe=page.locator('details.panel').filter({hasText:'添加自己的菜谱'});
  await recipe.locator('summary').click();
  await recipe.getByLabel('菜谱名称').fill('生命周期煮蛋');
  await recipe.getByLabel('厨具（逗号分隔）').fill('煮锅');
  await recipe.getByLabel('做法（每行一步）').fill('煮熟鸡蛋');
  await recipe.locator('select').selectOption({label:'鸡蛋（个）'});
  await recipe.getByLabel('数量',{exact:true}).fill('2');
  await recipe.getByRole('button',{name:'保存菜谱'}).click();
  await page.locator('.recipe').getByRole('heading',{name:'生命周期煮蛋',exact:true}).waitFor();
  await page.getByRole('button',{name:'生成本餐推荐'}).click();
  await page.getByRole('button',{name:'保存这餐方案'}).click();
  await waitText(page,/已保存方案/);
  const plan=(await api.call(token,'/plans')).data[0];
  await page.getByRole('button',{name:'编辑菜谱',exact:true}).click();
  const edit=page.locator('details.panel').filter({hasText:'编辑「生命周期煮蛋」'});
  await edit.getByLabel('菜谱名称').fill('修改后的煮蛋');
  await edit.getByLabel('数量',{exact:true}).fill('3');
  await edit.getByRole('button',{name:'保存菜谱'}).click();
  await page.locator('.recipe').getByRole('heading',{name:'修改后的煮蛋',exact:true}).waitFor();
  await page.getByRole('button',{name:'按当前库存更新'}).click();
  await waitText(page,/方案已按最新库存更新/);
  await page.getByRole('button',{name:'查看版本历史'}).click();
  await waitText(page,/版本 1 · 生命周期煮蛋/);
  await waitText(page,/版本 2 · 修改后的煮蛋/);
  const revisions=(await api.call(token,`/plans/${plan.id}/revisions`)).data;
  assert.deepEqual(revisions.map(r=>[r.version,r.snapshot.candidate.recipe.name]).sort((a,b)=>a[0]-b[0]),
   [[1,'生命周期煮蛋'],[2,'修改后的煮蛋']]);
  await page.getByRole('button',{name:'取消方案',exact:true}).click();
  await waitText(page,/已取消/);
  await page.reload();
  await signIn(page,'ui_lifecycle_0914','lifecycle-fixture-1');
  await useTab(page,'我的菜谱');
  await waitText(page,/已取消/);
  assert.equal(await page.getByRole('button',{name:'确认做完',exact:true}).count(),0);
  assert.equal((await api.call(token,'/plans')).data[0].status,'cancelled');
  assert.equal(Number((await inventory())[0].quantity),5,'规划、修订、取消均不扣库存');
  assert.deepEqual((await api.call(token,'/cooking')).data,[]);
  assert.deepEqual(page.problems,[]);
  await shot(page,'lifecycle-plan-cancelled.png');
  await context.close();
 }finally{
  await browser?.close();
  await server.stop();
 }
});
