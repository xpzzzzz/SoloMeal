import test from 'node:test';
import assert from 'node:assert/strict';
import {
 addKindAndBatch,desktopContext,horizontalOverflow,launchBrowser,makeApi,mobileContext,openPage,shot,
 signIn,signUp,startFixture,useTab,visibleButtons,waitText,
} from './support.mjs';

const PASSWORD='feedback-fixture-1';
const FIRST='反馈甲菜谱';
const SECOND='反馈乙菜谱';

const card=(page,name)=>page.locator('.recipe').filter({hasText:name});
// The favorite control renames itself to 已收藏, so every lookup matches both states.
const NAMES={收藏:/^已?收藏$/,喜欢:/^喜欢$/,不喜欢:/^不喜欢$/,清除评价:/^清除评价$/};
const button=(page,name,label)=>card(page,name).getByRole('button',{name:NAMES[label]});
const pressed=async(page,name,label)=>button(page,name,label).getAttribute('aria-pressed');

async function createRecipe(page,{name,methods}){
 await useTab(page,'我的菜谱');
 const editor=page.locator('details.panel').filter({hasText:'添加自己的菜谱'});
 // Saving leaves the panel open with cleared fields, so tapping the summary again would close it.
 if(!await editor.evaluate(el=>el.open))await editor.locator('summary').click();
 await editor.getByLabel('菜谱名称').fill(name);
 await editor.getByLabel('厨具（逗号分隔）').fill('煮锅');
 await editor.getByLabel('做法（每行一步）').fill('烧开后煮熟');
 await editor.locator('select').selectOption({label:'鸡蛋（个）'});
 await editor.getByLabel('数量',{exact:true}).fill('2');
 for(const method of methods)await editor.getByLabel(method,{exact:true}).check();
 await editor.getByRole('button',{name:'保存菜谱'}).click();
 await card(page,name).getByRole('heading',{name,exact:true}).waitFor();
}

// The card writes the whole state each time, so every tap is one PUT the page waits for.
async function tap(page,name,label){
 const saved=page.waitForResponse(r=>r.url().endsWith('/feedback')&&r.request().method()==='PUT',{timeout:30_000});
 await button(page,name,label).click();
 assert.equal((await saved).status(),200,`${label} 应当保存成功`);
}

