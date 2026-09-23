import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {
 desktopContext,launchBrowser,makeApi,openPage,signIn,startFixture,useTab,waitText,
} from './support.mjs';

let server,browser,api;
const PASSWORD='discovery-fixture-1';

// List reads are page-by-page, so the browser URL carries limit/offset beyond the panel's filter.
const isRead=r=>r.request().method()==='GET';
const onPath=(r,path)=>new URL(r.url()).pathname==='/api/v1'+path;
const draftsRead=r=>onPath(r,'/recipe-drafts')&&isRead(r);

// The panel re-reads drafts, batches, capabilities and preferences on every mount, so the
// caller waits for those reads instead of typing into a form a late response may rewrite.
async function openDiscovery(page){
 const reads=[
  page.waitForResponse(draftsRead),
  page.waitForResponse(r=>onPath(r,'/recipe-discoveries')&&isRead(r)),
  page.waitForResponse(r=>onPath(r,'/recipe-discoveries/capabilities')&&isRead(r)),
  page.waitForResponse(r=>onPath(r,'/me/preferences')&&isRead(r)),
 ];
 await useTab(page,'发现菜谱');
 await Promise.all(reads);
}

async function refreshDrafts(page){
 const loaded=page.waitForResponse(draftsRead);
 await page.getByRole('button',{name:'刷新候选列表',exact:true}).click();
 await loaded;
}

// One stocked ingredient, so the scripted candidates reuse a real name and unit and any
// inventory change is visible against this snapshot.
async function seedKitchen(url,user,password){
 const client=makeApi(url);
 await client.call(null,'/auth/register','POST',{username:user,password});
 const token=await client.signIn(user,password);
 const item=(await client.call(token,'/ingredients','POST',{name:'挂面',unit:'g'})).data;
 await client.call(token,'/inventory','POST',{ingredient_id:item.id,quantity:'1000',unit:'g',
  expiry_source:'unknown',location:'常温'},'e2e-discovery-seed');
 return {client,token,inventory:await client.call(token,'/inventory')};
}

const editor=(page,name)=>page.locator('section.draft-editor').filter({hasText:name});
const acceptOf=(page,name)=>editor(page,name).getByRole('button',{name:'确认加入菜谱库',exact:true});

// Validation answers asynchronously, and until it lands the editor still shows the errors
// stored with the last save — so the round trip is awaited before either side is read.
async function checkDraft(scope,codes){
 const answered=scope.page().waitForResponse(r=>new URL(r.url()).pathname.endsWith('/validate')&&r.request().method()==='POST');
 await scope.getByRole('button',{name:'按当前填写校验',exact:true}).click();
 const result=await (await answered).json();
 assert.deepEqual(result.errors.map(i=>i.code),codes,'校验应按字段逐项报告问题');
 for(let i=0;i<40;i++){
  if(await scope.locator('[role="alert"]').count()===codes.length)return result;
  await scope.page().waitForTimeout(250);
 }
 assert.fail(`页面提示与校验结果不符：${(await scope.locator('[role="alert"]').allInnerTexts()).join(' | ')}`);
}

