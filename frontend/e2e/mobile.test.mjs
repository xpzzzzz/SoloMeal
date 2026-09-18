import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {
 testDate,addKind,launchBrowser,makeApi,mobileContext,openPage,shot,signIn,signOut,signUp,startFixture,
 horizontalOverflow,openPreferences,useTab,visibleButtons,waitText,
} from './support.mjs';

let server,browser,api;
const PASSWORD='mobile-fixture-1';
const TABS=['一人食助手','食材库存','我的菜谱','报价与采购','小票录入','用餐记录','厨房偏好'];

before(async()=>{
 server=await startFixture(0);
 browser=await launchBrowser();
 api=makeApi(server.url);
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

// No fill() in these paths: the field is tapped, typed key by key, and submitted with Enter.
async function keyboardSignUp(page,username,password){
 await page.getByRole('button',{name:'第一次使用？创建账号'}).tap();
 await page.locator('input[name="username"]').tap();
 await page.keyboard.type(username,{delay:15});
 await page.keyboard.press('Tab');
 await page.keyboard.type(password,{delay:15});
 await page.keyboard.press('Enter');
 await page.waitForSelector('nav[aria-label="主导航"]');
}

async function savePreferences(page){
 const response=page.waitForResponse(r=>r.url().endsWith('/api/v1/me/preferences')&&r.request().method()==='PUT');
 await page.getByRole('button',{name:'保存偏好'}).tap();
 const saved=await response;
 assert.equal(saved.status(),200);
 return saved.json();
}

async function checkLayout(page,tab){
 assert.equal(await horizontalOverflow(page),0,`${tab} 不应出现横向溢出`);
 const buttons=await visibleButtons(page);
 assert.ok(buttons.length,`${tab} 应当有可点按的按钮`);
 const small=buttons.filter(b=>b.height<40);
 assert.deepEqual(small,[],`${tab} 上有过小的可点按按钮：${JSON.stringify(small)}`);
}

test('手机纯键盘可以建号、录库存、保存偏好与包装报价，重登后偏好仍在',async()=>{
 const context=await mobileContext(browser);
 const page=await openPage(context,server.url);
 assert.equal(await page.evaluate(()=>matchMedia('(pointer: coarse)').matches),true,'夹具应报告为触摸设备');
 await keyboardSignUp(page,'ui_mob_keys_0908',PASSWORD);
 assert.deepEqual((await page.getByRole('navigation',{name:'主导航'}).getByRole('button').allInnerTexts()),TABS);
 assert.ok(await page.getByRole('button',{name:'退出登录'}).isVisible(),'窄屏也必须能退出登录');

 await useTab(page,'食材库存');
 await page.locator('input[name="name"]').tap();
 await page.keyboard.type('番茄',{delay:15});
 await page.locator('select[name="unit"]').selectOption('piece');
 await page.getByRole('button',{name:'添加种类'}).tap();
 await page.locator('select[name="ingredient"] option',{hasText:'番茄（个）'}).first().waitFor({state:'attached'});
 await page.locator('select[name="ingredient"]').selectOption({label:'番茄（个）'});
 await page.locator('input[name="quantity"]').tap();
 await page.keyboard.type('3',{delay:15});
 await page.locator('input[name="expires"]').fill(testDate(12));
 await page.locator('select[name="location"]').selectOption('冷藏');
 await page.keyboard.press('Enter');
 await page.locator('table tbody tr',{hasText:'番茄'}).first().waitFor();
 const table=await page.locator('table').innerText();
 assert.match(table,/番茄/);
 assert.ok(table.includes(testDate(12)));
 assert.match(table,/3 个/);

 await openPreferences(page);
 await page.getByLabel('现有厨具（逗号分隔）').tap();
 await page.keyboard.type('煮锅，炒锅',{delay:15});
 const savedPreferences=await savePreferences(page);
 assert.deepEqual(savedPreferences.equipment,['煮锅','炒锅'],'中文逗号应分成两件厨具');

 await useTab(page,'报价与采购');
 const quotes=page.locator('section.panel').filter({hasText:'包装报价'});
 await quotes.locator('select').first().selectOption({label:'番茄（个）'});
 await quotes.locator('input[name="quantity"]').tap();
 await page.keyboard.type('6',{delay:15});
 await quotes.locator('input[name="price"]').fill('8.50');
 await quotes.locator('input[name="source"]').fill('楼下超市');
 await quotes.locator('input[name="date"]').fill(testDate());
 await page.getByRole('button',{name:'保存报价'}).tap();
 await waitText(page,/报价已保存/);
 assert.match(await page.evaluate(()=>document.body.innerText),/番茄 · 6 个 \/ 包 · ¥8\.50 · 楼下超市/);
 await shot(page,'mobile-quote.png');

 for(const tab of TABS){
  await useTab(page,tab);
  await checkLayout(page,tab);
 }

 // The token lives in memory only, so signing out and back in is how this build reloads.
 await signOut(page);
 await page.reload({waitUntil:'domcontentloaded'});
 await signIn(page,'ui_mob_keys_0908',PASSWORD);
 await useTab(page,'厨房偏好');
 // Preferences loads asynchronously on mount, so wait for the round trip rather than reading an empty field by accident.
 await page.waitForFunction(()=>document.querySelector('.preferences input')?.value!=='');
 assert.equal(await page.getByLabel('现有厨具（逗号分隔）').inputValue(),'煮锅,炒锅','偏好应来自服务端');
 await useTab(page,'食材库存');
 await waitText(page,/番茄/);
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await context.close();
});

test('手机上可以从报价走到采购入库、做饭与撤销',async()=>{
 const context=await mobileContext(browser);
 const page=await openPage(context,server.url);
 await signUp(page,'ui_mob_shop_0908',PASSWORD);
 await addKind(page,{name:'鸡蛋'});
 await openPreferences(page);
 await page.getByLabel('现有厨具（逗号分隔）').fill('煮锅');
 await savePreferences(page);

 await useTab(page,'报价与采购');
 const quotes=page.locator('section.panel').filter({hasText:'包装报价'});
 await quotes.locator('select').first().selectOption({label:'鸡蛋（个）'});
 await quotes.locator('input[name="quantity"]').fill('6');
 await quotes.locator('input[name="price"]').fill('5.50');
 await quotes.locator('input[name="source"]').fill('楼下超市');
 await quotes.locator('input[name="date"]').fill(testDate());
 await page.getByRole('button',{name:'保存报价'}).tap();
 await waitText(page,/报价已保存/);

 await useTab(page,'我的菜谱');
 const recipe=page.locator('details.panel').filter({hasText:'添加自己的菜谱'});
 await recipe.locator('summary').tap();
 await recipe.locator('input[name="name"]').fill('测试煮鸡蛋');
 await recipe.locator('input[name="servings"]').fill('1');
 await recipe.locator('input[name="minutes"]').fill('10');
 await recipe.locator('input[name="equipment"]').fill('煮锅');
 await recipe.locator('input[name="source"]').fill('手机录入');
 await recipe.locator('textarea[name="steps"]').fill('烧开后煮八分钟');
 const line=recipe.locator('div.row').filter({hasText:'可选配料'}).first();
 await line.locator('select').selectOption({label:'鸡蛋（个）'});
 await line.locator('input[type="number"]').fill('2');
 await page.getByRole('button',{name:'保存菜谱'}).tap();
 await waitText(page,/测试煮鸡蛋/);

 await page.getByRole('button',{name:'生成本餐推荐'}).tap();
 await waitText(page,/缺 鸡蛋/);
 await page.getByRole('button',{name:'保存这餐方案'}).first().tap();
 await waitText(page,/已保存方案/);
 await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
 await page.getByRole('button',{name:'准备采购'}).tap();
 await waitText(page,/采购版本/);
 const editor=page.locator('section.panel').filter({hasText:'采购版本'});
 assert.equal(await editor.locator('input[type="number"]').first().inputValue(),'6.000','整包报价应给出 6 个的建议量');
 await editor.locator('input[type="number"]').first().tap();
 await page.keyboard.press('Control+A');
 await page.keyboard.type('8');
 assert.equal(await editor.locator('input[type="number"]').first().inputValue(),'8','整数个可以用触摸键盘修改');
 await editor.locator('input[type="number"]').nth(1).fill('7.00');
 await page.getByRole('button',{name:'保存采购修改'}).tap();
 await waitText(page,/草稿已保存/);
 await shot(page,'mobile-purchase-draft.png');
 await page.getByRole('button',{name:'核对并入库'}).tap();
 await page.getByRole('button',{name:'确认已购买并整单入库'}).tap();
 await waitText(page,/整单已入库/);
 const token=await api.signIn('ui_mob_shop_0908',PASSWORD);
 assert.deepEqual((await api.call(token,'/inventory')).data.map(b=>[b.name,Number(b.quantity)]),[['鸡蛋',8]]);

 await useTab(page,'我的菜谱');
 await page.getByRole('button',{name:'按当前库存更新'}).tap();
 await waitText(page,/方案已按最新库存更新/);
 await page.getByRole('button',{name:'确认做完'}).first().tap();
 await waitText(page,/将记录 1 人份/);
 await page.locator('.modal').getByRole('button',{name:'确认做完'}).tap();
 await waitText(page,/已记录，库存同步更新/);
 assert.equal(Number((await api.call(token,'/inventory')).data.find(b=>b.name==='鸡蛋').quantity),6,'做饭应扣掉两个鸡蛋');

 await useTab(page,'用餐记录');
 await waitText(page,/测试煮鸡蛋/);
 await page.getByRole('button',{name:'撤销并恢复食材'}).tap();
 await waitText(page,/已撤销/);
 assert.equal(Number((await api.call(token,'/inventory')).data.find(b=>b.name==='鸡蛋').quantity),8,'撤销应恢复数量');
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await shot(page,'mobile-final.png');
 await context.close();
});
