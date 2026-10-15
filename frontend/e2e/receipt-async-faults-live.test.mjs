import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,useTab,waitText} from './support.mjs';

test('真实异步小票202响应丢失后，同操作键重试并在重登录后恢复',
 {skip:!process.env.RECEIPT_ASYNC_FAULTS_LIVE_URL},async()=>{
 const url=process.env.RECEIPT_ASYNC_FAULTS_LIVE_URL;
 assert.equal(url,'http://127.0.0.1:18110');
 const output=process.env.RECEIPT_ASYNC_PRIVATE_DIR;assert.ok(output);
 const api=makeApi(url),browser=await launchBrowser(),context=await desktopContext(browser);
 const username='m4_loss_'+Date.now(),password=crypto.randomUUID();
 try{
  await api.call(null,'/auth/register','POST',{username,password});
  const token=await api.signIn(username,password),page=await openPage(context,url);
  await signIn(page,username,password);await useTab(page,'小票录入');
  const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC','base64');
  await page.getByLabel('小票图片').setInputFiles({name:'fault.png',mimeType:'image/png',buffer:image});
  await page.getByRole('button',{name:'上传小票',exact:true}).click();await waitText(page,/小票已私有保存/);
  const row=(await api.call(token,'/receipts')).data[0],parseUrl=url+'/api/v1/receipts/'+row.id+'/parse';
  const keys=[];let firstTask;
  await page.route(parseUrl,async route=>{
   keys.push(route.request().headers()['idempotency-key']);
   const response=await route.fetch();assert.equal(response.status(),202);firstTask=(await response.json()).parse_task_id;
   await route.abort('failed');
  });
  await page.getByRole('button',{name:'自动识别小票',exact:true}).click();
  await page.getByRole('button',{name:'发送图片并识别',exact:true}).click();await waitText(page,/无法连接服务器/);
  await page.unroute(parseUrl);
  await page.route(parseUrl,async route=>{keys.push(route.request().headers()['idempotency-key']);await route.continue();});
  await page.getByRole('button',{name:'自动识别小票',exact:true}).click();
  await page.getByRole('button',{name:'发送图片并识别',exact:true}).click();
  await waitText(page,/识别结果待人工核对/);
  assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
  const parsed=(await api.call(token,'/receipts')).data[0];assert.equal(parsed.parse_task_id,firstTask);assert.equal(parsed.version,2);
  assert.deepEqual((await api.call(token,'/inventory')).data,[]);
  await page.reload();await signIn(page,username,password);await useTab(page,'小票录入');await waitText(page,/识别结果待人工核对/);
  assert.equal(await page.getByRole('button',{name:'核对小票入库',exact:true}).isDisabled(),true);
  assert.deepEqual(page.problems,[]);
  await mkdir(output,{recursive:true});await page.screenshot({path:path.join(output,'m4-response-loss.png'),fullPage:true});
  await writeFile(path.join(output,'m4-response-loss.json'),JSON.stringify({passed:true,receipt_id:row.id,task_id:firstTask,
   server_accepted_before_abort:true,original_key_reused:true,receipt_version:2,relogin_restored:true,
   inventory_count:0,real_model_calls:0},null,2));
 }finally{await context.close();await browser.close();}
});
