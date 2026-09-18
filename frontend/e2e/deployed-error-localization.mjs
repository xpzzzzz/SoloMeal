// Explicitly targets a real loopback deployment; not part of the fixture CI suite.
// Checks three layers of the 409 localization in one run: the shipped bundle carries the
// code table, the API still answers a terminal-run advance with the English contract text
// (the probe selects only known terminal runs before the POST, so it can never reach the
// model), and a model-disabled failed run renders in Chinese on the page.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {launchBrowser,desktopContext,openPage,signIn,useTab,waitText,bodyText} from './support.mjs';

const [url,evidence,output]=process.argv.slice(2);
assert.ok(url&&evidence&&output,'Usage: node e2e/deployed-error-localization.mjs URL PRIVATE_EVIDENCE_DIR OUTPUT_PREFIX');
assert.equal(new URL(url).hostname,'127.0.0.1','targets a loopback deployment only');
const credentials=JSON.parse(await readFile(path.join(evidence,'credentials.json'),'utf8'));
const browser=await launchBrowser();
try{
 const context=await desktopContext(browser);
 const page=await openPage(context,url);

 const asset=await page.evaluate(async()=>{
  const src=document.querySelector('script[src]')?.src;
  return src?{src,body:await (await fetch(src)).text()}:null;
 });
 assert.ok(asset,'the page must load a single bundled script');
 const bundleHasCodeTable=asset.body.includes('RUN_NOT_READY')&&asset.body.includes('当前运行状态无法继续');
 assert.ok(bundleHasCodeTable,'the shipped bundle must carry the RUN_NOT_READY localization');

 await signIn(page,credentials.username,credentials.password);
 await useTab(page,'一人食助手');
 await waitText(page,/一人食助手/);
 const token=await page.evaluate(async({u,p})=>{
  const l=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({username:u,password:p})});
  return l.status===200?(await l.json()).access_token:null;
 },{u:credentials.username,p:credentials.password});
 assert.ok(token,'verification login must succeed');

 // The zero-model guard runs before the POST, not after: only known terminal runs are
 // probed (advance rejects them with 409 without touching the model), and a ready run
 // on the target fails this check outright instead of being advanced.
 const advanceProbe=await page.evaluate(async(token)=>{
  const runs=await (await fetch('/api/v1/agent/runs',{headers:{Authorization:'Bearer '+token}})).json();
  const terminal=runs.filter(r=>['failed','completed','cancelled','approved'].includes(r.status));
  return {total:runs.length,terminal:terminal.map(r=>({id:r.id,status:r.status}))};
 },token);
 assert.equal(advanceProbe.total-advanceProbe.terminal.length,0,
  'every run on this deployment must already be terminal; a ready/running run would let the probe reach the model');
 assert.ok(advanceProbe.terminal.length>0,'at least one terminal run must exist to probe the 409 contract');
 const probeResults=await page.evaluate(async({token,ids})=>{
  const results=[];
  for(const r of ids){
   const response=await fetch('/api/v1/agent/runs/'+r.id+'/advance',{method:'POST',headers:{Authorization:'Bearer '+token}});
   results.push({run_id:r.id,run_status:r.status,status:response.status,body:await response.json().catch(()=>null)});
  }
  return {count:ids.length,results};
 },{token,ids:advanceProbe.terminal});
 const notReady=probeResults.results.filter(x=>x.status===409);
 assert.equal(probeResults.results.length,notReady.length,'a terminal advance must answer 409, nothing else');
 assert.ok(notReady.length>0,'at least one terminal run must answer the 409 contract');
 for(const probe of notReady){
  assert.equal(probe.body.error.code,'RUN_NOT_READY');
  assert.equal(probe.body.error.message,'Run is not ready to advance','the server contract text stays untouched');
 }

 const failedOpen=await page.evaluate(async(token)=>{
  const runs=await (await fetch('/api/v1/agent/runs',{headers:{Authorization:'Bearer '+token}})).json();
  const failed=runs.find(r=>r.status==='failed');
  if(!failed)return null;
  // The list projection carries no result body; the failure code lives in the run view.
  const full=await (await fetch('/api/v1/agent/runs/'+failed.id,{headers:{Authorization:'Bearer '+token}})).json();
  return {id:failed.id,error:full.result?.error};
 },token);
 let pageShown='';
 if(failedOpen){
  // Keep in sync with frontend/src/errorText.ts — assert the exact table text, not a
  // generic prefix, so a missing or drifted code entry cannot pass silently.
  const chineseByCode={RUN_NOT_READY:'当前运行状态无法继续，本次没有新进展；请查看运行状态，或开始新对话',
   STEP_LIMIT:'助手已达到单轮步数上限，继续或恢复都会立即再次超限；请开始新对话',
   CONTEXT_LIMIT:'对话上下文已达上限，请开始新对话',
   MODEL_NOT_CONFIGURED:'尚未配置模型，请按后端说明设置模型地址、名称和密钥',
   MODEL_UNAVAILABLE:'模型服务暂时不可用，请稍后重试',
   MODEL_PROTOCOL_ERROR:'模型应答异常，请稍后重试或改用页面操作'};
  const expected=chineseByCode[failedOpen.error?.code];
  assert.ok(expected,'the failed run carries a code the page localizes: '+JSON.stringify(failedOpen.error));
  await useTab(page,'一人食助手');
  await page.getByText('所有运行记录').click();
  const open=page.locator('button.text-button',{hasText:failedOpen.id.slice(0,8)});
  if(await open.count()){await open.first().click();await page.waitForTimeout(1_500);}
  pageShown=await bodyText(page);
  assert.match(pageShown,/本次运行失败：/);
  assert.ok(pageShown.includes('本次运行失败：'+expected),'the page must render the exact Chinese text for '+failedOpen.error.code);
  assert.ok(!pageShown.includes('Run is not ready'),'the server English contract text must not reach the page');
 }
 await page.screenshot({path:output+'-localization.png',fullPage:true});
 assert.deepEqual(page.problems,[]);
 await writeFile(output+'-checks.json',JSON.stringify({passed:true,
  bundle:{src:asset.src,RUN_NOT_READY_localized:bundleHasCodeTable},
  server_contract:probeResults,failed_run_shown:failedOpen?{id:failedOpen.id,code:failedOpen.error?.code}:null,
  scope:'static bundle check plus a read-only advance probe restricted to terminal runs before the POST; no write, no model'},null,2));
 console.log('Deployed error localization checks passed'+(pageShown?' (failed run rendered in Chinese)':' (no failed run to open)'));
}finally{await browser.close();}
