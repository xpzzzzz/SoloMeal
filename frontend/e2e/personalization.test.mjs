import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,signUp,startFixture,useTab} from './support.mjs';

const PASSWORD='personalization-fixture-1';

test('recommendations show real preference reasons and feedback text',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  const api=makeApi(server.url);
  const username='ui_personalization_0922';
  await signUp(page,username,PASSWORD);
  const token=await api.signIn(username,PASSWORD);
  const egg=(await api.call(token,'/ingredients','POST',{name:'鸡蛋',unit:'piece'})).data;
  const first=(await api.call(token,'/recipes','POST',{
   name:'个性化煮蛋',servings:1,minutes:10,equipment:['煮锅'],steps:['煮熟'],source:'F5 fixture',cooking_methods:['boil'],
   ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'}],
  })).data;
  await api.call(token,'/recipes','POST',{
   name:'个性化蒸蛋',servings:1,minutes:10,equipment:['煮锅'],steps:['蒸熟'],source:'F5 fixture',cooking_methods:['steam'],
   ingredients:[{ingredient_id:egg.id,quantity:'1',unit:'piece'}],
  });
  await api.call(token,'/inventory','POST',{ingredient_id:egg.id,quantity:'2',unit:'piece',location:'冷藏',expiry_source:'unknown'},'f5-stock-0001');
  await api.call(token,'/me/preferences','PUT',{
   equipment:['煮锅'],excluded_ingredients:[],default_servings:1,max_minutes:30,
   personal_time_enabled:true,personalization_enabled:true,
  });
  await api.call(token,'/cooking','POST',{recipe_id:first.id,servings:1},'f5-cook-0001');

  await page.reload({waitUntil:'domcontentloaded'});
  await signIn(page,username,PASSWORD);
  await useTab(page,'我的菜谱');
  await page.locator('.recipe').filter({hasText:'个性化煮蛋'}).getByRole('button',{name:'喜欢',exact:true}).click();
  await page.getByRole('button',{name:'生成本餐推荐'}).click();
  await page.getByRole('heading',{name:'本次推荐依据'}).waitFor();
  const explanations=await page.locator('.preference-explanation').allInnerTexts();
  assert.match(explanations.join('\n'),/个性化煮蛋：根据你的收藏\/喜欢评价提高排序/);
  assert.match(explanations.join('\n'),/个性化蒸蛋：最近1次完成记录中1次使用鸡蛋，偏好仍在积累/);
  assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{
  await browser?.close();
  await server.stop();
 }
});