before(async()=>{
 server=await startFixture(0,{recipeDiscovery:true});
 browser=await launchBrowser();
 api=makeApi(server.url);
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

test('脚本生成三道候选：逐项定位错误、编辑保存后才入库，且全程不动库存',async()=>{
 const user='ui_discovery_flow';
 const {token,inventory}=await seedKitchen(server.url,user,PASSWORD);
 const context=await desktopContext(browser);
 try{
  const page=await openPage(context,server.url);
  await signIn(page,user,PASSWORD);
  await openDiscovery(page);
  assert.match(await page.evaluate(()=>document.body.innerText),/候选由已配置的模型生成/);

  await page.getByLabel('人数（留空用厨房偏好）').fill('2');
  await page.getByLabel('最多用时（分钟，留空用厨房偏好）').fill('20');
  await page.getByLabel('本次可用厨具（逗号分隔，留空用厨房偏好）').fill('煮锅');
  await refreshDrafts(page);
  assert.equal(await page.getByLabel('人数（留空用厨房偏好）').inputValue(),'2','刷新读取不能覆盖已填写的人数');
  assert.equal(await page.getByLabel('本次可用厨具（逗号分隔，留空用厨房偏好）').inputValue(),'煮锅','刷新读取不能覆盖已填写的厨具');

  await page.getByRole('button',{name:'生成候选',exact:true}).click();
  await waitText(page,/本次返回 3 道候选（模型 scripted-discovery-fixture）/);
  assert.equal(await page.locator('section.draft-editor').count(),3,'一次生成应给出三道可编辑候选');
  assert.match(await page.evaluate(()=>document.body.innerText),/本次条件：2 人、最多 20 分钟/);

  // The unusable line must be reported on its own row, and must block confirmation.
  const problems=await editor(page,'脚本糊底一锅').locator('.draft-line').nth(2).getByRole('alert').allInnerTexts();
  assert.ok(problems.some(t=>/第 3 项食材的数量.*适量/.test(t)),`数量错误应标在第 3 项：${problems.join(' | ')}`);
  assert.ok(problems.some(t=>/第 3 项食材的单位.*碗/.test(t)),`单位错误应标在第 3 项：${problems.join(' | ')}`);
  assert.equal(await acceptOf(page,'脚本糊底一锅').isDisabled(),true);

  // Editing a draft has to be saved before it can be accepted, and what lands is what was saved.
  const egg=editor(page,'脚本番茄鸡蛋面').locator('.draft-line').nth(2);
  await egg.getByLabel('食材',{exact:true}).fill('脚本土鸡蛋');
  assert.match(await page.evaluate(()=>document.body.innerText),/确认后将新建食材：脚本葱花（克）、脚本土鸡蛋（个）/);
  assert.equal(await acceptOf(page,'脚本番茄鸡蛋面').isDisabled(),true,'有未保存修改时不能入库');
  await checkDraft(editor(page,'脚本番茄鸡蛋面'),[]);
  await editor(page,'脚本番茄鸡蛋面').getByRole('button',{name:'保存草稿',exact:true}).click();
  await waitText(page,/草稿已保存，库存未改变/);
  assert.ok(await waitEnabled(acceptOf(page,'脚本番茄鸡蛋面')),'已保存且无错误的候选才允许确认');
  await acceptOf(page,'脚本番茄鸡蛋面').click();
  await waitText(page,/「脚本番茄鸡蛋面」已加入菜谱库/);
  assert.equal(await page.locator('section.draft-editor').count(),2,'入库的候选离开待核对列表');

  await page.getByRole('button',{name:'用当前条件重新推荐',exact:true}).click();
  await waitText(page,/下一顿，做什么？/);
  await waitText(page,/脚本番茄鸡蛋面 · 2 人份/);
  assert.match(await page.evaluate(()=>document.body.innerText),/需采购1种食材：脚本土鸡蛋 2个/,'缺料应转为补购提示而不是丢掉候选');

  await openDiscovery(page);
  await editor(page,'脚本青菜汤饭').getByRole('button',{name:'丢弃草稿',exact:true}).click();
  await waitText(page,/草稿已丢弃，没有写入菜谱或库存/);
  assert.equal(await page.locator('section.draft-editor').count(),1);

  // Cross-check the page against what the service actually stored.
  const names=(await api.call(token,'/ingredients')).data.map(i=>i.name);
  assert.ok(names.includes('脚本土鸡蛋'),'保存后的改名应写入食材种类');
  assert.ok(!names.includes('脚本鸡蛋'),'改名之前的名称不应留下痕迹');
  const recipes=(await api.call(token,'/recipes')).data;
  assert.deepEqual(recipes.map(r=>[r.name,r.servings,r.minutes,r.ingredients.map(i=>i.name).sort()]),
   [['脚本番茄鸡蛋面',2,20,['挂面','脚本葱花','脚本土鸡蛋'].sort()]]);
  const batches=(await api.call(token,'/recipe-discoveries')).data;
  assert.equal(batches.length,1,'一次点击只登记一次生成');
  assert.deepEqual([batches[0].status,batches[0].drafts.length,batches[0].usage.total_tokens],['completed',3,690]);
  assert.deepEqual((await api.call(token,'/inventory')).data,inventory.data,'生成、编辑、校验、确认与丢弃都不改变库存');
  assert.deepEqual(page.problems,[]);
 }finally{await context.close();}
});

// A row list that already has one entry is not a signal that the second one arrived.
async function waitForDrafts(page,count){
 await page.waitForFunction(n=>document.querySelectorAll('section.draft-editor').length===n,count,{timeout:20_000});
}

// The panel clears its busy flag one render after it paints the list it just read, so a single
// read can catch a button disabled for the wrong reason. Poll for the state being asserted on.
async function waitEnabled(locator){
 for(let i=0;i<40;i++){
  if(await locator.isDisabled()===false)return true;
  await locator.page().waitForTimeout(250);
 }
 return false;
}

// One claim per click, so the panel cannot spend the same key twice while we stack batches.
async function generateOnce(page){
 const answered=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/recipe-discoveries'
  &&r.request().method()==='POST');
 await page.getByRole('button',{name:'生成候选',exact:true}).click();
 const batch=await (await answered).json();
 assert.equal(batch.drafts.length,3,'每次点击给出三道候选');
 return batch;
}

// The editor has to keep what the keyboard produced: a comma or Enter must survive long enough
// to type the entry after it, and the saved draft must hold two tools and two steps.
test('逐键输入厨具与步骤：末尾分隔符不被吞掉，保存与重开仍是两件厨具两步',async()=>{
 const user='ui_discovery_typing';
 const {client,token}=await seedKitchen(server.url,user,PASSWORD);
 const context=await desktopContext(browser);
 try{
  const page=await openPage(context,server.url);
  await signIn(page,user,PASSWORD);
  await openDiscovery(page);
  await page.getByRole('button',{name:'手工新建草稿',exact:true}).click();
  await waitText(page,/已创建一份空白手工草稿/);
  const draft=page.locator('section.draft-editor').first();
  await draft.getByLabel('菜谱名称',{exact:true}).fill('逐键输入面');
  await draft.getByLabel('人数',{exact:true}).fill('1');
  await draft.getByLabel('用时（分钟）',{exact:true}).fill('15');

  const tools=draft.getByLabel('厨具（逗号分隔）',{exact:true});
  await tools.pressSequentially('煮锅');
  await tools.pressSequentially('，炒锅');
  assert.equal(await tools.inputValue(),'煮锅，炒锅','刚输入的逗号必须还留在输入框里');

  // Chromium folds a wrapping <label>'s textarea content into the accessible name, so the label
  // lookup stops matching as soon as a step is typed. The editor has exactly one textarea.
  const steps=draft.locator('textarea');
  await steps.pressSequentially('水开下面');
  await steps.press('Enter');
  await steps.pressSequentially('盛出');
  assert.equal(await steps.inputValue(),'水开下面\n盛出','换行必须还留在文本框里');

  await draft.getByRole('button',{name:'增加食材行',exact:true}).click();
  const line=draft.locator('.draft-line').first();
  await line.getByLabel('食材',{exact:true}).fill('挂面');
  await line.getByLabel('数量',{exact:true}).fill('150');
  await checkDraft(draft,[]);
  await draft.getByRole('button',{name:'保存草稿',exact:true}).click();
  await waitText(page,/草稿已保存，库存未改变/);

  const saved=await client.call(token,'/recipe-drafts?status=draft');
  assert.equal(saved.data.length,1);
  assert.deepEqual([saved.data[0].payload.equipment,saved.data[0].payload.steps],
   [['煮锅','炒锅'],['水开下面','盛出']],'保存的必须是两项，而不是一项目被吞');
  assert.deepEqual(saved.data[0].validation_errors,[],'两项厨具两步应通过服务端校验');

  // Re-mounted from the stored draft, the same two entries are still what the user sees.
  await useTab(page,'我的菜谱');
  await openDiscovery(page);
  const reloaded=page.locator('section.draft-editor').first();
  assert.equal(await reloaded.getByLabel('厨具（逗号分隔）',{exact:true}).inputValue(),'煮锅，炒锅');
  assert.equal(await reloaded.locator('textarea').inputValue(),'水开下面\n盛出');
  assert.deepEqual(page.problems,[]);
 }finally{await context.close();}
});

// A draft from an older batch keeps its own conditions: re-recommending must send that batch's
// stored numbers, not the form values or the kitchen preference that are current right now.
test('确认第六批之前的草稿后，重新推荐仍带该批次保存的条件',async()=>{
 const user='ui_discovery_old_batch';
 const {token}=await seedKitchen(server.url,user,PASSWORD);
 const context=await desktopContext(browser);
 try{
  const page=await openPage(context,server.url);
  await signIn(page,user,PASSWORD);
  await openDiscovery(page);
  const setForm=async(servings,minutes)=>{
   await page.getByLabel('人数（留空用厨房偏好）').fill(String(servings));
   await page.getByLabel('最多用时（分钟，留空用厨房偏好）').fill(String(minutes));
   await page.getByLabel('本次可用厨具（逗号分隔，留空用厨房偏好）').fill('煮锅');
  };
  await setForm(1,15);
  await generateOnce(page);
  await setForm(2,20);
  const later=[];
  for(let i=0;i<5;i++)later.push(await generateOnce(page));
  await refreshDrafts(page);
  await waitForDrafts(page,18);
  assert.equal(await page.locator('details p').count(),5,'历史列表只显示最近五条');

  const target=page.locator('section.draft-editor')
   .filter({hasText:'本次条件：1 人、最多 15 分钟'})
   .filter({hasText:'脚本番茄鸡蛋面'}).first();
  assert.equal(await target.count(),1,'最早那一批的草稿仍在待核对列表里');
  assert.ok(await waitEnabled(target.getByRole('button',{name:'确认加入菜谱库',exact:true})));
  await target.getByRole('button',{name:'确认加入菜谱库',exact:true}).click();
  await waitText(page,/「脚本番茄鸡蛋面」已加入菜谱库/);
  assert.match(await page.evaluate(()=>document.body.innerText),/本次发现的条件（1 人、最多 15 分钟）/);

  const sent=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/v1/recommendations'
   &&r.method()==='POST');
  await page.getByRole('button',{name:'用当前条件重新推荐',exact:true}).click();
  const body=(await sent).postDataJSON();
  // The form says 2 人/20 分钟 and the preference says 2 人/30 分钟, so only the batch itself
  // can account for these numbers.
  assert.equal(body.servings,1,'重新推荐必须沿用该批次的人数');
  assert.equal(body.max_minutes,15,'重新推荐必须沿用该批次的用时上限');
  assert.deepEqual(body.equipment,['煮锅']);
  await waitText(page,/下一顿，做什么？/);
  const batches=await makeApi(server.url).call(token,'/recipe-discoveries');
  assert.equal(batches.data.length,6,'六批各登记一次生成');
  assert.deepEqual(page.problems,[]);
 }finally{await context.close();}
});

