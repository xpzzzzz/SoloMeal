// Same race class as preferences-race: the quotes panel's mount GET lands late, the saved
// quote flips the form key, and React remounts the form and discards what was typed.
import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,startFixture,testDate,useTab,waitText} from './support.mjs';

let server,browser,api;
const PASSWORD='quote-race-1';

before(async()=>{
 server=await startFixture(0);
 browser=await launchBrowser();
 api=makeApi(server.url);
});
after(async()=>{
 await browser?.close();
 await server?.stop();
});

test('挂载 GET 迟到不得重挂载清空已输入的报价',async()=>{
 const user='ui_quote_race_0918';
 const token=await api.signIn(user,PASSWORD);
 const ingredient=(await api.call(token,'/ingredients','POST',{name:'鸡蛋',unit:'piece'})).data;
 await api.call(token,'/quotes','POST',{ingredient_id:ingredient.id,package_quantity:'6',
  package_price:'5.50',source:'楼下超市',observed_on:testDate(),currency:'CNY',expected_version:0});

 const context=await desktopContext(browser);
 const page=await openPage(context,server.url);
 // Hold the panel's mount GET in flight until the caller has typed; the trailing * is needed
 // because the list request carries ?limit=&offset=.
 let release;
 const gate=new Promise(r=>{release=r;});
 await page.route('**/api/v1/quotes*',async route=>{
  if(route.request().method()!=='GET'){await route.continue();return;}
  const response=await route.fetch();
  await gate;
  await new Promise(r=>setTimeout(r,1_500));
  await route.fulfill({status:response.status(),contentType:'application/json',body:await response.text()});
 });
 await signIn(page,user,PASSWORD);
 await useTab(page,'报价与采购');
 const landed=page.waitForResponse(r=>r.url().includes('/api/v1/quotes')&&r.request().method()==='GET',{timeout:30_000});
 await page.locator('select').first().selectOption(ingredient.id);
 await page.getByLabel('每包装数量（个）').fill('8');
 await page.getByLabel('每包装价格（元）').fill('7.20');
 release();
 await landed;
 assert.equal(await page.getByLabel('每包装数量（个）').inputValue(),'8','挂载响应落地后不得清空已输入数量');
 assert.equal(await page.getByLabel('每包装价格（元）').inputValue(),'7.20','已输入价格同样必须保留');
 await page.getByRole('button',{name:'保存报价'}).click();
 await waitText(page,/报价已保存/);
 const stored=(await api.call(token,'/quotes')).data.find(q=>q.ingredient_id===ingredient.id);
 assert.equal(Number(stored.package_quantity),8,'保存的必须是用户输入的报价');
 assert.equal(Number(stored.package_price),7.2);
 assert.equal(page.problems.length,0,`页面不应出现未捕获异常：${page.problems.join('; ')}`);
 await context.close();
});
