import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,startFixture,useTab,waitText} from './support.mjs';
let server,browser,api;
before(async()=>{server=await startFixture(0,{receiptParser:true});browser=await launchBrowser();api=makeApi(server.url);});
after(async()=>{await browser?.close();await server?.stop();});
test('脚本识别需先同意发送，匹配后仍须人工核对且图片文字不执行',async()=>{
 const user='ui_receipt_recognition',password='vision-fixture-1';
 await api.call(null,'/auth/register','POST',{username:user,password});
 const token=await api.signIn(user,password);
 const ingredient=(await api.call(token,'/ingredients','POST',{name:'鸡蛋',unit:'piece'})).data;
 await api.call(token,'/ingredients/'+ingredient.id+'/aliases','POST',{alias:'鲜鸡蛋'});
 const context=await desktopContext(browser);
 try{
  const page=await openPage(context,server.url);
  await signIn(page,user,password);await useTab(page,'小票录入');
  const fs=await import('node:fs/promises');
  const image=await fs.readFile(new URL('./fixtures/receipt.png',import.meta.url));
  await page.getByLabel('小票图片').setInputFiles({name:'vision.png',mimeType:'image/png',buffer:image});
  await page.getByRole('button',{name:'上传小票',exact:true}).click();await waitText(page,/小票已私有保存/);
  await page.getByRole('button',{name:'自动识别小票',exact:true}).click();
  assert.equal((await api.call(token,'/receipts')).data[0].parse_status,'manual');
  await page.getByRole('button',{name:'发送图片并识别',exact:true}).click();
  await waitText(page,/识别结果待人工核对/);
  assert.equal(await page.getByLabel('对应食材').first().inputValue(),ingredient.id);
  assert.equal(await page.getByLabel('仍需核对').first().isChecked(),true);
  assert.equal(await page.getByRole('button',{name:'核对小票入库',exact:true}).isDisabled(),true);
  assert.deepEqual((await api.call(token,'/inventory')).data,[]);
  await page.getByLabel('排除非食材或不入库项').nth(1).check();
  await page.getByLabel('仍需核对').first().uncheck();
  await page.getByRole('button',{name:'保存小票草稿',exact:true}).click();
  await waitText(page,/小票草稿已保存/);
  await page.getByRole('button',{name:'核对小票入库',exact:true}).click();
  await page.getByRole('button',{name:'确认小票并整单入库',exact:true}).click();
  await waitText(page,/小票已整单入库/);
  assert.equal((await api.call(token,'/inventory')).data.length,1);
  assert.deepEqual(page.problems,[]);
 }finally{await context.close();}
});