// A fixture without --recipe-discovery keeps the same page but no generation provider.
test('未配置生成模型时生成入口关闭，仍可手工新建、校验并保存草稿',async()=>{
 const plain=await startFixture(0);
 const user='ui_discovery_manual';
 const {client:plainApi,token,inventory}=await seedKitchen(plain.url,user,PASSWORD);
 const context=await desktopContext(browser);
 try{
  const page=await openPage(context,plain.url);
  await signIn(page,user,PASSWORD);
  const loaded=page.waitForResponse(r=>r.url().endsWith('/recipe-discoveries/capabilities')&&r.request().method()==='GET');
  await useTab(page,'发现菜谱');
  await loaded;
  assert.match(await page.evaluate(()=>document.body.innerText),/当前未配置可用的生成模型/);
  assert.equal(await page.getByRole('button',{name:'生成候选',exact:true}).isDisabled(),true);

  await page.getByRole('button',{name:'手工新建草稿',exact:true}).click();
  await waitText(page,/已创建一份空白手工草稿/);
  const draft=page.locator('section.draft-editor').first();
  await draft.getByLabel('菜谱名称',{exact:true}).fill('手工测试面');
  await draft.getByLabel('人数',{exact:true}).fill('1');
  await draft.getByLabel('用时（分钟）',{exact:true}).fill('15');
  await draft.getByLabel('厨具（逗号分隔）',{exact:true}).fill('煮锅');
  await draft.getByLabel('做法（每行一步）',{exact:true}).fill('水开后下挂面煮三分钟');
  await draft.getByRole('button',{name:'增加食材行',exact:true}).click();
  const line=draft.locator('.draft-line').first();
  await line.getByLabel('食材',{exact:true}).fill('挂面');
  await line.getByLabel('数量',{exact:true}).fill('120');
  await line.getByLabel('可选配料',{exact:true}).check();
  await checkDraft(draft,['required_ingredient_missing']);
  await waitText(page,/至少要有一种不是可选的食材/);
  assert.equal(await acceptOf(page,'手工测试面').isDisabled(),true);
  await line.getByLabel('可选配料',{exact:true}).uncheck();
  await checkDraft(draft,[]);
  assert.equal(await acceptOf(page,'手工测试面').isDisabled(),true,'校验通过但仍需先保存');
  await draft.getByRole('button',{name:'保存草稿',exact:true}).click();
  await waitText(page,/草稿已保存，库存未改变/);
  assert.ok(await waitEnabled(acceptOf(page,'手工测试面')));

  const saved=(await plainApi.call(token,'/recipe-drafts?status=draft')).data;
  assert.equal(saved.length,1);
  assert.deepEqual([saved[0].source_type,saved[0].payload.name,saved[0].validation_errors],['manual','手工测试面',[]]);
  assert.deepEqual((await plainApi.call(token,'/inventory')).data,inventory.data,'手工草稿同样不改变库存');
  assert.deepEqual(page.problems,[]);
 }finally{
  await context.close();
  await plain.stop();
 }
});

