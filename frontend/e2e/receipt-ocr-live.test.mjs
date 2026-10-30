import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,useTab,waitText} from './support.mjs';

for(const scenario of ['ocr_only','conflict']){
 test('真实CPU OCR页面：'+scenario,{skip:!process.env.RECEIPT_OCR_LIVE_URL},async()=>{
  const url=process.env.RECEIPT_OCR_LIVE_URL;
  assert.equal(new URL(url).hostname,'127.0.0.1');assert.equal(new URL(url).port,'18110');
  const privateDir=process.env.RECEIPT_OCR_PRIVATE_DIR;assert.ok(privateDir);
  const api=makeApi(url),browser=await launchBrowser(),context=await desktopContext(browser);
  const username='m45_ui_'+scenario+'_'+Date.now(),password=crypto.randomUUID();
  try{
   await api.call(null,'/auth/register','POST',{username,password});const token=await api.signIn(username,password);
   for(const [name,unit] of [['牛奶','ml'],['苹果','g']])await api.call(token,'/ingredients','POST',{name,unit});
   const page=await openPage(context,url);await signIn(page,username,password);await useTab(page,'小票录入');
   let image=await readFile(path.join(process.env.RECEIPT_OCR_DATASET,'clear.png'));
   if(scenario==='conflict')image=Buffer.concat([image,Buffer.from('\nM45:conflict')]);
   await page.getByLabel('小票图片').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:image});
   await page.getByRole('button',{name:'上传小票',exact:true}).click();await waitText(page,/小票已私有保存/);
   await page.getByLabel('识别方式').selectOption(scenario==='ocr_only'?'ocr_only':'hybrid');
   await page.getByRole('button',{name:'自动识别小票',exact:true}).click();
   const accepting=page.waitForResponse(r=>r.url().endsWith('/parse')&&r.request().method()==='POST');
   await page.getByRole('button',{name:scenario==='ocr_only'?'开始本地识别':'发送图片并识别',exact:true}).click();
   const accepted=await accepting;assert.equal(accepted.status(),202);const receipt=await accepted.json();
   await waitText(page,/识别结果待人工核对/);
   assert.deepEqual((await api.call(token,'/inventory')).data,[]);
   assert.equal(await page.getByLabel('仍需核对').first().isChecked(),true);
   await page.getByText('文字识别与核对信息',{exact:true}).click();
   await waitText(page,/置信度/);
   if(scenario==='conflict'){
    await waitText(page,/识别结果存在 .* 处冲突/);
    assert.equal(await page.getByLabel('数量（未知留空）').first().inputValue(),'');
    assert.equal(await page.getByRole('button',{name:'核对小票入库',exact:true}).isDisabled(),true);
   }else{
    assert.equal(await page.getByLabel('数量（未知留空）').first().inputValue(),'500');
    assert.equal(await page.getByLabel('数量（未知留空）').nth(1).inputValue(),'750');
    await page.getByLabel('仍需核对').first().uncheck();await page.getByLabel('仍需核对').nth(1).uncheck();
    await page.getByRole('button',{name:'保存小票草稿',exact:true}).click();await waitText(page,/小票草稿已保存/);
    assert.deepEqual((await api.call(token,'/inventory')).data,[]);
    await page.getByRole('button',{name:'核对小票入库',exact:true}).click();
    await page.getByRole('button',{name:'确认小票并整单入库',exact:true}).click();await waitText(page,/小票已整单入库/);
    assert.equal((await api.call(token,'/inventory')).data.length,2);
    assert.equal((await api.call(token,'/inventory/events')).data.length,2);
   }
   assert.deepEqual(page.problems,[]);await mkdir(privateDir,{recursive:true});
   await page.screenshot({path:path.join(privateDir,'m45-ui-'+scenario+'.png'),fullPage:true});
   await writeFile(path.join(privateDir,'m45-ui-'+scenario+'.json'),JSON.stringify({scenario,passed:true,
    receipt_id:receipt.id,task_id:receipt.parse_task_id,real_model_calls:0,human_confirmation_required:true}));
  }finally{await context.close();await browser.close();}
 });
}
