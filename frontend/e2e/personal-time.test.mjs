import test from 'node:test';
import assert from 'node:assert/strict';
import {
 addKindAndBatch,desktopContext,launchBrowser,makeApi,openPage,openPreferences,signUp,startFixture,useTab,waitText,
} from './support.mjs';

// The whole point of the estimate is what the card says out loud, so every step here is read back
// from the recommendation card. The label is matched exactly: a longer claim contains the shorter
// one, so a substring test would pass on the card that was already on screen.
test('个人用时估计改变候选与卡片文案，关闭开关与撤销同样反映在页面上',async()=>{
 const server=await startFixture(0);
 let browser;
 try{
  browser=await launchBrowser();
  const context=await desktopContext(browser);
  const page=await openPage(context,server.url);
  const api=makeApi(server.url);
  await signUp(page,'ui_personal_time_0922','personal-time-1');
  await addKindAndBatch(page,{name:'鸡蛋',quantity:'300',location:'冷藏'});

  await useTab(page,'我的菜谱');
  const recipe=page.locator('details.panel').filter({hasText:'添加自己的菜谱'});
  await recipe.locator('summary').click();
  await recipe.getByLabel('菜谱名称').fill('计时煮蛋');
  await recipe.getByLabel('人数').fill('1');
  await recipe.getByLabel('用时（分钟）').fill('20');
  await recipe.getByLabel('厨具（逗号分隔）').fill('煮锅');
  await recipe.getByLabel('做法（每行一步）').fill('水开后下锅煮三分钟');
  await recipe.locator('select').selectOption({label:'鸡蛋（个）'});
  await recipe.getByLabel('数量',{exact:true}).fill('2');
  await recipe.getByRole('button',{name:'保存菜谱'}).click();
  await page.locator('.recipe').getByRole('heading',{name:'计时煮蛋',exact:true}).waitFor();

  const recommend=async()=>{
   await useTab(page,'我的菜谱');
   const landed=page.waitForResponse(r=>r.url().endsWith('/api/v1/recommendations')&&r.request().method()==='POST');
   await page.getByRole('button',{name:'生成本餐推荐'}).click();
   await landed;
  };
  const expectEstimate=async label=>{
   await page.waitForFunction(expected=>{
    const card=document.querySelector('.time-estimate');
    return card!==null&&card.innerText.trim()===expected;
   },label,{timeout:20_000});
  };

  await openPreferences(page);
  await page.getByLabel('现有厨具（逗号分隔）').fill('煮锅');
  await page.getByLabel('最多用时（分钟）').fill('24');
  const savedPreferences=page.waitForResponse(r=>r.url().endsWith('/me/preferences')&&r.request().method()==='PUT');
  await page.getByRole('button',{name:'保存偏好'}).click();
  assert.equal((await savedPreferences).status(),200);
  await recommend();
  await expectEstimate('标准20分钟，暂无个人记录');

  // One cooked meal with a typed-in duration is the whole sample set.
  await page.locator('.recipe').getByRole('button',{name:'记录做完这道菜'}).click();
  await page.locator('.modal').getByRole('button',{name:'确认做完',exact:true}).click();
  await useTab(page,'用餐记录');
  await page.getByRole('button',{name:'填写用时'}).click();
  await page.getByLabel('实际耗时（分钟，留空清除）').fill('40');
  await page.getByRole('button',{name:'保存用时'}).click();
  await waitText(page,/用时已保存，库存未改变/);

  // 20 standard minutes now reads as 25 for this kitchen, so the 24-minute limit drops the card.
  await recommend();
  await waitText(page,/没有符合条件的菜谱，请核对厨具、用时与忌口设置/);

  await openPreferences(page);
  await page.getByLabel('最多用时（分钟）').fill('30');
  await page.getByRole('button',{name:'保存偏好'}).click();
  await recommend();
  await expectEstimate('标准20分钟 / 你的预计25分钟，基于1次记录');

  // Back at the same limit, only the switch brings the candidate back, on standard time.
  await openPreferences(page);
  await page.getByLabel('最多用时（分钟）').fill('24');
  await page.getByLabel('按我做过的实际用时估计').uncheck();
  await page.getByRole('button',{name:'保存偏好'}).click();
  await recommend();
  await expectEstimate('标准20分钟，已关闭个人用时估计（另有1次记录未使用）');

  // Undoing leaves no samples, but the switch is still off: the card keeps naming the switch as the
  // reason, rather than falling back to the "nothing recorded yet" wording a fresh kitchen shows.
  await useTab(page,'用餐记录');
  const undone=page.waitForResponse(r=>r.url().includes('/cooking/')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'撤销并恢复食材'}).click();
  assert.equal((await undone).status(),200);
  await waitText(page,/已撤销/);
  await recommend();
  await expectEstimate('标准20分钟，已关闭个人用时估计');

  const token=await api.signIn('ui_personal_time_0922','personal-time-1');
  assert.equal((await api.call(token,'/cooking')).data[0].status,'retracted');
  assert.equal(Number((await api.call(token,'/inventory')).data[0].quantity),300,'推荐与撤销之后库存回到原处');
  await context.close();
 }finally{
  await browser?.close();
  await server?.stop();
 }
});