// Tags are a person's choice on a draft: what is picked here has to reach the recipe, and a
// value outside the vocabulary must stay on screen long enough to be removed.
test('草稿上选的烹饪方式随确认进入菜谱库，无法识别的写法留在原处可移除',async()=>{
 const user='ui_discovery_tags';
 const {client,token}=await seedKitchen(server.url,user,PASSWORD);
 const context=await desktopContext(browser);
 try{
  const page=await openPage(context,server.url);
  await signIn(page,user,PASSWORD);
  const newDraft=async name=>{
   await openDiscovery(page);
   const before=await page.locator('section.draft-editor').count();
   await page.getByRole('button',{name:'手工新建草稿',exact:true}).click();
   await waitText(page,/已创建一份空白手工草稿/);
   await waitForDrafts(page,before+1);
   // The list holds only the new draft here, so the position is stable while the heading
   // follows whatever name is being typed.
   const draft=page.locator('section.draft-editor').first();
   assert.equal(await draft.getByLabel('菜谱名称',{exact:true}).inputValue(),'','新建的应当是一份空白草稿');
   await draft.getByLabel('菜谱名称',{exact:true}).fill(name);
   await draft.getByLabel('人数',{exact:true}).fill('1');
   await draft.getByLabel('用时（分钟）',{exact:true}).fill('15');
   await draft.getByLabel('厨具（逗号分隔）',{exact:true}).fill('煮锅');
   await draft.getByLabel('做法（每行一步）',{exact:true}).fill('水开下面煮三分钟');
   await draft.getByRole('button',{name:'增加食材行',exact:true}).click();
   const line=draft.locator('.draft-line').first();
   await line.getByLabel('食材',{exact:true}).fill('挂面');
   await line.getByLabel('数量',{exact:true}).fill('120');
   return draft;
  };

  const picked=await newDraft('标签测试面');
  await picked.getByLabel('煮',{exact:true}).check();
  await picked.getByLabel('炖',{exact:true}).check();
  assert.equal(await picked.getByLabel('凉拌',{exact:true}).isChecked(),false);
  await checkDraft(picked,[]);
  await picked.getByRole('button',{name:'保存草稿',exact:true}).click();
  await waitText(page,/草稿已保存，库存未改变/);
  await acceptOf(page,'标签测试面').click();
  await waitText(page,/「标签测试面」已加入菜谱库/);
  const accepted=(await api.call(token,'/recipes')).data.find(r=>r.name==='标签测试面');
  assert.deepEqual(accepted.cooking_methods,['boil','stew'],'页面写的是中文，入库的是枚举值');
  await useTab(page,'我的菜谱');
  assert.deepEqual(await page.locator('.recipe').filter({hasText:'标签测试面'})
   .locator('.methods .tag').allInnerTexts(),['煮','炖'],'新菜谱卡片直接显示中文标签');

  const messy=await newDraft('待清理标签面');
  await checkDraft(messy,[]);
  await messy.getByRole('button',{name:'保存草稿',exact:true}).click();
  await waitText(page,/草稿已保存，库存未改变/);
  const stored=(await client.call(token,'/recipe-drafts?status=draft')).data.find(d=>d.payload.name==='待清理标签面');
  const polluted=await client.call(token,`/recipe-drafts/${stored.id}`,'PUT',
   {expected_version:stored.version,payload:{...stored.payload,cooking_methods:['deep_fry']}},
   'e2e-stray-tag-0001');
  assert.equal(polluted.status,200,'一份带着陌生写法的草稿要能存下来，而不是被悄悄丢掉');
  assert.deepEqual(polluted.data.validation_errors.map(i=>[i.field,i.code]),
   [['cooking_methods','cooking_method_invalid']]);
  // An editor keeps what was typed into it, so a value that arrived from outside the page
  // shows up when the panel mounts again — the same reload a person would do.
  await useTab(page,'我的菜谱');
  await openDiscovery(page);
  const stray=editor(page,'待清理标签面').locator('.stray');
  assert.match(await stray.innerText(),/deep_fry/,'无法识别的写法必须显示出来才能改');
  assert.equal(await acceptOf(page,'待清理标签面').isDisabled(),true,'带着无法识别标签的草稿不能入库');
  await stray.getByRole('button',{name:'移除',exact:true}).click();
  await checkDraft(editor(page,'待清理标签面'),[]);
  await editor(page,'待清理标签面').getByRole('button',{name:'保存草稿',exact:true}).click();
  await waitText(page,/草稿已保存，库存未改变/);
  assert.ok(await waitEnabled(acceptOf(page,'待清理标签面')));
  const clean=(await client.call(token,'/recipe-drafts?status=draft')).data
   .find(d=>d.payload.name==='待清理标签面');
  assert.deepEqual(clean.payload.cooking_methods,[],'移除后保存的应是空标签');
  assert.equal(await editor(page,'待清理标签面').locator('.stray').count(),0);
  assert.deepEqual(page.problems,[]);
 }finally{await context.close();}
});
