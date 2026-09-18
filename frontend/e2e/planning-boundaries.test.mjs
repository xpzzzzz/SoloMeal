import test from 'node:test';
import assert from 'node:assert/strict';
import {
 addKindAndBatch,desktopContext,launchBrowser,makeApi,openPage,openPreferences,shot,signUp,startFixture,useTab,waitText,
} from './support.mjs';

test('无可行菜谱、未知补购预算和旧方案确认均在页面解释且不扣库存',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  const api=makeApi(server.url);
  await signUp(page,'ui_planning_0914','planning-fixture-1');
  await addKindAndBatch(page,{name:'鸡蛋',quantity:'1',location:'冷藏'});
  const token=await api.signIn('ui_planning_0914','planning-fixture-1');
  const batch=(await api.call(token,'/inventory')).data[0];
  await useTab(page,'我的菜谱');
  const recipe=page.locator('details.panel').filter({hasText:'添加自己的菜谱'});
  await recipe.locator('summary').click();
  await recipe.getByLabel('菜谱名称').fill('边界煮蛋');
  await recipe.getByLabel('厨具（逗号分隔）').fill('煮锅');
  await recipe.getByLabel('做法（每行一步）').fill('煮熟鸡蛋');
  await recipe.locator('select').selectOption({label:'鸡蛋（个）'});
  await recipe.getByLabel('数量',{exact:true}).fill('2');
  await recipe.getByRole('button',{name:'保存菜谱'}).click();
  await page.locator('.recipe').getByRole('heading',{name:'边界煮蛋',exact:true}).waitFor();
  await page.getByRole('button',{name:'生成本餐推荐'}).click();
  await waitText(page,/没有符合条件的菜谱，请核对厨具、用时与忌口设置/);
  assert.equal(await page.getByRole('button',{name:'保存这餐方案'}).count(),0);

  await openPreferences(page);
  await page.getByLabel('现有厨具（逗号分隔）').fill('煮锅');
  const saved=page.waitForResponse(r=>r.url().endsWith('/me/preferences')&&r.request().method()==='PUT');
  await page.getByRole('button',{name:'保存偏好'}).click();
  assert.equal((await saved).status(),200);
  await useTab(page,'我的菜谱');
  await page.getByLabel('本次补购预算（元，可留空）').fill('10');
  await page.getByRole('button',{name:'生成本餐推荐'}).click();
  await waitText(page,/补购价格未知/);
  await page.getByRole('button',{name:'保存这餐方案'}).click();
  await waitText(page,/已保存方案/);
  await page.getByRole('button',{name:'确认做完',exact:true}).click();
  await page.locator('.modal').getByRole('button',{name:'确认做完',exact:true}).click();
  await waitText(page,/补购预算尚无法核实，请补充价格或修改预算/);
  await page.getByRole('button',{name:'暂不记录'}).click();
  assert.deepEqual((await api.call(token,'/cooking')).data,[]);
  assert.equal(Number((await api.call(token,'/inventory')).data[0].quantity),1);

  await useTab(page,'食材库存');
  const editor=page.locator('details.panel').filter({hasText:'盘点、编辑与归档批次'});
  await editor.locator('summary').click();
  await editor.getByLabel('需要编辑的批次').selectOption(batch.id);
  await editor.getByLabel(/实际剩余数量/).fill('4');
  await editor.getByRole('button',{name:'保存批次',exact:true}).click();
  await waitText(page,/批次已保存/);
  await useTab(page,'我的菜谱');
  await page.getByRole('button',{name:'确认做完',exact:true}).click();
  await page.locator('.modal').getByRole('button',{name:'确认做完',exact:true}).click();
  await waitText(page,/方案已过期：库存、日期或偏好发生变化，请更新方案后再确认/);
  assert.deepEqual((await api.call(token,'/cooking')).data,[]);
  assert.equal(Number((await api.call(token,'/inventory')).data[0].quantity),4);
  assert.equal((await api.call(token,'/plans')).data[0].status,'pending');
  assert.deepEqual(page.problems,[]);
  await shot(page,'planning-stale-confirmation.png');
  await context.close();
 }finally{
  await browser?.close();
  await server.stop();
 }
});