test('收藏与喜欢/不喜欢在刷新后仍在，删除菜谱不影响用餐记录',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  const api=makeApi(server.url);
  await signUp(page,'ui_fb_owner_0922',PASSWORD);
  await addKindAndBatch(page,{name:'鸡蛋',quantity:'6',location:'冷藏'});

  await createRecipe(page,{name:FIRST,methods:['炒','煮']});
  assert.deepEqual(await card(page,FIRST).locator('.methods .tag').allInnerTexts(),['炒','煮'],'卡片应显示中文标签');
  await createRecipe(page,{name:SECOND,methods:[]});
  assert.equal(await card(page,SECOND).locator('.methods').count(),0,'未选标签的菜谱不应出现空标签行');
  assert.equal(await pressed(page,FIRST,'收藏'),'false','新菜谱默认未收藏');
  assert.equal(await button(page,FIRST,'清除评价').count(),0,'还没有评价时不应出现清除入口');

  await tap(page,FIRST,'收藏');
  await waitText(page,/评价已保存/);
  assert.equal(await button(page,FIRST,'收藏').innerText(),'已收藏');
  assert.equal(await pressed(page,FIRST,'收藏'),'true');
  assert.equal(await pressed(page,SECOND,'收藏'),'false','收藏只属于这一道');
  await tap(page,SECOND,'喜欢');

  await tap(page,FIRST,'喜欢');
  assert.equal(await pressed(page,FIRST,'喜欢'),'true');
  await tap(page,FIRST,'不喜欢');
  assert.equal(await pressed(page,FIRST,'喜欢'),'false','换一个评价应替换而不是同时选中');
  assert.equal(await pressed(page,FIRST,'不喜欢'),'true');
  await tap(page,FIRST,'清除评价');
  assert.equal(await pressed(page,FIRST,'收藏'),'true','清除评价不应改动收藏');
  assert.equal(await pressed(page,FIRST,'不喜欢'),'false');
  assert.equal(await button(page,FIRST,'清除评价').count(),0);

  const token=await api.signIn('ui_fb_owner_0922',PASSWORD);
  const target=(await api.call(token,'/recipes')).data.find(r=>r.name===FIRST);
  assert.deepEqual(target.cooking_methods,['stir_fry','boil'],'页面写的是中文，存的是枚举值');
  assert.deepEqual({...(await api.call(token,`/recipes/${target.id}/feedback`)).data,updated_at:null},
   {recipe_id:target.id,favorite:true,rating:'neutral',version:4,updated_at:null},'四次保存各递增一次');
  // Another account can neither read nor write this feedback, and does not see the recipe.
  const other=await api.signIn('ui_fb_other_0922',PASSWORD);
  assert.equal((await api.call(other,`/recipes/${target.id}/feedback`)).status,404);
  assert.equal((await api.call(other,`/recipes/${target.id}/feedback`,'PUT',
   {favorite:true,rating:'like',expected_version:0},'feedback-other-0001')).status,404);
  assert.deepEqual((await api.call(other,'/recipes')).data.filter(r=>r.name===FIRST),[]);

  await page.reload({waitUntil:'domcontentloaded'});
  await signIn(page,'ui_fb_owner_0922',PASSWORD);
  await useTab(page,'我的菜谱');
  assert.equal(await pressed(page,FIRST,'收藏'),'true','重新登录后收藏仍在');
  assert.equal(await pressed(page,FIRST,'不喜欢'),'false','重新登录后评价也仍在');
  assert.equal(await pressed(page,SECOND,'喜欢'),'true');
  assert.equal(await page.locator('.recipe').count(),2);
  await page.getByLabel('只看收藏').check();
  assert.equal(await page.locator('.recipe').count(),1,'收藏筛选只留下已收藏的菜谱');
  assert.deepEqual(await card(page,FIRST).locator('.methods .tag').allInnerTexts(),['炒','煮']);
  await page.getByLabel('只看收藏').uncheck();
  assert.equal(await page.locator('.recipe').count(),2);
  await shot(page,'recipe-feedback-desktop.png');

  await card(page,FIRST).getByRole('button',{name:'记录做完这道菜'}).click();
  await page.locator('.modal').getByRole('button',{name:'确认做完'}).click();
  await waitText(page,/已记录，库存同步更新/);
  await card(page,FIRST).getByRole('button',{name:'删除菜谱'}).click();
  await card(page,FIRST).waitFor({state:'detached',timeout:30_000});
  assert.equal((await api.call(token,`/recipes/${target.id}/feedback`)).status,404,'菜谱删除后评价行随之删除');
  const kept=(await api.call(token,'/recipes')).data.find(r=>r.name===SECOND);
  assert.deepEqual({...(await api.call(token,`/recipes/${kept.id}/feedback`)).data,updated_at:null},
   {recipe_id:kept.id,favorite:false,rating:'like',version:1,updated_at:null},'删除只清理这一道的评价');
  await useTab(page,'用餐记录');
  await waitText(page,/反馈甲菜谱/);
  assert.match(await page.evaluate(()=>document.body.innerText),/已完成/,'菜谱删除后用餐记录仍应可读');
  await page.getByRole('button',{name:'撤销并恢复食材'}).click();
  await waitText(page,/已撤销/);
  assert.equal(Number((await api.call(token,'/inventory')).data.find(b=>b.name==='鸡蛋').quantity),6,'撤销仍按快照恢复食材');
  assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{
  await browser?.close();
  await server.stop();
 }
});

test('窄屏上收藏与评价可以点，标签与按钮都不挤破版面',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await mobileContext(browser);
  const page=await openPage(context,server.url);
  await signUp(page,'ui_fb_mobile_0922',PASSWORD);
  await addKindAndBatch(page,{name:'鸡蛋',quantity:'6',location:'冷藏'});
  await createRecipe(page,{name:FIRST,methods:['炒','炖']});
  await tap(page,FIRST,'收藏');
  await tap(page,FIRST,'喜欢');
  await waitText(page,/评价已保存/);
  assert.equal(await horizontalOverflow(page),0,'菜谱页不应出现横向溢出');
  const small=(await visibleButtons(page)).filter(b=>b.height<40);
  assert.deepEqual(small,[],'主要操作在触摸尺寸下仍要可点：'+JSON.stringify(small));
  for(const label of ['收藏','喜欢']){
   assert.equal(await button(page,FIRST,label).isVisible(),true,`${label} 应在窄屏可见`);
  }
  for(const name of ['记录做完这道菜','编辑菜谱']){
   assert.equal(await card(page,FIRST).getByRole('button',{name,exact:true}).isVisible(),true,`${name} 应在窄屏可见`);
  }
  assert.deepEqual(await card(page,FIRST).locator('.methods .tag').allInnerTexts(),['炒','炖']);
  assert.equal(await pressed(page,FIRST,'喜欢'),'true');
  await shot(page,'recipe-feedback-mobile.png');
  assert.deepEqual(page.problems,[]);
  await context.close();
 }finally{
  await browser?.close();
  await server.stop();
 }
});
