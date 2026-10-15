import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,useTab,waitText} from './support.mjs';

test('真实RabbitMQ/Celery：轮询保留未保存输入，重登录恢复草稿并人工确认一次',
 {skip:!process.env.RECEIPT_ASYNC_LIVE_URL},async()=>{
 const url=process.env.RECEIPT_ASYNC_LIVE_URL;
 assert.equal(new URL(url).hostname,'127.0.0.1');
 assert.equal(new URL(url).port,'18110');
 const privateDir=process.env.RECEIPT_ASYNC_PRIVATE_DIR;
 assert.ok(privateDir,'private evidence directory required');
 const api=makeApi(url),browser=await launchBrowser(),context=await desktopContext(browser);
 const username='m3_ui_'+Date.now(),password=crypto.randomUUID();
 try{
  await api.call(null,'/auth/register','POST',{username,password});
  const token=await api.signIn(username,password);
  const ingredient=(await api.call(token,'/ingredients','POST',{name:'鸡蛋',unit:'piece'})).data;
  await api.call(token,'/ingredients/'+ingredient.id+'/aliases','POST',{alias:'鲜鸡蛋'});
  const page=await openPage(context,url);await signIn(page,username,password);await useTab(page,'小票录入');
  const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC','base64');
  await page.getByLabel('小票图片').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:image});
  await page.getByRole('button',{name:'上传小票',exact:true}).click();await waitText(page,/小票已私有保存/);
  await page.getByRole('button',{name:'自动识别小票',exact:true}).click();
  const acceptedResponse=page.waitForResponse(r=>r.url().endsWith('/parse')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'发送图片并识别',exact:true}).click();
  const response=await acceptedResponse;assert.equal(response.status(),202);const accepted=await response.json();
  await page.getByRole('button',{name:'添加小票行',exact:true}).click();
  await page.getByLabel('小票名称').first().fill('人工未保存');
  await waitText(page,/识别结果待人工核对/);
  assert.equal(await page.getByLabel('小票名称').first().inputValue(),'人工未保存');
  assert.deepEqual((await api.call(token,'/inventory')).data,[]);
  await page.getByRole('button',{name:'刷新小票记录',exact:true}).click();
  assert.equal(await page.getByLabel('小票名称').first().inputValue(),'人工未保存');
  await page.reload();await signIn(page,username,password);await useTab(page,'小票录入');
  await waitText(page,/识别结果待人工核对/);
  assert.equal(await page.getByLabel('对应食材').first().inputValue(),ingredient.id);
  assert.equal(await page.getByLabel('数量（未知留空）').first().inputValue(),'6');
  assert.equal(await page.getByLabel('数量（未知留空）').nth(1).inputValue(),'');
  assert.equal(await page.getByLabel('仍需核对').first().isChecked(),true);
  assert.equal(await page.getByRole('button',{name:'核对小票入库',exact:true}).isDisabled(),true);
  await page.getByLabel('排除非食材或不入库项').nth(1).check();
  await page.getByLabel('仍需核对').first().uncheck();
  await page.getByRole('button',{name:'保存小票草稿',exact:true}).click();await waitText(page,/小票草稿已保存/);
  assert.deepEqual((await api.call(token,'/inventory')).data,[]);
  await page.getByRole('button',{name:'核对小票入库',exact:true}).click();
  await page.getByRole('button',{name:'确认小票并整单入库',exact:true}).click();await waitText(page,/小票已整单入库/);
  const inventory=(await api.call(token,'/inventory')).data,events=(await api.call(token,'/inventory/events')).data;
  assert.equal(inventory.length,1);assert.equal(inventory[0].quantity,'6.000');assert.equal(events.length,1);
  assert.deepEqual(page.problems,[]);
  await mkdir(privateDir,{recursive:true});
  await page.screenshot({path:path.join(privateDir,'m3-ui-normal.png'),fullPage:true});
  await writeFile(path.join(privateDir,'m3-ui-result.json'),JSON.stringify({passed:true,receipt_id:accepted.id,
   task_id:accepted.parse_task_id,accept_status:202,dirty_input_preserved:true,relogin_restored:true,
   inventory_count:1,event_count:1,real_model_calls:0},null,2));
 }finally{await context.close();await browser.close();}
});
