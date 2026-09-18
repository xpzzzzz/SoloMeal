// Explicitly targets a real Nginx rate-limit stack (loopback deployment); not part of the fixture CI suite.
// The page must show the Chinese waiting message carrying the Retry-After value Nginx itself produced,
// and recover on a manual refresh once the shared api bucket refills. The flood runs under a throwaway
// empty account so no demo data is touched; that user remains in the deployment as recorded cost.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {launchBrowser,desktopContext,openPage,signIn,useTab,waitText,bodyText} from './support.mjs';

const [url,evidence,output]=process.argv.slice(2);
assert.ok(url&&evidence&&output,'Usage: node e2e/deployed-429.mjs URL PRIVATE_EVIDENCE_DIR OUTPUT_PREFIX');
assert.equal(new URL(url).hostname,'127.0.0.1','targets a loopback deployment only');
const credentials=JSON.parse(await readFile(path.join(evidence,'credentials.json'),'utf8'));
const flood={username:'ratelimit429'+String(Date.now()).slice(-6),password:'deployed-429-page-scenario'};
const browser=await launchBrowser();
try{
 const context=await desktopContext(browser);
 const page=await openPage(context,url);

 let floodToken=await page.evaluate(async({u,p})=>{
  const r=await fetch('/api/v1/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({username:u,password:p})});
  if(r.status!==201&&r.status!==200)return null;
  const l=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({username:u,password:p})});
  return l.status===200?(await l.json()).access_token:null;
 },{u:flood.username,p:flood.password});
 if(!floodToken){await page.waitForTimeout(15_000);
  floodToken=await page.evaluate(async({u,p})=>{
   await fetch('/api/v1/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:u,password:p})});
   const l=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:u,password:p})});
   return l.status===200?(await l.json()).access_token:null;
  },{u:flood.username,p:flood.password});}
 assert.ok(floodToken,'the throwaway flood account must be usable (auth bucket)');

 await signIn(page,credentials.username,credentials.password);
 await useTab(page,'食材库存');
 await page.waitForSelector('table tbody tr');
 const riceBefore=(await bodyText(page)).includes('演示大米');

 let allowed=0,limited=0,retryAfter=null;
 for(let n=0;n<150;n++){
  const result=await page.evaluate(async(token)=>{
   const response=await fetch('/api/v1/inventory',{headers:{Authorization:'Bearer '+token}});
   return {status:response.status,retryAfter:response.headers.get('Retry-After')};
  },floodToken);
  if(result.status===200)allowed++;
  else if(result.status===429){limited++;retryAfter=result.retryAfter??retryAfter;}
  else assert.fail('unexpected status '+result.status);
 }
 assert.ok(limited>0,'the real Nginx api bucket must have returned at least one 429');
 assert.equal(retryAfter,'60','Nginx itself must set Retry-After: 60');

 await page.getByRole('button',{name:'刷新库存',exact:true}).click();
 await waitText(page,/请求较频繁，请稍后重试（约 60 秒）/);
 const notice=(await bodyText(page)).match(/请求较频繁[^\n]*/)[0];
 await page.screenshot({path:output+'-rate-limited.png',fullPage:true});

 // Recovery is bound to the network, not the DOM the 429 left behind: a refresh whose
 // GET fails keeps the stale batches on the page, so "table row exists" proves nothing.
 // One refresh fires five parallel GETs and clears the notice *before* they land, so a
 // single 200 plus a quiet moment is not enough: capture every api GET belonging to the
 // clicked refresh, require all five endpoints to answer 200 (paged GETs may repeat), and
 // wait until busy has ended (the refresh button is enabled again) before reading the page.
 const refreshPaths=['/api/v1/ingredients','/api/v1/inventory','/api/v1/recipes','/api/v1/cooking','/api/v1/plans'];
 const button=page.getByRole('button',{name:'刷新库存',exact:true});
 const started=Date.now();
 let recovered=false,attempts=0,lastStatuses=[];
 for(let attempt=0;attempt<25&&!recovered;attempt++){
  attempts++;
  const seen=[];
  const collect=r=>{const p=new URL(r.url()).pathname;if(refreshPaths.includes(p))seen.push({path:p,status:r.status()});};
  page.on('response',collect);
  await button.click();
  // busy is set in the click handler and cleared in perform's finally, so the window
  // this refresh occupies is exactly the span in which the button is disabled.
  // (locator.waitFor cannot watch enabled/disabled in this Playwright, hence polling.)
  // The window is closed when the button reads enabled and stays enabled for 400ms,
  // which also absorbs the tick between React committing busy=false and DOM reads.
  const neverDisabled=page.waitForFunction(()=>[...document.querySelectorAll('button')]
   .some(b=>b.textContent==='刷新库存'&&b.disabled),null,{timeout:2_000,polling:25}).then(()=>false,()=>true);
  await Promise.race([neverDisabled,new Promise(r=>setTimeout(r,400))]);
  let finished=false;
  for(let tick=0;tick<50&&!finished;tick++){
   await page.waitForTimeout(100);
   if(!(await button.isDisabled()))
    finished=await page.waitForFunction(()=>[...document.querySelectorAll('button')]
     .some(b=>b.textContent==='刷新库存'&&b.disabled),null,{timeout:400,polling:25}).then(()=>false,()=>true);
  }
  page.off('response',collect);
  lastStatuses=seen;
  recovered=finished&&seen.length>0&&refreshPaths.every(p=>seen.some(s=>s.path===p))&&seen.every(s=>s.status===200);
  if(!recovered)await page.waitForTimeout(2_000);
 }
 assert.ok(recovered,'a manual refresh must complete with all five endpoints answering 200 once the bucket refills; last: '+JSON.stringify(lastStatuses));
 assert.ok(!(await bodyText(page)).includes('请求较频繁'),'the rate-limit notice must clear after the successful refresh');
 const shown=await bodyText(page);
 assert.ok(shown.includes('演示大米')&&shown.includes('可用库存批次'),'the refreshed page must carry the demo inventory');
 assert.ok(riceBefore);
 await page.screenshot({path:output+'-recovered.png',fullPage:true});

 assert.deepEqual(page.problems,[]);
 await writeFile(output+'-checks.json',JSON.stringify({passed:true,flood:{requests:150,allowed,limited,account:flood.username},
  nginx_retry_after:retryAfter,page_notice:notice,recovery_seconds:Math.round((Date.now()-started)/100)/10,recovery_clicks:attempts,
  final_refresh_responses:lastStatuses,
  scope:'real Nginx rate-limit stack, browser page; the flood consumes the shared api bucket and leaves one empty throwaway user'},null,2));
 console.log('Deployed 429 page scenario passed ('+limited+' real 429s, recovered)');
}finally{await browser.close();}
